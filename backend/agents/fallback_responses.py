# agents/fallback_responses.py
"""
Centralized fallback responses for Pulsera health companion.
These hardcoded responses ensure the system NEVER leaves a patient hanging,
even during total API failure.
"""

from enum import Enum
from typing import Any, Dict


class RiskLevel(Enum):
    """Risk classification levels."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    UNKNOWN = "UNKNOWN"


class SessionState(Enum):
    """Current state of the health session."""
    CALIBRATING = "calibrating"
    ACTIVE = "active"
    DEGRADED = "degraded"
    VOICE_ONLY = "voice_only"
    EMERGENCY = "emergency"


# =============================================================================
# TIER 3 FALLBACKS - Hardcoded responses when ALL AI systems fail
# =============================================================================

HARDCODED_EMERGENCY_CONTACT = {
    "type": "emergency_fallback",
    "message": "I'm having trouble processing right now, but I hear that you may be in distress. Please contact a human caregiver or call emergency services if you need immediate help.",
    "action": "show_emergency_contacts",
    "ui_card": "emergency_contact",
    "should_alert_clinician": True
}

HARDCODED_MAINTENANCE_MSG = {
    "type": "maintenance_fallback", 
    "message": "I'm calibrating my systems. Please hold on for just a moment - I'll be right with you.",
    "action": "show_loading",
    "ui_card": None,
    "should_alert_clinician": False
}

HARDCODED_NEUTRAL_FALLBACK = {
    "type": "neutral_fallback",
    "message": "I'm here with you. Tell me more about how you're feeling today.",
    "action": None,
    "ui_card": None,
    "should_alert_clinician": False
}

# =============================================================================
# GREETING FALLBACKS - When initial greeting generation fails
# =============================================================================

def get_greeting_fallback(patient_name: str = "there", is_calibrating: bool = True) -> str:
    """Get a safe greeting when AI greeting fails."""
    first_name = patient_name.split()[0] if patient_name != "there" else "there"
    
    if is_calibrating:
        return f"Hi {first_name}! I'm checking your vitals now. While I calibrate, how have you been feeling since this morning?"
    else:
        return f"Hello {first_name}! It's good to see you. How are you feeling today?"


# =============================================================================
# VITAL RESPONSE FALLBACKS - Based on measured heart rate
# =============================================================================

def get_vital_response_fallback(
    heart_rate: float,
    hrv: float = None,
    patient_name: str = "there"
) -> Dict[str, Any]:
    """
    Get a safe vital response when AI fails.
    Uses simple threshold logic to provide appropriate response.
    """
    first_name = patient_name.split()[0] if patient_name != "there" else "there"
    
    # Simple threshold-based classification
    if 60 <= heart_rate <= 100:
        # Normal range
        return {
            "risk_level": RiskLevel.LOW.value,
            "message": f"Good news, {first_name}! Your heart rate is {int(heart_rate)} bpm, which looks healthy. Keep taking care of yourself!",
            "action": None,
            "should_follow_up": False
        }
    elif heart_rate < 60:
        # Low (could be athletic or concerning)
        return {
            "risk_level": RiskLevel.MEDIUM.value,
            "message": f"I'm seeing your heart rate at {int(heart_rate)} bpm, which is a bit low. Are you feeling lightheaded or dizzy at all?",
            "action": "ask_followup",
            "should_follow_up": True
        }
    elif 100 < heart_rate <= 120:
        # Elevated
        return {
            "risk_level": RiskLevel.MEDIUM.value,
            "message": f"I'm seeing your heart rate at {int(heart_rate)} bpm. Have you been active recently, or had any caffeine? Let's take a moment to relax together.",
            "action": "breathing_exercise",
            "should_follow_up": True
        }
    else:
        # High (>120)
        return {
            "risk_level": RiskLevel.HIGH.value,
            "message": f"Your heart rate is reading at {int(heart_rate)} bpm, which is elevated. Are you experiencing any chest pain or shortness of breath?",
            "action": "clinical_alert",
            "should_follow_up": True,
            "should_alert_clinician": True
        }


# =============================================================================
# ICEBREAKER QUESTIONS - Used during calibration to mask latency
# =============================================================================

ICEBREAKER_QUESTIONS = [
    "How did you sleep last night?",
    "Have you been drinking enough water today?",
    "How's your energy level feeling right now?",
    "Have you had any discomfort or pain today?",
    "What's been on your mind lately?",
    "Did you eat breakfast this morning?",
    "How would you rate your stress level today, from 1 to 10?",
    "Have you been able to get any movement or exercise in?",
]

def get_icebreaker_question(index: int = 0) -> str:
    """Get an icebreaker question for calibration phase."""
    return ICEBREAKER_QUESTIONS[index % len(ICEBREAKER_QUESTIONS)]


# =============================================================================
# CLINICAL REASONING FALLBACKS - For orchestrator agents
# =============================================================================

CLINICAL_REASONING_FALLBACKS = {
    RiskLevel.LOW.value: "Based on the available vital signs, values appear within normal physiological ranges. No immediate concerns identified. Routine monitoring recommended.",
    RiskLevel.MEDIUM.value: "Vital signs show some deviation from expected baseline. This could be due to temporary factors (stress, caffeine, activity) or may warrant closer observation. Recommend follow-up questions to assess context.",
    RiskLevel.HIGH.value: "Significant deviation detected in vital signs. While this may have benign causes, clinical review is advised. Patient should be asked about symptoms and recent activities. Consider escalation protocol.",
    RiskLevel.UNKNOWN.value: "Unable to complete full analysis. Recommend manual review of vital signs and patient check-in."
}

PATIENT_EXPLANATION_FALLBACKS = {
    RiskLevel.LOW.value: "Great news! Your vitals look healthy today. Keep up whatever you're doing - it's working!",
    RiskLevel.MEDIUM.value: "Your readings are a little different than usual. This isn't necessarily a concern, but let's keep an eye on things. How have you been feeling?",
    RiskLevel.HIGH.value: "I noticed some changes in your readings that I'd like to flag for your care team. Don't worry - this is just to make sure you get the attention you need. How are you feeling right now?",
    RiskLevel.UNKNOWN.value: "We couldn't complete the full analysis right now. Please try again, or contact your care team if you have any concerns."
}


# =============================================================================
# SENSOR FAILURE MESSAGES
# =============================================================================

SENSOR_MESSAGES = {
    "roi_failed": "I'm having trouble seeing you clearly. Could you please move to an area with better lighting?",
    "face_not_detected": "I can't quite see your face. Could you adjust your camera so I can see you better?",
    "calibration_failed": "The calibration didn't complete successfully. Let's try again - please stay still for a moment.",
    "voice_only_mode": "I'm switching to voice-only mode. I can still chat with you, but won't be able to measure your vitals right now.",
    "camera_unavailable": "I can't access your camera right now. Would you like to continue with just a voice check-in?"
}


# =============================================================================
# OUT OF SCOPE RESPONSES - When user asks non-health questions
# =============================================================================

OUT_OF_SCOPE_RESPONSE = {
    "message": "I'm your health companion, so I'm best at helping with health-related questions. Is there anything about how you're feeling that I can help with?",
    "action": None,
    "redirect": True
}

PROMPT_INJECTION_RESPONSE = {
    "message": "I'm here to help with your health check-in. How are you feeling today?",
    "action": "log_security_event",
    "blocked": True
}


# =============================================================================
# TRIAGE CONTINUATION MESSAGES
# =============================================================================

def get_triage_greeting(is_abnormal: bool, heart_rate: float = None) -> str:
    """Get greeting for triage continuation after check-in."""
    if is_abnormal and heart_rate:
        return f"I noticed your heart rate was {int(heart_rate)} bpm during our check-in. I'd like to ask you a few questions to better understand what might be going on. Is that okay?"
    else:
        return "Thanks for completing your check-in! I have a few follow-up questions to help me understand your health better. Ready?"


# =============================================================================
# JSON RESPONSE BUILDERS
# =============================================================================

def build_error_response(
    error_type: str = "unknown",
    user_message: str = None,
    should_retry: bool = True
) -> Dict[str, Any]:
    """Build a standardized error response."""
    return {
        "success": False,
        "error_type": error_type,
        "message": user_message or HARDCODED_NEUTRAL_FALLBACK["message"],
        "should_retry": should_retry,
        "fallback_used": True
    }

def build_degraded_response(
    message: str,
    risk_level: str = RiskLevel.UNKNOWN.value,
    data_available: Dict[str, bool] = None
) -> Dict[str, Any]:
    """Build a response indicating degraded service."""
    return {
        "success": True,
        "degraded": True,
        "message": message,
        "risk_level": risk_level,
        "data_available": data_available or {
            "vitals": False,
            "ai_analysis": False,
            "voice": True
        }
    }
