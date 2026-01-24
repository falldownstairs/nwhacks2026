# agents/gatekeeper.py
"""
Input Gatekeeper - Sanitization and Intent Classification Layer.
This lightweight pre-processor runs BEFORE hitting expensive LLM APIs.

Features:
1. Prompt injection detection and sanitization
2. Intent classification (Health_Check, Casual_Chat, Emergency, Out_of_Scope)
3. Quick routing to skip unnecessary API calls
"""

import re
from enum import Enum
from typing import Any, Dict, Optional, Tuple

from .fallback_responses import (HARDCODED_EMERGENCY_CONTACT,
                                 OUT_OF_SCOPE_RESPONSE,
                                 PROMPT_INJECTION_RESPONSE)


class Intent(Enum):
    """Classification of user intent."""
    HEALTH_CHECK = "health_check"      # Discussing symptoms, feelings, vitals
    CASUAL_CHAT = "casual_chat"        # Small talk, greetings
    EMERGENCY = "emergency"            # Urgent health concerns
    OUT_OF_SCOPE = "out_of_scope"      # Non-health topics
    UNKNOWN = "unknown"                # Cannot classify


class GatekeeperResult:
    """Result of gatekeeper processing."""
    
    def __init__(
        self,
        is_safe: bool,
        sanitized_text: str,
        intent: Intent,
        should_bypass_llm: bool = False,
        bypass_response: Optional[Dict[str, Any]] = None,
        flags: Optional[Dict[str, bool]] = None
    ):
        self.is_safe = is_safe
        self.sanitized_text = sanitized_text
        self.intent = intent
        self.should_bypass_llm = should_bypass_llm
        self.bypass_response = bypass_response
        self.flags = flags or {}


# =============================================================================
# PROMPT INJECTION PATTERNS - Things that should NEVER reach the LLM
# =============================================================================

INJECTION_PATTERNS = [
    # Direct instruction override attempts
    r"ignore (?:all )?(?:previous |prior )?instructions?",
    r"disregard (?:all )?(?:previous |prior )?(?:instructions?|prompts?)",
    r"forget (?:everything|all|your) (?:instructions?|training|rules)",
    r"you are now",
    r"act as (?:a |an )?(?:different|new)",
    r"pretend (?:to be|you are)",
    r"your new (?:role|instructions?|purpose)",
    r"system prompt",
    r"reveal your (?:instructions?|prompt|system)",
    r"what (?:are|were) your (?:instructions?|rules)",
    
    # Code/system exploitation
    r"```.*(?:python|javascript|bash|sql|exec|eval)",
    r"<script",
    r"import\s+os",
    r"subprocess\.",
    r"__.*__",  # Python dunders
    
    # SQL injection patterns (unlikely but defensive)
    r";\s*(?:drop|delete|truncate|update|insert)",
    r"'\s*(?:or|and)\s*'?\d*'?\s*=",
]

# Compiled patterns for efficiency
_INJECTION_REGEX = re.compile(
    "|".join(INJECTION_PATTERNS),
    re.IGNORECASE | re.DOTALL
)


# =============================================================================
# INTENT CLASSIFICATION KEYWORDS
# =============================================================================

EMERGENCY_KEYWORDS = [
    "chest pain", "can't breathe", "cannot breathe", "heart attack",
    "stroke", "unconscious", "passing out", "fainted", "fainting",
    "severe pain", "bleeding heavily", "can't move", "paralyzed",
    "suicide", "kill myself", "want to die", "end my life",
    "overdose", "took too many", "poisoned", "allergic reaction",
    "choking", "can't swallow", "throat closing"
]

HEALTH_KEYWORDS = [
    # Symptoms
    "feel", "feeling", "felt", "pain", "ache", "hurt", "sore",
    "tired", "fatigue", "exhausted", "weak", "dizzy", "nauseous",
    "headache", "migraine", "fever", "chills", "cough", "cold",
    "anxious", "stressed", "depressed", "worried", "scared",
    "sleep", "insomnia", "nightmare", "restless",
    
    # Body parts
    "head", "chest", "stomach", "back", "neck", "arm", "leg",
    "heart", "breathing", "throat", "eye", "ear",
    
    # Health actions
    "medicine", "medication", "pill", "doctor", "appointment",
    "exercise", "workout", "walk", "diet", "eating", "drinking",
    "blood pressure", "heart rate", "vitals", "temperature",
    
    # Wellness
    "better", "worse", "same", "improving", "okay", "not okay",
    "good", "bad", "terrible", "great", "fine"
]

CASUAL_KEYWORDS = [
    "hello", "hi", "hey", "good morning", "good afternoon", "good evening",
    "how are you", "what's up", "thanks", "thank you", "bye", "goodbye",
    "yes", "no", "maybe", "sure", "okay", "ok", "alright"
]

OUT_OF_SCOPE_KEYWORDS = [
    # Creative writing
    "write me a", "compose", "poem", "story", "essay", "song",
    
    # Code/tech unrelated to health
    "code", "programming", "javascript", "python", "algorithm",
    "website", "app", "software",
    
    # General knowledge
    "capital of", "who invented", "what year", "history of",
    "recipe for", "how to cook", "weather",
    
    # Entertainment
    "movie", "game", "sports score", "celebrity", "gossip",
    "joke", "riddle", "trivia"
]


def _contains_keywords(text: str, keywords: list) -> bool:
    """Check if text contains any of the keywords (case-insensitive)."""
    text_lower = text.lower()
    return any(kw in text_lower for kw in keywords)


def _count_keyword_matches(text: str, keywords: list) -> int:
    """Count how many keywords match (for weighted classification)."""
    text_lower = text.lower()
    return sum(1 for kw in keywords if kw in text_lower)


# =============================================================================
# MAIN GATEKEEPER FUNCTIONS
# =============================================================================

def sanitize_input(text: str) -> Tuple[str, bool]:
    """
    Sanitize user input by removing potentially dangerous content.
    
    Returns:
        Tuple of (sanitized_text, was_modified)
    """
    if not text:
        return "", False
    
    original = text
    
    # Remove null bytes and control characters (except newlines/tabs)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    
    # Remove excessive whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    
    # Truncate extremely long inputs (prevent token bombing)
    MAX_INPUT_LENGTH = 1000
    if len(text) > MAX_INPUT_LENGTH:
        text = text[:MAX_INPUT_LENGTH] + "..."
    
    return text, text != original


def detect_injection(text: str) -> bool:
    """
    Detect potential prompt injection attempts.
    
    Returns:
        True if injection pattern detected
    """
    if not text:
        return False
    
    return bool(_INJECTION_REGEX.search(text))


def classify_intent(text: str) -> Intent:
    """
    Classify user intent using keyword matching.
    Fast, local classification - no API calls.
    
    Returns:
        Intent enum value
    """
    if not text:
        return Intent.UNKNOWN
    
    text_lower = text.lower()
    
    # Emergency takes highest priority
    if _contains_keywords(text, EMERGENCY_KEYWORDS):
        return Intent.EMERGENCY
    
    # Count matches for weighted decision
    health_score = _count_keyword_matches(text, HEALTH_KEYWORDS)
    casual_score = _count_keyword_matches(text, CASUAL_KEYWORDS)
    out_of_scope_score = _count_keyword_matches(text, OUT_OF_SCOPE_KEYWORDS)
    
    # Short messages are likely casual
    if len(text.split()) <= 3:
        if casual_score > 0:
            return Intent.CASUAL_CHAT
        if health_score > 0:
            return Intent.HEALTH_CHECK
        return Intent.CASUAL_CHAT  # Default short messages to casual
    
    # Determine by highest score
    scores = {
        Intent.HEALTH_CHECK: health_score,
        Intent.CASUAL_CHAT: casual_score,
        Intent.OUT_OF_SCOPE: out_of_scope_score
    }
    
    max_intent = max(scores, key=scores.get)
    max_score = scores[max_intent]
    
    # If no clear signal, default to health context (we're a health app)
    if max_score == 0:
        return Intent.HEALTH_CHECK
    
    # Require higher threshold for out_of_scope to avoid false positives
    if max_intent == Intent.OUT_OF_SCOPE and out_of_scope_score < 2:
        return Intent.HEALTH_CHECK
    
    return max_intent


def process_input(text: str) -> GatekeeperResult:
    """
    Main gatekeeper function - sanitize and classify input.
    
    This is the single entry point for all user input processing.
    
    Returns:
        GatekeeperResult with sanitized text, intent, and routing decision
    """
    # Step 1: Sanitize
    sanitized, was_modified = sanitize_input(text)
    
    flags = {
        "was_sanitized": was_modified,
        "was_truncated": len(text) > 1000 if text else False
    }
    
    # Step 2: Check for injection
    if detect_injection(sanitized):
        return GatekeeperResult(
            is_safe=False,
            sanitized_text=sanitized,
            intent=Intent.UNKNOWN,
            should_bypass_llm=True,
            bypass_response=PROMPT_INJECTION_RESPONSE,
            flags={**flags, "injection_detected": True}
        )
    
    # Step 3: Classify intent
    intent = classify_intent(sanitized)
    
    # Step 4: Determine routing
    if intent == Intent.EMERGENCY:
        # Emergency: Let LLM handle, but flag for clinical alert
        return GatekeeperResult(
            is_safe=True,
            sanitized_text=sanitized,
            intent=intent,
            should_bypass_llm=False,  # LLM should respond empathetically
            flags={**flags, "emergency_flagged": True}
        )
    
    if intent == Intent.OUT_OF_SCOPE:
        # Out of scope: Return hardcoded refusal, save API tokens
        return GatekeeperResult(
            is_safe=True,
            sanitized_text=sanitized,
            intent=intent,
            should_bypass_llm=True,
            bypass_response=OUT_OF_SCOPE_RESPONSE,
            flags=flags
        )
    
    # Health check or casual chat: Process normally
    return GatekeeperResult(
        is_safe=True,
        sanitized_text=sanitized,
        intent=intent,
        should_bypass_llm=False,
        flags=flags
    )


def is_distressed(text: str) -> bool:
    """
    Quick check if user message indicates distress.
    Used by sentiment fallback when LLM is unavailable.
    
    Returns:
        True if negative/distressed sentiment detected
    """
    DISTRESS_INDICATORS = [
        "help", "scared", "afraid", "worried", "anxious", "panic",
        "pain", "hurt", "can't", "cannot", "struggling", "terrible",
        "awful", "horrible", "worst", "emergency", "please",
        "dying", "die", "dead", "bad", "worse", "suffering"
    ]
    
    if not text:
        return False
    
    text_lower = text.lower()
    distress_count = sum(1 for word in DISTRESS_INDICATORS if word in text_lower)
    
    # Also check for exclamation marks and question marks (urgency indicators)
    urgency_marks = text.count('!') + text.count('?')
    
    return distress_count >= 2 or (distress_count >= 1 and urgency_marks >= 2)
