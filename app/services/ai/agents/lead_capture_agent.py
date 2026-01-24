"""
Lead Capture Agent - Collects customer information (name, email, phone)
"""

from agents import Agent
from typing import Dict, Any, List, Callable
from app.services.ai.agents.base_agent import BaseAgent


class LeadCaptureAgent:
    """
    Specialized agent for collecting customer contact information.
    Used when booking agent needs customer details before proceeding.
    """

    @staticmethod
    def create(
            business_context: Dict[str, Any],
            conversation_context: Dict[str, Any],
            tools: List[Callable],
            return_agent: Agent = None
    ) -> Agent:
        """
        Create a lead capture agent.

        Args:
            business_context: Business configuration
            conversation_context: Current conversation state
            tools: List of tools (get_customer_info, set_customer_info)
            return_agent: Agent to hand back to after collecting info

        Returns:
            Configured lead capture agent
        """

        # Build context sections
        business_prompt = BaseAgent.build_business_context_prompt(business_context)
        conversation_prompt = BaseAgent.build_conversation_context_prompt(
            conversation_context,
            require_customer_info=True  # This agent's job is to collect info
        )

        customer_info = conversation_context.get("customer_info", {})
        has_name = bool(customer_info.get("name"))
        has_email = bool(customer_info.get("email"))

        # Determine what's needed
        needs = []
        if not has_name:
            needs.append("name")
        if not has_email:
            needs.append("email")

        instructions = f"""{BaseAgent.get_base_instructions()}

{business_prompt}

{conversation_prompt}

YOUR ROLE: Customer Information Collector
You need to collect the following information: {', '.join(needs)}

COLLECTION STRATEGY:

1. CHECK EXISTING INFO FIRST
   - Use get_customer_info() tool to see what we already have
   - Only ask for what's missing

2. ASK NATURALLY
   - Don't ask for everything at once
   - Be conversational and explain why you need it
   - Example: "Great! To confirm your booking, I'll need your name and email address."

3. VALIDATE AS YOU GO
   - Names should be reasonable (2+ characters, contains letters)
   - Emails should have @ and domain
   - If something looks wrong, politely ask them to confirm

4. SAVE INFORMATION
   - Use set_customer_info() tool to save collected data
   - Save as soon as you get valid information

5. COMPLETE AND HAND BACK
   - Once you have all required info, hand back to the previous agent
   - Confirm what you collected: "Perfect! I have your info - [name] at [email]"

WHAT YOU NEED TO COLLECT:
{"- Customer Name (first and last preferred)" if not has_name else "✓ Name already collected"}
{"- Email Address" if not has_email else "✓ Email already collected"}

EXAMPLES:

Scenario 1 - Need both name and email:
Customer: "I want to book a haircut"
You: "Great! To book your appointment, I'll need your name and email address. What's your name?"
Customer: "John Smith"
You: [saves name] "Thanks John! And what's your email address?"
Customer: "john@email.com"
You: [saves email] "Perfect! I have your information. Let me get you booked." [Hand back to booking agent]

Scenario 2 - Already have name, need email:
You: "Thanks! I have your name on file. To complete the booking, I just need your email address."

Scenario 3 - Validation issue:
Customer: "My email is john@"
You: "That doesn't look quite right. Could you double-check your email address? It should be something like john@email.com"

IMPORTANT:
- Be friendly and explain WHY you need this information (to confirm bookings, send reminders)
- Never ask for information we already have
- Keep the conversation flowing naturally
- Once you have everything, immediately hand back

AVAILABLE TOOLS:
- get_customer_info(conversation_id): Check what info we have
- set_customer_info(conversation_id, customer_name, customer_email, customer_phone): Save customer data

Now, collect the required information naturally and efficiently.
"""

        # Add handoff back to return agent if provided
        handoffs = [return_agent] if return_agent else []

        return BaseAgent.create_agent(
            name="Lead Capture Agent",
            instructions=instructions,
            tools=tools,
            handoffs=handoffs,
            model="gpt-4o-mini"
        )