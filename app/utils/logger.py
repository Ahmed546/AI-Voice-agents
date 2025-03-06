import logging
import logging.handlers
import os
import json
from datetime import datetime
from pythonjsonlogger import jsonlogger

from app.config import settings

class CustomJsonFormatter(jsonlogger.JsonFormatter):
    """Custom JSON formatter for structured logging."""
    def add_fields(self, log_record, record, message_dict):
        super(CustomJsonFormatter, self).add_fields(log_record, record, message_dict)
        
        # Add timestamp
        log_record['timestamp'] = datetime.utcnow().isoformat()
        log_record['level'] = record.levelname
        log_record['service'] = 'restaurant-voice-agent'
        log_record['environment'] = settings.ENVIRONMENT

def setup_logging():
    """Configure application logging."""
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    
    # Create logs directory if it doesn't exist
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    
    # Create root logger
    logger = logging.getLogger()
    logger.setLevel(log_level)
    
    # Clear existing handlers
    logger.handlers = []
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    
    # File handler with rotation
    log_file = os.path.join(log_dir, 'voice_agent.log')
    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=10485760, backupCount=10
    )
    file_handler.setLevel(log_level)
    
    # Format based on environment
    if settings.ENVIRONMENT == 'production':
        # JSON formatter for structured logging in production
        formatter = CustomJsonFormatter('%(timestamp)s %(level)s %(name)s %(message)s')
        console_handler.setFormatter(formatter)
        file_handler.setFormatter(formatter)
    else:
        # More readable format for development
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(name)s - %(message)s'
        )
        console_handler.setFormatter(formatter)
        file_handler.setFormatter(formatter)
    
    # Add handlers to logger
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    
    # Suppress noisy loggers
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)
    
    logger.info(f"Logging setup complete. Level: {settings.LOG_LEVEL}")
    
    return logger