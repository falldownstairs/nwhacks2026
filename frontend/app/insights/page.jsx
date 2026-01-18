'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import {
  CheckCircle,
  Brain,
  MessageSquare,
  ChevronDown,
  ChevronUp,
  ArrowUp,
  ArrowDown,
  AlertCircle,
  Info,
  Activity,
} from 'lucide-react';
import RiskBadge from '@/components/RiskBadge';
import LoadingSpinner from '@/components/LoadingSpinner';
import SkeletonCard from '@/components/SkeletonCard';
import { getAnalysis, clearAnalysis } from '@/lib/storage';
import { analyzeVitals, getPatient, getVitals } from '@/lib/api';
import { formatDate } from '@/lib/formatters';

export default function InsightsPage() {
  const router = useRouter();
  const [analysisData, setAnalysisData] = useState(null);
  const [patient, setPatient] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [expandedSections, setExpandedSections] = useState({
    agents: true,
    steps: false,
  });

  useEffect(() => {
    async function loadData() {
      setLoading(true);
      try {
        // Get patient data
        const patientData = await getPatient('maria_001');
        setPatient(patientData);

        // Check sessionStorage first
        const storedAnalysis = getAnalysis();
        if (storedAnalysis) {
          setAnalysisData(storedAnalysis);
          setLoading(false);
          return;
        }

        // Fallback: get latest vitals and analyze
        const vitalsResponse = await getVitals('maria_001', 1);
        const vitals = vitalsResponse?.vitals || [];
        if (vitals && vitals.length > 0) {
          const latest = vitals[vitals.length - 1];
          const result = await analyzeVitals({
            patient_id: 'maria_001',
            heart_rate: latest.heart_rate,
            hrv: latest.hrv,
            quality_score: latest.quality_score || 0.9,
          });
          setAnalysisData(result);
        }
      } catch (err) {
        console.error('Error loading insights:', err);
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, []);

  const toggleSection = (section) => {
    setExpandedSections((prev) => ({
      ...prev,
      [section]: !prev[section],
    }));
  };

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto space-y-4">
        <SkeletonCard height="h-40" />
        <SkeletonCard height="h-32" />
        <SkeletonCard height="h-48" />
        <SkeletonCard height="h-32" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-4xl mx-auto text-center py-12">
        <AlertCircle className="w-16 h-16 text-red-500 mx-auto mb-4" />
        <h2 className="text-xl font-semibold mb-2">Error Loading Analysis</h2>
        <p className="text-gray-400 mb-4">{error}</p>
        <button
          onClick={() => router.push('/check-in')}
          className="bg-blue-500 hover:bg-blue-600 text-white px-6 py-2 rounded-lg"
        >
          Run New Analysis
        </button>
      </div>
    );
  }

  if (!analysisData) {
    return (
      <div className="max-w-4xl mx-auto text-center py-12">
        <Brain className="w-16 h-16 text-gray-500 mx-auto mb-4" />
        <h2 className="text-xl font-semibold mb-2">No Analysis Available</h2>
        <p className="text-gray-400 mb-4">Complete a daily check-in to see AI insights</p>
        <button
          onClick={() => router.push('/check-in')}
          className="bg-blue-500 hover:bg-blue-600 text-white px-6 py-2 rounded-lg"
        >
          Start Check-In
        </button>
      </div>
    );
  }

  const baseline = patient?.baseline || { heart_rate: 68, hrv: 45 };
  const currentVitals = analysisData.vitals || {};
  const hrDeviation = baseline.heart_rate
    ? ((currentVitals.heart_rate - baseline.heart_rate) / baseline.heart_rate * 100).toFixed(1)
    : 0;
  const hrvDeviation = baseline.hrv
    ? ((currentVitals.hrv - baseline.hrv) / baseline.hrv * 100).toFixed(1)
    : 0;

  const riskLevel = analysisData.risk_level || 'LOW';
  const riskScore = analysisData.risk_score || 0;
  const clinicalReasoning = analysisData.clinical_reasoning || 'Analysis complete.';
  const patientExplanation = analysisData.patient_explanation || 'Your vitals have been reviewed.';
  const recommendedActions = analysisData.recommended_actions || ['Continue monitoring'];

  const getDeviationColor = (deviation) => {
    const absVal = Math.abs(parseFloat(deviation));
    if (absVal < 10) return 'text-green-400';
    if (absVal < 20) return 'text-yellow-400';
    return 'text-red-400';
  };

  const heroGradients = {
    LOW: 'from-green-900/50 to-gray-800',
    MEDIUM: 'from-yellow-900/50 to-gray-800',
    HIGH: 'from-red-900/50 to-gray-800',
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6 animate-fadeIn">
      {/* Hero Section */}
      <div className={`card bg-gradient-to-r ${heroGradients[riskLevel]} text-center py-8`}>
        <RiskBadge level={riskLevel} score={riskScore} />
        <h1 className="text-2xl font-bold mt-4">{patient?.name || 'Patient'}</h1>
        <p className="text-gray-400 text-sm mt-1">
          Analysis from {formatDate(analysisData.timestamp || new Date().toISOString())}
        </p>
      </div>

      {/* Vitals vs Baseline */}
      <div className="card">
        <h2 className="section-title flex items-center gap-2">
          <Activity className="w-5 h-5 text-blue-400" />
          Vitals vs Baseline
        </h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-gray-400 border-b border-gray-700">
                <th className="text-left py-3 px-2">Metric</th>
                <th className="text-center py-3 px-2">Current</th>
                <th className="text-center py-3 px-2">Baseline</th>
                <th className="text-center py-3 px-2">Deviation</th>
              </tr>
            </thead>
            <tbody>
              <tr className="border-b border-gray-700">
                <td className="py-3 px-2 font-medium">Heart Rate</td>
                <td className="text-center py-3 px-2">{currentVitals.heart_rate} bpm</td>
                <td className="text-center py-3 px-2 text-gray-400">{baseline.heart_rate} bpm</td>
                <td className={`text-center py-3 px-2 ${getDeviationColor(hrDeviation)} flex items-center justify-center gap-1`}>
                  {parseFloat(hrDeviation) > 0 ? <ArrowUp className="w-4 h-4" /> : <ArrowDown className="w-4 h-4" />}
                  {hrDeviation > 0 ? '+' : ''}{hrDeviation}%
                </td>
              </tr>
              <tr>
                <td className="py-3 px-2 font-medium">HRV</td>
                <td className="text-center py-3 px-2">{currentVitals.hrv} ms</td>
                <td className="text-center py-3 px-2 text-gray-400">{baseline.hrv} ms</td>
                <td className={`text-center py-3 px-2 ${getDeviationColor(hrvDeviation)} flex items-center justify-center gap-1`}>
                  {parseFloat(hrvDeviation) > 0 ? <ArrowUp className="w-4 h-4" /> : <ArrowDown className="w-4 h-4" />}
                  {hrvDeviation > 0 ? '+' : ''}{hrvDeviation}%
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      {/* AI Agent Analysis */}
      <div className="card">
        <button
          onClick={() => toggleSection('agents')}
          className="w-full flex items-center justify-between section-title mb-0"
        >
          <span className="flex items-center gap-2">
            <Brain className="w-5 h-5 text-purple-400" />
            AI Agent Analysis
          </span>
          {expandedSections.agents ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
        </button>
        
        {expandedSections.agents && (
          <div className="mt-4 space-y-4">
            {/* Daily Vitals Agent */}
            <div className="bg-gray-700/50 rounded-lg p-4">
              <div className="flex items-center gap-2 text-green-400 font-medium mb-2">
                <CheckCircle className="w-5 h-5" />
                Daily Vitals Agent
              </div>
              <p className="text-gray-300 text-sm">
                Quality score: {Math.round((currentVitals.quality_score || 0.9) * 100)}%<br />
                Retrieved patient baseline and vitals history.
              </p>
            </div>

            {/* Decompensation Agent */}
            <div className="bg-gray-700/50 rounded-lg p-4">
              <div className="flex items-center gap-2 text-blue-400 font-medium mb-2">
                <Brain className="w-5 h-5" />
                Decompensation Agent
              </div>
              <p className="text-gray-300 text-sm whitespace-pre-wrap">{clinicalReasoning}</p>
              <div className="mt-2 text-xs text-gray-500">
                Risk score: {riskScore}/100
              </div>
            </div>

            {/* Health Literacy Agent */}
            <div className="bg-purple-900/30 border border-purple-500/30 rounded-lg p-4">
              <div className="flex items-center gap-2 text-purple-400 font-medium mb-2">
                <MessageSquare className="w-5 h-5" />
                Health Literacy Agent
              </div>
              <p className="text-gray-200 text-base leading-relaxed">{patientExplanation}</p>
            </div>
          </div>
        )}
      </div>

      {/* Recommended Actions */}
      <div className="card">
        <h2 className="section-title flex items-center gap-2">
          <AlertCircle className="w-5 h-5 text-yellow-400" />
          Recommended Actions
        </h2>
        <ul className="space-y-3">
          {recommendedActions.map((action, index) => {
            const isUrgent = riskLevel === 'HIGH' && index === 0;
            return (
              <li
                key={index}
                className={`flex items-start gap-3 p-3 rounded-lg ${
                  isUrgent ? 'bg-red-900/30 border border-red-500/30' : 'bg-gray-700/50'
                }`}
              >
                {isUrgent ? (
                  <AlertCircle className="w-5 h-5 text-red-400 mt-0.5 flex-shrink-0" />
                ) : (
                  <Info className="w-5 h-5 text-blue-400 mt-0.5 flex-shrink-0" />
                )}
                <span className={isUrgent ? 'text-red-200' : 'text-gray-300'}>
                  {index + 1}. {action}
                </span>
              </li>
            );
          })}
        </ul>
      </div>

      {/* Agent Processing Steps */}
      <div className="card">
        <button
          onClick={() => toggleSection('steps')}
          className="w-full flex items-center justify-between section-title mb-0"
        >
          <span className="flex items-center gap-2">
            <CheckCircle className="w-5 h-5 text-green-400" />
            Agent Processing Steps
          </span>
          {expandedSections.steps ? <ChevronUp className="w-5 h-5" /> : <ChevronDown className="w-5 h-5" />}
        </button>
        
        {expandedSections.steps && (
          <ul className="mt-4 space-y-2 font-mono text-sm">
            {[
              'validate_input',
              'retrieve_baseline',
              'get_vitals_history',
              'calculate_deviations',
              'assess_risk',
              'generate_clinical_reasoning',
              'create_patient_explanation',
            ].map((step) => (
              <li key={step} className="flex items-center gap-2 text-gray-400">
                <CheckCircle className="w-4 h-4 text-green-500" />
                {step}
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Run New Analysis Button */}
      <div className="text-center pb-8">
        <button
          onClick={() => {
            clearAnalysis();
            router.push('/check-in');
          }}
          className="bg-blue-500 hover:bg-blue-600 text-white px-8 py-3 rounded-xl font-medium transition-all hover:scale-105"
        >
          Run New Analysis
        </button>
      </div>
    </div>
  );
}
