#!/usr/bin/env python3
# agents/demo_runner.py
"""
Demo script to test the AI agent system with different scenarios.
"""

import sys
import os

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.orchestrator import run_agent_analysis
from db_helpers import get_recent_vitals


def print_divider(title: str = ""):
    """Print a formatted divider."""
    print("\n" + "=" * 70)
    if title:
        print(f" {title}")
        print("=" * 70)


def get_trend_arrow(deviation: float) -> str:
    """Return trend arrow based on deviation."""
    if deviation > 5:
        return "↑"
    elif deviation < -5:
        return "↓"
    return "→"


def print_result(result: dict, scenario_name: str):
    """Pretty print the analysis result."""
    print_divider(f"📊 {scenario_name}")
    
    if not result.get("success", False):
        print(f"❌ Analysis failed: {result.get('error', 'Unknown error')}")
        return
    
    # Current vitals with trend arrows
    vitals = result.get("current_vitals", {})
    deviations = result.get("deviations", {})
    hr_pct = deviations.get("heart_rate_percent") or 0
    hrv_pct = deviations.get("hrv_percent") or 0
    
    print(f"\n🫀 Current Vitals:")
    print(f"   Heart Rate: {vitals.get('heart_rate')} bpm {get_trend_arrow(hr_pct)} ({hr_pct:+.1f}% from baseline)")
    print(f"   HRV: {vitals.get('hrv')} ms {get_trend_arrow(hrv_pct)} ({hrv_pct:+.1f}% from baseline)")
    print(f"   Quality: {vitals.get('quality_score', 0):.0%}")
    
    # Baseline
    baseline = result.get("baseline", {})
    if baseline:
        print(f"\n📏 Baseline:")
        print(f"   HR: {baseline.get('heart_rate')} bpm | HRV: {baseline.get('hrv')} ms")
    
    # Risk assessment with color emoji
    risk = result.get("risk_assessment", {})
    risk_level = risk.get("level", "UNKNOWN")
    risk_emoji = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}.get(risk_level, "⚪")
    
    print(f"\n{risk_emoji} Risk Assessment: {risk_level} ({risk.get('score', 0)}/100)")
    
    # Clinical reasoning (should now be concise)
    print(f"\n🩺 Clinical Reasoning:")
    clinical = risk.get("clinical_reasoning", "N/A")
    # Word wrap at 65 chars
    words = clinical.split()
    lines = []
    current_line = "   "
    for word in words:
        if len(current_line) + len(word) + 1 > 68:
            lines.append(current_line)
            current_line = "   " + word
        else:
            current_line += " " + word if current_line.strip() else word
    if current_line.strip():
        lines.append(current_line)
    print("\n".join(lines))
    
    # Recommended actions (top 3 only for demo)
    actions = risk.get("recommended_actions", [])[:3]
    if actions:
        print(f"\n📋 Key Actions:")
        for i, action in enumerate(actions, 1):
            print(f"   {i}. {action}")
    
    # Patient explanation (should now be concise)
    print(f"\n💬 Patient Explanation:")
    explanation = result.get("patient_explanation", "N/A")
    words = explanation.split()
    lines = []
    current_line = "   "
    for word in words:
        if len(current_line) + len(word) + 1 > 68:
            lines.append(current_line)
            current_line = "   " + word
        else:
            current_line += " " + word if current_line.strip() else word
    if current_line.strip():
        lines.append(current_line)
    print("\n".join(lines))
    
    # Agent steps (condensed)
    steps = result.get("agent_steps", [])
    if steps:
        print(f"\n🤖 Agent Steps: {len(steps)} completed")
    
    # Alerts
    alerts = result.get("alerts", [])
    if alerts:
        print(f"\n⚠️  {alerts[0]}")


def main():
    """Run demo scenarios."""
    print_divider("🏥 CHRONIC DISEASE MONITORING - AI AGENT DEMO")
    print("\nPatient: Maria Gonzalez (68yo, Heart Failure + Type 2 Diabetes)")
    print("Baseline: HR 68 bpm, HRV 45 ms")
    
    # Check actual vitals count in DB
    recent = get_recent_vitals("maria_001", 7)
    print(f"\n📊 Database: {len(recent)} vitals in last 7 days")
    
    # Scenario 1: HIGH RISK
    print_divider("SCENARIO 1: High Risk (Decompensation Warning)")
    print("Input: HR=89, HRV=28, Quality=88%")
    
    result1 = run_agent_analysis(
        patient_id="maria_001",
        heart_rate=89,
        hrv=28,
        quality_score=0.88
    )
    print_result(result1, "HIGH RISK")
    
    # Scenario 2: LOW RISK
    print_divider("SCENARIO 2: Low Risk (Stable)")
    print("Input: HR=70, HRV=44, Quality=92%")
    
    result2 = run_agent_analysis(
        patient_id="maria_001",
        heart_rate=70,
        hrv=44,
        quality_score=0.92
    )
    print_result(result2, "LOW RISK")
    
    print_divider("DEMO COMPLETE")
    print("\n✅ Agent system working!")
    print("💡 For hackathon: Focus on HIGH vs LOW contrast")
    print("⏱️  Traditional care: catches on Day 30 in ER")
    print("🚀 This system: catches on Day 28 = 2 DAYS EARLIER")


if __name__ == "__main__":
    main()
