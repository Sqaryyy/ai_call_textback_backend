"""
Base Agent - Shared configuration and utilities for all agents
"""

from agents import Agent
from typing import Dict, Any, List, Callable
import json


class BaseAgent:
    """
    Base class for creating configured agents.
    Provides common functionality and context building.
    """

    @staticmethod
    def build_business_context_prompt(business_context: Dict[str, Any]) -> str:
        """
        Build a formatted business context section for agent instructions.

        Args:
            business_context: Business configuration and details

        Returns:
            Formatted string with business context
        """
        business_name = business_context.get("business_name", "our business")
        business_type = business_context.get("business_type", "business")
        business_info = business_context.get("business_info", "")
        ai_instructions = business_context.get("ai_instructions", "")

        context_parts = [
            f"BUSINESS: {business_name}",
            f"TYPE: {business_type}",
        ]

        if business_info:
            context_parts.append(f"ABOUT: {business_info}")

        if ai_instructions:
            context_parts.append(f"\nSPECIAL INSTRUCTIONS:\n{ai_instructions}")

        # Add services if available
        service_catalog = business_context.get("service_catalog", {})
        if service_catalog:
            services = list(service_catalog.keys())
            context_parts.append(f"\nAVAILABLE SERVICES: {', '.join(services)}")

        # Add business hours if available
        business_hours = business_context.get("business_hours", {})
        if business_hours:
            context_parts.append(f"\nBUSINESS HOURS: {json.dumps(business_hours)}")

        # Add booking policies if available
        booking_policies = business_context.get("booking_policies", {})
        if booking_policies:
            context_parts.append(f"\nBOOKING POLICIES: {json.dumps(booking_policies)}")

        return "\n".join(context_parts)

    @staticmethod
    def build_conversation_context_prompt(conversation_context: Dict[str, Any],
                                          require_customer_info: bool = False) -> str:
        """
        Build conversation context - optionally flag missing customer info.

        Args:
            conversation_context: Current conversation state
            require_customer_info: If True, highlight missing name/email
        """
        flow_state = conversation_context.get("flow_state", "gathering_info")
        customer_info = conversation_context.get("customer_info", {})

        context_parts = [
            f"CONVERSATION STATE: {flow_state}",
        ]

        if customer_info:
            context_parts.append(f"KNOWN CUSTOMER INFO: {json.dumps(customer_info)}")

        # Only flag missing info if explicitly requested (for booking flows)
        if require_customer_info:
            has_name = bool(customer_info.get("name"))
            has_email = bool(customer_info.get("email"))

            missing = []
            if not has_name:
                missing.append("name")
            if not has_email:
                missing.append("email")

            if missing:
                context_parts.append(f"STILL NEED FOR BOOKING: {', '.join(missing)}")

        return "\n".join(context_parts)
    @staticmethod
    def create_agent(
            name: str,
            instructions: str,
            tools: List[Callable] = None,
            handoffs: List[Agent] = None,
            model: str = "gpt-4o-mini"
    ) -> Agent:
        """
        Create a configured agent instance.

        Args:
            name: Agent name
            instructions: System instructions for the agent
            tools: List of function tools the agent can use
            handoffs: List of agents this agent can hand off to
            model: OpenAI model to use

        Returns:
            Configured Agent instance
        """
        return Agent(
            name=name,
            instructions=instructions,
            tools=tools or [],
            handoffs=handoffs or [],
            model=model
        )

    @staticmethod
    def get_base_instructions() -> str:
        """
        Get common instructions that apply to all agents.

        Returns:
            Base instruction string
        """
        return """You are a professional AI assistant helping customers interact with a business.

    CORE GUIDELINES:
    - Be friendly, professional, and concise
    - Use natural, conversational language
    - Always confirm important details before taking action
    - If you're uncertain, ask clarifying questions
    - Use available tools to provide accurate information
    - Never make up information - use tools or state you don't know

    COMMUNICATION STYLE:
    - Keep responses brief and to the point
    - Use plain text only - no markdown, bold, asterisks, bullets, or formatting
    - Acknowledge customer emotions and concerns
    """