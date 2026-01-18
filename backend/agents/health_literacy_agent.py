# agents/health_literacy_agent.py
"""
Health Literacy Agent - Explains findings in patient-friendly language.
"""

from typing import Dict, Any
from .agent_config import VitalsState, get_gemini_model


def explain_to_patient_node(state: VitalsState) -> Dict[str, Any]:
    """
    Translates medical findings into patient-friendly language.
    
    Uses Gemini to create an explanation that:
    - Uses 8th grade reading level
    - Avoids medical jargon
    - Uses relatable analogies
    - Provides clear next steps
    """
    reasoning_steps = list(state.get("agent_reasoning", []))
    errors = list(state.get("errors", []))
    
    # Get relevant data
    vitals = state["current_vitals"]
    baseline = state.get("patient_baseline", {})
    risk_level = state.get("risk_level", "LOW")
    risk_score = state.get("risk_score", 0)
    recommended_actions = state.get("recommended_actions", [])
    
    # Get deviation percentages for explanation
    hr_pct = state.get("hr_deviation_percent", 0) or 0
    hrv_pct = state.get("hrv_deviation_percent", 0) or 0
    
    # Get first action for patient
    next_step = recommended_actions[0] if recommended_actions else "Continue your regular monitoring"
    
    # Generate patient explanation with Gemini - DIFFERENT prompts per risk level
    patient_explanation = None
    try:
        model = get_gemini_model(temperature=0.7)
        
        # Risk-specific prompts for better tone control
        if risk_level == "HIGH":
            prompt = f"""You are a caring nurse explaining CONCERNING vitals to a heart failure patient.

READINGS:
- Heart rate: {vitals['heart_rate']} bpm (normally {baseline.get('heart_rate', 68)}) - that's {abs(hr_pct):.0f}% higher
- Heart flexibility (HRV): {vitals['hrv']} ms (normally {baseline.get('hrv', 45)}) - that's {abs(hrv_pct):.0f}% lower

Write a 3-sentence explanation:
1. State clearly their heart is working harder than normal (use specific numbers)
2. Use the rubber band analogy for HRV (getting stiffer = less flexible)
3. Tell them to call their doctor TODAY - be clear but calm

Keep it under 60 words. Be warm but direct about the urgency. Start with "Hi there"."""

        elif risk_level == "MEDIUM":
            prompt = f"""You are a caring nurse explaining BORDERLINE vitals to a heart failure patient.

READINGS:
- Heart rate: {vitals['heart_rate']} bpm (normally {baseline.get('heart_rate', 68)}) - {abs(hr_pct):.0f}% different
- Heart flexibility (HRV): {vitals['hrv']} ms (normally {baseline.get('hrv', 45)}) - {abs(hrv_pct):.0f}% different

Write a 3-sentence explanation:
1. Acknowledge the readings are a bit off from normal
2. Use rubber band analogy (slightly less stretchy)
3. Suggest they monitor closely and call clinic tomorrow if no improvement

Keep it under 60 words. Be reassuring but encourage attention. Start with "Hi there"."""

        else:  # LOW risk
            prompt = f"""You are a caring nurse giving GOOD NEWS about vitals to a heart failure patient.

READINGS:  
- Heart rate: {vitals['heart_rate']} bpm (normally {baseline.get('heart_rate', 68)}) - only {abs(hr_pct):.1f}% different
- Heart flexibility (HRV): {vitals['hrv']} ms (normally {baseline.get('hrv', 45)}) - only {abs(hrv_pct):.1f}% different

Write a 2-sentence POSITIVE explanation:
1. Tell them great news - everything looks stable and close to normal
2. Encourage them to keep doing what they're doing

Keep it under 40 words. Be cheerful and encouraging. Start with "Great news!" Do NOT mention any concerns."""

        response = model.invoke(prompt)
        patient_explanation = response.content.strip()
        
        # Enforce word limits
        words = patient_explanation.split()
        max_words = 40 if risk_level == "LOW" else 70
        if len(words) > max_words:
            patient_explanation = ' '.join(words[:max_words]) + '...'
        
        reasoning_steps.append("✓ Patient explanation generated")
        
    except Exception as e:
        errors.append(f"Gemini API error in patient explanation: {str(e)}")
        
        # Concise fallback explanations by risk level
        if risk_level == "HIGH":
            patient_explanation = f"Hi there, your heart is working harder than normal today - {vitals['heart_rate']} beats per minute instead of your usual {baseline.get('heart_rate', 68)}. Your heart's flexibility has also decreased, like a rubber band getting stiffer. Please call your doctor's office today so we can adjust your care plan."
        elif risk_level == "MEDIUM":
            patient_explanation = f"Hi there, your readings are a bit off today - heart rate is {vitals['heart_rate']} (normally {baseline.get('heart_rate', 68)}) and flexibility is slightly down. Nothing urgent, but let's keep a close eye on it. Call the clinic tomorrow if you notice any changes."
        else:
            patient_explanation = f"Great news! Your heart is doing well today. Heart rate is {vitals['heart_rate']} and flexibility is {vitals['hrv']} - both very close to your normal. Keep up the good work!"
    
    return {
        "patient_explanation": patient_explanation,
        "agent_reasoning": reasoning_steps,
        "errors": errors
    }
