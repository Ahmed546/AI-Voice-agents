from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, Float
from sqlalchemy.orm import relationship
from datetime import datetime
from app.db.database import Base

class Order(Base):
    __tablename__ = "orders"
    
    id = Column(Integer, primary_key=True, index=True)
    customer_name = Column(String(100), nullable=False)
    customer_phone = Column(String(20), nullable=False, index=True)
    order_items = Column(Text, nullable=False)  # JSON string of order items
    order_total = Column(Integer)  # Total in cents
    is_delivery = Column(Boolean, default=False)
    delivery_address = Column(Text, nullable=True)
    delivery_fee = Column(Integer, nullable=True)  # In cents
    reservation_time = Column(DateTime, nullable=True)
    party_size = Column(Integer, nullable=True)
    status = Column(String(20), default="confirmed")  # confirmed, modified, cancelled, completed
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationship with conversations
    conversations = relationship("Conversation", back_populates="order")
    
    def __repr__(self):
        return f"<Order(id={self.id}, customer={self.customer_name}, status={self.status})>"

class Conversation(Base):
    __tablename__ = "conversations"
    
    id = Column(Integer, primary_key=True, index=True)
    call_sid = Column(String(50), nullable=False, index=True)
    customer_phone = Column(String(20), nullable=False, index=True)
    conversation_log = Column(Text, nullable=False)  # JSON string of conversation
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    duration = Column(Integer, nullable=True)  # Call duration in seconds
    sentiment_score = Column(Float, nullable=True)  # Optional sentiment analysis
    created_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime, nullable=True)
    
    # Relationship with orders
    order = relationship("Order", back_populates="conversations")
    
    def __repr__(self):
        return f"<Conversation(id={self.id}, call_sid={self.call_sid})>"

class ConversationTurn(Base):
    __tablename__ = "conversation_turns"
    
    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False)
    sequence = Column(Integer, nullable=False)  # Order in conversation
    speaker = Column(String(10), nullable=False)  # "customer" or "assistant"
    content = Column(Text, nullable=False)
    intent = Column(String(50), nullable=True)  # For customer turns
    latency = Column(Integer, nullable=True)  # Response time in ms for assistant turns
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    # Relationship with conversation
    conversation = relationship("Conversation")
    
    def __repr__(self):
        return f"<ConversationTurn(id={self.id}, speaker={self.speaker}, sequence={self.sequence})>"

class MenuItem(Base):
    __tablename__ = "menu_items"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    price = Column(Integer, nullable=False)  # In cents
    category = Column(String(50), nullable=False)  # appetizer, main, dessert, etc.
    is_available = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<MenuItem(id={self.id}, name={self.name}, price={self.price/100})>"

class ErrorLog(Base):
    __tablename__ = "error_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    call_sid = Column(String(50), nullable=True, index=True)
    error_type = Column(String(100), nullable=False)
    error_message = Column(Text, nullable=False)
    stack_trace = Column(Text, nullable=True)
    error_metadata = Column(Text, nullable=True)  # Changed from 'metadata' to 'error_metadata'
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<ErrorLog(id={self.id}, error_type={self.error_type})>"