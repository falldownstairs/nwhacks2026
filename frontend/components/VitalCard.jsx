'use client';

export default function VitalCard({ label, value, unit, baseline, icon: Icon, riskLevel = 'low' }) {
  const deviation = baseline ? ((value - baseline) / baseline * 100).toFixed(1) : 0;
  const isPositive = deviation >= 0;
  const arrow = Math.abs(deviation) < 5 ? '→' : isPositive ? '↑' : '↓';

  const bgColors = {
    low: 'bg-green-50 border-green-200',
    medium: 'bg-yellow-50 border-yellow-200',
    high: 'bg-red-50 border-red-200',
  };

  const textColors = {
    low: 'text-green-700',
    medium: 'text-yellow-700',
    high: 'text-red-700',
  };

  const iconColors = {
    low: 'text-green-500',
    medium: 'text-yellow-500',
    high: 'text-red-500',
  };

  const level = riskLevel?.toLowerCase() || 'low';

  return (
    <div className={`rounded-xl p-4 border-2 ${bgColors[level]} transition-all duration-200`}>
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-2">
          {Icon && <Icon className={`w-5 h-5 ${iconColors[level]}`} />}
          <span className="text-sm text-gray-500">{label}</span>
        </div>
        <div className={`text-sm font-medium ${textColors[level]}`}>
          {arrow} {isPositive ? '+' : ''}{deviation}%
        </div>
      </div>
      <div className="mt-2">
        <span className={`text-3xl font-bold ${textColors[level]}`}>{value}</span>
        <span className="text-lg text-gray-500 ml-1">{unit}</span>
      </div>
      {baseline && (
        <div className="mt-1 text-xs text-gray-400">
          Baseline: {baseline} {unit}
        </div>
      )}
    </div>
  );
}
