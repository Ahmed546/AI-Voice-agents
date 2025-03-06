from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Union
from datetime import datetime

class ConversationTurnSchema(BaseModel):
    id: int
    conversation_id: int
    sequence: int
    speaker: str  # "customer" or "assistant"
    content: str
    intent: Optional[str] = None
    latency: Optional[int] = None  # Response time in ms
    timestamp: datetime
    
    class Config:
        from_attributes = True

class ConversationSchema(BaseModel):
    id: int
    call_sid: str
    customer_phone: str
    conversation_log: str  # JSON string of conversation
    order_id: Optional[int] = None
    duration: Optional[int] = None  # Call duration in seconds
    sentiment_score: Optional[float] = None
    created_at: datetime
    ended_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

class ConversationResponse(BaseModel):
    conversation: ConversationSchema
    turns: Optional[List[ConversationTurnSchema]] = None
    order: Optional[Any] = None  # Will be OrderSchema when used
    
    class Config:
        from_attributes = True

class ConversationStatistics(BaseModel):
    time_period: str
    total_conversations: int
    completed_conversations: int
    completion_rate: float  # Percentage
    orders_created: int
    conversion_rate: float  # Percentage
    avg_sentiment: float
    avg_duration_seconds: float
    avg_response_latency_ms: float
    intent_distribution: Dict[str, int]
    error_count: int
    
    class Config:
        from_attributes = True