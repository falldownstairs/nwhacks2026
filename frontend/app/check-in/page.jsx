'use client';

import VoiceChat from '@/components/VoiceChat';
import { analyzeVitals } from '@/lib/api';
import { saveAnalysis, saveVitals } from '@/lib/storage';
import { Activity, AlertCircle, AlertTriangle, Camera, CheckCircle, Heart, MessageCircle, Wifi, WifiOff } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useRef, useState } from 'react';

const demoScenarios = {
  normal: {
    label: 'Normal Vitals',
    description: 'HR ~70, HRV ~44',
    baseHR: 70,
    baseHRV: 44,
    quality: 0.92,
    icon: CheckCircle,
    color: 'green',
  },
  medium: {
    label: 'Medium Risk',
    description: 'HR ~78, HRV ~35',
    baseHR: 78,
    baseHRV: 35,
    quality: 0.85,
    icon: AlertTriangle,
    color: 'yellow',
  },
  high: {
    label: 'High Risk',
    description: 'HR ~89, HRV ~28',
    baseHR: 89,
    baseHRV: 28,
    quality: 0.88,
    icon: AlertCircle,
    color: 'red',
  },
};

function generateVitals(mode) {
  const scenario = demoScenarios[mode];
  const variation = () => Math.floor(Math.random() * 5) - 2;
  return {
    heart_rate: scenario.baseHR + variation(),
    hrv: scenario.baseHRV + variation(),
    quality_score: scenario.quality,
  };
}

export default function CheckInPage() {
  const router = useRouter();
  const wsRef = useRef(null);
  const hrHistoryRef = useRef([]);

  const [step, setStep] = useState(1);
  const [countdown, setCountdown] = useState(30);
  const [progress, setProgress] = useState(0);
  const [capturedVitals, setCapturedVitals] = useState(null);
  const [demoMode, setDemoMode] = useState('normal');
  const [analyzing, setAnalyzing] = useState(false);
  const [useRealCamera, setUseRealCamera] = useState(true);
  
  // Voice chat state
  const [chatActive, setChatActive] = useState(false);
  const [vitalsForChat, setVitalsForChat] = useState(null);
  
  // WebSocket camera state
  const [connected, setConnected] = useState(false);
  const [connectionError, setConnectionError] = useState(null);
  const [frameData, setFrameData] = useState(null);
  const [faceDetected, setFaceDetected] = useState(false);
  const [currentHR, setCurrentHR] = useState(null);
  const [currentHRV, setCurrentHRV] = useState(null);
  const [calibrationProgress, setCalibrationProgress] = useState(0);
  
  // Refs to avoid useEffect dependency issues with countdown
  const currentHRVRef = useRef(null);

  // Connect to WebSocket camera
  const connectCamera = useCallback(() => {
    setConnectionError(null);
    
    const ws = new WebSocket('ws://localhost:8000/ws/camera');
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('Camera WebSocket connected');
      setConnected(true);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        setFrameData(data.frame);
        setFaceDetected(data.face_detected);
        setCalibrationProgress(data.calibration_progress || 0);
        
        if (data.heart_rate) {
          setCurrentHR(data.heart_rate);
          hrHistoryRef.current.push(data.heart_rate);
          if (hrHistoryRef.current.length > 30) {
            hrHistoryRef.current.shift();
          }
        }
        // HRV can be null if calculation is still initializing
        if (data.hrv !== undefined && data.hrv !== null) {
          setCurrentHRV(data.hrv);
          currentHRVRef.current = data.hrv;  // Keep ref in sync
        }
      } catch (e) {
        console.error('Error parsing camera data:', e);
      }
    };

    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
      setConnectionError('Failed to connect to camera. Make sure the backend is running.');
      setConnected(false);
    };

    ws.onclose = () => {
      console.log('Camera WebSocket closed');
      setConnected(false);
    };
  }, []);

  // Disconnect camera
  const disconnectCamera = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.send('stop');
      wsRef.current.close();
      wsRef.current = null;
    }
    setConnected(false);
    setFrameData(null);
  }, []);

  // Countdown effect
  useEffect(() => {
    if (step !== 2) return;

    const interval = setInterval(() => {
      setCountdown((prev) => {
        if (prev <= 1) {
          clearInterval(interval);
          
          // Generate final vitals
          let vitals;
          if (useRealCamera && hrHistoryRef.current.length > 0) {
            const avgHR = Math.round(
              hrHistoryRef.current.reduce((a, b) => a + b, 0) / hrHistoryRef.current.length
            );
            // Use ref for HRV to avoid dependency issues
            const hrvValue = currentHRVRef.current;
            vitals = {
              heart_rate: avgHR,
              // Use real HRV if available (RMSSD in ms), otherwise estimate based on HR
              hrv: hrvValue !== null && hrvValue !== undefined 
                ? hrvValue 
                : Math.max(20, 50 - Math.abs(avgHR - 70)),
              quality_score: 0.85,
            };
          } else {
            vitals = generateVitals(demoMode);
          }
          
          setCapturedVitals(vitals);
          setVitalsForChat(vitals);  // Send vitals to chat for AI response
          setStep(3);
          disconnectCamera();
          return 0;
        }
        return prev - 1;
      });
      setProgress((prev) => Math.min(prev + 100 / 30, 100));
    }, 1000);

    return () => clearInterval(interval);
  }, [step, demoMode, useRealCamera, disconnectCamera]);

  // Analyze and redirect
  useEffect(() => {
    if (step !== 3 || !capturedVitals) return;

    setAnalyzing(true);
    const timeout = setTimeout(async () => {
      try {
        const result = await analyzeVitals({
          patient_id: 'maria_001',
          ...capturedVitals,
        });
        saveVitals(capturedVitals);
        saveAnalysis(result);
        router.push('/');
      } catch (error) {
        console.error('Analysis failed:', error);
        setAnalyzing(false);
      }
    }, 2000);

    return () => clearTimeout(timeout);
  }, [step, capturedVitals, router]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      disconnectCamera();
      setChatActive(false);
    };
  }, [disconnectCamera]);

  const startMeasurement = () => {
    hrHistoryRef.current = [];
    currentHRVRef.current = null;
    setCurrentHR(null);
    setCurrentHRV(null);
    setStep(2);
    setCountdown(30);
    setProgress(0);
    setChatActive(true);  // Activate voice chat
    setVitalsForChat(null);  // Reset vitals for chat
    
    if (useRealCamera) {
      connectCamera();
    }
  };

  return (
    <div className={`mx-auto animate-fadeIn ${step === 2 || step === 3 ? 'max-w-5xl' : 'max-w-2xl'}`}>
      {/* Step 1: Welcome */}
      {step === 1 && (
        <div className="card text-center py-8">
          <Heart className="w-16 h-16 text-red-400 mx-auto mb-6 animate-heartbeat" />
          <h1 className="text-3xl font-bold mb-2">Daily Check-In</h1>
          <p className="text-xl text-gray-300 mb-2">Maria Gonzalez</p>
          <p className="text-gray-400 mb-6">This will take 30 seconds</p>

          {/* Camera Mode Toggle */}
          <div className="flex items-center justify-center gap-4 mb-6">
            <button
              onClick={() => setUseRealCamera(true)}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-all ${
                useRealCamera 
                  ? 'bg-blue-500 text-white' 
                  : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
              }`}
            >
              <Camera className="w-5 h-5" />
              Real Camera (Python)
            </button>
            <button
              onClick={() => setUseRealCamera(false)}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-all ${
                !useRealCamera 
                  ? 'bg-purple-500 text-white' 
                  : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
              }`}
            >
              <Activity className="w-5 h-5" />
              Demo Mode
            </button>
          </div>

          <button
            onClick={startMeasurement}
            className="bg-blue-500 hover:bg-blue-600 text-white text-xl font-semibold px-8 py-4 rounded-xl transition-all hover:scale-105"
          >
            Start Measurement
          </button>

          {/* Demo Mode Selector */}
          {!useRealCamera && (
            <div className="mt-8 pt-6 border-t border-gray-700">
              <p className="text-sm text-gray-500 mb-4">Select Demo Scenario</p>
              <div className="flex flex-wrap justify-center gap-3">
                {Object.entries(demoScenarios).map(([key, scenario]) => {
                  const Icon = scenario.icon;
                  const isActive = demoMode === key;
                  const colors = {
                    green: isActive ? 'bg-green-500 text-white' : 'border-green-500 text-green-400',
                    yellow: isActive ? 'bg-yellow-500 text-white' : 'border-yellow-500 text-yellow-400',
                    red: isActive ? 'bg-red-500 text-white' : 'border-red-500 text-red-400',
                  };
                  return (
                    <button
                      key={key}
                      onClick={() => setDemoMode(key)}
                      className={`flex flex-col items-center gap-1 px-4 py-3 rounded-xl border-2 transition-all ${
                        isActive ? colors[scenario.color] : `bg-transparent ${colors[scenario.color]} border-2`
                      }`}
                    >
                      <Icon className="w-5 h-5" />
                      <span className="font-medium">{scenario.label}</span>
                      <span className="text-xs opacity-75">{scenario.description}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {useRealCamera && (
            <div className="mt-6 p-4 bg-blue-900/30 rounded-xl text-sm text-blue-200">
              <p className="font-medium mb-2">📹 Using Python OpenCV Camera</p>
              <p className="text-blue-300">• Uses the same camera.py from the backend</p>
              <p className="text-blue-300">• Haar cascade face detection</p>
              <p className="text-blue-300">• FFT-based heart rate analysis</p>
            </div>
          )}
        </div>
      )}

      {/* Step 2: Camera Capture with Voice Chat */}
      {step === 2 && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Left Side: Camera Feed */}
          <div className="card text-center py-6">
            {useRealCamera ? (
              <>
                {/* Connection Status */}
                <div className="flex items-center justify-center gap-2 mb-4">
                  {connected ? (
                    <span className="flex items-center gap-2 text-green-400 text-sm">
                      <Wifi className="w-4 h-4" />
                      Connected to Python Camera
                    </span>
                  ) : (
                    <span className="flex items-center gap-2 text-yellow-400 text-sm">
                      <WifiOff className="w-4 h-4" />
                      Connecting...
                    </span>
                  )}
                </div>

                {/* Video Frame */}
                <div className="relative w-full aspect-video bg-black rounded-xl overflow-hidden mb-4">
                  {frameData ? (
                    <img
                      src={`data:image/jpeg;base64,${frameData}`}
                      alt="Camera feed"
                      className="w-full h-full object-contain"
                    />
                  ) : (
                    <div className="absolute inset-0 flex items-center justify-center">
                      <div className="text-center">
                        <div className="w-12 h-12 border-4 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
                        <p className="text-gray-400">Initializing camera...</p>
                      </div>
                    </div>
                  )}
                  
                  {/* Overlay Stats */}
                  {frameData && (
                    <div className="absolute top-4 right-4 flex flex-col gap-2">
                      <div className={`px-3 py-1 rounded-full text-sm font-medium ${
                        faceDetected ? 'bg-green-500/80' : 'bg-red-500/80'
                      }`}>
                        {faceDetected ? '✓ Face Detected' : '✗ No Face'}
                      </div>
                      {currentHR && (
                        <div className="bg-blue-500/80 px-3 py-1 rounded-full text-sm font-bold">
                          ❤️ {currentHR} BPM
                        </div>
                      )}
                    </div>
                  )}
                </div>

                {connectionError && (
                  <div className="bg-red-500/20 text-red-300 p-3 rounded-lg mb-4 text-sm">
                    {connectionError}
                  </div>
                )}

                {/* Calibration progress */}
                {!currentHR && calibrationProgress > 0 && (
                  <div className="mb-4">
                    <p className="text-sm text-gray-400 mb-1">Calibrating PPG signal...</p>
                    <div className="w-full bg-gray-700 rounded-full h-2">
                      <div 
                        className="bg-orange-500 h-full rounded-full transition-all"
                        style={{ width: `${calibrationProgress}%` }}
                      />
                    </div>
                  </div>
                )}
              </>
            ) : (
              /* Demo mode animation */
              <div className="relative w-40 h-40 mx-auto mb-6">
                <div className="absolute inset-0 rounded-full bg-blue-500/20 animate-ping" />
                <div className="absolute inset-4 rounded-full bg-blue-500/40 animate-pulse" />
                <div className="absolute inset-8 rounded-full bg-blue-500 flex items-center justify-center animate-heartbeat">
                  <Heart className="w-12 h-12 text-white" />
                </div>
              </div>
            )}

            <p className="text-4xl font-bold text-blue-400 mb-2">{countdown}s</p>
            <p className="text-gray-400 mb-4">
              {useRealCamera 
                ? (faceDetected ? 'Measuring vitals...' : 'Position your face in the frame')
                : 'Simulating measurement...'}
            </p>

            <div className="w-full bg-gray-700 rounded-full h-3 overflow-hidden">
              <div
                className="bg-blue-500 h-full rounded-full transition-all duration-1000"
                style={{ width: `${progress}%` }}
              />
            </div>
            <p className="text-sm text-gray-500 mt-2">{Math.round(progress)}% complete</p>
          </div>

          {/* Right Side: Voice Chat */}
          <div className="flex flex-col">
            <VoiceChat 
              patientId="maria_001"
              isActive={chatActive}
              vitalsData={vitalsForChat}
              className="flex-1"
            />
            <div className="mt-3 p-3 bg-blue-900/20 rounded-lg">
              <p className="text-xs text-blue-300 flex items-center gap-2">
                <MessageCircle className="w-4 h-4" />
                Chat with Pulse while we measure your vitals. Speak or type to share how you're feeling.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Step 3: Results with continued chat */}
      {step === 3 && capturedVitals && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Left Side: Results */}
          <div className="card text-center py-12">
            {analyzing ? (
              <>
                <div className="w-12 h-12 border-4 border-purple-500 border-t-transparent rounded-full animate-spin mx-auto mb-6" />
                <h2 className="text-2xl font-bold mb-2">Analyzing with AI...</h2>
                <p className="text-gray-400">Our agents are reviewing your vitals</p>
              </>
            ) : (
              <>
                <CheckCircle className="w-16 h-16 text-green-400 mx-auto mb-6" />
                <h2 className="text-2xl font-bold mb-6">Vitals Captured</h2>
                <div className="grid grid-cols-3 gap-4 mb-6">
                  <div className="bg-gray-700 rounded-xl p-4">
                    <Heart className="w-6 h-6 text-red-400 mx-auto mb-2" />
                    <p className="text-2xl font-bold">{capturedVitals.heart_rate}</p>
                    <p className="text-sm text-gray-400">bpm</p>
                  </div>
                  <div className="bg-gray-700 rounded-xl p-4">
                    <Activity className="w-6 h-6 text-green-400 mx-auto mb-2" />
                    <p className="text-2xl font-bold">{Math.round(capturedVitals.hrv)}</p>
                    <p className="text-sm text-gray-400">ms HRV</p>
                  </div>
                  <div className="bg-gray-700 rounded-xl p-4">
                    <CheckCircle className="w-6 h-6 text-blue-400 mx-auto mb-2" />
                    <p className="text-2xl font-bold">{Math.round(capturedVitals.quality_score * 100)}%</p>
                    <p className="text-sm text-gray-400">Quality</p>
                  </div>
                </div>
              </>
            )}
          </div>

          {/* Right Side: Chat continues with vital response */}
          <div className="flex flex-col">
            <VoiceChat 
              patientId="maria_001"
              isActive={chatActive}
              vitalsData={vitalsForChat}
              className="flex-1"
            />
          </div>
        </div>
      )}
    </div>
  );
}
