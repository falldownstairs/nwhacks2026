# agents/health_data_chat_agent.py
"""
Health Data Chat Agent - Conversational AI for answering questions about patient health data.
This agent has access to the patient's vitals history, trends, and can provide insights.

Now with full reliability architecture:
- Input sanitization and intent classification (Gatekeeper)
- Cascading LLM fallbacks (Gemini -> Groq -> VADER -> Hardcoded)
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from google import genai
from google.genai import types

from .fallback_responses import HARDCODED_NEUTRAL_FALLBACK
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


class HealthDataChatAgent:
    """
    Conversational AI agent for answering questions about patient health data.
    Uses Gemini 2.0 Flash with access to patient vitals history and trends.
    """

    SYSTEM_PROMPT = """You are Pulse, a knowledgeable and caring AI health companion. Your role is to:

1. ANSWER questions about the patient's health data, vitals, and trends
2. EXPLAIN what their numbers mean in simple, accessible terms
3. IDENTIFY patterns and provide insights from their data
4. OFFER lifestyle suggestions based on their trends
5. SUPPORT their health journey with encouragement

PERSONALITY:
- Warm, caring, and genuinely interested in the patient's wellbeing
- Knowledgeable but explains things simply - no medical jargon
- Encouraging and positive about health progress
- Honest but gentle about concerning trends
- Never alarmist - always provide context

CAPABILITIES:
- You have access to the patient's vitals history (heart rate, HRV)
- You can see their baseline values and recent trends
- You can identify patterns over days/weeks
- You understand what normal ranges look like

GUIDELINES:
- Keep responses conversational and friendly (2-4 sentences for simple questions)
- For data questions, reference specific numbers when helpful
- Explain trends in relatable terms ("Your heart rate has been a bit higher this week...")
- Never diagnose conditions - suggest they speak with their doctor for medical advice
- Celebrate improvements and provide gentle encouragement

EXAMPLE INTERACTIONS:
User: "How has my heart rate been?"
Pulse: "Your heart rate has been pretty steady this week, averaging around 72 bpm. That's right in your healthy baseline range! On Tuesday it was a bit higher at 78, but that's completely normal day-to-day variation."

User: "Is my HRV good?"
Pulse: "Your HRV is at 42ms, which is solid! HRV measures how adaptable your heart is to stress. Higher is generally better, and yours has actually improved by about 5% compared to last week. Keep up whatever you're doing!"

User: "Should I be worried about anything?"
Pulse: "Looking at your recent data, everything looks reassuring. Your vitals are consistent with your baseline, and I'm not seeing any concerning patterns. That said, I'm an AI assistant - for any specific health concerns, it's always best to chat with your doctor."

Remember: You're a supportive companion helping patients understand their health data, not a medical professional giving diagnoses."""

    def __init__(self, patient_context: Optional[Dict[str, Any]] = None, vitals_data: Optional[Dict[str, Any]] = None):
        """
        Initialize the health data chat agent.

        Args:
            patient_context: Context about the patient (name, conditions, baseline)
            vitals_data: Patient's vitals history and statistics
        """
        self.patient_context = patient_context or {}
        self.vitals_data = vitals_data or {}
        self.conversation_history: List[Dict[str, str]] = []
        self.chat_history = []
        
        # Reliability: Get the resilient LLM client
        self.resilient_client: ResilientLLMClient = get_llm_client()
        
        self._initialize_model()

    def _initialize_model(self):
        """Initialize the Gemini model."""
        if not GEMINI_API_KEY or not client:
            raise ValueError("GEMINI_API_KEY not found in environment variables")

        self.system_prompt = self._build_system_prompt()

    def _build_system_prompt(self) -> str:
        """Build the system prompt with patient context and data."""
        prompt = self.SYSTEM_PROMPT

        # Add patient context
        context_parts = ["\n\n=== PATIENT INFORMATION ==="]
        
        if self.patient_context:
            if self.patient_context.get("name"):
                context_parts.append(f"Name: {self.patient_context['name']}")
            if self.patient_context.get("age"):
                context_parts.append(f"Age: {self.patient_context['age']}")
            if self.patient_context.get("conditions"):
                context_parts.append(f"Health conditions: {', '.join(self.patient_context['conditions'])}")
            if self.patient_context.get("baseline"):
                baseline = self.patient_context["baseline"]
                context_parts.append(f"Baseline heart rate: {baseline.get('heart_rate', 'unknown')} bpm")
                context_parts.append(f"Baseline HRV: {baseline.get('hrv', 'unknown')} ms")

        # Add vitals data summary
        if self.vitals_data:
            context_parts.append("\n=== RECENT VITALS DATA ===")
            
            if self.vitals_data.get("stats"):
                stats = self.vitals_data["stats"]
                context_parts.append(f"7-day average heart rate: {stats.get('avg_hr', 'N/A'):.1f} bpm")
                context_parts.append(f"7-day average HRV: {stats.get('avg_hrv', 'N/A'):.1f} ms")
                context_parts.append(f"Heart rate range: {stats.get('min_hr', 'N/A')} - {stats.get('max_hr', 'N/A')} bpm")
                context_parts.append(f"HRV range: {stats.get('min_hrv', 'N/A')} - {stats.get('max_hrv', 'N/A')} ms")
                context_parts.append(f"Number of measurements: {stats.get('count', 0)}")
            
            if self.vitals_data.get("latest"):
                latest = self.vitals_data["latest"]
                context_parts.append(f"\nMost recent reading:")
                context_parts.append(f"  Heart rate: {latest.get('heart_rate', 'N/A')} bpm")
                context_parts.append(f"  HRV: {latest.get('hrv', 'N/A')} ms")
                if latest.get("timestamp"):
                    context_parts.append(f"  Recorded: {latest['timestamp']}")
            
            if self.vitals_data.get("recent_vitals"):
                context_parts.append(f"\nRecent daily readings (last 7 days):")
                for vital in self.vitals_data["recent_vitals"][-7:]:
                    ts = vital.get("timestamp", "")
                    if isinstance(ts, datetime):
                        ts = ts.strftime("%a %m/%d")
                    hr = vital.get("heart_rate", "N/A")
                    hrv = vital.get("hrv", "N/A")
                    context_parts.append(f"  {ts}: HR {hr} bpm, HRV {hrv} ms")
            
            if self.vitals_data.get("trend"):
                trend = self.vitals_data["trend"]
                context_parts.append(f"\nTrends:")
                context_parts.append(f"  Heart rate trend: {trend.get('hr_trend', 'stable')}")
                context_parts.append(f"  HRV trend: {trend.get('hrv_trend', 'stable')}")

        prompt += "\n".join(context_parts)
        return prompt

    def _send_message(self, message: str) -> str:
        """Send a message to Gemini and get a response."""
        self.chat_history.append(
            types.Content(role="user", parts=[types.Part.from_text(text=message)])
        )

        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=self.chat_history,
            config=types.GenerateContentConfig(
                system_instruction=self.system_prompt, 
                temperature=0.7
            ),
        )

        response_text = response.text.strip()

        self.chat_history.append(
            types.Content(
                role="model", parts=[types.Part.from_text(text=response_text)]
            )
        )

        return response_text

    def get_greeting(self) -> str:
        """Get an initial greeting."""
        patient_name = self.patient_context.get("name", "there")
        first_name = patient_name.split()[0] if patient_name != "there" else "there"

        # Include some context in greeting
        has_data = bool(self.vitals_data.get("recent_vitals"))
        
        if has_data:
            greeting_prompt = f"""Generate a warm, brief greeting for {first_name}. 
You have access to their health data and can help answer questions about their vitals, trends, or general health questions.
Mention that you can see their recent data and invite them to ask anything.
Keep it to 2 sentences max. Be friendly and approachable."""
        else:
            greeting_prompt = f"""Generate a warm, brief greeting for {first_name}.
Let them know you're here to help with health questions, though you don't have much data yet.
Encourage them to do a check-in to start tracking.
Keep it to 2 sentences max."""

        try:
            greeting = self._send_message(greeting_prompt)
            self.conversation_history.append({
                "role": "assistant",
                "content": greeting,
                "timestamp": datetime.utcnow().isoformat(),
            })
            return greeting
        except Exception as e:
            fallback = f"Hi {first_name}! I'm here to help you understand your health data. Feel free to ask me anything about your vitals or trends!"
            return fallback

    def process_message(self, user_message: str) -> Dict[str, Any]:
        """
        Process a user message and generate a response.

        Args:
            user_message: The user's message

        Returns:
            Dict containing response
        """
        self.conversation_history.append({
            "role": "user",
            "content": user_message,
            "timestamp": datetime.utcnow().isoformat(),
        })

        try:
            response = self._send_message(user_message)

            self.conversation_history.append({
                "role": "assistant",
                "content": response,
                "timestamp": datetime.utcnow().isoformat(),
            })

            return {
                "response": response,
                "success": True,
            }

        except Exception as e:
            error_response = "I'd love to help! Could you rephrase your question?"
            self.conversation_history.append({
                "role": "assistant",
                "content": error_response,
                "timestamp": datetime.utcnow().isoformat(),
            })

            return {
                "response": error_response,
                "success": False,
                "error": str(e),
            }

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
        })
        
        # Step 2: Check if we should bypass LLM
        if gatekeeper_result.should_bypass_llm:
            bypass_msg = gatekeeper_result.bypass_response.get("message", HARDCODED_NEUTRAL_FALLBACK["message"])
            
            self.conversation_history.append({
                "role": "assistant",
                "content": bypass_msg,
                "timestamp": datetime.utcnow().isoformat(),
                "type": "bypass"
            })
            
            return {
                "response": bypass_msg,
                "success": True,
                "bypassed_llm": True,
                "intent": gatekeeper_result.intent.value,
                "is_safe": gatekeeper_result.is_safe
            }
        
        # Step 3: Call resilient LLM with vitals context
        llm_response = await self.resilient_client.generate(
            prompt=gatekeeper_result.sanitized_text,
            system_prompt=self.system_prompt,
            chat_history=[{"role": h["role"], "content": h["content"]} 
                          for h in self.conversation_history[-10:]],
            context={**self.patient_context, "vitals": self.vitals_data}
        )
        
        response_text = llm_response.text
        
        # Store AI response
        self.conversation_history.append({
            "role": "assistant",
            "content": response_text,
            "timestamp": datetime.utcnow().isoformat(),
            "provider": llm_response.provider.value,
            "fallback_used": llm_response.fallback_used
        })
        
        return {
            "response": response_text,
            "success": True,
            "intent": gatekeeper_result.intent.value,
            "provider": llm_response.provider.value,
            "fallback_used": llm_response.fallback_used,
            "latency_ms": llm_response.latency_ms
        }

    def update_vitals_data(self, vitals_data: Dict[str, Any]):
        """Update the agent's vitals data context."""
        self.vitals_data = vitals_data
        self.system_prompt = self._build_system_prompt()

    def get_session_summary(self) -> Dict[str, Any]:
        """Get a summary of the chat session."""
        return {
            "conversation_history": self.conversation_history,
            "message_count": len([m for m in self.conversation_history if m["role"] == "user"]),
            "session_end": datetime.utcnow().isoformat(),
        }


def create_health_data_chat_agent(patient_id: str = None) -> HealthDataChatAgent:
    """
    Create a new Health Data chat agent with patient context and vitals.

    Args:
        patient_id: Patient ID to load context and data for

    Returns:
        Configured HealthDataChatAgent instance
    """
    patient_context = None
    vitals_data = None

    if patient_id:
        from db_helpers import calculate_stats, get_patient, get_recent_vitals

        # Get patient info
        patient = get_patient(patient_id)
        if patient:
            patient_context = {
                "name": patient.get("name"),
                "age": patient.get("age"),
                "conditions": patient.get("conditions", []),
                "baseline": patient.get("baseline", {}),
            }

        # Get vitals data
        recent_vitals = get_recent_vitals(patient_id, days=14)
        stats = calculate_stats(patient_id, days=7)
        
        vitals_data = {
            "recent_vitals": recent_vitals,
            "stats": stats,
            "latest": recent_vitals[-1] if recent_vitals else None,
        }
        
        # Calculate simple trend
        if len(recent_vitals) >= 3:
            recent_hrs = [v["heart_rate"] for v in recent_vitals[-3:]]
            older_hrs = [v["heart_rate"] for v in recent_vitals[:3]] if len(recent_vitals) >= 6 else recent_hrs
            
            recent_hrvs = [v["hrv"] for v in recent_vitals[-3:]]
            older_hrvs = [v["hrv"] for v in recent_vitals[:3]] if len(recent_vitals) >= 6 else recent_hrvs
            
            hr_diff = sum(recent_hrs)/len(recent_hrs) - sum(older_hrs)/len(older_hrs)
            hrv_diff = sum(recent_hrvs)/len(recent_hrvs) - sum(older_hrvs)/len(older_hrvs)
            
            hr_trend = "increasing" if hr_diff > 3 else "decreasing" if hr_diff < -3 else "stable"
            hrv_trend = "improving" if hrv_diff > 2 else "declining" if hrv_diff < -2 else "stable"
            
            vitals_data["trend"] = {
                "hr_trend": hr_trend,
                "hrv_trend": hrv_trend,
            }

    return HealthDataChatAgent(patient_context=patient_context, vitals_data=vitals_data)
