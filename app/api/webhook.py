from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session
import logging
import json
from datetime import datetime
import traceback
import random
import copy

from app.db.database import get_db
from app.db.models import Conversation, ConversationTurn, Order, ErrorLog
from app.services.twilio_service import twilio_service
from app.services.llm_service import llm_service
from app.services.rag_service import rag_service
from app.services.speech_enhancement_service import speech_enhancement_service
from app.utils.helpers import parse_datetime
from app.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)

# Convert to lightweight dictionaries for caching instead of ORM objects
_order_cache = {}
_conversation_cache = {}
_processing_cache = {}  # For storing speech_result during processing

def get_cached_order(order_id, db):
    """Get an order with caching for better performance."""
    if not order_id:
        return None
    
    # Return cached dictionary if available and convert to model instance 
    if order_id in _order_cache:
        order_dict = _order_cache[order_id]
        # Create a fresh Order instance based on cached data
        order = Order(id=order_dict["id"])
        for key, value in order_dict.items():
            if key != 'id':  # Already set id during creation
                setattr(order, key, value)
        return order
    
    # If not in cache, get from database and cache as dictionary
    order = db.query(Order).filter(Order.id == order_id).first()
    if order:
        # Store as dictionary to avoid session issues
        _order_cache[order_id] = {
            "id": order.id,
            "customer_name": order.customer_name,
            "customer_phone": order.customer_phone,
            "order_items": order.order_items,
            "is_delivery": order.is_delivery,
            "delivery_address": order.delivery_address,
            "status": order.status,
            "reservation_time": order.reservation_time.isoformat() if order.reservation_time else None,
            "party_size": order.party_size
        }
    return order

def get_cached_conversation(call_sid, db):
    """Get a conversation with caching for better performance."""
    # Return cached dictionary if available and convert to model instance
    if call_sid in _conversation_cache:
        conv_dict = _conversation_cache[call_sid]
        
        # Query for a fresh instance
        conversation = db.query(Conversation).filter(Conversation.call_sid == call_sid).first()
        
        # If not found, create a new instance with cached data
        if not conversation:
            conversation = Conversation(call_sid=call_sid)
            for key, value in conv_dict.items():
                if key != 'call_sid':  # Already set during creation
                    setattr(conversation, key, value)
            
            # Add to session to ensure it's attached
            db.add(conversation)
            
        return conversation
    
    # If not in cache, get from database and cache as dictionary
    conversation = db.query(Conversation).filter(Conversation.call_sid == call_sid).first()
    if conversation:
        # Store as dictionary to avoid session issues
        _conversation_cache[call_sid] = {
            "id": conversation.id,
            "call_sid": conversation.call_sid,
            "customer_phone": conversation.customer_phone,
            "order_id": conversation.order_id,
            "conversation_log": conversation.conversation_log,
            "sentiment_score": conversation.sentiment_score,
            "created_at": conversation.created_at.isoformat() if conversation.created_at else None,
            "ended_at": conversation.ended_at.isoformat() if conversation.ended_at else None,
            "duration": conversation.duration
        }
    return conversation

@router.post("/speech")
async def speech_webhook(request: Request, db: Session = Depends(get_db)):
    """Webhook for handling speech recognition results from Twilio."""
    try:
        form_data = await request.form()
        call_sid = form_data.get("CallSid")
        speech_result = form_data.get("SpeechResult")
        confidence = float(form_data.get("Confidence", 0)) if form_data.get("Confidence") else 0
        
        if not speech_result:
            logger.warning(f"No speech detected for call {call_sid}")
            return Response(
                content=twilio_service.create_progressive_response(
                    "I didn't catch that. Could you please repeat?"
                ),
                media_type="application/xml"
            )
        
        # Get the conversation with caching
        conversation = get_cached_conversation(call_sid, db)
        if not conversation:
            logger.error(f"Conversation not found for call {call_sid}")
            return Response(
                content=twilio_service.create_transfer_to_human_response(
                    "I'm having trouble with this call."
                ),
                media_type="application/xml"
            )
        
        # Send an immediate acknowledgment for complex queries
        complex_query = len(speech_result.split()) > 6
        if complex_query:
            # Store speech_result in separate cache for the background processing
            processing_key = f"processing_{call_sid}"
            _processing_cache[processing_key] = speech_result
            
            # Send acknowledgment
            acknowledgments = ["Got it.", "I understand.", "Let me check that."]
            ack = random.choice(acknowledgments)
            
            # Return a thinking response immediately
            return Response(
                content=twilio_service.create_progressive_response(ack),
                media_type="application/xml"
            )
        
        # Load conversation history
        try:
            conversation_history = json.loads(conversation.conversation_log)
        except json.JSONDecodeError:
            conversation_history = []
        
        # Extract language preference
        voice_language = "en-US"  # Default to English
        for entry in conversation_history:
            if "system" in entry and "Language selected:" in entry["system"]:
                if "ur-PK" in entry["system"]:
                    voice_language = "ur-PK"
                break
        
        # For simple and direct questions, check common responses first
        simple_query = len(speech_result.split()) < 5
        for key, response in settings.COMMON_RESPONSES.items():
            if key in speech_result.lower():
                # Add the response to conversation history
                conversation_history.append({"customer": speech_result, "assistant": response})
                conversation.conversation_log = json.dumps(conversation_history)
                
                # Create conversation turns
                customer_turn = ConversationTurn(
                    conversation_id=conversation.id,
                    sequence=len(conversation_history) * 2 - 1,
                    speaker="customer",
                    content=speech_result,
                    intent="general_inquiry"  # Assume general inquiry for predefined responses
                )
                
                assistant_turn = ConversationTurn(
                    conversation_id=conversation.id,
                    sequence=len(conversation_history) * 2,
                    speaker="assistant",
                    content=response
                )
                
                db.add(customer_turn)
                db.add(assistant_turn)
                db.commit()
                
                # Return direct response without API call
                return Response(
                    content=twilio_service.create_streaming_response(response, voice_language),
                    media_type="application/xml"
                )
        
        # Check for common intents based on keywords for faster classification
        intent = None
        if any(word in speech_result.lower() for word in ['bye', 'goodbye', 'thank', 'hang up', 'end']):
            intent = "end_call"
        elif any(word in speech_result.lower() for word in ['order', 'pizza', 'food', 'menu']):
            intent = "new_order"
        elif any(word in speech_result.lower() for word in ['reserve', 'reservation', 'book', 'table']):
            intent = "reservation"
        
        # Handle end_call intent immediately for better responsiveness
        if intent == "end_call":
            if voice_language == "en-US":
                response_text = f"Thank you for calling {settings.RESTAURANT_NAME}. Have a wonderful day!"
            else:
                response_text = f"{settings.RESTAURANT_NAME} کو کال کرنے کا شکریہ۔ آپ کا دن خوشگوار ہو!"
                
            # Update conversation with end
            conversation_history.append({"customer": speech_result, "assistant": response_text})
            conversation.conversation_log = json.dumps(conversation_history)
            conversation.ended_at = datetime.utcnow()
            
            # Create conversation turns
            customer_turn = ConversationTurn(
                conversation_id=conversation.id,
                sequence=len(conversation_history) * 2 - 1,
                speaker="customer",
                content=speech_result,
                intent=intent
            )
            
            assistant_turn = ConversationTurn(
                conversation_id=conversation.id,
                sequence=len(conversation_history) * 2,
                speaker="assistant",
                content=response_text
            )
            
            db.add(customer_turn)
            db.add(assistant_turn)
            db.commit()
            
            return Response(
                content=twilio_service.create_goodbye_response(response_text, voice_language),
                media_type="application/xml"
            )
        
        # Get cached order data if available
        order_data = None
        if conversation.order_id:
            order = get_cached_order(conversation.order_id, db)
            if order:
                order_data = {
                    "id": order.id,
                    "customer_name": order.customer_name,
                    "order_items": json.loads(order.order_items),
                    "is_delivery": order.is_delivery,
                    "status": order.status
                }
        
        # If intent is not pre-classified, classify it
        if not intent:
            intent = await llm_service.classify_intent(speech_result)
        
        # Handle special intents with guided responses
        if intent == "new_order" and not conversation.order_id:
            # Guide the customer through the ordering process more explicitly
            if not any(word in speech_result.lower() for word in ["pizza", "pasta", "food", "delivery", "pickup", "want", "like", "get"]):
                if voice_language == "en-US":
                    ai_response = "Would you like delivery or pickup? Our specials today are Margherita Pizza for $16, Chef's Special Pasta for $22, and Tiramisu for $8."
                else:
                    ai_response = "آپ ڈیلیوری پسند کریں گے یا پک اپ؟ آج ہماری خصوصی پیشکش میں شامل ہیں: مارگریٹا پیزا $16، شیف کا خصوصی پاستا $22، اور ٹیرامیسو $8۔"
                
                # Add to conversation history
                conversation_history.append({"customer": speech_result, "assistant": ai_response})
                conversation.conversation_log = json.dumps(conversation_history)
                
                # Create conversation turns
                customer_turn = ConversationTurn(
                    conversation_id=conversation.id,
                    sequence=len(conversation_history) * 2 - 1,
                    speaker="customer",
                    content=speech_result,
                    intent=intent
                )
                
                assistant_turn = ConversationTurn(
                    conversation_id=conversation.id,
                    sequence=len(conversation_history) * 2,
                    speaker="assistant",
                    content=ai_response
                )
                
                db.add(customer_turn)
                db.add(assistant_turn)
                db.commit()
                
                return Response(
                    content=twilio_service.create_streaming_response(ai_response, voice_language),
                    media_type="application/xml"
                )
        
        elif intent == "reservation":
            # Guide the customer through the reservation process more explicitly
            if not any(word in speech_result.lower() for word in ["tonight", "tomorrow", "today", "people", "persons", "time", "at"]):
                if voice_language == "en-US":
                    ai_response = "What day and time would you like to visit, and how many people will be in your party?"
                else:
                    ai_response = "آپ کس دن اور وقت آنا چاہیں گے، اور آپ کی پارٹی میں کتنے لوگ ہوں گے؟"
                
                # Add to conversation history
                conversation_history.append({"customer": speech_result, "assistant": ai_response})
                conversation.conversation_log = json.dumps(conversation_history)
                
                # Create conversation turns
                customer_turn = ConversationTurn(
                    conversation_id=conversation.id,
                    sequence=len(conversation_history) * 2 - 1,
                    speaker="customer",
                    content=speech_result,
                    intent=intent
                )
                
                assistant_turn = ConversationTurn(
                    conversation_id=conversation.id,
                    sequence=len(conversation_history) * 2,
                    speaker="assistant",
                    content=ai_response
                )
                
                db.add(customer_turn)
                db.add(assistant_turn)
                db.commit()
                
                return Response(
                    content=twilio_service.create_streaming_response(ai_response, voice_language),
                    media_type="application/xml"
                )
        
        # Generate response using LLM
        ai_response = await llm_service.generate_response(speech_result, conversation_history, order_data)
        
        # Enhance with RAG if needed
        ai_response = await rag_service.enhance_response(speech_result, conversation_history, ai_response)
        
        # Add to conversation history
        conversation_history.append({"customer": speech_result, "assistant": ai_response})
        
        # Create conversation turns
        customer_turn = ConversationTurn(
            conversation_id=conversation.id,
            sequence=len(conversation_history) * 2 - 1,
            speaker="customer",
            content=speech_result,
            intent=intent
        )
        
        assistant_turn = ConversationTurn(
            conversation_id=conversation.id,
            sequence=len(conversation_history) * 2,
            speaker="assistant",
            content=ai_response
        )
        
        db.add(customer_turn)
        db.add(assistant_turn)
        
        # Update conversation log
        conversation.conversation_log = json.dumps(conversation_history)
        db.commit()
        
        # Process new orders if intent is new_order
        if intent == "new_order" and not conversation.order_id:
            # Parse order details from conversation
            order_details = await llm_service.parse_order_details(speech_result, conversation_history)
            
            # Only create order if we have meaningful data
            if order_details.get("order_items") or order_details.get("reservation_time"):
                new_order = Order(
                    customer_name=order_details.get("customer_name", "Unknown"),
                    customer_phone=conversation.customer_phone,
                    order_items=json.dumps(order_details.get("order_items", [])),
                    is_delivery=order_details.get("is_delivery", False),
                    delivery_address=order_details.get("address"),
                    reservation_time=parse_datetime(order_details.get("reservation_time")),
                    party_size=order_details.get("party_size")
                )
                db.add(new_order)
                db.commit()
                
                # Link order to conversation
                conversation.order_id = new_order.id
                db.commit()
                
                # Cache the new order as dictionary
                _order_cache[new_order.id] = {
                    "id": new_order.id,
                    "customer_name": new_order.customer_name,
                    "customer_phone": new_order.customer_phone,
                    "order_items": new_order.order_items,
                    "is_delivery": new_order.is_delivery,
                    "delivery_address": new_order.delivery_address,
                    "status": new_order.status,
                    "reservation_time": new_order.reservation_time.isoformat() if new_order.reservation_time else None,
                    "party_size": new_order.party_size
                }
        
        # Create TwiML response with chunking for interrupted responses
        return Response(
            content=twilio_service.create_streaming_response(ai_response, voice_language),
            media_type="application/xml"
        )
        
    except Exception as e:
        logger.error(f"Error processing speech: {str(e)}")
        
        # Log the error
        try:
            error_log = ErrorLog(
                call_sid=form_data.get("CallSid") if 'form_data' in locals() else None,
                error_type=type(e).__name__,
                error_message=str(e),
                stack_trace=traceback.format_exc(),
                error_metadata=json.dumps({"url": str(request.url)})
            )
            db.add(error_log)
            db.commit()
        except:
            pass
        
        # Fallback response
        return Response(
            content=twilio_service.create_twiml_response(
                "I'm sorry, I encountered an error. Let me transfer you to a staff member who can help."
            ),
            media_type="application/xml"
        )

@router.post("/complete-processing")
async def complete_processing(request: Request, db: Session = Depends(get_db)):
    """Continue processing a complex query after sending initial acknowledgment."""
    form_data = await request.form()
    call_sid = form_data.get("CallSid")
    
    # Get the saved query from the processing cache instead of the conversation cache
    processing_key = f"processing_{call_sid}"
    speech_result = _processing_cache.get(processing_key)
    
    if not speech_result:
        return Response(
            content=twilio_service.create_twiml_response(
                "I'm sorry, I lost track of your question. Could you please repeat?"
            ),
            media_type="application/xml"
        )
    
    # Clear from cache
    _processing_cache.pop(processing_key, None)
    
    # Create a new form dict instead of modifying the request
    new_form_data = {
        "CallSid": call_sid,
        "SpeechResult": speech_result,
        "Confidence": "0.8"
    }
    
    # Create a custom request object
    class MockRequest:
        async def form(self):
            return new_form_data
        
        @property
        def url(self):
            return request.url
    
    return await speech_webhook(MockRequest(), db)

@router.post("/no-input")
async def no_input_webhook(request: Request, db: Session = Depends(get_db)):
    """Webhook for handling no input from user."""
    form_data = await request.form()
    call_sid = form_data.get("CallSid")
    
    logger.info(f"No input received for call {call_sid}")
    
    # Get fresh conversation from database with caching
    conversation = get_cached_conversation(call_sid, db)
    if not conversation:
        # Fallback if conversation not found
        return Response(
            content=twilio_service.create_twiml_response("Can I help you with anything today?"),
            media_type="application/xml"
        )
    
    # Make sure the conversation is attached to the current session
    db.add(conversation)
    
    # Extract language preference
    voice_language = "en-US"  # Default to English
    try:
        conversation_history = json.loads(conversation.conversation_log)
        for entry in conversation_history:
            if "system" in entry and "Language selected:" in entry["system"]:
                if "ur-PK" in entry["system"]:
                    voice_language = "ur-PK"
                break
    except:
        conversation_history = []
    
    # Fast count query for no-input events
    no_input_count = db.query(ConversationTurn).filter(
        ConversationTurn.conversation_id == conversation.id,
        ConversationTurn.content == "NO_INPUT"
    ).count()
    
    if no_input_count >= 3:
        # After multiple no-inputs, end the call politely
        if voice_language == "en-US":
            goodbye_message = f"I haven't heard a response. Thank you for calling {settings.RESTAURANT_NAME}. Feel free to call back anytime!"
        else:
            goodbye_message = f"مجھے کوئی جواب نہیں ملا۔ {settings.RESTAURANT_NAME} کو کال کرنے کا شکریہ۔ کسی بھی وقت دوبارہ کال کرنے میں آزاد ہیں!"
            
        # Update conversation record with end time
        conversation.ended_at = datetime.utcnow()
        db.commit()
        
        return Response(
            content=twilio_service.create_goodbye_response(goodbye_message, voice_language),
            media_type="application/xml"
        )
    
    # Add a no-input marker efficiently
    db.add(ConversationTurn(
        conversation_id=conversation.id,
        sequence=len(conversation_history) + 1 if conversation_history else 1,
        speaker="customer",
        content="NO_INPUT"
    ))
    db.commit()
    
    # Simple, brief prompts for better response time
    if voice_language == "en-US":
        if no_input_count == 0:
            response = "Are you still there?"
        else:
            response = "If you're there, please speak now."
    else:
        if no_input_count == 0:
            response = "کیا آپ ابھی بھی وہاں ہیں؟"
        else:
            response = "اگر آپ وہاں ہیں تو، براہ کرم اب بولیں۔"
    
    return Response(
        content=twilio_service.create_twiml_response(response, voice_language=voice_language),
        media_type="application/xml"
    )
@router.post("/complete-processing")
async def complete_processing(request: Request, db: Session = Depends(get_db)):
    """Continue processing a complex query after sending initial acknowledgment."""
    form_data = await request.form()
    call_sid = form_data.get("CallSid")
    
    # Get the saved query from the cache
    processing_key = f"processing_{call_sid}"
    speech_result = _conversation_cache.get(processing_key)
    
    if not speech_result:
        return Response(
            content=twilio_service.create_twiml_response(
                "I'm sorry, I lost track of your question. Could you please repeat?"
            ),
            media_type="application/xml"
        )
    
    # Clear from cache
    _conversation_cache.pop(processing_key, None)
    
    # Continue with normal processing (simulate a form with the speech result)
    mock_request = Request(scope=request.scope)
    mock_request.form = lambda: {
        "CallSid": call_sid,
        "SpeechResult": speech_result,
        "Confidence": "0.8"
    }
    
    return await speech_webhook(mock_request, db)

@router.post("/no-input")
async def no_input_webhook(request: Request, db: Session = Depends(get_db)):
    """Webhook for handling no input from user."""
    form_data = await request.form()
    call_sid = form_data.get("CallSid")
    
    logger.info(f"No input received for call {call_sid}")
    
    # Get cached conversation
    conversation = get_cached_conversation(call_sid, db)
    if not conversation:
        # Fallback if conversation not found
        return Response(
            content=twilio_service.create_twiml_response("Can I help you with anything today?"),
            media_type="application/xml"
        )
    
    # Extract language preference
    voice_language = "en-US"  # Default to English
    try:
        conversation_history = json.loads(conversation.conversation_log)
        for entry in conversation_history:
            if "system" in entry and "Language selected:" in entry["system"]:
                if "ur-PK" in entry["system"]:
                    voice_language = "ur-PK"
                break
    except:
        conversation_history = []
    
    # Fast count query for no-input events
    no_input_count = db.query(ConversationTurn).filter(
        ConversationTurn.conversation_id == conversation.id,
        ConversationTurn.content == "NO_INPUT"
    ).count()
    
    if no_input_count >= 3:
        # After multiple no-inputs, end the call politely
        if voice_language == "en-US":
            goodbye_message = f"I haven't heard a response. Thank you for calling {settings.RESTAURANT_NAME}. Feel free to call back anytime!"
        else:
            goodbye_message = f"مجھے کوئی جواب نہیں ملا۔ {settings.RESTAURANT_NAME} کو کال کرنے کا شکریہ۔ کسی بھی وقت دوبارہ کال کرنے میں آزاد ہیں!"
            
        # Update conversation record with end time
        conversation.ended_at = datetime.utcnow()
        db.commit()
        
        return Response(
            content=twilio_service.create_goodbye_response(goodbye_message, voice_language),
            media_type="application/xml"
        )
    
    # Add a no-input marker efficiently
    db.add(ConversationTurn(
        conversation_id=conversation.id,
        sequence=len(conversation_history) + 1 if conversation_history else 1,
        speaker="customer",
        content="NO_INPUT"
    ))
    db.commit()
    
    # Simple, brief prompts for better response time
    if voice_language == "en-US":
        if no_input_count == 0:
            response = "Are you still there?"
        else:
            response = "If you're there, please speak now."
    else:
        if no_input_count == 0:
            response = "کیا آپ ابھی بھی وہاں ہیں؟"
        else:
            response = "اگر آپ وہاں ہیں تو، براہ کرم اب بولیں۔"
    
    return Response(
        content=twilio_service.create_twiml_response(response, voice_language=voice_language),
        media_type="application/xml"
    )

@router.post("/speech-fallback")
async def speech_fallback(request: Request, db: Session = Depends(get_db)):
    """Handle speech recognition fallback when Twilio can't understand the customer."""
    form_data = await request.form()
    call_sid = form_data.get("CallSid")
    
    logger.info(f"Speech recognition fallback for call {call_sid}")
    
    # Find the conversation record
    conversation = get_cached_conversation(call_sid, db)
    if not conversation:
        # Fallback if conversation not found
        return Response(
            content=twilio_service.create_twiml_response(
                "I'm having trouble understanding. Could you please try again?"
            ),
            media_type="application/xml"
        )
    
    # Extract language preference
    voice_language = "en-US"  # Default to English
    try:
        conversation_history = json.loads(conversation.conversation_log)
        for entry in conversation_history:
            if "system" in entry and "Language selected:" in entry["system"]:
                if "ur-PK" in entry["system"]:
                    voice_language = "ur-PK"
                break
    except:
        conversation_history = []
    
    # Add a fallback marker to conversation turns
    db.add(ConversationTurn(
        conversation_id=conversation.id,
        sequence=len(conversation_history) + 1 if conversation_history else 1,
        speaker="customer",
        content="SPEECH_FALLBACK"
    ))
    db.commit()
    
    # Check how many fallbacks have occurred
    fallback_count = db.query(ConversationTurn).filter(
        ConversationTurn.conversation_id == conversation.id,
        ConversationTurn.content == "SPEECH_FALLBACK"
    ).count()
    
    if fallback_count >= 2:
        # After multiple fallbacks, offer transfer to human
        if voice_language == "en-US":
            transfer_message = "I'm having trouble understanding you. Let me transfer you to one of our staff members."
        else:
            transfer_message = "مجھے آپ کو سمجھنے میں دشواری ہو رہی ہے۔ میں آپ کو ہمارے عملے کے کسی رکن سے منسلک کروں گا۔"
            
        return Response(
            content=twilio_service.create_transfer_to_human_response(
                transfer_message,
                voice_language=voice_language
            ),
            media_type="application/xml"
        )
    
    # Generate appropriate prompt based on fallback count and language
    if voice_language == "en-US":
        response = "I didn't catch that. Could you please speak clearly?"
    else:
        response = "مجھے وہ سمجھ نہیں آیا۔ کیا آپ واضح طور پر بول سکتے ہیں؟"
    
    return Response(
        content=twilio_service.create_twiml_response(response, voice_language=voice_language),
        media_type="application/xml"
    )

@router.post("/status")
async def call_status_webhook(request: Request, db: Session = Depends(get_db)):
    """Webhook for handling call status updates from Twilio."""
    try:
        form_data = await request.form()
        call_sid = form_data.get("CallSid")
        call_status = form_data.get("CallStatus")
        call_duration = form_data.get("CallDuration")
        
        logger.info(f"Call status update - SID: {call_sid}, Status: {call_status}, Duration: {call_duration}")
        
        # Find the conversation record
        conversation = get_cached_conversation(call_sid, db)
        if not conversation:
            logger.warning(f"Conversation not found for call {call_sid}")
            return {"status": "warning", "message": "Conversation not found"}
        
        # Update the conversation based on call status
        if call_status == "completed":
            conversation.ended_at = datetime.utcnow()
            if call_duration:
                conversation.duration = int(call_duration)
                
            # If we have enough conversation data, perform sentiment analysis
            try:
                conversation_history = json.loads(conversation.conversation_log)
                if len(conversation_history) > 1:
                    sentiment_score = await llm_service.analyze_sentiment(conversation_history)
                    conversation.sentiment_score = sentiment_score
                    logger.info(f"Call sentiment score: {sentiment_score}")
            except Exception as e:
                logger.error(f"Error analyzing sentiment: {str(e)}")
            
            db.commit()
            
        return {"status": "success"}
        
    except Exception as e:
        logger.error(f"Error processing call status webhook: {str(e)}")
        
        # Log the error
        try:
            error_log = ErrorLog(
                call_sid=form_data.get("CallSid") if 'form_data' in locals() else None,
                error_type=type(e).__name__,
                error_message=str(e),
                stack_trace=traceback.format_exc(),
                error_metadata=json.dumps({"url": str(request.url)})
            )
            db.add(error_log)
            db.commit()
        except:
            pass
            
        return {"status": "error", "message": str(e)}

@router.post("/fallback")
async def fallback_webhook(request: Request, db: Session = Depends(get_db)):
    """Fallback webhook for handling errors in the Twilio call flow."""
    try:
        form_data = await request.form()
        call_sid = form_data.get("CallSid")
        error_type = form_data.get("ErrorType") 
        error_code = form_data.get("ErrorCode")
        error_message = form_data.get("ErrorMessage")
        
        logger.error(f"Fallback triggered - SID: {call_sid}, Error: {error_type} ({error_code}): {error_message}")
        
        # Log the error
        error_log = ErrorLog(
            call_sid=call_sid,
            error_type=error_type or "Twilio Fallback",
            error_message=error_message or f"Error code: {error_code}",
            error_metadata=json.dumps({"form_data": dict(form_data)})
        )
        db.add(error_log)
        
        # Find the conversation
        conversation = get_cached_conversation(call_sid, db)
        
        # Default language
        voice_language = "en-US"
        
        if conversation:
            # Extract language preference
            try:
                conversation_history = json.loads(conversation.conversation_log)
                for entry in conversation_history:
                    if "system" in entry and "Language selected:" in entry["system"]:
                        if "ur-PK" in entry["system"]:
                            voice_language = "ur-PK"
                        break
                        
                # Update the conversation with error info
                conversation_history.append({
                    "system": f"Error occurred: {error_type} - {error_message}"
                })
                conversation.conversation_log = json.dumps(conversation_history)
                db.commit()
            except:
                pass
        
        # Return a TwiML response to handle the fallback gracefully
        if voice_language == "en-US":
            transfer_message = "I'm experiencing technical difficulties. Let me transfer you to one of our staff members."
        else:
            transfer_message = "مجھے تکنیکی دشواریوں کا سامنا ہے۔ میں آپ کو ہمارے عملے کے کسی رکن سے منسلک کروں گا۔"
            
        return Response(
            content=twilio_service.create_transfer_to_human_response(
                transfer_message,
                voice_language=voice_language
            ),
            media_type="application/xml"
        )
        
    except Exception as e:
        logger.error(f"Error in fallback webhook: {str(e)}")
        
        # Create a basic TwiML response as a last resort
        response = """
        <?xml version="1.0" encoding="UTF-8"?>
        <Response>
            <Say voice="Polly.Joanna-Neural">I apologize for the technical difficulties. Please call back later or contact us directly. Thank you.</Say>
            <Hangup/>
        </Response>
        """
        return Response(content=response, media_type="application/xml")