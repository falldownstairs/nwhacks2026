import asyncio
import json
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

from agents import (create_pulse_chat_agent, run_agent_analysis,
                    transcribe_base64)
from agents.text_to_speech import synthesize_speech_streaming
from camera_stream import camera_websocket_endpoint
from database import patients, vitals
from db_helpers import (calculate_stats, get_all_vitals, get_baseline,
                        get_patient, get_recent_vitals, store_new_vital)
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Load environment variables
load_dotenv()

try:
    import uvloop

    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
except ImportError:
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
app = FastAPI(title="Chronic Disease MVP", version="1.0.0")

# CORS for Next.js frontend - allow configured origins plus localhost for dev
frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
allowed_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    frontend_url,
    # Also allow the https version if http was provided
    frontend_url.replace("http://", "https://") if frontend_url.startswith("http://") else frontend_url,
]
# Remove duplicates
allowed_origins = list(set(allowed_origins))

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Store active chat sessions
active_chat_sessions: Dict[str, Any] = {}


# ============== TTS Helper ==============


async def stream_tts_to_websocket(websocket: WebSocket, text: str):
    """
    Stream TTS audio chunks to the WebSocket client.
    Sends audio in chunks for real-time playback.
    """
    import base64
    import os

    # Skip TTS if no API key configured
    if not os.getenv("ELEVENLABS_API_KEY"):
        print("Warning: ELEVENLABS_API_KEY not set, skipping TTS")
        return

    try:
        chunk_buffer = b""
        chunk_count = 0

        async for audio_chunk in synthesize_speech_streaming(text):
            chunk_buffer += audio_chunk
            # Send chunks of ~8KB for smooth streaming
            if len(chunk_buffer) >= 8192:
                await websocket.send_json(
                    {
                        "type": "audio_chunk",
                        "audio": base64.b64encode(chunk_buffer).decode("utf-8"),
                        "is_final": False,
                    }
                )
                chunk_buffer = b""
                chunk_count += 1

        # Send any remaining audio as final chunk
        if chunk_buffer:
            await websocket.send_json(
                {
                    "type": "audio_chunk",
                    "audio": base64.b64encode(chunk_buffer).decode("utf-8"),
                    "is_final": True,
                }
            )
        elif chunk_count > 0:
            # If we sent chunks but buffer is empty, send empty final signal
            await websocket.send_json(
                {"type": "audio_chunk", "audio": "", "is_final": True}
            )

    except Exception as e:
        print(f"TTS streaming error: {str(e)}")
        # Don't fail the whole request if TTS fails
        await websocket.send_json(
            {"type": "tts_error", "message": f"Text-to-speech unavailable: {str(e)}"}
        )


# ============== WebSocket for Camera ==============


@app.websocket("/ws/camera")
async def websocket_camera(websocket: WebSocket):
    """WebSocket endpoint for real-time camera heart rate monitoring"""
    await camera_websocket_endpoint(websocket)


# ============== WebSocket for Voice Chat ==============


@app.websocket("/ws/chat/{patient_id}")
async def websocket_chat(websocket: WebSocket, patient_id: str):
    """
    WebSocket endpoint for real-time voice chat during health check-ins.

    Messages from client:
    - {"type": "text", "content": "message text"}
    - {"type": "audio", "data": "base64_audio", "format": "webm"}
    - {"type": "get_greeting"}
    - {"type": "vital_result", "heart_rate": 72, "hrv": 45, "is_normal": true}
    - {"type": "end_session"}

    Messages to client:
    - {"type": "greeting", "content": "Hello!"}
    - {"type": "response", "content": "AI response", "context": "extracted context"}
    - {"type": "transcription", "text": "transcribed text"}
    - {"type": "vital_response", "content": "Your vitals look great!"}
    - {"type": "audio_chunk", "audio": "base64_audio_chunk", "is_final": false}
    - {"type": "session_summary", "data": {...}}
    - {"type": "error", "message": "error description"}
    """
    await websocket.accept()

    # Create chat agent for this session
    try:
        chat_agent = create_pulse_chat_agent(patient_id)
        session_id = f"{patient_id}_{datetime.utcnow().timestamp()}"
        active_chat_sessions[session_id] = chat_agent
    except Exception as e:
        await websocket.send_json(
            {"type": "error", "message": f"Failed to initialize chat agent: {str(e)}"}
        )
        await websocket.close()
        return

    try:
        while True:
            # Receive message
            data = await websocket.receive_text()
            message = json.loads(data)
            msg_type = message.get("type")

            if msg_type == "get_greeting":
                # Send initial greeting
                greeting = chat_agent.get_greeting()
                await websocket.send_json({"type": "greeting", "content": greeting})
                # Stream TTS audio for greeting
                await stream_tts_to_websocket(websocket, greeting)

            elif msg_type == "text":
                # Process text message
                content = message.get("content", "")
                if content:
                    result = chat_agent.process_message(content)
                    await websocket.send_json(
                        {
                            "type": "response",
                            "content": result["response"],
                            "context": result.get("context_extracted", ""),
                        }
                    )
                    # Stream TTS audio for response
                    await stream_tts_to_websocket(websocket, result["response"])

            elif msg_type == "audio":
                # Transcribe audio and then process
                audio_data = message.get("data", "")
                audio_format = message.get("format", "webm")

                if audio_data:
                    # Transcribe using Groq
                    transcription = await transcribe_base64(audio_data, audio_format)

                    if transcription["success"] and transcription["text"]:
                        # Send transcription first
                        await websocket.send_json(
                            {"type": "transcription", "text": transcription["text"]}
                        )

                        # Then process with chat agent
                        result = chat_agent.process_message(transcription["text"])
                        await websocket.send_json(
                            {
                                "type": "response",
                                "content": result["response"],
                                "context": result.get("context_extracted", ""),
                            }
                        )
                        # Stream TTS audio for response
                        await stream_tts_to_websocket(websocket, result["response"])
                    else:
                        await websocket.send_json(
                            {
                                "type": "error",
                                "message": transcription.get(
                                    "error", "Transcription failed"
                                ),
                            }
                        )

            elif msg_type == "vital_result":
                # Generate response to vital measurement
                heart_rate = message.get("heart_rate", 0)
                hrv = message.get("hrv", 0)
                is_normal = message.get("is_normal", True)

                vital_response = chat_agent.get_vital_response(
                    heart_rate, hrv, is_normal
                )
                await websocket.send_json(
                    {"type": "vital_response", "content": vital_response}
                )
                # Stream TTS audio for vital response
                await stream_tts_to_websocket(websocket, vital_response)

            elif msg_type == "end_session":
                # End the session and return summary
                summary = chat_agent.get_session_summary()
                await websocket.send_json({"type": "session_summary", "data": summary})
                break

            else:
                await websocket.send_json(
                    {"type": "error", "message": f"Unknown message type: {msg_type}"}
                )

    except WebSocketDisconnect:
        print(f"Chat WebSocket disconnected for patient {patient_id}")
    except Exception as e:
        print(f"Chat WebSocket error: {str(e)}")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        # Cleanup session
        if session_id in active_chat_sessions:
            del active_chat_sessions[session_id]


# ============== WebSocket for Triage Continuation ==============


@app.websocket("/ws/triage")
async def websocket_triage(websocket: WebSocket):
    """
    WebSocket endpoint for triage continuation after check-in.
    
    Receives vitals and conversation context from check-in to continue
    the health assessment conversation on the dashboard.
    
    Messages from client:
    - {"type": "init", "vitals": {...}, "conversation_history": [...], "is_normal": bool}
    - {"type": "text", "text": "message text"}
    - {"type": "audio", "audio": "base64_audio"}
    - {"type": "end_session"}
    
    Messages to client:
    - {"type": "greeting", "text": "triage greeting"}
    - {"type": "response", "text": "AI response"}
    - {"type": "transcription", "text": "transcribed text"}
    - {"type": "audio_chunk", "audio": "base64_audio_chunk", "is_final": false}
    - {"type": "session_end"}
    - {"type": "error", "message": "error description"}
    """
    await websocket.accept()
    
    chat_agent = None
    initialized = False
    
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            msg_type = message.get("type")
            
            if msg_type == "init":
                # Initialize triage with context from check-in
                vitals = message.get("vitals", {})
                conversation_history = message.get("conversation_history", [])
                is_normal = message.get("is_normal", True)
                
                # Create chat agent with triage context
                chat_agent = create_pulse_chat_agent("maria_001")
                
                # Build context from check-in conversation
                context_summary = ""
                if conversation_history:
                    # Handle both array of message objects and array-like object with numeric keys
                    messages_list = conversation_history if isinstance(conversation_history, list) else list(conversation_history.values()) if isinstance(conversation_history, dict) else []
                    user_messages = []
                    for m in messages_list:
                        if isinstance(m, dict) and m.get("role") == "user":
                            user_messages.append(m.get("content", ""))
                        elif isinstance(m, str):
                            user_messages.append(m)
                    if user_messages:
                        context_summary = f"During check-in, patient shared: {'; '.join(user_messages[:3])}"
                
                # Generate appropriate triage greeting based on vitals
                hr = vitals.get("heart_rate", 0)
                hrv = vitals.get("hrv", 0)
                
                if is_normal:
                    # Path A: Normal vitals - reinforcement and lifestyle coaching
                    greeting = (
                        f"Your vitals from the check-in look great - heart rate at {hr} bpm "
                        f"and HRV at {round(hrv)} ms are well within healthy ranges. "
                        f"This is wonderful to see! {context_summary + ' ' if context_summary else ''}"
                        f"I'd love to hear more about what's been working well for you. "
                        f"Have you made any changes to your routine recently, or is there anything "
                        f"you'd like to discuss about maintaining your heart health?"
                    )
                else:
                    # Path B: Abnormal vitals - investigation and support
                    concerns = []
                    if hr > 85:
                        concerns.append(f"your heart rate is a bit elevated at {hr} bpm")
                    if hr < 60:
                        concerns.append(f"your heart rate is lower than usual at {hr} bpm")
                    if hrv < 35:
                        concerns.append(f"your HRV at {round(hrv)} ms suggests some stress on your system")
                    
                    concern_text = " and ".join(concerns) if concerns else "some of your readings need attention"
                    
                    greeting = (
                        f"I've reviewed your check-in results, and I noticed {concern_text}. "
                        f"{context_summary + ' ' if context_summary else ''}"
                        f"This doesn't mean something is wrong, but I'd like to understand better. "
                        f"How have you been feeling today? Have you noticed anything different - "
                        f"maybe stress, sleep changes, or any unusual symptoms?"
                    )
                
                initialized = True
                await websocket.send_json({"type": "greeting", "text": greeting})
                await stream_tts_to_websocket(websocket, greeting)
                
            elif msg_type == "text" and initialized and chat_agent:
                # Process text message
                text = message.get("text", "")
                if text:
                    result = chat_agent.process_message(text)
                    response = result.get("response", "I understand. Tell me more.")
                    await websocket.send_json({"type": "response", "text": response})
                    await stream_tts_to_websocket(websocket, response)
                    
            elif msg_type == "audio" and initialized and chat_agent:
                # Process audio message
                audio_data = message.get("audio", "")
                if audio_data:
                    # Transcribe
                    transcript = await transcribe_base64(audio_data)
                    if transcript:
                        await websocket.send_json({"type": "transcription", "text": transcript})
                        # Process transcribed text
                        result = chat_agent.process_message(transcript)
                        response = result.get("response", "I understand. Tell me more.")
                        await websocket.send_json({"type": "response", "text": response})
                        await stream_tts_to_websocket(websocket, response)
                    else:
                        await websocket.send_json({"type": "error", "message": "Could not transcribe audio"})
                        
            elif msg_type == "end_session":
                await websocket.send_json({"type": "session_end"})
                break
                
            else:
                if not initialized:
                    await websocket.send_json({"type": "error", "message": "Session not initialized. Send init message first."})
                else:
                    await websocket.send_json({"type": "error", "message": f"Unknown message type: {msg_type}"})
                    
    except WebSocketDisconnect:
        print("Triage WebSocket disconnected")
    except Exception as e:
        print(f"Triage WebSocket error: {str(e)}")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass


# ============== REST Endpoints for Chat ==============


class ChatMessageRequest(BaseModel):
    patient_id: str
    message: str
    session_id: Optional[str] = None


class AudioTranscribeRequest(BaseModel):
    audio_base64: str
    format: str = "webm"
    language: str = "en"


@app.post("/chat/message")
async def chat_message(request: ChatMessageRequest):
    """
    Send a text message to the chat agent (REST alternative to WebSocket).
    Note: For real-time conversation, prefer the WebSocket endpoint.
    """
    try:
        chat_agent = create_pulse_chat_agent(request.patient_id)

        # If no greeting has been sent, get one first
        greeting = chat_agent.get_greeting()

        # Process the message
        result = chat_agent.process_message(request.message)

        return {
            "success": True,
            "greeting": greeting,
            "response": result["response"],
            "context_extracted": result.get("context_extracted", ""),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat/transcribe")
async def transcribe_audio_endpoint(request: AudioTranscribeRequest):
    """
    Transcribe audio to text using Groq Whisper.
    """
    try:
        result = await transcribe_base64(
            request.audio_base64, request.format, request.language
        )

        if result["success"]:
            return {
                "success": True,
                "text": result["text"],
                "language": result.get("language", "en"),
            }
        else:
            raise HTTPException(
                status_code=400, detail=result.get("error", "Transcription failed")
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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


class VitalAnalyzeRequest(BaseModel):
    patient_id: str
    heart_rate: float
    hrv: float
    quality_score: float = 0.9


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
            "hrv": patient.baseline_hrv,
        },
        "created_at": datetime.utcnow(),
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
        "vitals_deleted": vitals_deleted.deleted_count,
    }


# ============== Vitals Endpoints ==============


@app.post("/vitals", status_code=201)
def create_vital(vital: VitalCreate):
    """Store new vitals measurement (from camera)"""
    # Verify patient exists
    if not get_patient(vital.patient_id):
        raise HTTPException(status_code=404, detail="Patient not found")

    vital_id = store_new_vital(
        vital.patient_id, vital.heart_rate, vital.hrv, vital.quality_score
    )

    # Check for alerts
    alerts = check_vital_alerts(vital.patient_id, vital.heart_rate, vital.hrv)

    return {"message": "Vital recorded", "vital_id": vital_id, "alerts": alerts}


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

    latest = vitals.find_one({"patient_id": patient_id}, sort=[("timestamp", -1)])

    if not latest:
        raise HTTPException(status_code=404, detail="No vitals found")

    latest["_id"] = str(latest["_id"])
    return latest


# ============== AI Agent Analysis Endpoint ==============


@app.post("/vitals/analyze")
def analyze_vitals(request: VitalAnalyzeRequest):
    """
    Store vitals and run AI agent analysis for decompensation detection.

    This endpoint:
    1. Stores the new vital measurement
    2. Runs the 3-agent AI analysis workflow:
       - Daily Vitals Agent: Validates and retrieves context
       - Decompensation Agent: Calculates risk and clinical reasoning
       - Health Literacy Agent: Generates patient-friendly explanation
    3. Returns comprehensive analysis results
    """
    # Verify patient exists
    if not get_patient(request.patient_id):
        raise HTTPException(status_code=404, detail="Patient not found")

    # Store the vital first
    vital_id = store_new_vital(
        request.patient_id, request.heart_rate, request.hrv, request.quality_score
    )

    # Run AI agent analysis
    try:
        analysis = run_agent_analysis(
            patient_id=request.patient_id,
            heart_rate=request.heart_rate,
            hrv=request.hrv,
            quality_score=request.quality_score,
        )
    except Exception as e:
        # Return partial response if AI analysis fails
        return {
            "vital_id": vital_id,
            "patient_id": request.patient_id,
            "analysis_error": str(e),
            "risk_assessment": {
                "score": 0,
                "level": "UNKNOWN",
                "clinical_reasoning": "AI analysis unavailable",
                "recommended_actions": [
                    "Continue monitoring",
                    "Contact provider if concerned",
                ],
            },
            "patient_explanation": "Your vitals have been recorded. Please continue your regular monitoring.",
            "agent_steps": [],
            "alerts": [f"AI analysis failed: {str(e)}"],
        }

    # Return complete response
    return {
        "vital_id": vital_id,
        "patient_id": request.patient_id,
        "current_vitals": analysis.get("current_vitals"),
        "baseline": analysis.get("baseline"),
        "deviations": analysis.get("deviations"),
        "risk_assessment": analysis.get("risk_assessment"),
        "patient_explanation": analysis.get("patient_explanation"),
        "agent_steps": analysis.get("agent_steps", []),
        "alerts": analysis.get("alerts", []),
        "errors": analysis.get("errors", []),
    }


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
        raise HTTPException(
            status_code=400,
            detail="Not enough data for trend analysis (need at least 3 readings)",
        )

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
        concerns.append(
            "Heart rate rising while HRV declining - possible decompensation"
        )
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
                "direction": "rising"
                if hr_trend > 1
                else "falling"
                if hr_trend < -1
                else "stable",
                "slope": round(hr_trend, 2),
            },
            "hrv": {
                "direction": "rising"
                if hrv_trend > 1
                else "falling"
                if hrv_trend < -1
                else "stable",
                "slope": round(hrv_trend, 2),
            },
        },
        "status": status,
        "concerns": concerns,
    }


@app.get("/analytics/{patient_id}/alerts")
def get_alerts(patient_id: str):
    """Check current alerts based on latest vitals and baseline"""
    patient = get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    latest = vitals.find_one({"patient_id": patient_id}, sort=[("timestamp", -1)])

    if not latest:
        return {"patient_id": patient_id, "alerts": [], "status": "no_data"}

    alerts = check_vital_alerts(patient_id, latest["heart_rate"], latest["hrv"])

    return {
        "patient_id": patient_id,
        "timestamp": latest["timestamp"],
        "current_hr": latest["heart_rate"],
        "current_hrv": latest["hrv"],
        "alerts": alerts,
        "alert_count": len(alerts),
    }


@app.get("/analytics/{patient_id}/baseline-comparison")
def compare_to_baseline(patient_id: str):
    """Compare current vitals to baseline"""
    patient = get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    baseline = patient.get("baseline", {})
    if not baseline.get("heart_rate") or not baseline.get("hrv"):
        raise HTTPException(
            status_code=400, detail="No baseline established for patient"
        )

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
            "hrv": round(stats["avg_hrv"], 1),
        },
        "deviation": {
            "heart_rate": {"absolute": round(hr_diff, 1), "percent": round(hr_pct, 1)},
            "hrv": {"absolute": round(hrv_diff, 1), "percent": round(hrv_pct, 1)},
        },
        "assessment": get_assessment(hr_pct, hrv_pct),
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
        alerts.append(
            {
                "type": "high_hr",
                "severity": "warning",
                "message": f"Heart rate elevated: {heart_rate} bpm",
            }
        )
    elif heart_rate > 120:
        alerts.append(
            {
                "type": "high_hr",
                "severity": "critical",
                "message": f"Heart rate critically high: {heart_rate} bpm",
            }
        )

    if heart_rate < 50:
        alerts.append(
            {
                "type": "low_hr",
                "severity": "warning",
                "message": f"Heart rate low: {heart_rate} bpm",
            }
        )

    if hrv < 20:
        alerts.append(
            {
                "type": "low_hrv",
                "severity": "warning",
                "message": f"HRV critically low: {hrv} ms",
            }
        )
    elif hrv < 30:
        alerts.append(
            {
                "type": "low_hrv",
                "severity": "info",
                "message": f"HRV below optimal: {hrv} ms",
            }
        )

    # Baseline comparison
    baseline = get_baseline(patient_id)
    if baseline and baseline.get("heart_rate") and baseline.get("hrv"):
        hr_change = (
            (heart_rate - baseline["heart_rate"]) / baseline["heart_rate"]
        ) * 100
        hrv_change = ((hrv - baseline["hrv"]) / baseline["hrv"]) * 100

        if hr_change > 20:
            alerts.append(
                {
                    "type": "baseline_deviation",
                    "severity": "warning",
                    "message": f"Heart rate {hr_change:.0f}% above baseline",
                }
            )

        if hrv_change < -30:
            alerts.append(
                {
                    "type": "baseline_deviation",
                    "severity": "warning",
                    "message": f"HRV {abs(hrv_change):.0f}% below baseline",
                }
            )

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
