from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime

class OrderItemSchema(BaseModel):
    item: str
    quantity: int = 1
    special_instructions: Optional[str] = None
    price: Optional[int] = None  # In cents
    
    class Config:
        from_attributes = True

class OrderSchema(BaseModel):
    id: int
    customer_name: str
    customer_phone: str
    order_items: List[Dict[str, Any]] = Field(..., description="JSON string of order items")
    order_total: Optional[int] = None  # Total in cents
    is_delivery: bool = False
    delivery_address: Optional[str] = None
    delivery_fee: Optional[int] = None  # In cents
    reservation_time: Optional[datetime] = None
    party_size: Optional[int] = None
    status: str
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class CreateOrderSchema(BaseModel):
    customer_name: str
    customer_phone: str
    order_items: List[Dict[str, Any]]
    is_delivery: bool = False
    delivery_address: Optional[str] = None
    reservation_time: Optional[datetime] = None
    party_size: Optional[int] = None
    notes: Optional[str] = None

class UpdateOrderSchema(BaseModel):
    customer_name: Optional[str] = None
    order_items: Optional[List[Dict[str, Any]]] = None
    is_delivery: Optional[bool] = None
    delivery_address: Optional[str] = None
    reservation_time: Optional[datetime] = None
    party_size: Optional[int] = None
    status: Optional[str] = None
    notes: Optional[str] = None

class OrderResponse(BaseModel):
    order: OrderSchema
    conversations: Optional[List[Any]] = None
    
    class Config:
        from_attributes = True