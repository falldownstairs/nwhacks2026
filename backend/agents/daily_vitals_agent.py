# agents/daily_vitals_agent.py
"""
Daily Vitals Agent - Validates vitals data and prepares it for analysis.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Dict, Any
from .agent_config import VitalsState, get_gemini_model
from db_helpers import get_baseline, get_recent_vitals


def validate_vitals_node(state: VitalsState) -> Dict[str, Any]:
    """
    Validates vitals data and retrieves baseline/history for analysis.
    
    This agent:
    1. Validates quality score is above threshold
    2. Retrieves patient baseline from database
    3. Retrieves last 7 days of vitals history
    4. Calculates percentage deviation from baseline
    5. Uses Gemini to assess measurement reliability
    """
    patient_id = state["patient_id"]
    vitals = state["current_vitals"]
    reasoning_steps = list(state.get("agent_reasoning", []))
    alerts = list(state.get("alerts", []))
    errors = list(state.get("errors", []))
    
    # Step 1: Validate quality score
    quality_score = vitals.get("quality_score", 0)
    if quality_score < 0.7:
        alerts.append(f"Low quality measurement: {quality_score:.0%} confidence")
        reasoning_steps.append(f"⚠️ Quality score {quality_score:.0%} below 70% threshold")
    else:
        reasoning_steps.append(f"✓ Vitals validated with {quality_score:.0%} confidence")
    
    # Step 2: Retrieve patient baseline
    try:
        baseline = get_baseline(patient_id)
        if not baseline:
            errors.append("No baseline established for patient")
            reasoning_steps.append("⚠️ No baseline found - using default thresholds")
            baseline = {"heart_rate": 70, "hrv": 40}  # Default values
    except Exception as e:
        errors.append(f"Database error retrieving baseline: {str(e)}")
        baseline = {"heart_rate": 70, "hrv": 40}
    
    # Step 3: Retrieve vitals history
    try:
        history = get_recent_vitals(patient_id, days=7)
        reasoning_steps.append(f"✓ Retrieved {len(history)} vitals from last 7 days")
    except Exception as e:
        errors.append(f"Database error retrieving history: {str(e)}")
        history = []
    
    # Step 4: Calculate deviations from baseline
    hr_deviation = None
    hrv_deviation = None
    
    if baseline and baseline.get("heart_rate") and baseline.get("hrv"):
        current_hr = vitals["heart_rate"]
        current_hrv = vitals["hrv"]
        baseline_hr = baseline["heart_rate"]
        baseline_hrv = baseline["hrv"]
        
        hr_deviation = ((current_hr - baseline_hr) / baseline_hr) * 100
        hrv_deviation = ((current_hrv - baseline_hrv) / baseline_hrv) * 100
        
        reasoning_steps.append(
            f"✓ Baseline comparison: HR {hr_deviation:+.1f}%, HRV {hrv_deviation:+.1f}%"
        )
    
    # Step 5: Use Gemini to assess reliability and note concerns
    gemini_summary = None
    try:
        model = get_gemini_model(temperature=0.3)
        
        prompt = f"""You are a clinical data quality analyst. Assess this vital signs measurement:

Heart Rate: {vitals['heart_rate']} bpm
HRV: {vitals['hrv']} ms  
Quality Score: {quality_score:.0%}
Patient Baseline: HR {baseline.get('heart_rate', 'N/A')} bpm, HRV {baseline.get('hrv', 'N/A')} ms

In 2-3 sentences:
1. Is this measurement reliable based on the quality score?
2. Note any immediate concerns about the values compared to baseline.
Be concise and clinical."""

        response = model.invoke(prompt)
        gemini_summary = response.content
        reasoning_steps.append("✓ AI quality assessment complete")
        
    except Exception as e:
        errors.append(f"Gemini API error: {str(e)}")
        gemini_summary = "AI assessment unavailable"
    
    # Return updated state
    return {
        "patient_baseline": baseline,
        "vitals_history": history,
        "hr_deviation_percent": hr_deviation,
        "hrv_deviation_percent": hrv_deviation,
        "agent_reasoning": reasoning_steps,
        "alerts": alerts,
        "errors": errors
    }
