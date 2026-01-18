# agents/orchestrator.py
"""
LangGraph Orchestrator - Chains the three agents into a workflow.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Dict, Any
from langgraph.graph import StateGraph, END

from .agent_config import VitalsState, create_initial_state
from .daily_vitals_agent import validate_vitals_node
from .decompensation_agent import assess_risk_node
from .health_literacy_agent import explain_to_patient_node


def create_vitals_analysis_graph() -> StateGraph:
    """
    Creates the LangGraph workflow for vitals analysis.
    
    Flow: START → validate_vitals → assess_risk → explain_to_patient → END
    """
    # Create the graph with our state schema
    workflow = StateGraph(VitalsState)
    
    # Add nodes for each agent
    workflow.add_node("validate_vitals", validate_vitals_node)
    workflow.add_node("assess_risk", assess_risk_node)
    workflow.add_node("explain_to_patient", explain_to_patient_node)
    
    # Define the flow
    workflow.set_entry_point("validate_vitals")
    workflow.add_edge("validate_vitals", "assess_risk")
    workflow.add_edge("assess_risk", "explain_to_patient")
    workflow.add_edge("explain_to_patient", END)
    
    return workflow


def run_agent_analysis(
    patient_id: str,
    heart_rate: float,
    hrv: float,
    quality_score: float
) -> Dict[str, Any]:
    """
    Main function to run the complete agent analysis workflow.
    
    Args:
        patient_id: Patient identifier
        heart_rate: Current heart rate in bpm
        hrv: Current HRV in ms
        quality_score: Measurement quality (0-1)
        
    Returns:
        Complete analysis results including risk assessment and explanations
    """
    try:
        # Create initial state
        initial_state = create_initial_state(
            patient_id=patient_id,
            heart_rate=heart_rate,
            hrv=hrv,
            quality_score=quality_score
        )
        
        # Create and compile the graph
        workflow = create_vitals_analysis_graph()
        app = workflow.compile()
        
        # Run the workflow
        final_state = app.invoke(initial_state)
        
        # Format the response
        return {
            "success": True,
            "patient_id": patient_id,
            "current_vitals": final_state.get("current_vitals"),
            "baseline": final_state.get("patient_baseline"),
            "deviations": {
                "heart_rate_percent": final_state.get("hr_deviation_percent"),
                "hrv_percent": final_state.get("hrv_deviation_percent")
            },
            "risk_assessment": {
                "score": final_state.get("risk_score", 0),
                "level": final_state.get("risk_level", "UNKNOWN"),
                "clinical_reasoning": final_state.get("clinical_reasoning"),
                "recommended_actions": final_state.get("recommended_actions", [])
            },
            "patient_explanation": final_state.get("patient_explanation"),
            "agent_steps": final_state.get("agent_reasoning", []),
            "alerts": final_state.get("alerts", []),
            "errors": final_state.get("errors", [])
        }
        
    except Exception as e:
        return {
            "success": False,
            "patient_id": patient_id,
            "error": str(e),
            "risk_assessment": {
                "score": 0,
                "level": "UNKNOWN",
                "clinical_reasoning": "Analysis failed",
                "recommended_actions": ["Contact healthcare provider for manual assessment"]
            },
            "patient_explanation": "We couldn't complete the analysis right now. Please try again or contact your care team.",
            "agent_steps": [],
            "alerts": [f"Analysis error: {str(e)}"],
            "errors": [str(e)]
        }


if __name__ == "__main__":
    # Quick test
    result = run_agent_analysis(
        patient_id="maria_001",
        heart_rate=89,
        hrv=28,
        quality_score=0.88
    )
    
    print("\n" + "="*60)
    print("AGENT ANALYSIS RESULT")
    print("="*60)
    print(f"Risk Level: {result['risk_assessment']['level']}")
    print(f"Risk Score: {result['risk_assessment']['score']}/100")
    print(f"\nClinical Reasoning:\n{result['risk_assessment']['clinical_reasoning']}")
    print(f"\nPatient Explanation:\n{result['patient_explanation']}")
    print(f"\nAgent Steps: {result['agent_steps']}")
