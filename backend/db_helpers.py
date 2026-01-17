# db_helpers.py
from database import patients, vitals
from datetime import datetime, timedelta

def get_patient(patient_id):
    """Get patient details"""
    return patients.find_one({"_id": patient_id})

def get_recent_vitals(patient_id, days=7):
    """Get last N days of vitals"""
    cutoff = datetime.utcnow() - timedelta(days=days)
    
    results = list(vitals.find(
        {
            "patient_id": patient_id,
            "timestamp": {"$gte": cutoff}
        }
    ).sort("timestamp", 1))  # 1 = ascending
    
    return results

def get_all_vitals(patient_id):
    """Get complete vitals history"""
    return list(vitals.find(
        {"patient_id": patient_id}
    ).sort("timestamp", 1))

def store_new_vital(patient_id, heart_rate, hrv, quality_score):
    """Store new vitals measurement"""
    vital = {
        "patient_id": patient_id,
        "timestamp": datetime.utcnow(),
        "heart_rate": heart_rate,
        "hrv": hrv,
        "quality_score": quality_score
    }
    
    result = vitals.insert_one(vital)
    return str(result.inserted_id)

def get_baseline(patient_id):
    """Get patient's baseline vitals"""
    patient = get_patient(patient_id)
    if patient and "baseline" in patient:
        return patient["baseline"]
    return None

def calculate_stats(patient_id, days=7):
    """Calculate statistics for recent vitals"""
    recent = get_recent_vitals(patient_id, days)
    
    if not recent:
        return None
    
    hrs = [v["heart_rate"] for v in recent]
    hrvs = [v["hrv"] for v in recent]
    
    return {
        "avg_hr": sum(hrs) / len(hrs),
        "avg_hrv": sum(hrvs) / len(hrvs),
        "min_hr": min(hrs),
        "max_hr": max(hrs),
        "min_hrv": min(hrvs),
        "max_hrv": max(hrvs),
        "count": len(recent)
    }