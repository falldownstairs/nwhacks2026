'use client';

import { Bot, Loader2, Mic, MicOff, Send, Volume2, VolumeX, X } from 'lucide-react';
import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from 'react';

const TriageChat = forwardRef(function TriageChat({ 
  vitals, 
  conversationContext,
  onDismiss,
  onComplete,
  className = '' 
}, ref) {
  const [messages, setMessages] = useState([]);
  const [inputValue, setInputValue] = useState('');
  const [isConnected, setIsConnected] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isMuted, setIsMuted] = useState(false);
  const [error, setError] = useState(null);
  
  const wsRef = useRef(null);
  const messagesEndRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const audioChunksBufferRef = useRef([]);
  const audioElementRef = useRef(null);
  const sessionEndedRef = useRef(false);

  // Determine triage path based on vitals
  const isNormalVitals = vitals && 
    vitals.heart_rate >= 60 && vitals.heart_rate <= 85 &&
    vitals.hrv >= 35;

  // Scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Play audio from accumulated chunks
  const playAccumulatedAudio = useCallback(() => {
    if (audioChunksBufferRef.current.length === 0 || isMuted) {
      setIsSpeaking(false);
      return;
    }

    const combinedBlob = new Blob(audioChunksBufferRef.current, { type: 'audio/mpeg' });
    audioChunksBufferRef.current = [];
    
    const audioUrl = URL.createObjectURL(combinedBlob);
    
    if (audioElementRef.current) {
      audioElementRef.current.pause();
      URL.revokeObjectURL(audioElementRef.current.src);
    }
    
    const audio = new Audio(audioUrl);
    audioElementRef.current = audio;
    
    audio.onplay = () => setIsSpeaking(true);
    audio.onended = () => {
      setIsSpeaking(false);
      URL.revokeObjectURL(audioUrl);
    };
    audio.onerror = () => {
      setIsSpeaking(false);
      URL.revokeObjectURL(audioUrl);
    };
    
    audio.play().catch(err => {
      console.error('Audio playback failed:', err);
      setIsSpeaking(false);
    });
  }, [isMuted]);

  // Connect to triage WebSocket
  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;
    
    try {
      const wsUrl = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000';
      const ws = new WebSocket(`${wsUrl}/ws/triage`);
      wsRef.current = ws;
      
      ws.onopen = () => {
        console.log('Triage WebSocket connected');
        setIsConnected(true);
        setError(null);
        
        // Send initialization message with vitals and conversation context
        ws.send(JSON.stringify({
          type: 'init',
          vitals: vitals,
          conversation_history: conversationContext,
          is_normal: isNormalVitals
        }));
      };
      
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          
          switch (data.type) {
            case 'greeting':
            case 'response':
              setMessages(prev => [...prev, {
                role: 'assistant',
                content: data.text,
                timestamp: new Date().toISOString()
              }]);
              setIsProcessing(false);
              break;
              
            case 'audio_chunk':
              if (data.audio && !isMuted) {
                const binaryString = atob(data.audio);
                const bytes = new Uint8Array(binaryString.length);
                for (let i = 0; i < binaryString.length; i++) {
                  bytes[i] = binaryString.charCodeAt(i);
                }
                audioChunksBufferRef.current.push(new Blob([bytes], { type: 'audio/mpeg' }));
                
                if (data.is_final) {
                  playAccumulatedAudio();
                }
              }
              break;
              
            case 'transcription':
              if (data.text) {
                setMessages(prev => [...prev, {
                  role: 'user',
                  content: data.text,
                  timestamp: new Date().toISOString()
                }]);
              }
              break;
              
            case 'error':
              setError(data.message);
              setIsProcessing(false);
              break;
              
            case 'session_end':
              onComplete?.();
              break;
          }
        } catch (e) {
          console.error('Error parsing WebSocket message:', e);
        }
      };
      
      ws.onclose = () => {
        console.log('Triage WebSocket closed');
        setIsConnected(false);
      };
      
      ws.onerror = (err) => {
        console.error('Triage WebSocket error:', err);
        setError('Connection error');
        setIsConnected(false);
      };
    } catch (err) {
      console.error('Failed to connect to triage WebSocket:', err);
      setError('Failed to connect');
    }
  }, [vitals, conversationContext, isNormalVitals, isMuted, playAccumulatedAudio, onComplete]);

  // Auto-connect when mounted
  useEffect(() => {
    connect();
    
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      if (audioElementRef.current) {
        audioElementRef.current.pause();
      }
    };
  }, [connect]);

  // Send text message
  const sendMessage = useCallback(() => {
    if (!inputValue.trim() || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    
    const text = inputValue.trim();
    setInputValue('');
    setIsProcessing(true);
    
    setMessages(prev => [...prev, {
      role: 'user',
      content: text,
      timestamp: new Date().toISOString()
    }]);
    
    wsRef.current.send(JSON.stringify({
      type: 'text',
      text: text
    }));
  }, [inputValue]);

  // Start voice recording
  const startRecording = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];
      
      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };
      
      mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
        stream.getTracks().forEach(track => track.stop());
        
        // Convert to base64 and send
        const reader = new FileReader();
        reader.onloadend = () => {
          const base64Audio = reader.result.split(',')[1];
          if (wsRef.current?.readyState === WebSocket.OPEN) {
            setIsProcessing(true);
            wsRef.current.send(JSON.stringify({
              type: 'audio',
              audio: base64Audio
            }));
          }
        };
        reader.readAsDataURL(audioBlob);
      };
      
      mediaRecorder.start();
      setIsRecording(true);
    } catch (err) {
      console.error('Failed to start recording:', err);
      setError('Microphone access denied');
    }
  }, []);

  // Stop voice recording
  const stopRecording = useCallback(() => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
    }
  }, [isRecording]);

  // Toggle mute
  const toggleMute = useCallback(() => {
    setIsMuted(prev => {
      if (!prev && audioElementRef.current) {
        audioElementRef.current.pause();
        setIsSpeaking(false);
      }
      return !prev;
    });
  }, []);

  // Expose methods via ref
  useImperativeHandle(ref, () => ({
    endSession: () => {
      sessionEndedRef.current = true;
      if (wsRef.current) {
        wsRef.current.close();
      }
    },
    getMessages: () => messages,
    isIdle: () => !isProcessing && !isRecording && !isSpeaking
  }), [messages, isProcessing, isRecording, isSpeaking]);

  return (
    <div className={`fixed bottom-4 right-4 w-96 bg-gray-800 rounded-2xl shadow-2xl border border-gray-700 overflow-hidden z-50 ${className}`}>
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 bg-gradient-to-r from-purple-600 to-blue-600">
        <div className="flex items-center gap-2">
          <Bot className="w-5 h-5 text-white" />
          <span className="font-semibold text-white">Pulsera Triage</span>
          {isSpeaking && (
            <Volume2 className="w-4 h-4 text-white animate-pulse" />
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={toggleMute}
            className="p-1 hover:bg-white/20 rounded-full transition-colors"
            title={isMuted ? 'Unmute' : 'Mute'}
          >
            {isMuted ? (
              <VolumeX className="w-4 h-4 text-white" />
            ) : (
              <Volume2 className="w-4 h-4 text-white" />
            )}
          </button>
          <button
            onClick={onDismiss}
            className="p-1 hover:bg-white/20 rounded-full transition-colors"
            title="Close"
          >
            <X className="w-4 h-4 text-white" />
          </button>
        </div>
      </div>

      {/* Vitals summary */}
      <div className="px-4 py-2 bg-gray-900/50 border-b border-gray-700">
        <p className="text-xs text-gray-400">
          Check-in vitals: <span className="text-white">{vitals?.heart_rate} bpm</span> • 
          <span className="text-white"> {Math.round(vitals?.hrv || 0)} ms HRV</span>
          {isNormalVitals ? (
            <span className="ml-2 text-green-400">● Normal</span>
          ) : (
            <span className="ml-2 text-yellow-400">● Review needed</span>
          )}
        </p>
      </div>

      {/* Messages */}
      <div className="h-64 overflow-y-auto p-4 space-y-3">
        {!isConnected && !error && (
          <div className="flex items-center justify-center h-full">
            <Loader2 className="w-6 h-6 animate-spin text-purple-400" />
          </div>
        )}
        
        {error && (
          <div className="bg-red-500/20 text-red-300 p-3 rounded-lg text-sm">
            {error}
          </div>
        )}
        
        {messages.map((msg, idx) => (
          <div
            key={idx}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[80%] px-4 py-2 rounded-2xl text-sm ${
                msg.role === 'user'
                  ? 'bg-blue-600 text-white rounded-br-md'
                  : 'bg-gray-700 text-gray-100 rounded-bl-md'
              }`}
            >
              {msg.content}
            </div>
          </div>
        ))}
        
        {isProcessing && (
          <div className="flex justify-start">
            <div className="bg-gray-700 px-4 py-2 rounded-2xl rounded-bl-md">
              <div className="flex gap-1">
                <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
            </div>
          </div>
        )}
        
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="p-3 border-t border-gray-700 bg-gray-900/50">
        <div className="flex gap-2">
          <button
            onClick={isRecording ? stopRecording : startRecording}
            disabled={!isConnected || isProcessing}
            className={`p-2 rounded-full transition-colors ${
              isRecording
                ? 'bg-red-500 hover:bg-red-600 animate-pulse'
                : 'bg-gray-700 hover:bg-gray-600'
            } disabled:opacity-50 disabled:cursor-not-allowed`}
          >
            {isRecording ? (
              <MicOff className="w-5 h-5 text-white" />
            ) : (
              <Mic className="w-5 h-5 text-white" />
            )}
          </button>
          
          <input
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyPress={(e) => e.key === 'Enter' && sendMessage()}
            placeholder="Type a message..."
            disabled={!isConnected || isProcessing}
            className="flex-1 bg-gray-700 text-white px-4 py-2 rounded-full text-sm placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 disabled:opacity-50"
          />
          
          <button
            onClick={sendMessage}
            disabled={!inputValue.trim() || !isConnected || isProcessing}
            className="p-2 bg-purple-600 hover:bg-purple-700 rounded-full transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Send className="w-5 h-5 text-white" />
          </button>
        </div>
      </div>
    </div>
  );
});

export default TriageChat;
