from fastapi import APIRouter, Depends, HTTPException, Query, Path
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from typing import List, Optional
import logging
import json
from datetime import datetime, timedelta

from app.db.database import get_db
from app.db.models import Conversation, ConversationTurn, Order, ErrorLog
from app.services.twilio_service import twilio_service
from app.schemas.order import OrderSchema, OrderResponse
from app.schemas.conversation import ConversationSchema, ConversationResponse, ConversationStatistics

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/orders", response_model=List[OrderResponse])
async def get_orders(
    status: Optional[str] = Query(None, description="Filter by order status"),
    from_date: Optional[datetime] = Query(None, description="Filter by start date"),
    to_date: Optional[datetime] = Query(None, description="Filter by end date"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """Get a list of orders with optional filtering."""
    query = db.query(Order)
    
    if status:
        query = query.filter(Order.status == status)
    
    if from_date:
        query = query.filter(Order.created_at >= from_date)
    
    if to_date:
        query = query.filter(Order.created_at <= to_date)
    
    total = query.count()
    orders = query.order_by(desc(Order.created_at)).offset(offset).limit(limit).all()
    
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": orders
    }

@router.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: int = Path(..., description="Order ID"),
    db: Session = Depends(get_db)
):
    """Get detailed information about a specific order."""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # Load associated conversations
    conversations = db.query(Conversation).filter(Conversation.order_id == order_id).all()
    
    return {
        "order": order,
        "conversations": conversations
    }

@router.put("/orders/{order_id}/status")
async def update_order_status(
    order_id: int = Path(..., description="Order ID"),
    status: str = Query(..., description="New order status"),
    db: Session = Depends(get_db)
):
    """Update the status of an order."""
    valid_statuses = ["confirmed", "modified", "cancelled", "completed"]
    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}")
    
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    order.status = status
    order.updated_at = datetime.utcnow()
    db.commit()
    
    return {"status": "success", "order_id": order_id, "new_status": status}

@router.get("/conversations", response_model=List[ConversationResponse])
async def get_conversations(
    from_date: Optional[datetime] = Query(None, description="Filter by start date"),
    to_date: Optional[datetime] = Query(None, description="Filter by end date"),
    sentiment_min: Optional[float] = Query(None, ge=-1, le=1, description="Minimum sentiment score"),
    sentiment_max: Optional[float] = Query(None, ge=-1, le=1, description="Maximum sentiment score"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """Get a list of conversations with optional filtering."""
    query = db.query(Conversation)
    
    if from_date:
        query = query.filter(Conversation.created_at >= from_date)
    
    if to_date:
        query = query.filter(Conversation.created_at <= to_date)
    
    if sentiment_min is not None:
        query = query.filter(Conversation.sentiment_score >= sentiment_min)
    
    if sentiment_max is not None:
        query = query.filter(Conversation.sentiment_score <= sentiment_max)
    
    total = query.count()
    conversations = query.order_by(desc(Conversation.created_at)).offset(offset).limit(limit).all()
    
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": conversations
    }

@router.get("/conversations/{conversation_id}", response_model=ConversationSchema)
async def get_conversation(
    conversation_id: int = Path(..., description="Conversation ID"),
    db: Session = Depends(get_db)
):
    """Get detailed information about a specific conversation."""
    conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    # Load conversation turns
    turns = db.query(ConversationTurn).filter(
        ConversationTurn.conversation_id == conversation_id
    ).order_by(ConversationTurn.sequence).all()
    
    # Get order if available
    order = None
    if conversation.order_id:
        order = db.query(Order).filter(Order.id == conversation.order_id).first()
    
    return {
        "conversation": conversation,
        "turns": turns,
        "order": order
    }

@router.get("/stats", response_model=ConversationStatistics)
async def get_statistics(
    days: int = Query(7, ge=1, le=90, description="Number of days to analyze"),
    db: Session = Depends(get_db)
):
    """Get statistics about voice agent performance."""
    # Calculate date range
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)
    
    # Get total conversations
    total_conversations = db.query(Conversation).filter(
        Conversation.created_at >= start_date,
        Conversation.created_at <= end_date
    ).count()
    
    # Get completed conversations (those with ended_at populated)
    completed_conversations = db.query(Conversation).filter(
        Conversation.created_at >= start_date,
        Conversation.created_at <= end_date,
        Conversation.ended_at != None
    ).count()
    
    # Get conversations that resulted in orders
    orders_created = db.query(Conversation).filter(
        Conversation.created_at >= start_date,
        Conversation.created_at <= end_date,
        Conversation.order_id != None
    ).count()
    
    # Get average sentiment score
    sentiment_result = db.query(func.avg(Conversation.sentiment_score)).filter(
        Conversation.created_at >= start_date,
        Conversation.created_at <= end_date,
        Conversation.sentiment_score != None
    ).first()
    
    avg_sentiment = sentiment_result[0] if sentiment_result and sentiment_result[0] is not None else 0.0
    
    # Get average conversation duration
    duration_result = db.query(func.avg(Conversation.duration)).filter(
        Conversation.created_at >= start_date,
        Conversation.created_at <= end_date,
        Conversation.duration != None
    ).first()
    
    avg_duration = duration_result[0] if duration_result and duration_result[0] is not None else 0.0
    
    # Get intents distribution
    intent_counts = {}
    intent_results = db.query(
        ConversationTurn.intent, func.count(ConversationTurn.id)
    ).filter(
        ConversationTurn.timestamp >= start_date,
        ConversationTurn.timestamp <= end_date,
        ConversationTurn.speaker == "customer",
        ConversationTurn.intent != None
    ).group_by(ConversationTurn.intent).all()
    
    for intent, count in intent_results:
        if intent:
            intent_counts[intent] = count
    
    # Get assistant response latency
    latency_result = db.query(func.avg(ConversationTurn.latency)).filter(
        ConversationTurn.timestamp >= start_date,
        ConversationTurn.timestamp <= end_date,
        ConversationTurn.speaker == "assistant",
        ConversationTurn.latency != None
    ).first()
    
    avg_latency = latency_result[0] if latency_result and latency_result[0] is not None else 0.0
    
    # Get error count
    error_count = db.query(ErrorLog).filter(
        ErrorLog.created_at >= start_date,
        ErrorLog.created_at <= end_date
    ).count()
    
    return {
        "time_period": f"{start_date.isoformat()} to {end_date.isoformat()}",
        "total_conversations": total_conversations,
        "completed_conversations": completed_conversations,
        "completion_rate": (completed_conversations / total_conversations * 100) if total_conversations > 0 else 0,
        "orders_created": orders_created,
        "conversion_rate": (orders_created / total_conversations * 100) if total_conversations > 0 else 0,
        "avg_sentiment": avg_sentiment,
        "avg_duration_seconds": avg_duration,
        "avg_response_latency_ms": avg_latency,
        "intent_distribution": intent_counts,
        "error_count": error_count
    }

@router.get("/errors", response_model=List[dict])
async def get_errors(
    from_date: Optional[datetime] = Query(None, description="Filter by start date"),
    to_date: Optional[datetime] = Query(None, description="Filter by end date"),
    error_type: Optional[str] = Query(None, description="Filter by error type"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """Get a list of error logs with optional filtering."""
    query = db.query(ErrorLog)
    
    if from_date:
        query = query.filter(ErrorLog.created_at >= from_date)
    
    if to_date:
        query = query.filter(ErrorLog.created_at <= to_date)
    
    if error_type:
        query = query.filter(ErrorLog.error_type == error_type)
    
    total = query.count()
    errors = query.order_by(desc(ErrorLog.created_at)).offset(offset).limit(limit).all()
    
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": errors
    }