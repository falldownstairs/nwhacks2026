# database.py
import os
from datetime import datetime

from dotenv import load_dotenv
from pymongo import MongoClient

# Load .env file
load_dotenv()

# Use Atlas URI from .env
MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise ValueError("MONGO_URI not found in environment variables")

client = MongoClient(MONGO_URI)
db = client["chronic_disease_mvp"]

# Collections
patients = db["patients"]
vitals = db["vitals"]
