from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Gather
from tenacity import retry, stop_after_attempt, wait_exponential
import logging

from app.config import settings

logger = logging.getLogger(__name__)

class TwilioService:
    def __init__(self):
        self.client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        self.phone_number = settings.TWILIO_PHONE_NUMBER
        
    def create_twiml_response(self, message, gather_speech=True, timeout=3, speech_timeout="auto"):
        """
        Create a TwiML response with the specified message.
        
        Args:
            message (str): The message to be spoken by the bot
            gather_speech (bool): Whether to gather speech input after speaking
            timeout (int): How long to wait for user input
            speech_timeout (str): Speech timeout setting ("auto" or duration in seconds)
            
        Returns:
            str: TwiML response as a string
        """
        response = VoiceResponse()
        
        # Add the AI's message
        response.say(message, voice='Polly.Joanna')
        
        # If we want to gather speech response
        if gather_speech:
            gather = Gather(
                input='speech',
                action='/api/webhook/speech',
                timeout=timeout,
                speech_timeout=speech_timeout,
                language='en-US',
                enhanced=True,  # Use enhanced speech recognition when available
                speech_model='phone_call'  # Optimized for phone calls
            )
            response.append(gather)
            
            # If no input is received, retry
            response.redirect('/api/webhook/no-input')
        
        return str(response)
    
    def create_transfer_to_human_response(self, message=None):
        """Create a TwiML response that transfers to a human."""
        response = VoiceResponse()
        
        if message:
            response.say(message, voice='Polly.Joanna')
            response.pause(length=1)
            
        # Replace with your actual human transfer logic
        # This could be a Dial to a specific person or queue
        response.say("Transferring you to one of our staff. Please hold.", voice='Polly.Joanna')
        
        # Example: Transfer to a specific phone number
        # response.dial("+1234567890")
        
        # Example: Transfer to a queue
        # response.enqueue("restaurant_staff")
        
        return str(response)
    
    def create_goodbye_response(self, message):
        """Create a TwiML response for ending the call."""
        response = VoiceResponse()
        response.say(message, voice='Polly.Joanna')
        response.hangup()
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