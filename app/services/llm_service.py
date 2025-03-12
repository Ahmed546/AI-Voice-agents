import openai
import json
import logging
import random
from tenacity import retry, stop_after_attempt, wait_exponential
import time
import asyncio
from typing import List, Dict, Any, Optional

from app.config import settings

logger = logging.getLogger(__name__)

# Create an OpenAI client with explicit API key
client = openai.Client(api_key=settings.OPENAI_API_KEY)

class LLMService:
    def __init__(self):
        self.max_retries = settings.MAX_RETRIES
        # Use faster models for intent classification and simple responses
        self.default_model = "gpt-3.5-turbo"  # Fast model for intents and basic responses
        self.conversation_model = "gpt-3.5-turbo"  # Use this instead of gpt-4 for faster responses
        # Only use gpt-4 for complex order understanding
        self.order_model = "gpt-4"  # Keep the more advanced model just for order parsing
        self.intent_system_prompt = settings.INTENT_SYSTEM_PROMPT
        self.conversation_system_prompt = settings.CONVERSATION_SYSTEM_PROMPT
        self.order_parser_system_prompt = settings.ORDER_PARSER_SYSTEM_PROMPT
        self.client = client  # Expose the client for use by other services
        
        # Add response cache
        self.response_cache = {}
        self.intent_cache = {}
        
        # Log model usage for debugging
        logger.info(f"Using models - default: {self.default_model}, conversation: {self.conversation_model}, order: {self.order_model}")
    
    async def process_in_parallel(self, speech_result, conversation_history, order_data):
        """Process intent and response in parallel for faster results."""
        # Start both operations concurrently
        intent_task = asyncio.create_task(
            self.classify_intent(speech_result)
        )
        response_task = asyncio.create_task(
            self.generate_response(speech_result, conversation_history, order_data)
        )
        
        # Wait for both to complete
        intent, response = await asyncio.gather(intent_task, response_task)
        
        return intent, response
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True
    )
    async def classify_intent(self, transcript: str) -> str:
        """
        Classify the intent of user's speech using OpenAI.
        
        Args:
            transcript (str): The user's speech transcript
            
        Returns:
            str: The classified intent
        """
        # Check cache first
        cache_key = transcript.lower().strip()
        if cache_key in self.intent_cache:
            return self.intent_cache[cache_key]
        
        # Check for common intents based on simple keyword matching
        if any(word in cache_key for word in ['bye', 'goodbye', 'thank', 'hang up', 'end']):
            self.intent_cache[cache_key] = "end_call"
            return "end_call"
        
        if any(word in cache_key for word in ['order', 'pizza', 'food', 'menu']):
            self.intent_cache[cache_key] = "new_order"
            return "new_order"
            
        if any(word in cache_key for word in ['reserve', 'reservation', 'book', 'table']):
            self.intent_cache[cache_key] = "reservation"
            return "reservation"
        
        start_time = time.time()
        
        try:
            # Use the synchronous client since we're in an async function
            response = client.chat.completions.create(
                model=self.default_model,
                messages=[
                    {"role": "system", "content": self.intent_system_prompt},
                    {"role": "user", "content": transcript}
                ],
                max_tokens=10,
                temperature=0.3
            )
            
            intent = response.choices[0].message.content.strip().lower()
            processing_time = time.time() - start_time
            logger.debug(f"Intent classification completed in {processing_time:.2f}s: {intent}")
            
            # Cache the intent for future use
            self.intent_cache[cache_key] = intent
            
            return intent
        
        except Exception as e:
            logger.error(f"Intent classification failed: {str(e)}")
            # Default to unclear if we can't classify
            return "unclear"
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True
    )
    async def generate_response(
        self, 
        transcript: str, 
        conversation_history: List[Dict[str, str]], 
        order_data: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Generate AI response based on customer's transcript and conversation history.
        
        Args:
            transcript (str): The user's speech transcript
            conversation_history (List[Dict]): List of conversation turns
            order_data (Dict, optional): Order data if available
            
        Returns:
            str: The generated response
        """
        # Check cache first for common queries
        cache_key = transcript.lower().strip()
        if cache_key in self.response_cache:
            return self.response_cache[cache_key]
            
        # Check for common questions and provide instant responses
        for key, response in settings.COMMON_RESPONSES.items():
            if key in cache_key:
                self.response_cache[cache_key] = response
                return response
        
        start_time = time.time()
        
        # Prepare messages including conversation history
        messages = [
            {"role": "system", "content": self.conversation_system_prompt}
        ]
        
        # Limit conversation history to last 5 exchanges to reduce token usage
        recent_history = conversation_history[-5:] if len(conversation_history) > 5 else conversation_history
        
        # Add conversation history
        for exchange in recent_history:
            if "customer" in exchange:
                messages.append({"role": "user", "content": exchange["customer"]})
            if "assistant" in exchange and exchange.get("assistant"):
                messages.append({"role": "assistant", "content": exchange["assistant"]})
        
        # Add current transcript
        messages.append({"role": "user", "content": transcript})
        
        # Add order data if available
        if order_data:
            order_context = f"Customer has an existing order: {json.dumps(order_data)}"
            messages.append({"role": "system", "content": order_context})
        
        try:
            # Use the synchronous client
            response = client.chat.completions.create(
                model=self.conversation_model,
                messages=messages,
                max_tokens=100,  # Reduced token length for faster response
                temperature=0.7
            )
            
            ai_response = response.choices[0].message.content
            processing_time = time.time() - start_time
            logger.debug(f"Response generation completed in {processing_time:.2f}s")
            
            # Cache the response for future use (only for simple queries)
            if len(transcript.split()) < 8:  # Cache only simple queries
                self.response_cache[cache_key] = ai_response
            
            return ai_response
        
        except asyncio.TimeoutError:
            logger.error("Response generation timed out")
            return "I'm sorry, I'm having trouble processing your request. Let me transfer you to a staff member who can help."
        
        except Exception as e:
            logger.error(f"Response generation failed: {str(e)}")
            return "I apologize, but I'm experiencing some technical difficulties. Let me transfer you to one of our staff members."
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True
    )
    async def parse_order_details(self, transcript: str, conversation_history: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        Extract order details from conversation.
        
        Args:
            transcript (str): The user's speech transcript
            conversation_history (List[Dict]): List of conversation turns
            
        Returns:
            Dict: Extracted order details
        """
        start_time = time.time()
        
        # Prepare the full conversation
        full_conversation = ""
        for exchange in conversation_history:
            if "customer" in exchange:
                full_conversation += f"Customer: {exchange['customer']}\n"
            if "assistant" in exchange and exchange.get("assistant"):
                full_conversation += f"Assistant: {exchange['assistant']}\n"
        
        full_conversation += f"Customer: {transcript}"
        
        try:
            # Use the advanced model for order parsing
            response = client.chat.completions.create(
                model=self.order_model,
                messages=[
                    {"role": "system", "content": self.order_parser_system_prompt},
                    {"role": "user", "content": full_conversation}
                ],
                response_format={"type": "json_object"},
                max_tokens=500,
                temperature=0.2
            )
            
            order_details = json.loads(response.choices[0].message.content)
            processing_time = time.time() - start_time
            logger.debug(f"Order parsing completed in {processing_time:.2f}s")
            
            return order_details
            
        except json.JSONDecodeError:
            logger.error("Failed to parse order details JSON")
            # Fallback for parsing errors
            return {
                "customer_name": None,
                "order_items": [],
                "is_delivery": False,
                "address": None,
                "reservation_time": None,
                "party_size": None,
                "parsing_error": True
            }
            
        except Exception as e:
            logger.error(f"Order parsing failed: {str(e)}")
            return {
                "customer_name": None,
                "order_items": [],
                "is_delivery": False,
                "address": None,
                "reservation_time": None,
                "party_size": None,
                "error": str(e)
            }
    
    async def analyze_sentiment(self, conversation_history: List[Dict[str, str]]) -> float:
        """
        Analyze the sentiment of a conversation.
        
        Args:
            conversation_history (List[Dict]): List of conversation turns
            
        Returns:
            float: Sentiment score from -1 (negative) to 1 (positive)
        """
        # Prepare the full conversation
        full_conversation = ""
        for exchange in conversation_history:
            if "customer" in exchange:
                full_conversation += f"Customer: {exchange['customer']}\n"
            if "assistant" in exchange and exchange.get("assistant"):
                full_conversation += f"Assistant: {exchange['assistant']}\n"
        
        system_prompt = """
        Analyze the sentiment of this customer conversation. 
        Return only a single number between -1 and 1 where:
        -1 = Very negative
        0 = Neutral
        1 = Very positive
        
        Return only the number, no explanation.
        """
        
        try:
            response = client.chat.completions.create(
                model=self.default_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": full_conversation}
                ],
                max_tokens=10,
                temperature=0.2
            )
            
            sentiment_text = response.choices[0].message.content.strip()
            try:
                sentiment_score = float(sentiment_text)
                return max(-1.0, min(1.0, sentiment_score))  # Clamp to [-1, 1]
            except ValueError:
                logger.error(f"Failed to parse sentiment score: {sentiment_text}")
                return 0.0
                
        except Exception as e:
            logger.error(f"Sentiment analysis failed: {str(e)}")
            return 0.0  # Default to neutral
            
# Create a singleton instance
llm_service = LLMService()