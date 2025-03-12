from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Gather
from tenacity import retry, stop_after_attempt, wait_exponential
import logging
import random

from app.config import settings

logger = logging.getLogger(__name__)

class TwilioService:
    def __init__(self):
        self.client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        self.phone_number = settings.TWILIO_PHONE_NUMBER
        
    def create_language_selection_response(self, message):
        """
        Create a TwiML response for language selection.
        
        Args:
            message (str): The language selection prompt
            
        Returns:
            str: TwiML response as a string
        """
        response = VoiceResponse()
        
        # Add the language selection prompt
        response.say(message, voice='Polly.Joanna-Neural', language="en-US", volume="loud")
        
        # Create a gather for digit input
        gather = Gather(
            action='/api/voice/handle-language',
            num_digits=1,
            timeout=5,
            bargeIn="true"
        )
        response.append(gather)
        
        # If no input is received, repeat the prompt
        response.redirect('/api/voice/incoming')
        
        return str(response)
        
    def create_progressive_response(self, initial_message, voice_language="en-US"):
        """
        Create a response that speaks immediately while processing continues.
        
        Args:
            initial_message (str): Initial immediate response
            voice_language (str): Language for voice response
            
        Returns:
            str: TwiML response as a string
        """
        response = VoiceResponse()
        
        # Select voice based on language
        voice = 'Polly.Joanna-Neural'  # Default voice for English
        if voice_language == "ur-PK":
            voice = 'Polly.Aditi-Neural'
        
        # Say the initial acknowledgment immediately
        response.say(initial_message, voice=voice, language=voice_language, volume="loud")
        
        # Create a gather that will listen immediately
        gather = Gather(
            input='speech dtmf',
            action='/api/webhook/speech',
            timeout=3,
            speech_timeout=1,
            language=voice_language,
            enhanced=True,
            speech_model='phone_call',
            bargeIn="true"
        )
        response.append(gather)
        
        # If no input is received, redirect
        response.redirect('/api/webhook/no-input')
        
        return str(response)
    
    def create_streaming_response(self, message, voice_language="en-US"):
        """
        Create a TwiML response that breaks long messages into chunks.
        
        Args:
            message (str): The full message to deliver in chunks
            voice_language (str): Language for voice response
            
        Returns:
            str: TwiML response as a string
        """
        response = VoiceResponse()
        
        # Select voice based on language
        voice = 'Polly.Joanna-Neural'  # Default voice for English
        if voice_language == "ur-PK":
            voice = 'Polly.Aditi-Neural'
        
        # Break message into sentences
        sentences = message.split('. ')
        
        # Only speak the first sentence or a short portion initially
        if sentences and len(sentences) > 0:
            first_part = sentences[0] + '.'
            
            # Speak just the first sentence
            response.say(first_part, voice=voice, language=voice_language, volume="loud")
            
            # Create Gather with responsive settings
            gather = Gather(
                input='speech dtmf',
                action='/api/webhook/speech',
                timeout=2,  # Short timeout
                speech_timeout=1,
                language=voice_language,
                enhanced=True,
                speech_model='phone_call',
                bargeIn="true"
            )
            
            # Add the remainder of the message to the gather
            # This ensures it won't be spoken if the user interrupts
            if len(sentences) > 1:
                remaining = '. '.join(sentences[1:])
                if remaining and not remaining.endswith('.'):
                    remaining += '.'
                gather.say(remaining, voice=voice, language=voice_language, volume="loud")
            
            response.append(gather)
            
            # If no input is received, redirect
            response.redirect('/api/webhook/no-input')
        else:
            # Fallback for empty messages
            response.say("How can I help you?", voice=voice, language=voice_language, volume="loud")
            
            gather = Gather(
                input='speech dtmf',
                action='/api/webhook/speech',
                timeout=2,
                speech_timeout=1,
                language=voice_language,
                enhanced=True,
                speech_model='phone_call',
                bargeIn="true"
            )
            response.append(gather)
            response.redirect('/api/webhook/no-input')
        
        return str(response)
        
    def create_twiml_response(self, message, gather_speech=True, timeout=2, speech_timeout=1, voice_language="en-US"):
        """
        Create a TwiML response with the specified message.
        
        Args:
            message (str): The message to be spoken by the bot
            gather_speech (bool): Whether to gather speech input after speaking
            timeout (int): How long to wait for user input
            speech_timeout (int): Speech timeout setting
            voice_language (str): The language for voice response
            
        Returns:
            str: TwiML response as a string
        """
        # Use the streaming response method which handles chunking
        return self.create_streaming_response(message, voice_language)
    
    def create_transfer_to_human_response(self, message=None, voice_language="en-US"):
        """Create a TwiML response that transfers to a human."""
        response = VoiceResponse()
        
        # Select appropriate voice based on language
        voice = 'Polly.Joanna-Neural'  # Default voice for English
        if voice_language == "ur-PK":
            voice = 'Polly.Aditi-Neural'  # Use an Indian voice as closest to Urdu
        
        if message:
            response.say(message, voice=voice, language=voice_language, volume="loud")
            response.pause(length=1)
            
        # Transfer message depends on language
        transfer_msg = "Transferring you to one of our staff. Please hold."
        if voice_language == "ur-PK":
            transfer_msg = "آپ کو ہمارے عملے کے ایک رکن سے منسلک کیا جا رہا ہے۔ براہ کرم انتظار کریں۔"
            
        response.say(transfer_msg, voice=voice, language=voice_language, volume="loud")
        
        # Example: Transfer to a specific phone number
        # response.dial("+1234567890")
        
        # Example: Transfer to a queue
        # response.enqueue("restaurant_staff")
        
        return str(response)
    
    def create_goodbye_response(self, message, voice_language="en-US"):
        """Create a TwiML response for ending the call."""
        response = VoiceResponse()
        
        # Select appropriate voice based on language
        voice = 'Polly.Joanna-Neural'  # Default voice for English
        if voice_language == "ur-PK":
            voice = 'Polly.Aditi-Neural'  # Use an Indian voice as closest to Urdu
            
        response.say(message, voice=voice, language=voice_language, volume="loud")
        response.hangup()
        return str(response)
        
    def create_thinking_response(self, voice_language="en-US"):
        """Create a response with thinking sounds to bridge processing time."""
        response = VoiceResponse()
        
        # Select appropriate voice based on language
        voice = 'Polly.Joanna-Neural'  # Default voice for English
        if voice_language == "ur-PK":
            voice = 'Polly.Aditi-Neural'
        
        # Choose a random thinking phrase
        thinking_phrases = [
            "Let me check that for you.",
            "Just a moment.",
            "Looking that up now."
        ]
        if voice_language == "ur-PK":
            thinking_phrases = [
                "میں آپ کے لیے چیک کر رہا ہوں۔",
                "بس ایک لمحے۔",
                "ابھی دیکھ رہا ہوں۔"
            ]
        
        thinking_phrase = random.choice(thinking_phrases)
        
        # Say the thinking phrase
        response.say(thinking_phrase, voice=voice, language=voice_language, volume="loud")
        
        # Add a pause to simulate thinking
        response.pause(length=1)
        
        # Redirect to continue processing
        response.redirect('/api/webhook/complete-processing')
        
        return str(response)
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def make_call(self, to_number, webhook_url=None):
        """
        Initiate an outbound call using Twilio.
        
        Args:
            to_number (str): The phone number to call
            webhook_url (str, optional): Custom webhook URL. Defaults to settings.TWILIO_WEBHOOK_URL.
            
        Returns:
            str: The SID of the initiated call
        """
        if not webhook_url:
            webhook_url = settings.TWILIO_WEBHOOK_URL
            
        try:
            call = self.client.calls.create(
                to=to_number,
                from_=self.phone_number,
                url=webhook_url,
                status_callback=f"{webhook_url}/status",
                status_callback_event=['initiated', 'ringing', 'answered', 'completed'],
                status_callback_method='POST'
            )
            logger.info(f"Initiated call to {to_number}, SID: {call.sid}")
            return call.sid
        except Exception as e:
            logger.error(f"Failed to initiate call to {to_number}: {str(e)}")
            raise
    
    def get_call_info(self, call_sid):
        """
        Get information about a specific call.
        
        Args:
            call_sid (str): The SID of the call
            
        Returns:
            dict: Call information
        """
        try:
            call = self.client.calls(call_sid).fetch()
            return {
                'sid': call.sid,
                'status': call.status,
                'direction': call.direction,
                'duration': call.duration,
                'from': call.from_,
                'to': call.to,
                'start_time': call.start_time,
                'end_time': call.end_time
            }
        except Exception as e:
            logger.error(f"Failed to get call info for SID {call_sid}: {str(e)}")
            return None
    
    def end_call(self, call_sid):
        """
        End an in-progress call.
        
        Args:
            call_sid (str): The SID of the call to end
            
        Returns:
            bool: Success status
        """
        try:
            self.client.calls(call_sid).update(status="completed")
            logger.info(f"Ended call with SID {call_sid}")
            return True
        except Exception as e:
            logger.error(f"Failed to end call with SID {call_sid}: {str(e)}")
            return False

# Create a singleton instance
twilio_service = TwilioService()