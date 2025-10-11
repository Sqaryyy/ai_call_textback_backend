# app/schemas/__init__.py
from .webhook_events import (
    TwilioCallWebhook,
    TwilioSMSWebhook,
    TwilioStatusCallback
)

from .task_payloads import (
    ProcessCallPayload,
    ProcessSMSPayload,
    SendSMSPayload,
    BookAppointmentPayload,
    CleanupPayload
)

from .conversation_dto import (
    ConversationStatus,
    MessageRole,
    ConversationFlowState,
    MessageDTO,
    ConversationDTO,
    ConversationStateUpdate
)

from .openai_schemas import (
    OpenAIRole,
    FunctionCallType,
    OpenAIMessage,
    OpenAIChatRequest,
    OpenAIChatResponse,
    BusinessContext,
    AvailabilityRequest
)

from .calendar_events import (
    CalendarProvider,
    AppointmentStatus,
    TimeSlot,
    AvailabilityResponse,
    AppointmentRequest,
    AppointmentResponse,
    CalendarCredentials,
    BusinessHours,
    BusinessProfile,
    PhoneNumberValidator,
    CorrelationIdMixin,
    TimestampMixin
)