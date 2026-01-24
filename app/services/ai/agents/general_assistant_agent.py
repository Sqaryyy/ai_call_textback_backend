"""
General Assistant Agent - Updated with better response formatting instructions
"""

from agents import Agent
from typing import Dict, Any, List, Callable
from app.services.ai.agents.base_agent import BaseAgent


class GeneralAssistantAgent:
    """
    Specialized agent for answering questions and providing business information.
    Handles FAQs, service inquiries, hours, policies, and general support.
    """

    @staticmethod
    def create(
        business_context: Dict[str, Any],
        conversation_context: Dict[str, Any],
        tools: List[Callable],
        booking_agent: Agent = None
    ) -> Agent:
        """
        Create a general assistant agent.

        Args:
            business_context: Business configuration
            conversation_context: Current conversation state
            tools: List of tools (get_services_summary, etc.)
            booking_agent: Agent to hand off to if customer wants to book

        Returns:
            Configured general assistant agent
        """

        # Build context sections
        business_prompt = BaseAgent.build_business_context_prompt(business_context)
        conversation_prompt = BaseAgent.build_conversation_context_prompt(
            conversation_context,
            require_customer_info=False  # Don't pressure for customer info
        )

        # Extract key information for quick reference
        business_name = business_context.get("business_name", "our business")
        business_hours = business_context.get("business_hours", {})
        contact_info = business_context.get("contact_info", {})
        service_catalog = business_context.get("service_catalog", {})
        quick_responses = business_context.get("quick_responses", {})
        booking_policies = business_context.get("booking_policies", {})

        # Build FAQ section if available
        faq_section = ""
        if quick_responses:
            faq_section = "\n\nFREQUENTLY ASKED QUESTIONS:\n"
            for question, answer in quick_responses.items():
                faq_section += f"Q: {question}\nA: {answer}\n\n"

        # Build services section
        services_section = ""
        if service_catalog:
            services_section = "\n\nSERVICES WE OFFER:\n"
            for service_name, service_details in service_catalog.items():
                if isinstance(service_details, dict):
                    price = service_details.get("price", "")
                    duration = service_details.get("duration", "")
                    description = service_details.get("description", "")
                    services_section += f"- {service_name}"
                    if price:
                        services_section += f" (${price})"
                    if duration:
                        services_section += f" - {duration} minutes"
                    if description:
                        services_section += f"\n  {description}"
                    services_section += "\n"
                else:
                    services_section += f"- {service_name}\n"

        # Build hours section
        hours_section = ""
        if business_hours:
            hours_section = "\n\nBUSINESS HOURS:\n"
            for day, hours in business_hours.items():
                if isinstance(hours, dict):
                    if hours.get("closed", False):
                        hours_section += f"{day}: Closed\n"
                    else:
                        hours_section += f"{day}: {hours.get('open', 'N/A')} - {hours.get('close', 'N/A')}\n"
                else:
                    hours_section += f"{day}: {hours}\n"

        # Build contact section
        contact_section = ""
        if contact_info:
            contact_section = "\n\nCONTACT INFORMATION:\n"
            if contact_info.get("phone"):
                contact_section += f"Phone: {contact_info['phone']}\n"
            if contact_info.get("email"):
                contact_section += f"Email: {contact_info['email']}\n"
            if contact_info.get("website"):
                contact_section += f"Website: {contact_info['website']}\n"
            if contact_info.get("address"):
                contact_section += f"Address: {contact_info['address']}\n"

        # Build policies section
        policies_section = ""
        if booking_policies:
            policies_section = "\n\nBOOKING POLICIES:\n"
            if booking_policies.get("cancellation_policy"):
                policies_section += f"Cancellation: {booking_policies['cancellation_policy']}\n"
            if booking_policies.get("cancellation_notice_hours"):
                policies_section += f"Cancellation Notice: {booking_policies['cancellation_notice_hours']} hours\n"
            if booking_policies.get("rescheduling_policy"):
                policies_section += f"Rescheduling: {booking_policies['rescheduling_policy']}\n"
            if booking_policies.get("no_show_policy"):
                policies_section += f"No-Show: {booking_policies['no_show_policy']}\n"

        instructions = f"""{BaseAgent.get_base_instructions()}

{business_prompt}

{conversation_prompt}

YOUR ROLE: Information & Support Specialist
You answer customer questions about {business_name}. Provide helpful, accurate information about services, hours, policies, and general inquiries.

CRITICAL: You have been handed off from the router agent. DO NOT announce this handoff or mention being "reached" or "connected". Simply answer the customer's question directly and naturally.

{services_section}

{hours_section}

{contact_section}

{policies_section}

{faq_section}

WHAT YOU CAN HELP WITH:

1. SERVICE INFORMATION
   - What services are offered
   - Service descriptions, duration, pricing
   - Which service is right for their needs
   - Use get_services_summary() tool only if the info above is insufficient

2. BUSINESS HOURS & LOCATION
   - When the business is open
   - Location/address information
   - Holiday hours
   - Time zone information

3. PRICING & POLICIES
   - Service costs
   - Cancellation policies
   - Booking policies
   - Payment methods

4. GENERAL QUESTIONS
   - "How does it work?"
   - "What should I expect?"
   - "Do you offer X service?"
   - "What's included?"

5. REDIRECTING TO BOOKING
   - If customer wants to book after getting info, offer to help
   - Hand off to Booking Agent when ready

RESPONSE STYLE RULES - CRITICAL:

1. **CONVERSATIONAL & CONCISE**: 
   - Write like you're texting a friend, not writing a formal document
   - Keep responses SHORT - aim for 2-3 sentences max for simple questions
   - NO markdown formatting (**, ###, -, bullets) unless absolutely necessary
   - Use plain, natural language

2. **ANSWER DIRECTLY**:
   - Jump straight to the answer without preamble
   - Don't repeat the question back
   - Don't list out technical fields or data structures
   - Don't format information as if you're reading from a database

3. **WHEN USING TOOLS**:
   - Use tool data to form your answer, don't just dump the data
   - Synthesize information into natural sentences
   - Example: Instead of "**Service**: Interior Design, **Price**: Custom pricing"
   - Say: "We offer interior design with custom pricing based on your project"


IMPORTANT REMINDERS:
- NEVER say "It seems we've reached the general assistant" or "How can I assist you today?"
- Answer the exact question asked, nothing more
- Use the business context sections above FIRST before calling tools
- Only call get_services_summary() if the services section above doesn't have enough detail
- Keep it conversational and brief
- NO structured lists or markdown formatting in responses
- Speak naturally like a helpful team member

AVAILABLE TOOLS:
- get_services_summary(): Get service information (USE SPARINGLY - prefer business context above)

HANDOFF TRIGGER:
If customer expresses intent to book ("I want to book", "Let's schedule", "Can I make an appointment"), hand off to Booking Agent.

Now, help the customer with their questions naturally and concisely!
"""

        # Add handoff to booking agent if provided
        handoffs = [booking_agent] if booking_agent else []

        return BaseAgent.create_agent(
            name="General Assistant Agent",
            instructions=instructions,
            tools=tools,
            handoffs=handoffs,
            model="gpt-4o-mini"
        )