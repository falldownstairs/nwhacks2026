'use client';

import {
  CheckCircle,
  Circle,
  AlertTriangle,
  AlertCircle,
  Activity,
  TrendingUp,
  Calendar,
  DollarSign,
  Clock,
  Home,
  Building2,
} from 'lucide-react';

const traditionalEvents = [
  { days: '1-25', icon: CheckCircle, color: 'green', label: 'Normal monitoring', faded: true },
  { days: '26-28', icon: Circle, color: 'yellow', label: 'Vitals declining (unnoticed)', faded: true },
  { days: '29', icon: AlertTriangle, color: 'orange', label: 'Symptoms worsening' },
  { days: '30', icon: Building2, color: 'red', label: 'ER VISIT', highlight: true },
];

const aiAssistedEvents = [
  { days: '1-25', icon: CheckCircle, color: 'green', label: 'AI monitoring active' },
  { days: '26-27', icon: Activity, color: 'yellow', label: 'Pattern detected' },
  { days: '28', icon: AlertCircle, color: 'blue', label: 'HIGH RISK ALERT', highlight: true },
  { days: '28', icon: CheckCircle, color: 'green', label: 'Telehealth scheduled' },
  { days: '29-30', icon: TrendingUp, color: 'green', label: 'Vitals stabilizing' },
];

const stats = [
  {
    label: 'Detection Time',
    ai: 'Day 28',
    traditional: 'Day 30',
    icon: Calendar,
  },
  {
    label: 'Patient Outcome',
    ai: 'Managed at Home',
    traditional: 'Hospitalized',
    icon: Home,
  },
  {
    label: 'Cost Impact',
    ai: '$150 Telehealth',
    traditional: '$12,000+ ER',
    icon: DollarSign,
  },
  {
    label: 'Recovery Time',
    ai: '2 days',
    traditional: '7+ days',
    icon: Clock,
  },
];

function TimelineEvent({ event, side }) {
  const Icon = event.icon;
  const colors = {
    green: 'text-green-400 bg-green-500/20',
    yellow: 'text-yellow-400 bg-yellow-500/20',
    orange: 'text-orange-400 bg-orange-500/20',
    red: 'text-red-400 bg-red-500/20',
    blue: 'text-blue-400 bg-blue-500/20',
  };

  return (
    <div
      className={`flex items-center gap-3 p-3 rounded-lg transition-all ${
        event.highlight
          ? `${colors[event.color]} ${event.color === 'red' ? 'animate-pulse-slow' : 'ring-2 ring-blue-500/50'}`
          : event.faded
          ? 'opacity-50'
          : ''
      }`}
    >
      <div className={`p-2 rounded-full ${colors[event.color]}`}>
        <Icon className={`w-5 h-5 ${colors[event.color].split(' ')[0]}`} />
      </div>
      <div>
        <p className="text-sm text-gray-400">Day {event.days}</p>
        <p className={`font-medium ${event.highlight ? 'text-lg' : ''}`}>{event.label}</p>
      </div>
    </div>
  );
}

export default function TimelinePage() {
  return (
    <div className="max-w-6xl mx-auto space-y-8 animate-fadeIn">
      {/* Header */}
      <div className="text-center">
        <h1 className="text-3xl md:text-4xl font-bold mb-2">Early Detection Impact</h1>
        <p className="text-gray-400 text-lg">Traditional Care vs AI-Assisted Monitoring</p>
      </div>

      {/* Timelines Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 relative">
        {/* Traditional Care */}
        <div className="card">
          <h2 className="text-xl font-semibold mb-6 text-gray-400 flex items-center gap-2">
            <Building2 className="w-5 h-5" />
            Traditional Care Pathway
          </h2>
          <div className="relative">
            <div className="absolute left-6 top-0 bottom-0 w-0.5 bg-gray-600" />
            <div className="space-y-4 relative">
              {traditionalEvents.map((event, index) => (
                <TimelineEvent key={index} event={event} side="left" />
              ))}
            </div>
          </div>
        </div>

        {/* AI-Assisted */}
        <div className="card border-2 border-blue-500/30">
          <h2 className="text-xl font-semibold mb-6 text-blue-400 flex items-center gap-2">
            <Activity className="w-5 h-5" />
            AI-Assisted Pathway
          </h2>
          <div className="relative">
            <div className="absolute left-6 top-0 bottom-0 w-0.5 bg-blue-500/50" />
            <div className="space-y-4 relative">
              {aiAssistedEvents.map((event, index) => (
                <TimelineEvent key={index} event={event} side="right" />
              ))}
            </div>
          </div>
        </div>

        {/* Center Impact Metric - Desktop */}
        <div className="hidden lg:flex absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 z-10">
          <div className="bg-gradient-to-br from-blue-600 to-green-600 rounded-2xl p-6 text-center shadow-2xl border-4 border-white/20 animate-pulse-slow">
            <Calendar className="w-8 h-8 mx-auto mb-2" />
            <p className="text-6xl font-bold">2</p>
            <p className="text-sm font-semibold">DAYS EARLIER</p>
            <div className="mt-3 pt-3 border-t border-white/30">
              <p className="text-xl font-bold">$12,000</p>
              <p className="text-xs">SAVED</p>
            </div>
            <p className="text-xs mt-2 opacity-80">ER VISIT PREVENTED</p>
          </div>
        </div>
      </div>

      {/* Mobile Impact Metric */}
      <div className="lg:hidden">
        <div className="bg-gradient-to-br from-blue-600 to-green-600 rounded-2xl p-6 text-center shadow-2xl">
          <Calendar className="w-10 h-10 mx-auto mb-2" />
          <p className="text-5xl font-bold">2</p>
          <p className="text-lg font-semibold">DAYS EARLIER</p>
          <div className="flex justify-center gap-6 mt-4 pt-4 border-t border-white/30">
            <div>
              <p className="text-2xl font-bold">$12,000</p>
              <p className="text-sm">SAVED</p>
            </div>
            <div className="border-l border-white/30 pl-6">
              <p className="text-2xl font-bold">1</p>
              <p className="text-sm">ER PREVENTED</p>
            </div>
          </div>
        </div>
      </div>

      {/* Statistics Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {stats.map((stat, index) => {
          const Icon = stat.icon;
          return (
            <div key={index} className="card overflow-hidden p-0">
              <div className="p-3 bg-gray-700/50 border-b border-gray-700">
                <div className="flex items-center gap-2 text-gray-400">
                  <Icon className="w-4 h-4" />
                  <span className="text-sm">{stat.label}</span>
                </div>
              </div>
              <div className="grid grid-cols-2">
                <div className="p-4 bg-green-900/30 border-r border-gray-700">
                  <p className="text-xs text-green-400 mb-1">AI-Assisted</p>
                  <p className="font-bold text-green-300">{stat.ai}</p>
                </div>
                <div className="p-4 bg-red-900/30">
                  <p className="text-xs text-red-400 mb-1">Traditional</p>
                  <p className="font-bold text-red-300">{stat.traditional}</p>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Bottom CTA */}
      <div className="card bg-gradient-to-r from-blue-900/50 to-purple-900/50 text-center py-8">
        <h3 className="text-2xl font-bold mb-2">See It In Action</h3>
        <p className="text-gray-400 mb-6">
          Experience how our AI agents detect early warning signs
        </p>
        <a
          href="/check-in"
          className="inline-flex items-center gap-2 bg-blue-500 hover:bg-blue-600 text-white px-8 py-3 rounded-xl font-medium transition-all hover:scale-105"
        >
          <Activity className="w-5 h-5" />
          Start Demo Check-In
        </a>
      </div>
    </div>
  );
}
