# agents/decompensation_agent.py
"""
Decompensation Agent - Analyzes vitals to detect early warning signs of disease worsening.
"""

from typing import Dict, Any, List
from .agent_config import VitalsState, get_gemini_model


def calculate_trend(values: List[float]) -> str:
    """Determine if values are trending up, down, or stable."""
    if len(values) < 3:
        return "insufficient_data"
    
    # Compare first third to last third
    third = len(values) // 3
    early_avg = sum(values[:third]) / third if third > 0 else values[0]
    late_avg = sum(values[-third:]) / third if third > 0 else values[-1]
    
    change_pct = ((late_avg - early_avg) / early_avg) * 100 if early_avg != 0 else 0
    
    if change_pct > 5:
        return "worsening"
    elif change_pct < -5:
        return "improving"
    return "stable"


def assess_risk_node(state: VitalsState) -> Dict[str, Any]:
    """
    Performs comprehensive risk assessment for decompensation.
    
    Risk scoring rules:
    - HR >20% above baseline: +30 points
    - HRV <-30% below baseline: +40 points  
    - Negative trend over 3+ days: +20 points
    - Maximum score: 100
    
    Risk levels:
    - 0-30: LOW
    - 31-69: MEDIUM
    - 70-100: HIGH
    """
    reasoning_steps = list(state.get("agent_reasoning", []))
    alerts = list(state.get("alerts", []))
    errors = list(state.get("errors", []))
    
    # Get current values
    vitals = state["current_vitals"]
    baseline = state.get("patient_baseline", {})
    history = state.get("vitals_history", [])
    hr_deviation = state.get("hr_deviation_percent", 0) or 0
    hrv_deviation = state.get("hrv_deviation_percent", 0) or 0
    
    # Calculate risk score
    risk_score = 0
    risk_factors = []
    
    # Factor 1: Heart rate elevation
    if hr_deviation > 20:
        risk_score += 30
        risk_factors.append(f"Elevated HR (+{hr_deviation:.0f}% from baseline)")
    elif hr_deviation > 10:
        risk_score += 15
        risk_factors.append(f"Mildly elevated HR (+{hr_deviation:.0f}%)")
    
    # Factor 2: HRV depression
    if hrv_deviation < -30:
        risk_score += 40
        risk_factors.append(f"Significantly reduced HRV ({hrv_deviation:.0f}%)")
    elif hrv_deviation < -15:
        risk_score += 20
        risk_factors.append(f"Reduced HRV ({hrv_deviation:.0f}%)")
    
    # Factor 3: Trend analysis (if we have history)
    hr_trend = "stable"
    hrv_trend = "stable"
    
    if len(history) >= 3:
        hr_values = [v["heart_rate"] for v in history]
        hrv_values = [v["hrv"] for v in history]
        
        hr_trend = calculate_trend(hr_values)
        hrv_trend = calculate_trend(hrv_values)
        
        # Worsening pattern: HR rising AND HRV falling
        if hr_trend == "worsening" and hrv_trend == "worsening":
            risk_score += 20
            risk_factors.append("Consistent worsening trend over recent days")
        elif hr_trend == "worsening" or hrv_trend == "worsening":
            risk_score += 10
            risk_factors.append("Partial worsening trend detected")
    
    # Cap at 100
    risk_score = min(risk_score, 100)
    
    # Determine risk level
    if risk_score >= 70:
        risk_level = "HIGH"
    elif risk_score >= 31:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"
    
    reasoning_steps.append(f"✓ Risk score calculated: {risk_score}/100 ({risk_level})")
    
    # Generate recommended actions based on risk level
    if risk_level == "HIGH":
        recommended_actions = [
            "Schedule urgent telehealth consultation within 48 hours",
            "Notify care team immediately",
            "Monitor for additional symptoms: shortness of breath, leg swelling, weight gain",
            "Review current medication compliance",
            "Consider emergency visit if symptoms worsen"
        ]
        alerts.append(f"HIGH RISK: Score {risk_score}/100 - Immediate attention required")
    elif risk_level == "MEDIUM":
        recommended_actions = [
            "Increase monitoring frequency to twice daily",
            "Consider notifying healthcare provider",
            "Track fluid intake and weight daily",
            "Watch for symptom changes",
            "Schedule follow-up within 1 week if no improvement"
        ]
        alerts.append(f"MEDIUM RISK: Score {risk_score}/100 - Enhanced monitoring advised")
    else:
        recommended_actions = [
            "Continue daily monitoring as scheduled",
            "Maintain current medication regimen",
            "Keep up healthy lifestyle habits",
            "Report any new symptoms promptly"
        ]
    
    # Use Gemini for clinical reasoning - CONCISE, focused on current measurement only
    clinical_reasoning = None
    try:
        model = get_gemini_model(temperature=0.3)
        
        prompt = f"""You are a cardiologist reviewing vitals for a 68-year-old heart failure patient.

CURRENT READING:
- Heart Rate: {vitals['heart_rate']} bpm (baseline: {baseline.get('heart_rate', 70)} bpm)
- HRV: {vitals['hrv']} ms (baseline: {baseline.get('hrv', 40)} ms)
- Deviations: HR {hr_deviation:+.1f}%, HRV {hrv_deviation:+.1f}%

RISK SCORE: {risk_score}/100 ({risk_level})

Provide a 2-3 sentence clinical assessment:
1. What does this deviation indicate physiologically?
2. What is the clinical significance?
3. What action is warranted?

CRITICAL: Analyze THIS SINGLE MEASUREMENT only. Do NOT mention trends, recent improvements, or historical patterns unless the deviations are minimal.
Keep response under 60 words. Be direct and clinical."""

        response = model.invoke(prompt)
        clinical_reasoning = response.content.strip()
        
        # Enforce word limit
        words = clinical_reasoning.split()
        if len(words) > 75:
            clinical_reasoning = ' '.join(words[:75]) + '...'
        
        reasoning_steps.append("✓ Clinical assessment complete")
        
    except Exception as e:
        errors.append(f"Gemini API error in risk assessment: {str(e)}")
        # Concise fallback reasoning by risk level
        if risk_level == "HIGH":
            clinical_reasoning = f"Significant cardiac stress. HR {hr_deviation:+.0f}% above baseline indicates increased workload. HRV {hrv_deviation:+.0f}% below baseline suggests autonomic dysfunction. Pattern consistent with decompensation requiring urgent evaluation."
        elif risk_level == "MEDIUM":
            clinical_reasoning = f"Moderate deviation from baseline. HR elevated {hr_deviation:+.0f}%, HRV reduced {abs(hrv_deviation):.0f}%. Early cardiac stress pattern. Enhanced monitoring recommended."
        else:
            clinical_reasoning = f"Vitals within acceptable range. Minor deviations (HR {hr_deviation:+.1f}%, HRV {hrv_deviation:+.1f}%) not clinically significant. Continue routine monitoring."
        
    except Exception as e:
        errors.append(f"Gemini API error in risk assessment: {str(e)}")
        # Concise fallback reasoning by risk level
        if risk_level == "HIGH":
            clinical_reasoning = f"Significant cardiac stress. HR {hr_deviation:+.0f}% above baseline indicates increased workload. HRV {hrv_deviation:+.0f}% below baseline suggests autonomic dysfunction. Pattern consistent with decompensation requiring urgent evaluation."
        elif risk_level == "MEDIUM":
            clinical_reasoning = f"Moderate deviation from baseline. HR elevated {hr_deviation:+.0f}%, HRV reduced {abs(hrv_deviation):.0f}%. Early cardiac stress pattern. Enhanced monitoring recommended."
        else:
            clinical_reasoning = f"Vitals within acceptable range. Minor deviations (HR {hr_deviation:+.1f}%, HRV {hrv_deviation:+.1f}%) not clinically significant. Continue routine monitoring."
    
    return {
        "risk_score": risk_score,
        "risk_level": risk_level,
        "clinical_reasoning": clinical_reasoning,
        "recommended_actions": recommended_actions,
        "agent_reasoning": reasoning_steps,
        "alerts": alerts,
        "errors": errors
    }
