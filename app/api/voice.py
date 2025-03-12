from fastapi import APIRouter, Depends, HTTPException, Request, Response, Body
from sqlalchemy.orm import Session
import logging
import json
from datetime import datetime
import asyncio
import traceback

from app.db.database import get_db
from app.db.models import Conversation, ConversationTurn, Order, ErrorLog
from app.services.twilio_service import twilio_service
from app.services.llm_service import llm_service
from app.services.rag_service import rag_service
from app.services.speech_enhancement_service import speech_enhancement_service
from app.utils.helpers import parse_phone_number, parse_datetime
from app.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/incoming")
async def incoming_call(request: Request, db: Session = Depends(get_db)):
    """Handle incoming call from Twilio."""
    form_data = await request.form()
    call_sid = form_data.get("CallSid")
    from_number = form_data.get("From")
    
    logger.info(f"Incoming call from {from_number}, SID: {call_sid}")
    
    # Normalize phone number
    customer_phone = parse_phone_number(from_number)
    
    # Create a new conversation record
    new_conversation = Conversation(
        call_sid=call_sid,
        customer_phone=customer_phone,
        conversation_log=json.dumps([]),
        order_id=None
    )
    db.add(new_conversation)
    db.commit()
    
    # Language selection prompt
    language_prompt = f"Thank you for calling {settings.RESTAURANT_NAME}. Press 1 for English or press 2 for Urdu."
    
    # Create TwiML response with language selection options
    response = twilio_service.create_language_selection_response(language_prompt)
    
    return Response(content=response, media_type="application/xml")

@router.post("/handle-language")
async def handle_language_selection(request: Request, db: Session = Depends(get_db)):
    """Handle language selection."""
    form_data = await request.form()
    call_sid = form_data.get("CallSid")
    digits_pressed = form_data.get("Digits")
    
    # Find the conversation record
    conversation = db.query(Conversation).filter(Conversation.call_sid == call_sid).first()
    if not conversation:
        logger.error(f"Conversation not found for call {call_sid}")
        twiml_response = twilio_service.create_twiml_response(
            "I'm sorry, I'm having trouble with this call. Please try again later."
        )
        return Response(content=twiml_response, media_type="application/xml")
    
    # Get language based on digits pressed
    language = "en-US"  # Default to English
    if digits_pressed == "2":
        language = "ur-PK"  # Urdu
    
    # Store language preference in conversation metadata
    try:
        conversation_history = json.loads(conversation.conversation_log)
    except json.JSONDecodeError:
        conversation_history = []
    
    # Add language selection to conversation metadata
    conversation_history.append({"system": f"Language selected: {language}"})
    conversation.conversation_log = json.dumps(conversation_history)
    db.commit()
    
    # Check for existing orders for this customer
    existing_orders = db.query(Order).filter(
        Order.customer_phone == conversation.customer_phone,
        Order.status.in_(["confirmed", "modified"])
    ).order_by(Order.created_at.desc()).first()
    
    # Update conversation with order info if available
    if existing_orders:
        conversation.order_id = existing_orders.id
        db.commit()
    
    # Get personalized greeting based on customer status and language
    if language == "en-US":
        if existing_orders:
            greeting = f"Welcome back to {settings.RESTAURANT_NAME}. I see you have an existing order with us. How can I help you today?"
        else:
            greeting = f"Welcome to {settings.RESTAURANT_NAME}. How can I help you today? You can ask about our menu, place an order, or make a reservation."
    else:  # Urdu
        if existing_orders:
            greeting = f"{settings.RESTAURANT_NAME} میں دوبارہ خوش آمدید۔ میں دیکھ رہا ہوں کہ آپ کا ایک موجودہ آرڈر ہے۔ میں آج آپ کی کیسے مدد کر سکتا ہوں؟"
        else:
            greeting = f"{settings.RESTAURANT_NAME} میں خوش آمدید۔ میں آپ کی کیسے مدد کر سکتا ہوں؟ آپ ہمارے مینو کے بارے میں پوچھ سکتے ہیں، آرڈر دے سکتے ہیں، یا ریزرویشن کر سکتے ہیں۔"
    
    # Create TwiML response
    twiml_response = twilio_service.create_twiml_response(greeting, voice_language=language)
    
    return Response(content=twiml_response, media_type="application/xml")


# In app/api/voice.py
# Make sure you add this route handler

@router.post("/handle-language")
async def handle_language_selection(request: Request, db: Session = Depends(get_db)):
    """Handle language selection."""
    form_data = await request.form()
    call_sid = form_data.get("CallSid")
    digits_pressed = form_data.get("Digits")
    
    # Find the conversation record
    conversation = db.query(Conversation).filter(Conversation.call_sid == call_sid).first()
    if not conversation:
        logger.error(f"Conversation not found for call {call_sid}")
        twiml_response = twilio_service.create_twiml_response(
            "I'm sorry, I'm having trouble with this call. Please try again later."
        )
        return Response(content=twiml_response, media_type="application/xml")
    
    # Get language based on digits pressed - Default to English for safety
    language = "en-US"
    if digits_pressed == "2":
        language = "en-US"  # Temporarily set to English until we fix Urdu issues
    
    # Store language preference in conversation metadata
    try:
        conversation_history = json.loads(conversation.conversation_log)
    except json.JSONDecodeError:
        conversation_history = []
    
    # Add language selection to conversation metadata
    conversation_history.append({"system": f"Language selected: {language}"})
    conversation.conversation_log = json.dumps(conversation_history)
    db.commit()
    
    # Check for existing orders for this customer
    existing_orders = db.query(Order).filter(
        Order.customer_phone == conversation.customer_phone,
        Order.status.in_(["confirmed", "modified"])
    ).order_by(Order.created_at.desc()).first()
    
    # Update conversation with order info if available
    if existing_orders:
        conversation.order_id = existing_orders.id
        db.commit()
    
    # Get personalized greeting - For now use English regardless of selection
    if existing_orders:
        greeting = f"Welcome back to {settings.RESTAURANT_NAME}. I see you have an existing order with us. How can I help you today?"
    else:
        greeting = f"Welcome to {settings.RESTAURANT_NAME}. How can I help you today? You can ask about our menu, place an order, or make a reservation."
    
    # Create TwiML response - Force English language for now
    twiml_response = twilio_service.create_twiml_response(greeting, voice_language="en-US")
    
    return Response(content=twiml_response, media_type="application/xml")
# Handle order status checks
async def handle_order_status_check(conversation, db):
    """Handle order status check intent."""
    if not conversation.order_id:
        return "I don't see any active orders for your phone number. Would you like to place a new order?"
    
    order = db.query(Order).filter(Order.id == conversation.order_id).first()
    if not order:
        return "I'm having trouble finding your order details. Please call back in a few minutes or speak with a staff member."
    
    # Generate response based on order status
    if order.status == "confirmed":
        eta_text = ""
        if order.is_delivery:
            eta_text = " Your delivery should arrive within 30-45 minutes."
        else:
            eta_text = " Your order should be ready for pickup in 15-20 minutes."
            
        return f"Your order has been confirmed and is being prepared.{eta_text} The order total is ${order.order_total/100:.2f}."
    
    elif order.status == "modified":
        return f"Your order has been modified as requested. The updated total is ${order.order_total/100:.2f}."
    
    elif order.status == "cancelled":
        return "Your order has been cancelled. Is there anything else I can help you with?"
    
    elif order.status == "completed":
        return "Your order has been completed. We hope you enjoyed your meal! Would you like to place a new order?"
    
    return f"Your order status is: {order.status}. Is there anything specific you'd like to know about your order?"