'use client';

import { useState, useEffect, useCallback } from 'react';
import { getPatient, getVitals, getAlerts } from '@/lib/api';

export function usePatientData(patientId) {
  const [patient, setPatient] = useState(null);
  const [vitals, setVitals] = useState([]);
  const [latestVital, setLatestVital] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchData = useCallback(async () => {
    if (!patientId) return;

    setLoading(true);
    setError(null);

    try {
      const [patientData, vitalsResponse, alertsData] = await Promise.all([
        getPatient(patientId),
        getVitals(patientId, 7),
        getAlerts(patientId),
      ]);

      const vitalsData = vitalsResponse?.vitals || [];
      setPatient(patientData);
      setVitals(vitalsData);
      setLatestVital(vitalsData.length > 0 ? vitalsData[vitalsData.length - 1] : null);
      setAlerts(alertsData.alerts || []);
    } catch (err) {
      console.error('Error fetching patient data:', err);
      setError(err.message || 'Failed to fetch patient data');
    } finally {
      setLoading(false);
    }
  }, [patientId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return {
    patient,
    vitals,
    latestVital,
    alerts,
    loading,
    error,
    refetch: fetchData,
  };
}

export default usePatientData;
