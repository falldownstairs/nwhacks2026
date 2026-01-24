'use client';

import '@/lib/chartConfig';
import { Activity, Heart, RefreshCw } from 'lucide-react';
import Link from 'next/link';
import { Line } from 'react-chartjs-2';

import ChatWidget from '@/components/ChatWidget';
import RiskBadge from '@/components/RiskBadge';
import SkeletonCard from '@/components/SkeletonCard';
import VitalCard from '@/components/VitalCard';
import { usePatientData } from '@/hooks/usePatientData';
import { formatRelativeTime, getDayName } from '@/lib/formatters';
import { calculateRiskLevel } from '@/lib/riskCalculator';

export default function Dashboard() {
  const { patient, vitals, latestVital, alerts, loading, error, refetch } = usePatientData('maria_001');

  if (loading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <SkeletonCard height="h-64" />
        <SkeletonCard height="h-64" />
        <SkeletonCard height="h-80" />
        <SkeletonCard height="h-80" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] gap-4">
        <div className="text-red-500 text-xl">Error: {error}</div>
        <button
          onClick={refetch}
          className="flex items-center gap-2 bg-blue-500 hover:bg-blue-600 text-white px-4 py-2 rounded-lg"
        >
          <RefreshCw className="w-4 h-4" />
          Try Again
        </button>
      </div>
    );
  }

  const baseline = patient?.baseline || { heart_rate: 68, hrv: 45 };
  const latestHR = latestVital?.heart_rate || 0;
  const latestHRV = latestVital?.hrv || 0;
  
  const risk = calculateRiskLevel(latestHR, latestHRV, baseline.heart_rate, baseline.hrv);
  const riskLevel = alerts.length > 0 ? (alerts[0]?.severity || risk.level).toLowerCase() : risk.level.toLowerCase();

  // Chart data
  const chartLabels = vitals.slice(-7).map((v) => getDayName(v.timestamp));
  const hrData = vitals.slice(-7).map((v) => v.heart_rate);
  const hrvData = vitals.slice(-7).map((v) => v.hrv);

  const chartData = {
    labels: chartLabels,
    datasets: [
      {
        label: 'Heart Rate (bpm)',
        data: hrData,
        borderColor: 'rgb(59, 130, 246)',
        backgroundColor: 'rgba(59, 130, 246, 0.1)',
        tension: 0.3,
        fill: true,
      },
      {
        label: 'HRV (ms)',
        data: hrvData,
        borderColor: 'rgb(34, 197, 94)',
        backgroundColor: 'rgba(34, 197, 94, 0.1)',
        tension: 0.3,
        fill: true,
      },
    ],
  };

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: 'top',
        labels: { color: '#9ca3af' },
      },
    },
    scales: {
      x: {
        ticks: { color: '#9ca3af' },
        grid: { color: '#374151' },
      },
      y: {
        ticks: { color: '#9ca3af' },
        grid: { color: '#374151' },
      },
    },
  };

  return (
    <div className="space-y-6 animate-fadeIn">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Welcome back, {patient?.name?.split(' ')[0] || 'Patient'}</h1>
          <p className="text-gray-400">
            {patient?.age}yo • {patient?.conditions?.join(', ') || 'Heart Failure'}
          </p>
        </div>
        <button
          onClick={refetch}
          className="flex items-center gap-2 text-gray-400 hover:text-white"
        >
          <RefreshCw className="w-4 h-4" />
          Refresh
        </button>
      </div>

      {/* Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Card 1: Current Vitals */}
        <div className="card animate-fadeIn" style={{ animationDelay: '0.1s' }}>
          <h2 className="section-title flex items-center gap-2">
            <Heart className="w-5 h-5 text-red-400" />
            Current Vitals
          </h2>
          <div className="space-y-4">
            <VitalCard
              label="Heart Rate"
              value={latestHR}
              unit="bpm"
              baseline={baseline.heart_rate}
              icon={Heart}
              riskLevel={riskLevel}
            />
            <VitalCard
              label="Heart Rate Variability"
              value={latestHRV}
              unit="ms"
              baseline={baseline.hrv}
              icon={Activity}
              riskLevel={riskLevel}
            />
          </div>
          {latestVital && (
            <p className="text-xs text-gray-500 mt-3">
              Last updated: {formatRelativeTime(latestVital.timestamp)}
            </p>
          )}
        </div>

        {/* Card 2: Risk Assessment */}
        <div className="card animate-fadeIn" style={{ animationDelay: '0.2s' }}>
          <h2 className="section-title flex items-center gap-2">
            <Activity className="w-5 h-5 text-blue-400" />
            Risk Assessment
          </h2>
          <div className="flex flex-col items-center justify-center py-6">
            <RiskBadge level={risk.level} score={risk.score} />
            {risk.factors.length > 0 && (
              <div className="mt-4 text-sm text-gray-400">
                {risk.factors.map((f, i) => (
                  <div key={i}>• {f.factor}: +{f.points} pts</div>
                ))}
              </div>
            )}
          </div>
          {latestVital && (
            <p className="text-xs text-gray-500 text-center">
              Updated: {formatRelativeTime(latestVital.timestamp)}
            </p>
          )}
        </div>

        {/* Card 3: 7-Day Trend Chart */}
        <div className="card animate-fadeIn" style={{ animationDelay: '0.3s' }}>
          <h2 className="section-title flex items-center gap-2">
            <Activity className="w-5 h-5 text-green-400" />
            7-Day Trend
          </h2>
          <div className="h-[300px]">
            {vitals.length > 0 ? (
              <Line data={chartData} options={chartOptions} />
            ) : (
              <div className="flex items-center justify-center h-full text-gray-500">
                No vitals data available
              </div>
            )}
          </div>
        </div>

        {/* Card 4: Quick Actions */}
        <div className="card animate-fadeIn" style={{ animationDelay: '0.4s' }}>
          <h2 className="section-title flex items-center gap-2">
            <Activity className="w-5 h-5 text-purple-400" />
            Quick Actions
          </h2>
          <div className="space-y-3">
            <Link
              href="/check-in"
              className="flex items-center justify-center gap-2 w-full bg-blue-500 hover:bg-blue-600 text-white py-3 px-4 rounded-lg transition-colors"
            >
              <Activity className="w-5 h-5" />
              Start Daily Check-In
            </Link>
          </div>
        </div>
      </div>

      {/* Floating Chat Widget */}
      <ChatWidget patientId="maria_001" />
    </div>
  );
}
