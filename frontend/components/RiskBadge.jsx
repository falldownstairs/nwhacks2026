'use client';

import { CheckCircle, AlertTriangle, AlertCircle } from 'lucide-react';

export default function RiskBadge({ level, score }) {
  const config = {
    LOW: {
      bg: 'bg-green-500',
      icon: CheckCircle,
      text: 'LOW RISK',
    },
    MEDIUM: {
      bg: 'bg-yellow-500',
      icon: AlertTriangle,
      text: 'MEDIUM RISK',
    },
    HIGH: {
      bg: 'bg-red-500 animate-pulse',
      icon: AlertCircle,
      text: 'HIGH RISK',
    },
  };

  const levelUpper = level?.toUpperCase() || 'LOW';
  const { bg, icon: Icon, text } = config[levelUpper] || config.LOW;

  return (
    <div className="flex flex-col items-center gap-2">
      <div className={`${bg} text-white px-6 py-3 md:px-8 md:py-4 rounded-full font-semibold flex items-center gap-2 text-lg md:text-xl shadow-lg`}>
        <Icon className="w-5 h-5 md:w-6 md:h-6" />
        <span>{text}</span>
      </div>
      <div className="text-gray-400 text-sm">
        Score: {score ?? 0}/100
      </div>
    </div>
  );
}
