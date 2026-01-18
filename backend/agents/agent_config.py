# agents/agent_config.py
"""
Configuration for AI agents using Google Gemini and shared state definitions.
"""

import os
from typing import TypedDict, List, Optional, Dict, Any
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

# Load environment variables
load_dotenv()

# Initialize Gemini model
def get_gemini_model(temperature: float = 0.7) -> ChatGoogleGenerativeAI:
    """Get configured Gemini model instance."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not found in environment variables")
    
    return ChatGoogleGenerativeAI(
        model="gemini-2.0-flash-exp",
        google_api_key=api_key,
        temperature=temperature,
        convert_system_message_to_human=True
    )

# Shared state structure for all agents
class VitalsState(TypedDict):
    """State shared across all agents in the workflow."""
    # Input data
    patient_id: str
    current_vitals: Dict[str, float]  # heart_rate, hrv, quality_score
    
    # Retrieved from database
    patient_baseline: Optional[Dict[str, float]]  # heart_rate, hrv
    vitals_history: Optional[List[Dict[str, Any]]]  # Last 7 days
    
    # Calculated metrics
    hr_deviation_percent: Optional[float]
    hrv_deviation_percent: Optional[float]
    
    # Risk assessment
    risk_score: int  # 0-100
    risk_level: str  # LOW, MEDIUM, HIGH
    
    # Agent outputs
    alerts: List[str]
    agent_reasoning: List[str]  # Steps taken by agents
    clinical_reasoning: Optional[str]  # Detailed clinical analysis
    recommended_actions: List[str]
    
    # Final output
    patient_explanation: Optional[str]  # Patient-friendly explanation
    
    # Error tracking
    errors: List[str]


def create_initial_state(
    patient_id: str, 
    heart_rate: float, 
    hrv: float, 
    quality_score: float
) -> VitalsState:
    """Create initial state for the agent workflow."""
    return VitalsState(
        patient_id=patient_id,
        current_vitals={
            "heart_rate": heart_rate,
            "hrv": hrv,
            "quality_score": quality_score
        },
        patient_baseline=None,
        vitals_history=None,
        hr_deviation_percent=None,
        hrv_deviation_percent=None,
        risk_score=0,
        risk_level="LOW",
        alerts=[],
        agent_reasoning=[],
        clinical_reasoning=None,
        recommended_actions=[],
        patient_explanation=None,
        errors=[]
    )
