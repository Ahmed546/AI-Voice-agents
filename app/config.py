import os
from pydantic_settings import BaseSettings
from dotenv import load_dotenv
from typing import Optional

# Load environment variables from .env file
load_dotenv()

class Settings(BaseSettings):
    # API Keys
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    ANTHROPIC_API_KEY: Optional[str] = os.getenv("ANTHROPIC_API_KEY", "")
    
    # Twilio Configuration
    TWILIO_ACCOUNT_SID: str = os.getenv("TWILIO_ACCOUNT_SID", "")
    TWILIO_AUTH_TOKEN: str = os.getenv("TWILIO_AUTH_TOKEN", "")
    TWILIO_PHONE_NUMBER: str = os.getenv("TWILIO_PHONE_NUMBER", "")
    TWILIO_WEBHOOK_URL: str = os.getenv("TWILIO_WEBHOOK_URL", "http://localhost:8000/api/voice/incoming")
    
    # Database Configuration
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./restaurant_voice_agent.db")
    
    # Application Settings
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    MAX_RETRIES: int = int(os.getenv("MAX_RETRIES", "3"))
    DEFAULT_MODEL: str = os.getenv("DEFAULT_MODEL", "gpt-3.5-turbo")  # Updated model name
    CONVERSATION_MODEL: str = os.getenv("CONVERSATION_MODEL", "gpt-4")  # Updated model name
    RESPONSE_TIMEOUT: int = int(os.getenv("RESPONSE_TIMEOUT", "5"))
    
    # Restaurant Configuration
    RESTAURANT_NAME: str = os.getenv("RESTAURANT_NAME", "Mario's Italian Restaurant")
    RESTAURANT_HOURS: str = os.getenv("RESTAURANT_HOURS", "Tuesday-Sunday, 11am-10pm (closed Mondays)")
    
    # Parse integers with error handling for comments in env values
    def parse_int_env(env_key, default):
        value = os.getenv(env_key, str(default))
        # Strip any comments (anything after a '#' or spaces)
        if '#' in value:
            value = value.split('#')[0].strip()
        elif ' ' in value:
            value = value.split(' ')[0].strip()
        return int(value)
    
    DELIVERY_RADIUS: int = parse_int_env("DELIVERY_RADIUS", 5)
    DELIVERY_FEE: int = parse_int_env("DELIVERY_FEE", 3)
    MIN_RESERVATION_SIZE: int = parse_int_env("MIN_RESERVATION_SIZE", 5)
    
    # Optional Monitoring
    SENTRY_DSN: Optional[str] = os.getenv("SENTRY_DSN", "")
    
    # System Prompts
    INTENT_SYSTEM_PROMPT: str = """
    You are an AI assistant for a restaurant. Classify the customer's intent into one of the following categories:
    - new_order: Customer wants to place a new order
    - modify_order: Customer wants to modify an existing order
    - cancel_order: Customer wants to cancel an order
    - check_status: Customer wants to check order status
    - reservation: Customer wants to make a reservation
    - general_inquiry: Customer has a general question
    - end_call: Customer wants to end the call
    - unclear: Intent is not clear
    
    Return only the category as a single word.
    """
    
    CONVERSATION_SYSTEM_PROMPT: str = """
    You are an AI assistant for {restaurant_name}. Your name is {restaurant_name} Virtual Assistant.
    You handle phone orders and reservations politely and efficiently.
    
    Restaurant details:
    - Hours: {restaurant_hours}
    - Delivery available within {delivery_radius} miles, ${delivery_fee} delivery fee
    - Reservations needed for parties of {min_reservation_size} or more
    
    When taking orders or making reservations:
    1. Get customer name
    2. Get order details or reservation time/party size
    3. Confirm details before finalizing
    4. End with a polite message
    
    Keep responses conversational but concise (max 3 sentences).
    If you can't help or understand, politely offer to transfer to a human.
    """
    
    ORDER_PARSER_SYSTEM_PROMPT: str = """
    Extract order details from the conversation. Return a JSON object with these fields:
    - customer_name: customer's name or null if unknown
    - order_items: array of items ordered with quantity and special instructions
    - is_delivery: boolean indicating if delivery is requested
    - address: delivery address or null if not provided
    - reservation_time: datetime string if a reservation was made or null
    - party_size: number of people if a reservation was made or null
    
    Only include information explicitly stated in the conversation.
    """
    
    class Config:
        env_file = ".env"
        case_sensitive = True

# Create settings instance
settings = Settings()

# Format the system prompts with restaurant details
settings.CONVERSATION_SYSTEM_PROMPT = settings.CONVERSATION_SYSTEM_PROMPT.format(
    restaurant_name=settings.RESTAURANT_NAME,
    restaurant_hours=settings.RESTAURANT_HOURS,
    delivery_radius=settings.DELIVERY_RADIUS,
    delivery_fee=settings.DELIVERY_FEE,
    min_reservation_size=settings.MIN_RESERVATION_SIZE
)