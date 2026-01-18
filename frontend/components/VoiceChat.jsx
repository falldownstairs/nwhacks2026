'use client';

import { Loader2, MessageCircle, Mic, MicOff, Send, Volume2 } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * VoiceChat Component
 * 
 * Real-time voice chat interface for Pulse health companion.
 * Uses WebSocket for communication and browser MediaRecorder for voice capture.
 */
export default function VoiceChat({ 
  patientId = 'maria_001',
  vitalsData = null,     // Pass in vitals data when measurement complete
  isActive = true,       // Whether chat should be active
  className = ''
}) {
  // WebSocket and connection state
  const wsRef = useRef(null);
  const [connected, setConnected] = useState(false);
  const [connecting, setConnecting] = useState(false);
  
  // Recording state
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const [isRecording, setIsRecording] = useState(false);
  const [hasPermission, setHasPermission] = useState(null);
  
  // Chat state
  const [messages, setMessages] = useState([]);
  const [inputText, setInputText] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const [showTextInput, setShowTextInput] = useState(false);
  
  // Auto-scroll ref
  const messagesEndRef = useRef(null);

  // Scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Handle incoming WebSocket messages - define first to avoid hoisting issues
  const handleMessage = useCallback((data) => {
    setIsProcessing(false);
    
    switch (data.type) {
      case 'greeting':
        setMessages(prev => [...prev, {
          role: 'assistant',
          content: data.content,
          timestamp: new Date().toISOString()
        }]);
        break;
      
      case 'transcription':
        // User's transcribed speech
        setMessages(prev => [...prev, {
          role: 'user',
          content: data.text,
          timestamp: new Date().toISOString(),
          isTranscription: true
        }]);
        setIsProcessing(true); // Wait for AI response
        break;
      
      case 'response':
        setMessages(prev => [...prev, {
          role: 'assistant',
          content: data.content,
          context: data.context,
          timestamp: new Date().toISOString()
        }]);
        break;
      
      case 'vital_response':
        setMessages(prev => [...prev, {
          role: 'assistant',
          content: data.content,
          timestamp: new Date().toISOString(),
          isVitalResponse: true
        }]);
        break;
      
      case 'session_summary':
        console.log('Session summary:', data.data);
        break;
      
      case 'error':
        console.error('Chat error:', data.message);
        setMessages(prev => [...prev, {
          role: 'system',
          content: `Error: ${data.message}`,
          timestamp: new Date().toISOString(),
          isError: true
        }]);
        break;
      
      default:
        console.log('Unknown message type:', data.type);
    }
  }, []);

  // Connect to WebSocket - defined after handleMessage
  const connectChat = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;
    
    setConnecting(true);
    
    // Check if backend is likely running first
    const wsUrl = `ws://localhost:8000/ws/chat/${patientId}`;
    console.log('Attempting to connect to:', wsUrl);
    
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('Chat WebSocket connected');
      setConnected(true);
      setConnecting(false);
      // Request greeting
      ws.send(JSON.stringify({ type: 'get_greeting' }));
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        handleMessage(data);
      } catch (e) {
        console.error('Error parsing chat message:', e);
      }
    };

    ws.onerror = () => {
      // WebSocket errors don't expose details for security reasons
      // This usually means the server is not reachable
      console.warn('Chat WebSocket connection failed - backend may not be running');
      setConnected(false);
      setConnecting(false);
      
      // Add a helpful message to the chat
      setMessages(prev => [...prev, {
        role: 'system',
        content: 'Unable to connect to Pulse AI. Please ensure the backend server is running.',
        timestamp: new Date().toISOString(),
        isError: true
      }]);
    };

    ws.onclose = (event) => {
      console.log('Chat WebSocket closed', event.code, event.reason);
      setConnected(false);
      setConnecting(false);
    };
  }, [patientId, handleMessage]);

  // Initialize connection when component mounts
  useEffect(() => {
    if (isActive) {
      connectChat();
    }
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [isActive, connectChat]);

  // Send vital results when they come in
  useEffect(() => {
    if (vitalsData && wsRef.current?.readyState === WebSocket.OPEN) {
      const isNormal = vitalsData.heart_rate >= 60 && vitalsData.heart_rate <= 100;
      wsRef.current.send(JSON.stringify({
        type: 'vital_result',
        heart_rate: vitalsData.heart_rate,
        hrv: vitalsData.hrv,
        is_normal: isNormal
      }));
    }
  }, [vitalsData]);

  // Request microphone permission
  const requestMicPermission = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach(track => track.stop()); // Stop the test stream
      setHasPermission(true);
      return true;
    } catch (err) {
      console.error('Microphone permission denied:', err);
      setHasPermission(false);
      return false;
    }
  }, []);

  // Start recording
  const startRecording = useCallback(async () => {
    if (!hasPermission) {
      const granted = await requestMicPermission();
      if (!granted) return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ 
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          sampleRate: 16000
        }
      });
      
      const mediaRecorder = new MediaRecorder(stream, {
        mimeType: 'audio/webm;codecs=opus'
      });
      
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
              data: base64Audio,
              format: 'webm'
            }));
          }
        };
        reader.readAsDataURL(audioBlob);
      };

      mediaRecorder.start(100); // Collect data every 100ms
      setIsRecording(true);
    } catch (err) {
      console.error('Error starting recording:', err);
    }
  }, [hasPermission, requestMicPermission]);

  // Stop recording
  const stopRecording = useCallback(() => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
    }
  }, [isRecording]);

  // Send text message
  const sendTextMessage = useCallback(() => {
    if (!inputText.trim() || !wsRef.current) return;
    
    // Add user message immediately
    setMessages(prev => [...prev, {
      role: 'user',
      content: inputText,
      timestamp: new Date().toISOString()
    }]);
    
    // Send to server
    setIsProcessing(true);
    wsRef.current.send(JSON.stringify({
      type: 'text',
      content: inputText
    }));
    
    setInputText('');
  }, [inputText]);

  // Handle Enter key
  const handleKeyPress = useCallback((e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendTextMessage();
    }
  }, [sendTextMessage]);

  return (
    <div className={`flex flex-col bg-gray-800/50 rounded-xl border border-gray-700 ${className}`}>
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-700">
        <div className="flex items-center gap-2">
          <MessageCircle className="w-5 h-5 text-blue-400" />
          <span className="font-medium text-gray-200">Pulse AI</span>
          {connected && (
            <span className="flex items-center gap-1 text-xs text-green-400">
              <span className="w-2 h-2 bg-green-400 rounded-full animate-pulse" />
              Connected
            </span>
          )}
        </div>
        <button
          onClick={() => setShowTextInput(!showTextInput)}
          className="text-xs text-gray-400 hover:text-white transition-colors"
        >
          {showTextInput ? 'Hide keyboard' : 'Use keyboard'}
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3 min-h-[200px] max-h-[300px]">
        {messages.length === 0 && !connecting && (
          <div className="text-center text-gray-500 py-8">
            <Volume2 className="w-8 h-8 mx-auto mb-2 opacity-50" />
            <p className="text-sm">Connecting to Pulse AI...</p>
          </div>
        )}
        
        {connecting && (
          <div className="text-center text-gray-500 py-8">
            <Loader2 className="w-8 h-8 mx-auto mb-2 animate-spin opacity-50" />
            <p className="text-sm">Initializing chat...</p>
          </div>
        )}
        
        {messages.map((msg, idx) => (
          <div
            key={idx}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[85%] rounded-2xl px-4 py-2 ${
                msg.role === 'user'
                  ? 'bg-blue-500 text-white rounded-br-sm'
                  : msg.isError
                  ? 'bg-red-500/20 text-red-300 rounded-bl-sm'
                  : msg.isVitalResponse
                  ? 'bg-green-500/20 text-green-200 rounded-bl-sm border border-green-500/30'
                  : 'bg-gray-700 text-gray-200 rounded-bl-sm'
              }`}
            >
              <p className="text-sm leading-relaxed">{msg.content}</p>
              {msg.isTranscription && (
                <span className="text-xs opacity-70 mt-1 block">🎤 Voice</span>
              )}
            </div>
          </div>
        ))}
        
        {isProcessing && (
          <div className="flex justify-start">
            <div className="bg-gray-700 rounded-2xl rounded-bl-sm px-4 py-2">
              <div className="flex items-center gap-1">
                <span className="w-2 h-2 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-2 h-2 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-2 h-2 bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
            </div>
          </div>
        )}
        
        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="p-4 border-t border-gray-700">
        {/* Text input (optional) */}
        {showTextInput && (
          <div className="flex gap-2 mb-3">
            <input
              type="text"
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              onKeyPress={handleKeyPress}
              placeholder="Type a message..."
              className="flex-1 bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-sm text-white placeholder-gray-400 focus:outline-none focus:border-blue-500"
              disabled={!connected || isProcessing}
            />
            <button
              onClick={sendTextMessage}
              disabled={!connected || !inputText.trim() || isProcessing}
              className="bg-blue-500 hover:bg-blue-600 disabled:bg-gray-600 disabled:cursor-not-allowed text-white p-2 rounded-lg transition-colors"
            >
              <Send className="w-5 h-5" />
            </button>
          </div>
        )}

        {/* Voice button */}
        <div className="flex justify-center">
          <button
            onClick={isRecording ? stopRecording : startRecording}
            disabled={!connected || isProcessing}
            className={`relative flex items-center justify-center w-16 h-16 rounded-full transition-all ${
              isRecording
                ? 'bg-red-500 hover:bg-red-600 animate-pulse'
                : connected
                ? 'bg-blue-500 hover:bg-blue-600'
                : 'bg-gray-600 cursor-not-allowed'
            }`}
          >
            {isRecording ? (
              <MicOff className="w-7 h-7 text-white" />
            ) : (
              <Mic className="w-7 h-7 text-white" />
            )}
            
            {/* Recording indicator ring */}
            {isRecording && (
              <span className="absolute inset-0 rounded-full border-4 border-red-400 animate-ping" />
            )}
          </button>
        </div>
        
        <p className="text-center text-xs text-gray-500 mt-2">
          {!connected 
            ? 'Connecting...' 
            : isRecording 
            ? 'Listening... tap to stop'
            : 'Tap to speak'}
        </p>
        
        {hasPermission === false && (
          <p className="text-center text-xs text-red-400 mt-1">
            Microphone access denied. Please enable it in your browser settings.
          </p>
        )}
      </div>
    </div>
  );
}
