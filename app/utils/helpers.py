import re
from datetime import datetime
import logging
import json
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

def parse_phone_number(phone_number: str) -> str:
    """
    Normalize phone number format.
    
    Args:
        phone_number (str): Input phone number in any format
        
    Returns:
        str: Normalized E.164 format phone number
    """
    if not phone_number:
        return ""
    
    # Remove all non-numeric characters
    digits_only = re.sub(r'\D', '', phone_number)
    
    # Ensure it starts with a "+" if it doesn't already
    if not phone_number.startswith('+'):
        # If it's a US number without country code (10 digits)
        if len(digits_only) == 10:
            return f"+1{digits_only}"
        # If it already has the country code
        elif len(digits_only) > 10:
            return f"+{digits_only}"
    
    # Return original number format if it already had "+"
    return phone_number

def parse_datetime(datetime_str: Optional[str]) -> Optional[datetime]:
    """
    Parse datetime string to datetime object.
    
    Args:
        datetime_str (str): Datetime string in various formats
        
    Returns:
        datetime: Parsed datetime object or None
    """
    if not datetime_str:
        return None
    
    formats_to_try = [
        "%Y-%m-%dT%H:%M:%S.%fZ",  # ISO format with milliseconds and Z
        "%Y-%m-%dT%H:%M:%SZ",     # ISO format with Z
        "%Y-%m-%dT%H:%M:%S",      # ISO format without timezone
        "%Y-%m-%d %H:%M:%S",      # Standard format
        "%Y-%m-%d %H:%M",         # Without seconds
        "%Y-%m-%d",               # Date only
        "%m/%d/%Y %H:%M:%S",      # US format with time
        "%m/%d/%Y",               # US format date only
    ]
    
    for fmt in formats_to_try:
        try:
            return datetime.strptime(datetime_str, fmt)
        except ValueError:
            continue
    
    logger.warning(f"Could not parse datetime string: {datetime_str}")
    return None

def calculate_order_total(order_items: List[Dict[str, Any]], menu_items: Dict[str, int], delivery_fee: int = 0) -> int:
    """
    Calculate total order cost in cents.
    
    Args:
        order_items (List[Dict]): List of ordered items with quantity
        menu_items (Dict): Dictionary of menu items with prices
        delivery_fee (int): Delivery fee in cents
        
    Returns:
        int: Total order cost in cents
    """
    total = 0
    
    for item in order_items:
        item_name = item.get("item", "").lower()
        quantity = item.get("quantity", 1)
        
        # Try to find the price, defaulting to 1000 cents if unknown
        price = menu_items.get(item_name, 1000)
        total += price * quantity
    
    # Add delivery fee if any
    total += delivery_fee
    
    return total

def safe_json_loads(json_str: str, default: Any = None) -> Any:
    """
    Safely load JSON string, returning default value on error.
    
    Args:
        json_str (str): JSON string to parse
        default (Any): Default value to return on error
        
    Returns:
        Any: Parsed JSON or default value
    """
    if not json_str:
        return default
        
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {str(e)}")
        return default

def truncate_conversation_for_context(conversation_history: List[Dict[str, str]], max_turns: int = 10) -> List[Dict[str, str]]:
    """
    Truncate conversation history to the most recent turns for context window management.
    
    Args:
        conversation_history (List[Dict]): Full conversation history
        max_turns (int): Maximum number of turns to keep
        
    Returns:
        List[Dict]: Truncated conversation history
    """
    if len(conversation_history) <= max_turns:
        return conversation_history
        
    # Keep the most recent turns
    return conversation_history[-max_turns:]

def format_currency(amount_cents: int) -> str:
    """
    Format cents amount as a dollar string.
    
    Args:
        amount_cents (int): Amount in cents
        
    Returns:
        str: Formatted dollar amount
    """
    dollars = amount_cents / 100
    return f"${dollars:.2f}"

def get_call_duration_str(seconds: int) -> str:
    """
    Format call duration in seconds to a readable string.
    
    Args:
        seconds (int): Duration in seconds
        
    Returns:
        str: Formatted duration string
    """
    if seconds < 60:
        return f"{seconds} seconds"
    
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''}, {seconds} second{'s' if seconds != 1 else ''}"
    
    hours, minutes = divmod(minutes, 60)
    return f"{hours} hour{'s' if hours != 1 else ''}, {minutes} minute{'s' if minutes != 1 else ''}"