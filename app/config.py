import os
from pydantic_settings import BaseSettings
from dotenv import load_dotenv
from typing import Optional, Dict


# Load environment variables from .env file
load_dotenv()

# Define parse_int_env function OUTSIDE the Settings class
def parse_int_env(env_key, default):
    """Parse integer environment variables safely, handling comments."""
    value = os.getenv(env_key, str(default))
    # Strip any comments (anything after a '#' or spaces)
    if '#' in value:
        value = value.split('#')[0].strip()
    elif ' ' in value:
        value = value.split(' ')[0].strip()
    return int(value)

COMMON_RESPONSES = {
            "menu": "We offer pizzas, pastas, salads and desserts. Our specialties include Margherita Pizza, Seafood Linguine and Tiramisu.",
            "hours": "We're open Tuesday through Sunday from 11am to 10pm. We're closed on Mondays.",
            "delivery": "We deliver within 5 miles for a $3 fee. Typical delivery time is 30-45 minutes.",
            "specials": "Today's specials are Margherita Pizza for $16, Chef's Special Pasta for $22, and Tiramisu for $8.",
            "price": "Pizzas range from $16-20, pastas from $13-22, appetizers from $5-12, and desserts from $6-9.",
            "reservation": "You can make a reservation for any size party. For groups of 5 or more, reservations are required.",
            "payment": "We accept all major credit cards, cash, and digital payment apps.",
            "location": "We're located at 123 Main Street, next to the city park.",
            "wait time": "Current wait time for dine-in is about 15-20 minutes. Delivery orders take 30-45 minutes.",
            "parking": "Free parking is available behind our restaurant.",
            "vegetarian": "We have several vegetarian options including Margherita Pizza, Fettuccine Alfredo, and Caprese Salad.",
            "allergen": "Please let us know about any allergies. We can accommodate most dietary restrictions."
        }

class Settings(BaseSettings):
    # API Keys
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    ANTHROPIC_API_KEY: Optional[str] = os.getenv("ANTHROPIC_API_KEY", "")
   
    
    

    COMMON_RESPONSES: Dict[str, str] = COMMON_RESPONSES
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
    MAX_RETRIES: int = parse_int_env("MAX_RETRIES", 3)
    DEFAULT_MODEL: str = os.getenv("DEFAULT_MODEL", "gpt-3.5-turbo")
    CONVERSATION_MODEL: str = os.getenv("CONVERSATION_MODEL", "gpt-4")
    RESPONSE_TIMEOUT: int = parse_int_env("RESPONSE_TIMEOUT", 5)
    
    # Restaurant Configuration
    RESTAURANT_NAME: str = os.getenv("RESTAURANT_NAME", "Mario's Italian Restaurant")
    RESTAURANT_HOURS: str = os.getenv("RESTAURANT_HOURS", "Tuesday-Sunday, 11am-10pm (closed Mondays)")
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
    
  # Update these prompts in app/config.py

    CONVERSATION_SYSTEM_PROMPT: str = """
        You are an AI assistant for {restaurant_name}. Your name is {restaurant_name} Virtual Assistant.

        VERY IMPORTANT GUIDELINES:
        1. Be extremely concise. Keep all responses under 2 sentences.
        2. Get straight to the point - customers can interrupt at any time.
        3. Never provide unnecessary details unless specifically asked.
        4. Ask only ONE question at a time.
        5. For orders, gather information efficiently: first food items, then delivery/pickup, then name.
        6. Use direct language with no fillers or unnecessary pleasantries.

        Restaurant details:
        - Hours: {restaurant_hours}
        - Delivery: {delivery_radius} miles, ${delivery_fee} fee
        - Reservations needed for parties of {min_reservation_size}+
        - Specials: Margherita Pizza ($16), Chef's Special Pasta ($22), Tiramisu ($8)

        Remember, keep it brief. Customers prefer short, direct responses.
        """
  
    # Also add a version for Urdu
    CONVERSATION_SYSTEM_PROMPT_URDU: str = """
    آپ {restaurant_name} کے لیے ایک AI اسسٹنٹ ہیں۔ آپ کا نام {restaurant_name} ورچوئل اسسٹنٹ ہے۔
    آپ پیشہ ورانہ اور موثر طریقے سے فون آرڈرز اور ریزرویشنز کو سنبھالتے ہیں۔

    ریستوراں کی تفصیلات:
    - اوقات کار: {restaurant_hours}
    - {delivery_radius} میل کے اندر ڈیلیوری دستیاب ہے، ${delivery_fee} ڈیلیوری فیس
    - {min_reservation_size} یا زیادہ افراد کے لیے ریزرویشن کی ضرورت ہے
    - خصوصی پیشکشیں: مارگریٹا پیزا ($16)، شیف کا خصوصی پاستا ($22)، ٹیرامیسو ($8)

    انتہائی اہم رہنما ہدایات:
    1. انتہائی مختصر اور بات پر آئیں۔ جب ممکن ہو تو 2 جملوں تک جوابات رکھیں۔
    2. گاہک کو سننے کو ترجیح دیں۔ انہیں گفتگو کی قیادت کرنے دیں۔
    3. جب تک خاص طور پر نہ پوچھا جائے، غیر ضروری وضاحتیں یا اضافی تفصیلات نہ دیں۔
    4. گفتگو کو مرکوز رکھنے کے لیے ایک وقت میں صرف ایک سوال پوچھیں۔
    5. آرڈرز کے لیے: گاہک کا نام، کھانے کی اشیاء، اور ڈیلیوری/پک اپ کی ترجیح موثر طریقے سے حاصل کریں۔
    6. براہ راست زبان استعمال کریں۔ کوئی بھرنے والے یا غیر ضروری تعارفات نہیں۔

    یاد رکھیں کہ گاہک کسی بھی وقت آپ کو روک سکتا ہے، لہذا سب سے پہلے سب سے اہم معلومات پہنچائیں۔
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

# Format the Urdu system prompt with restaurant details
settings.CONVERSATION_SYSTEM_PROMPT_URDU = settings.CONVERSATION_SYSTEM_PROMPT_URDU.format(
    restaurant_name=settings.RESTAURANT_NAME,
    restaurant_hours=settings.RESTAURANT_HOURS,
    delivery_radius=settings.DELIVERY_RADIUS,
    delivery_fee=settings.DELIVERY_FEE,
    min_reservation_size=settings.MIN_RESERVATION_SIZE
)