import axios from 'axios';

const api = axios.create({
  baseURL: 'http://localhost:8000',
  headers: {
    'Content-Type': 'application/json',
  },
});

export async function getPatient(patientId) {
  try {
    const response = await api.get(`/patients/${patientId}`);
    return response.data;
  } catch (error) {
    console.error('Error fetching patient:', error);
    throw error;
  }
}

export async function getVitals(patientId, days = 7) {
  try {
    const response = await api.get(`/vitals/${patientId}?days=${days}`);
    return response.data;
  } catch (error) {
    console.error('Error fetching vitals:', error);
    throw error;
  }
}

export async function analyzeVitals(data) {
  try {
    const response = await api.post('/vitals/analyze', {
      patient_id: data.patient_id,
      heart_rate: data.heart_rate,
      hrv: data.hrv,
      quality_score: data.quality_score,
    });
    return response.data;
  } catch (error) {
    console.error('Error analyzing vitals:', error);
    throw error;
  }
}

export async function getAlerts(patientId) {
  try {
    const response = await api.get(`/analytics/${patientId}/alerts`);
    return response.data;
  } catch (error) {
    console.error('Error fetching alerts:', error);
    throw error;
  }
}

export async function getBaselineComparison(patientId) {
  try {
    const response = await api.get(`/analytics/${patientId}/baseline-comparison`);
    return response.data;
  } catch (error) {
    console.error('Error fetching baseline comparison:', error);
    throw error;
  }
}

export default api;
