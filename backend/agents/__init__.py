# agents/__init__.py
from .health_data_chat_agent import (HealthDataChatAgent,
                                     create_health_data_chat_agent)
from .orchestrator import run_agent_analysis
from .pulse_chat_agent import PulseChatAgent, create_pulse_chat_agent
from .speech_to_text import get_stt_client, transcribe_audio, transcribe_base64
from .text_to_speech import synthesize_speech, synthesize_speech_streaming

# Reliability modules
from .gatekeeper import process_input, Intent, GatekeeperResult, is_distressed
from .llm_client import get_llm_client, ResilientLLMClient, LLMProvider, LLMResponse
from .fallback_responses import (
    HARDCODED_EMERGENCY_CONTACT,
    HARDCODED_MAINTENANCE_MSG,
    HARDCODED_NEUTRAL_FALLBACK,
    SENSOR_MESSAGES,
    get_greeting_fallback,
    get_vital_response_fallback,
    get_icebreaker_question,
    RiskLevel,
)

__all__ = [
    "run_agent_analysis",
    "PulseChatAgent",
    "create_pulse_chat_agent",
    "HealthDataChatAgent",
    "create_health_data_chat_agent",
    "transcribe_audio",
    "transcribe_base64",
    "get_stt_client",
    "synthesize_speech",
    "synthesize_speech_streaming",
    # Reliability exports
    "process_input",
    "Intent",
    "GatekeeperResult",
    "is_distressed",
    "get_llm_client",
    "ResilientLLMClient",
    "LLMProvider",
    "LLMResponse",
    "HARDCODED_EMERGENCY_CONTACT",
    "HARDCODED_MAINTENANCE_MSG",
    "HARDCODED_NEUTRAL_FALLBACK",
    "SENSOR_MESSAGES",
    "get_greeting_fallback",
    "get_vital_response_fallback",
    "get_icebreaker_question",
    "RiskLevel",
]
