import logging
import json
from typing import List, Dict, Any, Optional
import re

from app.services.vector_store import vector_store
from app.services.llm_service import llm_service

logger = logging.getLogger(__name__)

class RAGService:
    """RAG (Retrieval-Augmented Generation) service for enhancing responses with knowledge base."""
    
    def __init__(self):
        """Initialize the RAG service."""
        self.vector_store = vector_store
        self.llm_service = llm_service
    
    async def enhance_response(self, query: str, conversation_history: List[Dict[str, str]], 
                            llm_response: str) -> str:
        """
        Enhance the LLM response with relevant information from the knowledge base.
        
        Args:
            query: The user's query
            conversation_history: The conversation history
            llm_response: The original LLM response
            
        Returns:
            Enhanced response with accurate information
        """
        # Check if the query or response mentions specific information we should look up
        enriched_response = llm_response
        
        # Extract potential menu items or categories to look up
        menu_items = self._extract_menu_items(query, llm_response)
        
        # If menu items are mentioned, enrich with specific details
        if menu_items:
            knowledge_context = self._get_menu_item_details(menu_items)
            if knowledge_context:
                enriched_response = await self._rewrite_with_knowledge(
                    query, conversation_history, llm_response, knowledge_context
                )
                
        # Extract policy topics that might be relevant
        policy_topics = self._extract_policy_topics(query, llm_response)
        
        # If policy topics are mentioned, enrich with accurate policy information
        if policy_topics:
            knowledge_context = self._get_policy_details(policy_topics)
            if knowledge_context:
                enriched_response = await self._rewrite_with_knowledge(
                    query, conversation_history, enriched_response, knowledge_context
                )
                
        # Check for mentions of specials
        if any(word in query.lower() for word in ["special", "specials", "deal", "deals", "promo", "promotion"]):
            knowledge_context = self._get_specials_details()
            if knowledge_context:
                enriched_response = await self._rewrite_with_knowledge(
                    query, conversation_history, enriched_response, knowledge_context
                )
        
        return enriched_response
    
    def _extract_menu_items(self, query: str, response: str) -> List[str]:
        """Extract potential menu items or categories from text."""
        combined_text = (query + " " + response).lower()
        
        # Define regular expressions for key menu terms
        menu_item_pattern = r'(?:pizza|pasta|linguine|fettuccine|tiramisu|lasagna|margherita|seafood|dessert|appetizer|salad|bread)'
        
        # Find all matches
        matches = re.findall(menu_item_pattern, combined_text)
        
        # Deduplicate and return
        return list(set(matches))
    
    def _extract_policy_topics(self, query: str, response: str) -> List[str]:
        """Extract potential policy topics from text."""
        combined_text = (query + " " + response).lower()
        
        # Define regular expressions for key policy terms
        policy_pattern = r'(?:delivery|pickup|reservation|allergies|dietary|gluten|vegetarian|vegan|hours|payment|cancel|minimum order)'
        
        # Find all matches
        matches = re.findall(policy_pattern, combined_text)
        
        # Map to our known policy topics
        policy_mapping = {
            'delivery': 'Delivery',
            'pickup': 'Delivery',  # Use delivery policy for pickup info too
            'reservation': 'Reservations',
            'allergies': 'Special Dietary Needs',
            'dietary': 'Special Dietary Needs',
            'gluten': 'Special Dietary Needs',
            'vegetarian': 'Special Dietary Needs',
            'vegan': 'Special Dietary Needs',
        }
        
        # Map and deduplicate
        policy_topics = []
        for match in matches:
            if match in policy_mapping:
                policy_topics.append(policy_mapping[match])
        
        return list(set(policy_topics))
    
    def _get_menu_item_details(self, menu_items: List[str]) -> str:
        """Get details about menu items from the knowledge base."""
        knowledge_chunks = []
        
        for item in menu_items:
            # Try to find exact matches first
            menu_item = self.vector_store.get_menu_item(item)
            if menu_item:
                # Format the menu item information
                item_info = (
                    f"{menu_item['name']}: {menu_item['description']} "
                    f"Price: ${menu_item['price']:.2f}. "
                    f"Ingredients: {', '.join(menu_item['ingredients'])}. "
                    f"Dietary info: {menu_item['dietary_info']}"
                )
                knowledge_chunks.append(item_info)
                continue
                
            # If not exact match, search by relevance
            results = self.vector_store.search(item, top_k=2)
            for result in results:
                if result['similarity'] > 0.75:  # Only use if reasonably relevant
                    knowledge_chunks.append(result['text'])
        
        # Return combined knowledge context
        if knowledge_chunks:
            return "\n\n".join(knowledge_chunks)
        return ""
    
    def _get_policy_details(self, policy_topics: List[str]) -> str:
        """Get policy details from the knowledge base."""
        knowledge_chunks = []
        
        for topic in policy_topics:
            policy = self.vector_store.get_policy(topic)
            if policy:
                policy_info = f"{policy['topic']} Policy: {policy['content']}"
                knowledge_chunks.append(policy_info)
        
        # Return combined knowledge context
        if knowledge_chunks:
            return "\n\n".join(knowledge_chunks)
        return ""
    
    def _get_specials_details(self) -> str:
        """Get details about current specials."""
        specials = self.vector_store.get_specials()
        if not specials:
            return ""
            
        knowledge_chunks = []
        for special in specials:
            special_info = f"{special['name']}: {special['content']}"
            knowledge_chunks.append(special_info)
            
        return "\n\n".join(knowledge_chunks)
    
    async def _rewrite_with_knowledge(self, query: str, conversation_history: List[Dict[str, str]], 
                               original_response: str, knowledge_context: str) -> str:
        """Rewrite the response using the provided knowledge context."""
        try:
            # Create a system prompt for rewriting with knowledge
            system_prompt = f"""
            You are an AI assistant for a restaurant. You're going to rewrite the response to a customer's question
            using the accurate information provided to you. Your goal is to be as helpful and accurate as possible.

            Here is accurate information from the restaurant's knowledge base:
            {knowledge_context}

            Incorporate this information into your response in a natural way - don't just list facts.
            Keep the same friendly, helpful tone as the original response.
            If the original response contains any information that contradicts the knowledge base, use the knowledge base information instead.
            If the original response already contains all the correct information, you can keep it as is.
            Keep your response conversational and concise.
            """
            
            # Prepare messages including conversation history context
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query},
                {"role": "assistant", "content": original_response},
                {"role": "user", "content": "Please rewrite your response to be more accurate using the information provided in the system prompt."}
            ]
            
            # Get rewritten response - Remove the await keyword
            response = self.llm_service.client.chat.completions.create(
                model=self.llm_service.conversation_model,
                messages=messages,
                max_tokens=250,
                temperature=0.4
            )
            
            rewritten_response = response.choices[0].message.content
            
            logger.debug(f"Rewrote response using knowledge context")
            return rewritten_response
            
        except Exception as e:
            logger.error(f"Error rewriting with knowledge: {str(e)}")
            # Fall back to original response if rewriting fails
            return original_response

# Create a singleton instance
rag_service = RAGService()