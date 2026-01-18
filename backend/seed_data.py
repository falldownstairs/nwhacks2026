# seed_data.py
import random
from datetime import datetime, timedelta

from database import patients, vitals


def clear_database():
    """Wipe everything for fresh start"""
    patients.delete_many({})
    vitals.delete_many({})
    print("✓ Database cleared")

def create_maria():
    """Create our demo patient"""
    maria = {
        "_id": "maria_001",
        "name": "Prajwal Prashanth",
        "age": 18,
        "conditions": ["Heart Failure", "Type 2 Diabetes"],
        "baseline": {
            "heart_rate": 68,
            "hrv": 45
        },
        "created_at": datetime.utcnow()
    }
    
    patients.insert_one(maria)
    print("✓ Created patient: Maria Gonzalez")
    return maria["_id"]

def generate_normal_vitals(patient_id, days=30, skip_last_days=0):
    """Generate stable vitals, optionally skipping recent days for declining period"""
    base_date = datetime.utcnow() - timedelta(days=days)
    
    measurements = []
    for day in range(days - skip_last_days):
        timestamp = base_date + timedelta(days=day, hours=8)  # 8 AM each day
        
        vital = {
            "patient_id": patient_id,
            "timestamp": timestamp,
            "heart_rate": random.randint(64, 72),      # 68 ± 4
            "hrv": random.randint(41, 49),             # 45 ± 4
            "quality_score": round(random.uniform(0.85, 0.95), 2)
        }
        measurements.append(vital)
    
    vitals.insert_many(measurements)
    print(f"✓ Added {days - skip_last_days} days of normal vitals")

def generate_declining_vitals(patient_id, days=5):
    """Generate 5 days of declining vitals (decompensation)"""
    base_date = datetime.utcnow() - timedelta(days=days)
    
    measurements = []
    for day in range(days):
        timestamp = base_date + timedelta(days=day, hours=8)
        
        # Progressive worsening each day
        hr = 68 + int(day * 5.25)      # Day 0: 68 → Day 4: 89
        hrv = 45 - int(day * 4.25)     # Day 0: 45 → Day 4: 28
        
        vital = {
            "patient_id": patient_id,
            "timestamp": timestamp,
            "heart_rate": hr,
            "hrv": hrv,
            "quality_score": 0.88
        }
        measurements.append(vital)
    
    vitals.insert_many(measurements)
    print(f"✓ Added {days} days of declining vitals")
    
    # Print the progression so you can see it
    print("\n📊 Vitals Progression:")
    print("Day | HR  | HRV")
    print("----|-----|----")
    for i, m in enumerate(measurements):
        print(f" {i}  | {m['heart_rate']:3d} | {m['hrv']:3d}")

def seed_everything():
    """Run complete database setup"""
    print("\n🌱 Seeding database...\n")
    
    clear_database()
    patient_id = create_maria()
    
    # Generate 30 days total: 25 normal + 5 declining (no overlap)
    declining_days = 5
    generate_normal_vitals(patient_id, days=30, skip_last_days=declining_days)
    generate_declining_vitals(patient_id, days=declining_days)
    
    # Verify
    total_vitals = vitals.count_documents({"patient_id": patient_id})
    print(f"\n✅ Database ready! Total vitals: {total_vitals}")
    print(f"📅 Date range: 30 days (25 normal + 5 declining)")
    print(f"👤 Patient ID: {patient_id}")

if __name__ == "__main__":
    seed_everything()
    