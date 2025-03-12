import re
import random
import logging
import hashlib
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

class SpeechEnhancementService:
    """Service for making AI speech more human-like."""
    
    def __init__(self):
        """Initialize the speech enhancement service."""
        self.response_cache = {}
        self.max_cache_size = 100
    
    def add_fillers(self, text: str) -> str:
        """Add human-like filler phrases to text."""
        # List of simpler filler phrases without SSML
        fillers = [
            "Umm, ",
            "Let's see. ",
            "Hmm, ",
            "Well, ",
            "So, ",
            "You know, "
        ]
        
        # Don't add fillers to very short responses
        if len(text) < 50:
            return text
        
        # Split text into sentences
        sentences = re.split(r'(?<=[.!?])\s+', text)
        
        # Insert filler at 1-2 random positions for longer responses
        if len(sentences) > 2:
            # Pick 1-2 random positions for insertion
            num_fillers = min(2, len(sentences) - 1)
            positions = random.sample(range(1, len(sentences)), num_fillers)
            
            # Insert fillers at chosen positions
            for pos in sorted(positions, reverse=True):
                filler = random.choice(fillers)
                sentences.insert(pos, filler)
        
        # Rejoin text
        return " ".join(sentences)
    
    def add_thinking_pauses(self, text: str) -> str:
        """Add natural thinking pauses to text."""
        # Simply add a pause after sentences instead of using SSML
        text = re.sub(r'\.(?=\s+[A-Z])', '. ', text)
        return text
    
    def cache_response(self, query: str, response: str) -> None:
        """Cache a response for future use."""
        # Create a hash key from the query
        key = hashlib.md5(query.lower().strip().encode()).hexdigest()
        
        # If cache is full, remove a random item
        if len(self.response_cache) >= self.max_cache_size:
            random_key = random.choice(list(self.response_cache.keys()))
            del self.response_cache[random_key]
        
        # Add to cache
        self.response_cache[key] = response
    
    def get_cached_response(self, query: str) -> Optional[str]:
        """Get a cached response if available."""
        key = hashlib.md5(query.lower().strip().encode()).hexdigest()
        return self.response_cache.get(key)
    
    def enhance_speech(self, text: str) -> str:
        """Apply all speech enhancements."""
        text = self.add_fillers(text)
        text = self.add_thinking_pauses(text)
        return text

# Create a singleton instance
speech_enhancement_service = SpeechEnhancementService()