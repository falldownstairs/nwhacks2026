import axios from "axios";

// Use environment variable for backend URL, fallback to localhost for development
const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";
const WS_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000";

const api = axios.create({
    baseURL: BACKEND_URL,
    headers: {
        "Content-Type": "application/json",
        "ngrok-skip-browser-warning": "true",  // Skip ngrok interstitial page
    },
});

export async function getPatient(patientId) {
    try {
        const response = await api.get(`/patients/${patientId}`);
        return response.data;
    } catch (error) {
        console.error("Error fetching patient:", error);
        throw error;
    }
}

export async function getVitals(patientId, days = 7) {
    try {
        const response = await api.get(`/vitals/${patientId}?days=${days}`);
        return response.data;
    } catch (error) {
        console.error("Error fetching vitals:", error);
        throw error;
    }
}

export async function analyzeVitals(data) {
    try {
        const response = await api.post("/vitals/analyze", {
            patient_id: data.patient_id,
            heart_rate: data.heart_rate,
            hrv: data.hrv,
            quality_score: data.quality_score,
        });
        return response.data;
    } catch (error) {
        console.error("Error analyzing vitals:", error);
        throw error;
    }
}

export async function getAlerts(patientId) {
    try {
        const response = await api.get(`/analytics/${patientId}/alerts`);
        return response.data;
    } catch (error) {
        console.error("Error fetching alerts:", error);
        throw error;
    }
}

export async function getBaselineComparison(patientId) {
    try {
        const response = await api.get(
            `/analytics/${patientId}/baseline-comparison`,
        );
        return response.data;
    } catch (error) {
        console.error("Error fetching baseline comparison:", error);
        throw error;
    }
}

// ============== Chat API Functions ==============

/**
 * Send a text message to the chat agent (REST fallback)
 * For real-time chat, use the WebSocket connection instead.
 */
export async function sendChatMessage(patientId, message) {
    try {
        const response = await api.post("/chat/message", {
            patient_id: patientId,
            message: message,
        });
        return response.data;
    } catch (error) {
        console.error("Error sending chat message:", error);
        throw error;
    }
}

/**
 * Transcribe audio to text using Groq Whisper (REST fallback)
 * For real-time transcription, use the WebSocket connection instead.
 */
export async function transcribeAudio(
    audioBase64,
    format = "webm",
    language = "en",
) {
    try {
        const response = await api.post("/chat/transcribe", {
            audio_base64: audioBase64,
            format: format,
            language: language,
        });
        return response.data;
    } catch (error) {
        console.error("Error transcribing audio:", error);
        throw error;
    }
}

/**
 * Create a WebSocket connection for voice chat
 * @param {string} patientId - Patient ID for the chat session
 * @returns {WebSocket} WebSocket connection
 */
export function createChatWebSocket(patientId) {
    return new WebSocket(`${WS_URL}/ws/chat/${patientId}`);
}

export default api;
