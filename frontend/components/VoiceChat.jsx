'use client';

import { Loader2, MessageCircle, Mic, MicOff, Send, Volume2, VolumeX } from 'lucide-react';
import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from 'react';

/**
 * VoiceChat Component
 * 
 * Real-time voice chat interface for Pulsera health companion.
 * Uses WebSocket for communication and browser MediaRecorder for voice capture.
 */
const VoiceChat = forwardRef(function VoiceChat({ 
  patientId = 'maria_001',
  vitalsData = null,     // Pass in vitals data when measurement complete (no longer used for auto-response)
  isActive = true,       // Whether chat should be active
  onStateChange = null,  // Callback: ({isSpeaking, isRecording, isProcessing}) => void
  onSessionEnd = null,   // Callback: (sessionSummary) => void - called when session ends
  showHeader = true,     // Whether to show the chat header (false when used in ChatWidget)
  endpoint = 'chat',     // WebSocket endpoint: 'chat' for check-in, 'health-chat' for dashboard
  className = ''
}, ref) {
  // WebSocket and connection state
  const wsRef = useRef(null);
  const [connected, setConnected] = useState(false);
  const [connecting, setConnecting] = useState(false);
  
  // Recording state
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const [isRecording, setIsRecording] = useState(false);
  const [hasPermission, setHasPermission] = useState(null);
  
  // Audio playback state (TTS)
  const audioRef = useRef(null);
  const audioChunksBufferRef = useRef([]);  // Buffer to accumulate streaming chunks
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isMuted, setIsMuted] = useState(false);
  
  // Chat state
  const [messages, setMessages] = useState([]);
  const [inputText, setInputText] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  
  // Auto-scroll ref
  const messagesEndRef = useRef(null);

  // Notify parent of state changes
  useEffect(() => {
    if (onStateChange) {
      onStateChange({ isSpeaking, isRecording, isProcessing });
    }
  }, [isSpeaking, isRecording, isProcessing, onStateChange]);

  // Scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Initialize Audio element
  useEffect(() => {
    audioRef.current = new Audio();
    audioRef.current.onplay = () => setIsSpeaking(true);
    audioRef.current.onended = () => setIsSpeaking(false);
    audioRef.current.onerror = (e) => {
      // Only log if there's an actual source set (not just initialization errors)
      if (audioRef.current?.src && audioRef.current.src !== '' && !audioRef.current.src.endsWith('/')) {
        console.warn('Audio playback error:', e.target?.error?.message || 'Unknown error');
      }
      setIsSpeaking(false);
    };
    
    return () => {
      if (audioRef.current) {
        audioRef.current.pause();
        if (audioRef.current.src && audioRef.current.src.startsWith('blob:')) {
          URL.revokeObjectURL(audioRef.current.src);
        }
        audioRef.current.src = '';
      }
    };
  }, []);

  // Helper to decode base64 to Uint8Array
  const base64ToBytes = useCallback((base64) => {
    const binaryString = atob(base64);
    const bytes = new Uint8Array(binaryString.length);
    for (let i = 0; i < binaryString.length; i++) {
      bytes[i] = binaryString.charCodeAt(i);
    }
    return bytes;
  }, []);

  // Play accumulated audio chunks
  const playAccumulatedAudio = useCallback(() => {
    if (isMuted || audioChunksBufferRef.current.length === 0) {
      audioChunksBufferRef.current = [];
      return;
    }
    
    try {
      // Combine all chunks into one Uint8Array
      const totalLength = audioChunksBufferRef.current.reduce((acc, chunk) => acc + chunk.length, 0);
      const combined = new Uint8Array(totalLength);
      let offset = 0;
      for (const chunk of audioChunksBufferRef.current) {
        combined.set(chunk, offset);
        offset += chunk.length;
      }
      
      // Clear the buffer
      audioChunksBufferRef.current = [];
      
      // Create blob and play
      const blob = new Blob([combined], { type: 'audio/mpeg' });
      const url = URL.createObjectURL(blob);
      
      // Revoke previous URL if exists
      if (audioRef.current.src && audioRef.current.src.startsWith('blob:')) {
        URL.revokeObjectURL(audioRef.current.src);
      }
      
      audioRef.current.src = url;
      audioRef.current.play().catch(err => {
        console.error('Error playing audio:', err);
        setIsSpeaking(false);
      });
    } catch (err) {
      console.error('Error processing audio:', err);
      audioChunksBufferRef.current = [];
      setIsSpeaking(false);
    }
  }, [isMuted]);

  // Queue audio chunk - accumulates until final chunk received
  const queueAudioChunk = useCallback((base64Audio, isFinal) => {
    if (isMuted) {
      if (isFinal) audioChunksBufferRef.current = [];
      return;
    }
    
    if (base64Audio) {
      const bytes = base64ToBytes(base64Audio);
      audioChunksBufferRef.current.push(bytes);
    }
    
    // Play when we receive the final chunk
    if (isFinal) {
      playAccumulatedAudio();
    }
  }, [isMuted, base64ToBytes, playAccumulatedAudio]);

  // Stop current audio playback
  const stopAudio = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
    }
    audioChunksBufferRef.current = [];
    setIsSpeaking(false);
  }, []);

  // Toggle mute
  const toggleMute = useCallback(() => {
    setIsMuted(prev => {
      if (!prev) {
        // Muting - stop current audio
        stopAudio();
      }
      return !prev;
    });
  }, [stopAudio]);

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
      
      case 'audio_chunk':
        // Queue audio for playback - accumulate chunks until final
        queueAudioChunk(data.audio, data.is_final);
        break;
      
      case 'tts_error':
        // TTS failed but don't show error to user - text is already displayed
        console.warn('TTS unavailable:', data.message);
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
  }, [queueAudioChunk]);

  // Track if connection ever succeeded (to distinguish failed connect vs disconnect)
  const hadConnectionRef = useRef(false);
  const connectionTimeoutRef = useRef(null);

  // Connect to WebSocket - defined after handleMessage
  const connectChat = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;
    
    setConnecting(true);
    hadConnectionRef.current = false;
    
    // Set a timeout to show error if connection takes too long
    connectionTimeoutRef.current = setTimeout(() => {
      if (!hadConnectionRef.current) {
        setMessages(prev => [...prev, {
          role: 'system',
          content: 'Unable to connect to Pulsera AI. Please ensure the backend server is running.',
          timestamp: new Date().toISOString(),
          isError: true
        }]);
      }
    }, 10000); // 10 seconds
    
    // Check if backend is likely running first
    const wsUrl = `${process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000'}/ws/${endpoint}/${patientId}`;
    console.log('Attempting to connect to:', wsUrl);
    
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('Chat WebSocket connected');
      hadConnectionRef.current = true;
      setConnected(true);
      setConnecting(false);
      // Clear the timeout since we connected successfully
      if (connectionTimeoutRef.current) {
        clearTimeout(connectionTimeoutRef.current);
        connectionTimeoutRef.current = null;
      }
      // Clear any connection error messages that appeared during handshake
      setMessages(prev => prev.filter(msg => 
        !(msg.isError && msg.content.includes('Unable to connect'))
      ));
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
      // Just log - we'll handle the user message in timeout if needed
      console.warn('Chat WebSocket error event');
    };

    ws.onclose = (event) => {
      console.log('Chat WebSocket closed', event.code, event.reason);
      setConnected(false);
      setConnecting(false);
    };
  }, [patientId, endpoint, handleMessage]);

  // Initialize connection when component mounts
  useEffect(() => {
    if (isActive) {
      connectChat();
    }
    return () => {
      // Clean up timeout on unmount
      if (connectionTimeoutRef.current) {
        clearTimeout(connectionTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [isActive, connectChat]);

  // Send vitals to trigger triage response when vitalsData changes
  useEffect(() => {
    if (vitalsData && wsRef.current?.readyState === WebSocket.OPEN) {
      const isNormal = vitalsData.heart_rate >= 60 && vitalsData.heart_rate <= 85 && vitalsData.hrv >= 35;
      wsRef.current.send(JSON.stringify({
        type: 'vital_result',
        heart_rate: vitalsData.heart_rate,
        hrv: vitalsData.hrv,
        is_normal: isNormal
      }));
    }
  }, [vitalsData]);

  // End session and get summary - call this before unmounting to get conversation data
  const endSession = useCallback(() => {
    return new Promise((resolve) => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        // Set up one-time handler for session_summary
        const handleSummary = (event) => {
          try {
            const data = JSON.parse(event.data);
            if (data.type === 'session_summary') {
              wsRef.current.removeEventListener('message', handleSummary);
              const summary = {
                ...data.data,
                messages: messages  // Include frontend messages too
              };
              if (onSessionEnd) {
                onSessionEnd(summary);
              }
              resolve(summary);
            }
          } catch (e) {
            console.error('Error parsing session summary:', e);
          }
        };
        
        wsRef.current.addEventListener('message', handleSummary);
        wsRef.current.send(JSON.stringify({ type: 'end_session' }));
        
        // Timeout fallback
        setTimeout(() => {
          wsRef.current?.removeEventListener('message', handleSummary);
          const fallbackSummary = { messages, subjective_summary: 'Session ended' };
          if (onSessionEnd) {
            onSessionEnd(fallbackSummary);
          }
          resolve(fallbackSummary);
        }, 3000);
      } else {
        const fallbackSummary = { messages, subjective_summary: 'No active session' };
        if (onSessionEnd) {
          onSessionEnd(fallbackSummary);
        }
        resolve(fallbackSummary);
      }
    });
  }, [messages, onSessionEnd]);

  // Expose methods via ref for parent components
  useImperativeHandle(ref, () => ({
    endSession,
    getMessages: () => messages,
    isIdle: () => !isSpeaking && !isRecording && !isProcessing
  }), [endSession, messages, isSpeaking, isRecording, isProcessing]);

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
    <div className={`flex flex-col bg-gray-800/50 rounded-xl border border-gray-700/50 shadow-xl h-full max-h-[600px] ${className}`}>
      {/* Header - can be hidden when embedded in ChatWidget */}
      {showHeader && (
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-700/50 bg-gray-800/30 rounded-t-xl">
          <div className="flex items-center gap-3">
            <MessageCircle className="w-6 h-6 text-blue-400" />
            <span className="font-semibold text-lg text-gray-100">Pulsera AI</span>
            {connected && (
              <span className="flex items-center gap-1.5 text-xs text-green-400 bg-green-400/10 px-2 py-1 rounded-full">
                <span className="w-2 h-2 bg-green-400 rounded-full animate-pulse" />
                Connected
              </span>
            )}
            {isSpeaking && (
              <span className="flex items-center gap-1.5 text-xs text-purple-400 bg-purple-400/10 px-2 py-1 rounded-full">
                <Volume2 className="w-3 h-3 animate-pulse" />
                Speaking
              </span>
            )}
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={toggleMute}
              className={`p-2 rounded-lg transition-colors ${
                isMuted 
                  ? 'bg-red-500/20 text-red-400 hover:bg-red-500/30' 
                  : 'text-gray-400 hover:text-white hover:bg-gray-700'
              }`}
              title={isMuted ? 'Unmute AI voice' : 'Mute AI voice'}
            >
              {isMuted ? <VolumeX className="w-5 h-5" /> : <Volume2 className="w-5 h-5" />}
            </button>
        </div>
      </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-5 space-y-4 min-h-0">
        {messages.length === 0 && !connecting && (
          <div className="text-center text-gray-500 py-12">
            <Volume2 className="w-10 h-10 mx-auto mb-3 opacity-50" />
            <p className="text-sm">Connecting to Pulsera AI...</p>
          </div>
        )}
        
        {connecting && (
          <div className="text-center text-gray-500 py-12">
            <Loader2 className="w-10 h-10 mx-auto mb-3 animate-spin opacity-50" />
            <p className="text-sm">Initializing chat...</p>
          </div>
        )}
        
        {messages.map((msg, idx) => (
          <div
            key={idx}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[80%] rounded-2xl px-4 py-3 ${
                msg.role === 'user'
                  ? 'bg-blue-500 text-white rounded-br-md'
                  : msg.isError
                  ? 'bg-red-500/20 text-red-300 rounded-bl-md border border-red-500/30'
                  : msg.isVitalResponse
                  ? 'bg-green-500/20 text-green-200 rounded-bl-md border border-green-500/30'
                  : 'bg-gray-700/80 text-gray-100 rounded-bl-md border border-gray-600/30'
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

      {/* Input Area - Redesigned with integrated mic */}
      <div className="p-4 border-t border-gray-700/50 bg-gray-800/30 rounded-b-xl">
        {/* Combined input with mic button */}
        <div className="flex items-center gap-3 bg-gray-700/50 rounded-xl p-2 border border-gray-600/50">
          {/* Text input */}
          <input
            type="text"
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="Type a message or tap mic to speak..."
            className="flex-1 bg-transparent px-3 py-2 text-sm text-white placeholder-gray-400 focus:outline-none"
            disabled={!connected || isProcessing || isRecording}
          />
          
          {/* Send text button (shows when there's text) */}
          {inputText.trim() && (
            <button
              onClick={sendTextMessage}
              disabled={!connected || isProcessing}
              className="bg-blue-500 hover:bg-blue-600 disabled:bg-gray-600 disabled:cursor-not-allowed text-white p-2.5 rounded-lg transition-colors"
            >
              <Send className="w-5 h-5" />
            </button>
          )}
          
          {/* Mic button (integrated into input bar) */}
          <button
            onClick={isRecording ? stopRecording : startRecording}
            disabled={!connected || isProcessing}
            className={`relative flex items-center justify-center w-11 h-11 rounded-xl transition-all ${
              isRecording
                ? 'bg-red-500 hover:bg-red-600'
                : connected
                ? 'bg-blue-500 hover:bg-blue-600'
                : 'bg-gray-600 cursor-not-allowed'
            }`}
          >
            {isRecording ? (
              <MicOff className="w-5 h-5 text-white" />
            ) : (
              <Mic className="w-5 h-5 text-white" />
            )}
            
            {/* Recording indicator */}
            {isRecording && (
              <span className="absolute inset-0 rounded-xl border-2 border-red-400 animate-ping" />
            )}
          </button>
        </div>
        
        <p className="text-center text-xs text-gray-500 mt-3">
          {!connected 
            ? 'Connecting...' 
            : isRecording 
            ? '🔴 Listening... tap to stop'
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
});

export default VoiceChat;