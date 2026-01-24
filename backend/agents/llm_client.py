# agents/llm_client.py
"""
Resilient LLM Client - Cascading fallback architecture for Pulsera.

Implements the "Intelligence Cascade" from the reliability spec:
1. Primary: Gemini Pro/Flash (main LLM)
2. Fallback Tier 1: Groq with openai/gpt-oss-120b (3s timeout on primary)
3. Fallback Tier 2: Local VADER sentiment analysis
4. Fallback Tier 3: Hardcoded emergency responses

This ensures Pulsera NEVER hangs on a patient, even during total API failure.
"""

import asyncio
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import httpx
from dotenv import load_dotenv

# Conditional import for VADER sentiment
try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    VADER_AVAILABLE = True
except ImportError:
    VADER_AVAILABLE = False

# Google Gemini imports
try:
    from google import genai
    from google.genai import types
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

from .fallback_responses import (HARDCODED_EMERGENCY_CONTACT,
                                 HARDCODED_MAINTENANCE_MSG,
                                 HARDCODED_NEUTRAL_FALLBACK, RiskLevel,
                                 get_greeting_fallback,
                                 get_vital_response_fallback)
from .gatekeeper import is_distressed

load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)

# API Keys
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"


class LLMProvider(Enum):
    """Available LLM providers."""
    GEMINI_FLASH = "gemini_flash"
    GROQ = "groq"
    LOCAL_SENTIMENT = "local_sentiment"
    HARDCODED = "hardcoded"


@dataclass
class LLMResponse:
    """Standardized response from any LLM provider."""
    success: bool
    text: str
    provider: LLMProvider
    latency_ms: float
    fallback_used: bool = False
    fallback_reason: Optional[str] = None
    sentiment: Optional[str] = None  # For Tier 2 fallback
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CircuitBreakerState:
    """Track circuit breaker state per provider."""
    failures: int = 0
    last_failure: Optional[datetime] = None
    is_open: bool = False
    
    # Configuration
    failure_threshold: int = 3
    reset_timeout: timedelta = field(default_factory=lambda: timedelta(seconds=30))
    
    def record_failure(self):
        """Record a failure and potentially open the circuit."""
        self.failures += 1
        self.last_failure = datetime.now()
        if self.failures >= self.failure_threshold:
            self.is_open = True
            logger.warning(f"Circuit breaker OPENED after {self.failures} failures")
    
    def record_success(self):
        """Record success and reset the counter."""
        self.failures = 0
        self.is_open = False
    
    def should_allow_request(self) -> bool:
        """Check if request should be allowed."""
        if not self.is_open:
            return True
        
        # Check if reset timeout has passed (half-open state)
        if self.last_failure and datetime.now() - self.last_failure > self.reset_timeout:
            logger.info("Circuit breaker entering HALF-OPEN state")
            return True
        
        return False


class ResilientLLMClient:
    """
    Resilient LLM client with automatic failover.
    
    Usage:
        client = ResilientLLMClient()
        response = await client.generate(
            prompt="How are you feeling?",
            system_prompt="You are a health companion.",
            context={"patient_name": "John"}
        )
    """
    
    # Timeouts in seconds
    GEMINI_TIMEOUT = 5.0      # Primary timeout
    GROQ_TIMEOUT = 8.0        # Fallback timeout (slightly longer)
    
    def __init__(self):
        """Initialize the resilient LLM client."""
        self.gemini_client = None
        self.vader_analyzer = None
        
        # Circuit breakers per provider
        self.circuit_breakers: Dict[LLMProvider, CircuitBreakerState] = {
            LLMProvider.GEMINI_FLASH: CircuitBreakerState(),
            LLMProvider.GROQ: CircuitBreakerState(),
        }
        
        # Initialize Gemini client
        if GEMINI_AVAILABLE and GEMINI_API_KEY:
            try:
                self.gemini_client = genai.Client(api_key=GEMINI_API_KEY)
                logger.info("Gemini client initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Gemini client: {e}")
        
        # Initialize VADER sentiment analyzer
        if VADER_AVAILABLE:
            try:
                self.vader_analyzer = SentimentIntensityAnalyzer()
                logger.info("VADER sentiment analyzer initialized")
            except Exception as e:
                logger.error(f"Failed to initialize VADER: {e}")
    
    async def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        chat_history: Optional[List[Dict[str, str]]] = None,
        context: Optional[Dict[str, Any]] = None,
        temperature: float = 0.7,
        max_tokens: int = 500
    ) -> LLMResponse:
        """
        Generate a response using the cascading fallback architecture.
        
        Args:
            prompt: User message
            system_prompt: System instructions
            chat_history: Previous messages in the conversation
            context: Additional context (patient info, vitals, etc.)
            temperature: LLM temperature
            max_tokens: Maximum tokens in response
            
        Returns:
            LLMResponse with text and metadata about which provider was used
        """
        start_time = datetime.now()
        chat_history = chat_history or []
        context = context or {}
        
        # TIER 1: Try Gemini Flash (Primary)
        if self._should_try_provider(LLMProvider.GEMINI_FLASH):
            try:
                response = await self._call_gemini(
                    prompt, system_prompt, chat_history, temperature
                )
                if response:
                    self.circuit_breakers[LLMProvider.GEMINI_FLASH].record_success()
                    latency = (datetime.now() - start_time).total_seconds() * 1000
                    return LLMResponse(
                        success=True,
                        text=response,
                        provider=LLMProvider.GEMINI_FLASH,
                        latency_ms=latency,
                        fallback_used=False
                    )
            except asyncio.TimeoutError:
                logger.warning(f"Gemini timed out after {self.GEMINI_TIMEOUT}s")
                self.circuit_breakers[LLMProvider.GEMINI_FLASH].record_failure()
            except Exception as e:
                logger.error(f"Gemini error: {e}")
                self.circuit_breakers[LLMProvider.GEMINI_FLASH].record_failure()
        
        # TIER 1.5: Try Groq with openai/gpt-oss-120b
        if self._should_try_provider(LLMProvider.GROQ):
            try:
                response = await self._call_groq(
                    prompt, system_prompt, chat_history, temperature, max_tokens
                )
                if response:
                    self.circuit_breakers[LLMProvider.GROQ].record_success()
                    latency = (datetime.now() - start_time).total_seconds() * 1000
                    return LLMResponse(
                        success=True,
                        text=response,
                        provider=LLMProvider.GROQ,
                        latency_ms=latency,
                        fallback_used=True,
                        fallback_reason="gemini_unavailable"
                    )
            except asyncio.TimeoutError:
                logger.warning(f"Groq timed out after {self.GROQ_TIMEOUT}s")
                self.circuit_breakers[LLMProvider.GROQ].record_failure()
            except Exception as e:
                logger.error(f"Groq error: {e}")
                self.circuit_breakers[LLMProvider.GROQ].record_failure()
        
        # TIER 2: Local Sentiment Analysis
        sentiment_result = self._analyze_sentiment(prompt)
        latency = (datetime.now() - start_time).total_seconds() * 1000
        
        if sentiment_result["is_distressed"]:
            # User is distressed - return empathetic emergency message
            return LLMResponse(
                success=True,
                text=HARDCODED_EMERGENCY_CONTACT["message"],
                provider=LLMProvider.LOCAL_SENTIMENT,
                latency_ms=latency,
                fallback_used=True,
                fallback_reason="all_llm_unavailable",
                sentiment="negative",
                metadata={"should_alert": True, "sentiment_scores": sentiment_result["scores"]}
            )
        
        # TIER 3: Hardcoded neutral fallback
        return LLMResponse(
            success=True,
            text=HARDCODED_NEUTRAL_FALLBACK["message"],
            provider=LLMProvider.HARDCODED,
            latency_ms=latency,
            fallback_used=True,
            fallback_reason="all_llm_unavailable",
            sentiment="neutral",
            metadata={"sentiment_scores": sentiment_result["scores"]}
        )
    
    def _should_try_provider(self, provider: LLMProvider) -> bool:
        """Check if we should try a specific provider."""
        if provider == LLMProvider.GEMINI_FLASH:
            if not self.gemini_client:
                return False
        elif provider == LLMProvider.GROQ:
            if not GROQ_API_KEY:
                return False
        
        # Check circuit breaker
        if provider in self.circuit_breakers:
            return self.circuit_breakers[provider].should_allow_request()
        
        return True
    
    async def _call_gemini(
        self,
        prompt: str,
        system_prompt: str,
        chat_history: List[Dict[str, str]],
        temperature: float
    ) -> Optional[str]:
        """Call Gemini Flash API with timeout."""
        if not self.gemini_client:
            return None
        
        # Build conversation history for Gemini
        contents = []
        for msg in chat_history:
            role = "user" if msg.get("role") == "user" else "model"
            contents.append(
                types.Content(
                    role=role,
                    parts=[types.Part.from_text(text=msg.get("content", ""))]
                )
            )
        
        # Add current prompt
        contents.append(
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=prompt)]
            )
        )
        
        # Make the call with timeout
        async def _gemini_call():
            response = self.gemini_client.models.generate_content(
                model="gemini-2.0-flash",
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=temperature
                )
            )
            return response.text.strip() if response.text else None
        
        # Run in executor with timeout (Gemini client is sync)
        loop = asyncio.get_event_loop()
        return await asyncio.wait_for(
            loop.run_in_executor(None, lambda: self.gemini_client.models.generate_content(
                model="gemini-2.0-flash",
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=temperature
                )
            ).text.strip()),
            timeout=self.GEMINI_TIMEOUT
        )
    
    async def _call_groq(
        self,
        prompt: str,
        system_prompt: str,
        chat_history: List[Dict[str, str]],
        temperature: float,
        max_tokens: int
    ) -> Optional[str]:
        """Call Groq API with openai/gpt-oss-120b model."""
        if not GROQ_API_KEY:
            return None
        
        # Build messages array
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        for msg in chat_history:
            messages.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", "")
            })
        
        messages.append({"role": "user", "content": prompt})
        
        payload = {
            "model": "meta-llama/llama-4-scout-17b-16e-instruct",  # Groq's fast model
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                GROQ_CHAT_URL,
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json"
                },
                json=payload,
                timeout=self.GROQ_TIMEOUT
            )
            
            if response.status_code == 200:
                data = response.json()
                return data["choices"][0]["message"]["content"].strip()
            else:
                logger.error(f"Groq API error: {response.status_code} - {response.text}")
                return None
    
    def _analyze_sentiment(self, text: str) -> Dict[str, Any]:
        """
        Analyze sentiment locally using VADER or keyword matching.
        
        Returns dict with:
            - is_distressed: bool
            - sentiment: "positive", "negative", "neutral"
            - scores: dict of sentiment scores
        """
        result = {
            "is_distressed": False,
            "sentiment": "neutral",
            "scores": {}
        }
        
        if self.vader_analyzer:
            # Use VADER for sentiment analysis
            scores = self.vader_analyzer.polarity_scores(text)
            result["scores"] = scores
            
            # compound score: -1 (negative) to +1 (positive)
            compound = scores["compound"]
            
            if compound <= -0.3:
                result["sentiment"] = "negative"
                result["is_distressed"] = True
            elif compound >= 0.3:
                result["sentiment"] = "positive"
            else:
                result["sentiment"] = "neutral"
                # Even neutral sentiment can indicate distress with certain keywords
                result["is_distressed"] = is_distressed(text)
        else:
            # Fallback to keyword-based detection
            result["is_distressed"] = is_distressed(text)
            result["sentiment"] = "negative" if result["is_distressed"] else "neutral"
        
        return result
    
    async def generate_with_vitals(
        self,
        prompt: str,
        system_prompt: str,
        vitals: Dict[str, float],
        patient_context: Optional[Dict[str, Any]] = None,
        chat_history: Optional[List[Dict[str, str]]] = None
    ) -> LLMResponse:
        """
        Generate a response with vital signs context.
        Falls back to rule-based vital response if all LLMs fail.
        """
        patient_context = patient_context or {}
        
        # Enhance system prompt with vitals context
        vitals_context = f"""
CURRENT VITALS:
- Heart Rate: {vitals.get('heart_rate', 'N/A')} BPM
- HRV: {vitals.get('hrv', 'N/A')} ms
- Quality Score: {vitals.get('quality_score', 'N/A')}%
"""
        enhanced_prompt = system_prompt + vitals_context
        
        # Try the cascade
        response = await self.generate(
            prompt=prompt,
            system_prompt=enhanced_prompt,
            chat_history=chat_history,
            context=patient_context
        )
        
        # If we hit hardcoded fallback, use vital-aware fallback instead
        if response.provider == LLMProvider.HARDCODED:
            heart_rate = vitals.get("heart_rate", 75)
            fallback = get_vital_response_fallback(
                heart_rate=heart_rate,
                hrv=vitals.get("hrv"),
                patient_name=patient_context.get("name", "there")
            )
            response.text = fallback["message"]
            response.metadata["vital_fallback"] = fallback
        
        return response
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get health status of all LLM providers."""
        return {
            "gemini": {
                "available": self.gemini_client is not None,
                "circuit_open": self.circuit_breakers[LLMProvider.GEMINI_FLASH].is_open,
                "failures": self.circuit_breakers[LLMProvider.GEMINI_FLASH].failures
            },
            "groq": {
                "available": GROQ_API_KEY is not None,
                "circuit_open": self.circuit_breakers[LLMProvider.GROQ].is_open,
                "failures": self.circuit_breakers[LLMProvider.GROQ].failures
            },
            "vader": {
                "available": self.vader_analyzer is not None
            }
        }


# Global instance for singleton pattern
_client_instance: Optional[ResilientLLMClient] = None


def get_llm_client() -> ResilientLLMClient:
    """Get or create the global LLM client instance."""
    global _client_instance
    if _client_instance is None:
        _client_instance = ResilientLLMClient()
    return _client_instance
