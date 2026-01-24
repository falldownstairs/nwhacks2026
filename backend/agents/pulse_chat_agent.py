# agents/pulse_chat_agent.py
"""
Pulse Chat Agent - Conversational AI for health check-ins using Gemini 2.0 Flash.
This agent acts as a compassionate health companion during vital measurements.

Now with full reliability architecture:
- Input sanitization and intent classification (Gatekeeper)
- Cascading LLM fallbacks (Gemini -> Groq -> VADER -> Hardcoded)
- Never hangs on a patient
"""

import asyncio
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from google import genai
from google.genai import types

from .fallback_responses import (HARDCODED_NEUTRAL_FALLBACK,
                                 ICEBREAKER_QUESTIONS, get_greeting_fallback,
                                 get_icebreaker_question,
                                 get_vital_response_fallback)
# Reliability imports
from .gatekeeper import GatekeeperResult, Intent, process_input
from .llm_client import LLMProvider, ResilientLLMClient, get_llm_client

load_dotenv()

logger = logging.getLogger(__name__)

# Configure Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
client = None
if GEMINI_API_KEY:
    client = genai.Client(api_key=GEMINI_API_KEY)


class PulseChatAgent:
    """
    Conversational AI agent for Pulse health companion.
    Uses Gemini 2.0 Flash for fast, empathetic responses during health check-ins.
    """

    SYSTEM_PROMPT = """You are Pulse, a warm and compassionate AI health companion. Your role is to:

1. SUPPORT patients during their vital sign measurements by engaging in friendly, calming conversation
2. GATHER subjective health context (how they're feeling, symptoms, concerns)
3. PROVIDE empathetic responses that acknowledge their feelings
4. GUIDE them through the measurement process with reassurance

PERSONALITY:
- Warm, caring, and genuinely interested in the patient's wellbeing
- Professional but not clinical - like a friendly nurse
- Patient and understanding
- Encouraging and positive
- Never dismissive of concerns

CONVERSATION GUIDELINES:
- Keep responses concise (2-3 sentences max during measurements)
- Ask open-ended questions about how they're feeling
- Acknowledge emotions and validate concerns
- Use simple, accessible language (no medical jargon)
- Be culturally sensitive and inclusive

CONTEXT AWARENESS:
- You're chatting while their vitals are being measured via camera
- The calibration takes about 30 seconds
- Your job is to make this time valuable by collecting subjective health data
- Tag important health information in your memory

EXAMPLE INTERACTIONS:
User: "I'm feeling tired today"
Pulse: "I hear you - tiredness can be tough. Have you been sleeping okay, or is there something on your mind that's been keeping you up?"

User: "My head hurts"
Pulse: "I'm sorry to hear about your headache. When did it start, and would you describe it as more of a dull ache or a sharp pain?"

User: "I'm stressed about work"
Pulse: "That sounds really challenging. Stress can definitely affect how we feel physically. Take a deep breath with me - you're doing great just by checking in on your health today."

Remember: You're gathering valuable health context while providing emotional support. Every interaction should feel caring and purposeful."""

    def __init__(self, patient_context: Optional[Dict[str, Any]] = None):
        """
        Initialize the chat agent.

        Args:
            patient_context: Optional context about the patient (name, conditions, history)
        """
        self.patient_context = patient_context or {}
        self.conversation_history: List[Dict[str, str]] = []
        self.subjective_data: List[Dict[str, Any]] = []
        self.model = None
        self.chat = None
        
        # Reliability: Get the resilient LLM client
        self.resilient_client: ResilientLLMClient = get_llm_client()
        
        # Icebreaker tracking for calibration phase
        self.icebreaker_index = 0
        self.is_calibrating = True
        
        self._initialize_model()

    def _initialize_model(self):
        """Initialize the Gemini model and chat session."""
        if not GEMINI_API_KEY or not client:
            raise ValueError("GEMINI_API_KEY not found in environment variables")

        # Store the system prompt
        self.system_prompt = self._build_system_prompt()

        # Initialize chat history for the new API
        self.chat_history = []

    def _build_system_prompt(self) -> str:
        """Build the system prompt with patient context."""
        prompt = self.SYSTEM_PROMPT

        if self.patient_context:
            context_parts = ["\n\nPATIENT CONTEXT:"]
            if self.patient_context.get("name"):
                context_parts.append(f"- Patient name: {self.patient_context['name']}")
            if self.patient_context.get("age"):
                context_parts.append(f"- Age: {self.patient_context['age']}")
            if self.patient_context.get("conditions"):
                context_parts.append(
                    f"- Known conditions: {', '.join(self.patient_context['conditions'])}"
                )
            if self.patient_context.get("baseline"):
                baseline = self.patient_context["baseline"]
                context_parts.append(
                    f"- Typical heart rate: {baseline.get('heart_rate', 'unknown')} bpm"
                )

            prompt += "\n".join(context_parts)

        return prompt

    def _send_message(self, message: str) -> str:
        """Send a message to Gemini and get a response using the new API."""
        # Add user message to history
        self.chat_history.append(
            types.Content(role="user", parts=[types.Part.from_text(text=message)])
        )

        # Generate response
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=self.chat_history,
            config=types.GenerateContentConfig(
                system_instruction=self.system_prompt, temperature=0.7
            ),
        )

        response_text = response.text.strip()

        # Add assistant response to history
        self.chat_history.append(
            types.Content(
                role="model", parts=[types.Part.from_text(text=response_text)]
            )
        )

        return response_text

    def get_greeting(self) -> str:
        """Get an initial greeting to start the conversation."""
        patient_name = self.patient_context.get("name", "there")
        first_name = patient_name.split()[0] if patient_name != "there" else "there"

        greeting_prompt = f"""Generate a warm, brief greeting for {first_name} who is starting their health check-in. 
The camera is calibrating their vitals. Ask them how they've been feeling today in a caring way.
Keep it to 2 sentences max."""

        try:
            greeting = self._send_message(greeting_prompt)

            # Store in history
            self.conversation_history.append(
                {
                    "role": "assistant",
                    "content": greeting,
                    "timestamp": datetime.utcnow().isoformat(),
                }
            )

            return greeting
        except Exception as e:
            # Fallback greeting if API fails
            fallback = f"Hi {first_name}! I'm checking your vitals now. While I calibrate, how have you been feeling since this morning?"
            self.conversation_history.append(
                {
                    "role": "assistant",
                    "content": fallback,
                    "timestamp": datetime.utcnow().isoformat(),
                }
            )
            return fallback

    def get_icebreaker(self) -> str:
        """
        Get an icebreaker question during calibration phase.
        Used to mask rPPG latency with meaningful subjective data collection.
        """
        question = get_icebreaker_question(self.icebreaker_index)
        self.icebreaker_index = (self.icebreaker_index + 1) % len(ICEBREAKER_QUESTIONS)
        
        self.conversation_history.append({
            "role": "assistant",
            "content": question,
            "timestamp": datetime.utcnow().isoformat(),
            "type": "icebreaker"
        })
        
        return question

    def set_calibration_complete(self):
        """Mark calibration as complete."""
        self.is_calibrating = False

    async def process_message_resilient(self, user_message: str) -> Dict[str, Any]:
        """
        Process a user message with full reliability pipeline.
        
        Pipeline:
        1. Gatekeeper (sanitize + classify intent)
        2. Bypass LLM for out-of-scope or blocked content
        3. Resilient LLM call (Gemini -> Groq -> VADER -> Hardcoded)
        
        Args:
            user_message: The user's raw message
            
        Returns:
            Dict containing response and metadata
        """
        # Step 1: Gatekeeper
        gatekeeper_result: GatekeeperResult = process_input(user_message)
        
        # Store user message (sanitized)
        self.conversation_history.append({
            "role": "user",
            "content": gatekeeper_result.sanitized_text,
            "timestamp": datetime.utcnow().isoformat(),
            "intent": gatekeeper_result.intent.value,
            "flags": gatekeeper_result.flags
        })
        
        # Step 2: Check if we should bypass LLM
        if gatekeeper_result.should_bypass_llm:
            bypass_msg = gatekeeper_result.bypass_response.get("message", HARDCODED_NEUTRAL_FALLBACK["message"])
            
            self.conversation_history.append({
                "role": "assistant",
                "content": bypass_msg,
                "timestamp": datetime.utcnow().isoformat(),
                "type": "bypass",
                "reason": "blocked" if not gatekeeper_result.is_safe else "out_of_scope"
            })
            
            return {
                "response": bypass_msg,
                "success": True,
                "bypassed_llm": True,
                "intent": gatekeeper_result.intent.value,
                "is_safe": gatekeeper_result.is_safe
            }
        
        # Step 3: Build context-aware prompt
        context_prompt = f"""User said: "{gatekeeper_result.sanitized_text}"

Respond empathetically and briefly (2-3 sentences). If they mention any symptoms, feelings, or health-related information, acknowledge it caringly.

After your response, on a new line starting with "CONTEXT:", briefly note any health-relevant information from their message (symptoms, mood, physical state, concerns). If nothing health-relevant, write "CONTEXT: general check-in"."""
        
        # Step 4: Call resilient LLM
        llm_response = await self.resilient_client.generate(
            prompt=context_prompt,
            system_prompt=self.system_prompt,
            chat_history=[{"role": h["role"], "content": h["content"]} 
                          for h in self.conversation_history[-10:]],  # Last 10 messages for context
            context=self.patient_context
        )
        
        full_response = llm_response.text
        
        # Parse response and context
        if "CONTEXT:" in full_response:
            parts = full_response.split("CONTEXT:")
            ai_response = parts[0].strip()
            context_tag = parts[1].strip() if len(parts) > 1 else "general"
        else:
            ai_response = full_response
            context_tag = "general"
        
        # Store AI response
        self.conversation_history.append({
            "role": "assistant",
            "content": ai_response,
            "timestamp": datetime.utcnow().isoformat(),
            "provider": llm_response.provider.value,
            "fallback_used": llm_response.fallback_used
        })
        
        # Store subjective data
        self.subjective_data.append({
            "user_input": gatekeeper_result.sanitized_text,
            "context_tag": context_tag,
            "timestamp": datetime.utcnow().isoformat(),
            "intent": gatekeeper_result.intent.value
        })
        
        # Flag emergency intent for clinical alert
        should_alert = gatekeeper_result.intent == Intent.EMERGENCY
        if llm_response.metadata.get("should_alert"):
            should_alert = True
        
        return {
            "response": ai_response,
            "context_extracted": context_tag,
            "success": True,
            "intent": gatekeeper_result.intent.value,
            "provider": llm_response.provider.value,
            "fallback_used": llm_response.fallback_used,
            "latency_ms": llm_response.latency_ms,
            "should_alert_clinician": should_alert
        }

    def process_message(self, user_message: str) -> Dict[str, Any]:
        """
        Process a user message and generate a response.

        Args:
            user_message: The user's message

        Returns:
            Dict containing response and extracted context
        """
        # Store user message
        self.conversation_history.append(
            {
                "role": "user",
                "content": user_message,
                "timestamp": datetime.utcnow().isoformat(),
            }
        )

        # Build context-aware prompt
        context_prompt = f"""User said: "{user_message}"

Respond empathetically and briefly (2-3 sentences). If they mention any symptoms, feelings, or health-related information, acknowledge it caringly.

After your response, on a new line starting with "CONTEXT:", briefly note any health-relevant information from their message (symptoms, mood, physical state, concerns). If nothing health-relevant, write "CONTEXT: general check-in"."""

        try:
            full_response = self._send_message(context_prompt)

            # Parse response and context
            if "CONTEXT:" in full_response:
                parts = full_response.split("CONTEXT:")
                ai_response = parts[0].strip()
                context_tag = parts[1].strip() if len(parts) > 1 else "general"
            else:
                ai_response = full_response
                context_tag = "general"

            # Store AI response
            self.conversation_history.append(
                {
                    "role": "assistant",
                    "content": ai_response,
                    "timestamp": datetime.utcnow().isoformat(),
                }
            )

            # Store subjective data
            self.subjective_data.append(
                {
                    "user_input": user_message,
                    "context_tag": context_tag,
                    "timestamp": datetime.utcnow().isoformat(),
                }
            )

            return {
                "response": ai_response,
                "context_extracted": context_tag,
                "success": True,
            }

        except Exception as e:
            error_response = "I'm here with you. Tell me more about how you're feeling."
            self.conversation_history.append(
                {
                    "role": "assistant",
                    "content": error_response,
                    "timestamp": datetime.utcnow().isoformat(),
                }
            )

            return {
                "response": error_response,
                "context_extracted": "error",
                "success": False,
                "error": str(e),
            }

    def get_vital_response(self, heart_rate: float, hrv: float, is_normal: bool) -> str:
        """
        Generate a response after vitals are measured.

        Args:
            heart_rate: Measured heart rate
            hrv: Measured HRV
            is_normal: Whether vitals are within normal range
        """
        # Gather conversation context for better response
        mood_context = self._summarize_subjective_context()

        if is_normal:
            prompt = f"""The patient's vitals just came in:
- Heart rate: {heart_rate} bpm (normal range)
- HRV: {hrv} ms

Their conversation context: {mood_context}

Give a brief, reassuring response (2-3 sentences) acknowledging their good vitals and connecting it to how they said they were feeling. Be warm and encouraging."""
        else:
            prompt = f"""The patient's vitals just came in:
- Heart rate: {heart_rate} bpm (elevated/abnormal)
- HRV: {hrv} ms

Their conversation context: {mood_context}

Give a brief, calm response (2-3 sentences). Don't alarm them, but acknowledge the reading and ask if any of the common causes might apply (recent exercise, caffeine, stress). Be supportive and gentle."""

        try:
            vital_response = self._send_message(prompt)

            # Clean up any CONTEXT: tags that might slip through
            if "CONTEXT:" in vital_response:
                vital_response = vital_response.split("CONTEXT:")[0].strip()

            self.conversation_history.append(
                {
                    "role": "assistant",
                    "content": vital_response,
                    "timestamp": datetime.utcnow().isoformat(),
                    "type": "vital_response",
                }
            )

            return vital_response
        except Exception:
            if is_normal:
                return f"Good news! Your heart rate is {heart_rate} bpm, which looks healthy. Keep taking care of yourself!"
            else:
                return f"I'm seeing your heart rate at {heart_rate} bpm. Have you been active recently, or had any caffeine? Let's take a moment to relax."

    def _summarize_subjective_context(self) -> str:
        """Summarize the subjective context collected during conversation."""
        if not self.subjective_data:
            return "No specific context shared"

        contexts = [
            d["context_tag"]
            for d in self.subjective_data
            if d["context_tag"] != "general"
        ]
        if not contexts:
            return "General check-in, no specific symptoms mentioned"

        return "; ".join(contexts)

    def get_session_summary(self) -> Dict[str, Any]:
        """Get a summary of the chat session for storage."""
        return {
            "conversation_history": self.conversation_history,
            "subjective_data": self.subjective_data,
            "subjective_summary": self._summarize_subjective_context(),
            "message_count": len(
                [m for m in self.conversation_history if m["role"] == "user"]
            ),
            "session_end": datetime.utcnow().isoformat(),
        }


# Convenience function for creating agents
def create_pulse_chat_agent(patient_id: str = None) -> PulseChatAgent:
    """
    Create a new Pulse chat agent, optionally with patient context.

    Args:
        patient_id: Optional patient ID to load context for

    Returns:
        Configured PulseChatAgent instance
    """
    patient_context = None

    if patient_id:
        # Import here to avoid circular imports
        from db_helpers import get_patient

        patient = get_patient(patient_id)
        if patient:
            patient_context = {
                "name": patient.get("name"),
                "age": patient.get("age"),
                "conditions": patient.get("conditions", []),
                "baseline": patient.get("baseline", {}),
            }

    return PulseChatAgent(patient_context=patient_context)
    return PulseChatAgent(patient_context=patient_context)
