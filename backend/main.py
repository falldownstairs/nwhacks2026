# main.py
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from db_helpers import (
    get_patient, get_recent_vitals, get_all_vitals, 
    store_new_vital, get_baseline, calculate_stats
)
from database import patients, vitals

app = FastAPI(title="Chronic Disease MVP", version="1.0.0")

# CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============== Pydantic Models ==============

class PatientCreate(BaseModel):
    patient_id: str
    name: str
    age: int
    conditions: List[str] = []
    baseline_heart_rate: Optional[float] = None
    baseline_hrv: Optional[float] = None

class PatientUpdate(BaseModel):
    name: Optional[str] = None
    age: Optional[int] = None
    conditions: Optional[List[str]] = None
    baseline_heart_rate: Optional[float] = None
    baseline_hrv: Optional[float] = None

class VitalCreate(BaseModel):
    patient_id: str
    heart_rate: float
    hrv: float
    quality_score: float = 0.9

class AlertThresholds(BaseModel):
    hr_high: float = 100
    hr_low: float = 50
    hrv_low: float = 20
    hr_change_percent: float = 20  # % change from baseline
    hrv_change_percent: float = 30

# ============== Health Check ==============

@app.get("/")
def read_root():
    return {"status": "healthy", "service": "Chronic Disease MVP API"}

@app.get("/health")
def health_check():
    try:
        # Test DB connection
        patients.find_one()
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database error: {str(e)}")

# ============== Patient CRUD ==============

@app.post("/patients", status_code=201)
def create_patient(patient: PatientCreate):
    """Create a new patient"""
    # Check if patient already exists
    if patients.find_one({"_id": patient.patient_id}):
        raise HTTPException(status_code=400, detail="Patient ID already exists")
    
    patient_doc = {
        "_id": patient.patient_id,
        "name": patient.name,
        "age": patient.age,
        "conditions": patient.conditions,
        "baseline": {
            "heart_rate": patient.baseline_heart_rate,
            "hrv": patient.baseline_hrv
        },
        "created_at": datetime.utcnow()
    }
    
    patients.insert_one(patient_doc)
    return {"message": "Patient created", "patient_id": patient.patient_id}

@app.get("/patients")
def list_patients():
    """List all patients"""
    all_patients = list(patients.find())
    # Convert _id to patient_id for cleaner response
    for p in all_patients:
        p["patient_id"] = p.pop("_id")
    return {"patients": all_patients, "count": len(all_patients)}

@app.get("/patients/{patient_id}")
def get_patient_by_id(patient_id: str):
    """Get a single patient by ID"""
    patient = get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    
    patient["patient_id"] = patient.pop("_id")
    return patient

@app.put("/patients/{patient_id}")
def update_patient(patient_id: str, update: PatientUpdate):
    """Update patient details"""
    patient = get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    
    update_doc = {}
    if update.name is not None:
        update_doc["name"] = update.name
    if update.age is not None:
        update_doc["age"] = update.age
    if update.conditions is not None:
        update_doc["conditions"] = update.conditions
    if update.baseline_heart_rate is not None:
        update_doc["baseline.heart_rate"] = update.baseline_heart_rate
    if update.baseline_hrv is not None:
        update_doc["baseline.hrv"] = update.baseline_hrv
    
    if update_doc:
        update_doc["updated_at"] = datetime.utcnow()
        patients.update_one({"_id": patient_id}, {"$set": update_doc})
    
    return {"message": "Patient updated", "patient_id": patient_id}

@app.delete("/patients/{patient_id}")
def delete_patient(patient_id: str):
    """Delete a patient and their vitals"""
    patient = get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    
    # Delete patient and their vitals
    patients.delete_one({"_id": patient_id})
    vitals_deleted = vitals.delete_many({"patient_id": patient_id})
    
    return {
        "message": "Patient deleted",
        "patient_id": patient_id,
        "vitals_deleted": vitals_deleted.deleted_count
    }

# ============== Vitals Endpoints ==============

@app.post("/vitals", status_code=201)
def create_vital(vital: VitalCreate):
    """Store new vitals measurement (from camera)"""
    # Verify patient exists
    if not get_patient(vital.patient_id):
        raise HTTPException(status_code=404, detail="Patient not found")
    
    vital_id = store_new_vital(
        vital.patient_id,
        vital.heart_rate,
        vital.hrv,
        vital.quality_score
    )
    
    # Check for alerts
    alerts = check_vital_alerts(vital.patient_id, vital.heart_rate, vital.hrv)
    
    return {
        "message": "Vital recorded",
        "vital_id": vital_id,
        "alerts": alerts
    }

@app.get("/vitals/{patient_id}")
def get_vitals(patient_id: str, days: Optional[int] = None):
    """Get vitals for a patient. If days specified, returns recent; otherwise all."""
    if not get_patient(patient_id):
        raise HTTPException(status_code=404, detail="Patient not found")
    
    if days:
        vital_list = get_recent_vitals(patient_id, days)
    else:
        vital_list = get_all_vitals(patient_id)
    
    # Convert ObjectId to string
    for v in vital_list:
        v["_id"] = str(v["_id"])
    
    return {"patient_id": patient_id, "vitals": vital_list, "count": len(vital_list)}

@app.get("/vitals/{patient_id}/latest")
def get_latest_vital(patient_id: str):
    """Get the most recent vital reading"""
    if not get_patient(patient_id):
        raise HTTPException(status_code=404, detail="Patient not found")
    
    latest = vitals.find_one(
        {"patient_id": patient_id},
        sort=[("timestamp", -1)]
    )
    
    if not latest:
        raise HTTPException(status_code=404, detail="No vitals found")
    
    latest["_id"] = str(latest["_id"])
    return latest

# ============== Analytics Endpoints ==============

@app.get("/analytics/{patient_id}/stats")
def get_patient_stats(patient_id: str, days: int = 7):
    """Get statistical summary of recent vitals"""
    if not get_patient(patient_id):
        raise HTTPException(status_code=404, detail="Patient not found")
    
    stats = calculate_stats(patient_id, days)
    if not stats:
        raise HTTPException(status_code=404, detail="No vitals data for analysis")
    
    return {"patient_id": patient_id, "days": days, "stats": stats}

@app.get("/analytics/{patient_id}/trends")
def get_trends(patient_id: str, days: int = 7):
    """Analyze trends in vitals - detecting improvement or decline"""
    if not get_patient(patient_id):
        raise HTTPException(status_code=404, detail="Patient not found")
    
    recent = get_recent_vitals(patient_id, days)
    if len(recent) < 3:
        raise HTTPException(status_code=400, detail="Not enough data for trend analysis (need at least 3 readings)")
    
    # Calculate trend using simple linear regression slope
    hr_values = [v["heart_rate"] for v in recent]
    hrv_values = [v["hrv"] for v in recent]
    
    hr_trend = calculate_trend(hr_values)
    hrv_trend = calculate_trend(hrv_values)
    
    # Determine status
    status = "stable"
    concerns = []
    
    # Rising HR + Falling HRV = potential decompensation
    if hr_trend > 2 and hrv_trend < -2:
        status = "declining"
        concerns.append("Heart rate rising while HRV declining - possible decompensation")
    elif hr_trend > 3:
        status = "concerning"
        concerns.append("Heart rate trending upward")
    elif hrv_trend < -3:
        status = "concerning"
        concerns.append("HRV trending downward")
    elif hr_trend < -2 and hrv_trend > 2:
        status = "improving"
    
    return {
        "patient_id": patient_id,
        "days": days,
        "readings_analyzed": len(recent),
        "trends": {
            "heart_rate": {
                "direction": "rising" if hr_trend > 1 else "falling" if hr_trend < -1 else "stable",
                "slope": round(hr_trend, 2)
            },
            "hrv": {
                "direction": "rising" if hrv_trend > 1 else "falling" if hrv_trend < -1 else "stable",
                "slope": round(hrv_trend, 2)
            }
        },
        "status": status,
        "concerns": concerns
    }

@app.get("/analytics/{patient_id}/alerts")
def get_alerts(patient_id: str):
    """Check current alerts based on latest vitals and baseline"""
    patient = get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    
    latest = vitals.find_one(
        {"patient_id": patient_id},
        sort=[("timestamp", -1)]
    )
    
    if not latest:
        return {"patient_id": patient_id, "alerts": [], "status": "no_data"}
    
    alerts = check_vital_alerts(patient_id, latest["heart_rate"], latest["hrv"])
    
    return {
        "patient_id": patient_id,
        "timestamp": latest["timestamp"],
        "current_hr": latest["heart_rate"],
        "current_hrv": latest["hrv"],
        "alerts": alerts,
        "alert_count": len(alerts)
    }

@app.get("/analytics/{patient_id}/baseline-comparison")
def compare_to_baseline(patient_id: str):
    """Compare current vitals to baseline"""
    patient = get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    
    baseline = patient.get("baseline", {})
    if not baseline.get("heart_rate") or not baseline.get("hrv"):
        raise HTTPException(status_code=400, detail="No baseline established for patient")
    
    # Get recent stats (last 3 days)
    stats = calculate_stats(patient_id, days=3)
    if not stats:
        raise HTTPException(status_code=404, detail="No recent vitals for comparison")
    
    hr_diff = stats["avg_hr"] - baseline["heart_rate"]
    hrv_diff = stats["avg_hrv"] - baseline["hrv"]
    hr_pct = (hr_diff / baseline["heart_rate"]) * 100
    hrv_pct = (hrv_diff / baseline["hrv"]) * 100
    
    return {
        "patient_id": patient_id,
        "baseline": baseline,
        "current_avg": {
            "heart_rate": round(stats["avg_hr"], 1),
            "hrv": round(stats["avg_hrv"], 1)
        },
        "deviation": {
            "heart_rate": {
                "absolute": round(hr_diff, 1),
                "percent": round(hr_pct, 1)
            },
            "hrv": {
                "absolute": round(hrv_diff, 1),
                "percent": round(hrv_pct, 1)
            }
        },
        "assessment": get_assessment(hr_pct, hrv_pct)
    }

# ============== Helper Functions ==============

def calculate_trend(values: List[float]) -> float:
    """Calculate linear regression slope (change per reading)"""
    n = len(values)
    if n < 2:
        return 0.0
    
    x_mean = (n - 1) / 2
    y_mean = sum(values) / n
    
    numerator = sum((i - x_mean) * (values[i] - y_mean) for i in range(n))
    denominator = sum((i - x_mean) ** 2 for i in range(n))
    
    if denominator == 0:
        return 0.0
    
    return numerator / denominator

def check_vital_alerts(patient_id: str, heart_rate: float, hrv: float) -> List[dict]:
    """Check vitals against thresholds and baseline"""
    alerts = []
    
    # Absolute thresholds
    if heart_rate > 100:
        alerts.append({"type": "high_hr", "severity": "warning", "message": f"Heart rate elevated: {heart_rate} bpm"})
    elif heart_rate > 120:
        alerts.append({"type": "high_hr", "severity": "critical", "message": f"Heart rate critically high: {heart_rate} bpm"})
    
    if heart_rate < 50:
        alerts.append({"type": "low_hr", "severity": "warning", "message": f"Heart rate low: {heart_rate} bpm"})
    
    if hrv < 20:
        alerts.append({"type": "low_hrv", "severity": "warning", "message": f"HRV critically low: {hrv} ms"})
    elif hrv < 30:
        alerts.append({"type": "low_hrv", "severity": "info", "message": f"HRV below optimal: {hrv} ms"})
    
    # Baseline comparison
    baseline = get_baseline(patient_id)
    if baseline and baseline.get("heart_rate") and baseline.get("hrv"):
        hr_change = ((heart_rate - baseline["heart_rate"]) / baseline["heart_rate"]) * 100
        hrv_change = ((hrv - baseline["hrv"]) / baseline["hrv"]) * 100
        
        if hr_change > 20:
            alerts.append({
                "type": "baseline_deviation",
                "severity": "warning",
                "message": f"Heart rate {hr_change:.0f}% above baseline"
            })
        
        if hrv_change < -30:
            alerts.append({
                "type": "baseline_deviation", 
                "severity": "warning",
                "message": f"HRV {abs(hrv_change):.0f}% below baseline"
            })
    
    return alerts

def get_assessment(hr_pct: float, hrv_pct: float) -> str:
    """Generate assessment based on baseline deviations"""
    if hr_pct > 20 and hrv_pct < -25:
        return "ALERT: Significant deviation from baseline. Possible cardiac decompensation. Consider clinical review."
    elif hr_pct > 15 or hrv_pct < -20:
        return "WARNING: Moderate deviation from baseline. Continue monitoring closely."
    elif hr_pct > 10 or hrv_pct < -10:
        return "CAUTION: Mild deviation from baseline. Monitor for trends."
    elif hr_pct < -10 and hrv_pct > 10:
        return "POSITIVE: Vitals improving relative to baseline."
    else:
        return "STABLE: Vitals within normal range of baseline."
