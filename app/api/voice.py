from fastapi import APIRouter, Depends, HTTPException, Request, Response, Body
from sqlalchemy.orm import Session
import logging
import json
import traceback
from datetime import datetime
import asyncio

from app.db.database import get_db
from app.db.models import Conversation, ConversationTurn, Order, ErrorLog
from app.services.twilio_service import twilio_service
from app.services.llm_service import llm_service
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
    
    # Check for existing conversations/orders for this customer
    existing_orders = db.query(Order).filter(
        Order.customer_phone == customer_phone,
        Order.status.in_(["confirmed", "modified"])
    ).order_by(Order.created_at.desc()).first()
    
    # Create a new conversation record
    new_conversation = Conversation(
        call_sid=call_sid,
        customer_phone=customer_phone,
        conversation_log=json.dumps([]),
        order_id=existing_orders.id if existing_orders else None
    )
    db.add(new_conversation)
    db.commit()
    
    # Get custom greeting based on whether they have existing orders
    greeting = "Thank you for calling Mario's Italian Restaurant. This is Mario's virtual assistant."
    
    if existing_orders:
        greeting += f" I see you have an existing order with us. How can I help you today?"
    else:
        greeting += " How can I help you today?"
    
    # Create TwiML response
    twiml_response = twilio_service.create_twiml_response(greeting)
    
    return Response(content=twiml_response, media_type="application/xml")

@router.post("/process-speech")
async def process_speech(request: Request, db: Session = Depends(get_db)):
    """Process customer speech and generate a response."""
    try:
        form_data = await request.form()
        call_sid = form_data.get("CallSid")
        speech_result = form_data.get("SpeechResult")
        confidence = float(form_data.get("Confidence", 0))
        
        if not speech_result:
            logger.warning(f"No speech detected for call {call_sid}")
            twiml_response = twilio_service.create_twiml_response(
                "I'm sorry, I didn't catch that. Could you please repeat?"
            )
            return Response(content=twiml_response, media_type="application/xml")
        
        # Find the conversation record
        conversation = db.query(Conversation).filter(Conversation.call_sid == call_sid).first()
        if not conversation:
            logger.error(f"Conversation not found for call {call_sid}")
            twiml_response = twilio_service.create_twiml_response(
                "I'm sorry, I'm having trouble with this call. Let me transfer you to a staff member."
            )
            return Response(content=twiml_response, media_type="application/xml")
        
        # Load conversation history
        try:
            conversation_history = json.loads(conversation.conversation_log)
        except json.JSONDecodeError:
            conversation_history = []
        
        # Classify intent
        intent = await llm_service.classify_intent(speech_result)
        
        # Add customer's speech to conversation history
        conversation_history.append({"customer": speech_result})
        
        # Create a new conversation turn record for customer
        new_turn = ConversationTurn(
            conversation_id=conversation.id,
            sequence=len(conversation_history),
            speaker="customer",
            content=speech_result,
            intent=intent
        )
        db.add(new_turn)
        
        # Handle special intents
        if intent == "end_call":
            response_text = "Thank you for calling Mario's Italian Restaurant. Have a great day!"
            twiml_response = twilio_service.create_goodbye_response(response_text)
            
            # Update conversation record with end time
            conversation.ended_at = datetime.utcnow()
            conversation.conversation_log = json.dumps(conversation_history)
            db.commit()
            
            return Response(content=twiml_response, media_type="application/xml")
        
        # Load existing order data if available
        order_data = None
        if conversation.order_id:
            order = db.query(Order).filter(Order.id == conversation.order_id).first()
            if order:
                order_data = {
                    "id": order.id,
                    "customer_name": order.customer_name,
                    "order_items": json.loads(order.order_items),
                    "is_delivery": order.is_delivery,
                    "status": order.status
                }
        
        # Generate AI response
        start_time = datetime.utcnow()
        ai_response = await llm_service.generate_response(speech_result, conversation_history, order_data)
        latency = (datetime.utcnow() - start_time).total_seconds() * 1000  # ms
        
        # Update conversation history with assistant's response
        conversation_history[-1]["assistant"] = ai_response
        
        # Create a new conversation turn record for assistant
        assistant_turn = ConversationTurn(
            conversation_id=conversation.id,
            sequence=len(conversation_history),
            speaker="assistant",
            content=ai_response,
            latency=latency
        )
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
        
        # Create TwiML response
        twiml_response = twilio_service.create_twiml_response(ai_response)
        
        return Response(content=twiml_response, media_type="application/xml")
        
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
        twiml_response = twilio_service.create_twiml_response(
            "I'm sorry, I encountered an error. Let me transfer you to a staff member who can help."
        )
        return Response(content=twiml_response, media_type="application/xml")

@router.post("/handle-no-input")
async def handle_no_input(request: Request, db: Session = Depends(get_db)):
    """Handle cases where no input is received from the customer."""
    form_data = await request.form()
    call_sid = form_data.get("CallSid")
    
    logger.info(f"No input received for call {call_sid}")
    
    # Find the conversation record
    conversation = db.query(Conversation).filter(Conversation.call_sid == call_sid).first()
    if not conversation:
        # Fallback if conversation not found
        twiml_response = twilio_service.create_twiml_response(
            "I didn't hear anything. Can I help you with anything today?"
        )
        return Response(content=twiml_response, media_type="application/xml")
    
    # Get conversation history
    try:
        conversation_history = json.loads(conversation.conversation_log)
    except json.JSONDecodeError:
        conversation_history = []
    
    # Check if this is repeated no-input
    no_input_count = db.query(ConversationTurn).filter(
        ConversationTurn.conversation_id == conversation.id,
        ConversationTurn.content == "NO_INPUT"
    ).count()
    
    if no_input_count >= 2:
        # After multiple no-inputs, end the call politely
        twiml_response = twilio_service.create_goodbye_response(
            "I haven't heard a response. Thank you for calling Mario's Italian Restaurant. Feel free to call back anytime!"
        )
        
        # Update conversation record with end time
        conversation.ended_at = datetime.utcnow()
        db.commit()
        
        return Response(content=twiml_response, media_type="application/xml")
    
    # Add a no-input marker to conversation turns
    new_turn = ConversationTurn(
        conversation_id=conversation.id,
        sequence=len(conversation_history) + 1 if conversation_history else 1,
        speaker="customer",
        content="NO_INPUT"
    )
    db.add(new_turn)
    db.commit()
    
    # Generate appropriate prompt based on no-input count
    if no_input_count == 0:
        response = "I didn't hear anything. Can I help you with an order or reservation today?"
    else:
        response = "I still don't hear anything. If you're there, please speak now, or I'll end the call."
    
    twiml_response = twilio_service.create_twiml_response(response)
    return Response(content=twiml_response, media_type="application/xml")

@router.post("/call", status_code=201)
async def initiate_call(
    phone_number: str = Body(..., embed=True),
    db: Session = Depends(get_db)
):
    """Initiate an outbound call to a customer."""
    try:
        # Normalize phone number
        formatted_number = parse_phone_number(phone_number)
        
        # Initiate call via Twilio
        call_sid = twilio_service.make_call(formatted_number)
        
        return {"status": "success", "call_sid": call_sid}
    except Exception as e:
        logger.error(f"Failed to initiate call: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to initiate call: {str(e)}")