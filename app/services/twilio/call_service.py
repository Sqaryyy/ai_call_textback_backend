# app/services/twilio/call_service.py - Enhanced
class CallService:
    def create_forward_twiml(self, forwarding_number: str, timeout: int = 30):
        """Generate TwiML to forward call"""
        return f"""
        <Response>
            <Dial timeout="{timeout}" action="/webhooks/call/result">
                <Number>{forwarding_number}</Number>
            </Dial>
        </Response>
        """

    def create_fallback_twiml(self, message: str):
        """Generate TwiML for missed call message"""
        return f"""
        <Response>
            <Say voice="alice">{message}</Say>
            <Hangup/>
        </Response>
        """