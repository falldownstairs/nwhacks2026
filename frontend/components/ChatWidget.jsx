'use client';

import { MessageCircle, X, Minimize2 } from 'lucide-react';
import { useState, useRef, useCallback } from 'react';
import VoiceChat from './VoiceChat';

/**
 * ChatWidget Component
 * 
 * A floating chat widget that appears in the bottom-right corner.
 * Allows users to talk to the Pulsera AI assistant anytime about their health data.
 */
export default function ChatWidget({ patientId = 'maria_001' }) {
  const [isOpen, setIsOpen] = useState(false);
  const [isMinimized, setIsMinimized] = useState(false);
  const [hasUnread, setHasUnread] = useState(false);
  const voiceChatRef = useRef(null);
  const [chatState, setChatState] = useState({ isSpeaking: false, isRecording: false, isProcessing: false });

  // Handle chat state changes
  const handleChatStateChange = useCallback((state) => {
    setChatState(state);
    // Mark as unread if AI is speaking while widget is closed
    if (state.isSpeaking && !isOpen) {
      setHasUnread(true);
    }
  }, [isOpen]);

  const toggleOpen = () => {
    if (!isOpen) {
      // Opening - clear unread
      setHasUnread(false);
    }
    setIsOpen(!isOpen);
    setIsMinimized(false);
  };

  const toggleMinimize = () => {
    setIsMinimized(!isMinimized);
  };

  return (
    <>
      {/* Chat Window */}
      {isOpen && (
        <div 
          className={`fixed bottom-24 right-6 z-50 transition-all duration-300 ease-in-out ${
            isMinimized ? 'w-72 h-14' : 'w-96 h-[500px]'
          }`}
        >
          <div className="w-full h-full bg-gray-900 rounded-2xl shadow-2xl border border-gray-700 overflow-hidden flex flex-col">
            {/* Custom Header */}
            <div className="flex items-center justify-between px-4 py-3 bg-gray-800 border-b border-gray-700">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 bg-gradient-to-br from-blue-500 to-purple-600 rounded-full flex items-center justify-center">
                  <MessageCircle className="w-4 h-4 text-white" />
                </div>
                <div>
                  <span className="font-medium text-gray-200 text-sm">Pulsera AI</span>
                  {chatState.isSpeaking && (
                    <span className="block text-xs text-purple-400">Speaking...</span>
                  )}
                  {chatState.isRecording && (
                    <span className="block text-xs text-red-400">Listening...</span>
                  )}
                  {chatState.isProcessing && !chatState.isRecording && !chatState.isSpeaking && (
                    <span className="block text-xs text-blue-400">Thinking...</span>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-1">
                <button
                  onClick={toggleMinimize}
                  className="p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-gray-700 transition-colors"
                  title={isMinimized ? 'Expand' : 'Minimize'}
                >
                  <Minimize2 className="w-4 h-4" />
                </button>
                <button
                  onClick={toggleOpen}
                  className="p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-gray-700 transition-colors"
                  title="Close"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* Voice Chat Content */}
            {!isMinimized && (
              <div className="flex-1 overflow-hidden">
                <VoiceChat
                  ref={voiceChatRef}
                  patientId={patientId}
                  isActive={isOpen}
                  onStateChange={handleChatStateChange}
                  showHeader={false}
                  endpoint="health-chat"
                  className="h-full border-0 rounded-none bg-transparent"
                />
              </div>
            )}
          </div>
        </div>
      )}

      {/* Floating Action Button */}
      <button
        onClick={toggleOpen}
        className={`fixed bottom-6 right-6 z-50 w-14 h-14 rounded-full shadow-lg transition-all duration-300 flex items-center justify-center group ${
          isOpen 
            ? 'bg-gray-700 hover:bg-gray-600' 
            : 'bg-gradient-to-br from-blue-500 to-purple-600 hover:from-blue-600 hover:to-purple-700'
        } ${chatState.isSpeaking || chatState.isRecording ? 'animate-pulse' : ''}`}
        title={isOpen ? 'Close chat' : 'Talk to Pulsera AI'}
      >
        {isOpen ? (
          <X className="w-6 h-6 text-white" />
        ) : (
          <>
            <MessageCircle className="w-6 h-6 text-white" />
            {/* Unread indicator */}
            {hasUnread && (
              <span className="absolute -top-1 -right-1 w-4 h-4 bg-red-500 rounded-full flex items-center justify-center">
                <span className="w-2 h-2 bg-white rounded-full" />
              </span>
            )}
            {/* Pulse ring when active */}
            {(chatState.isSpeaking || chatState.isRecording) && (
              <span className="absolute inset-0 rounded-full border-2 border-white/50 animate-ping" />
            )}
          </>
        )}
      </button>

      {/* Tooltip when closed */}
      {!isOpen && (
        <div className="fixed bottom-6 right-24 z-40 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none">
          <div className="bg-gray-800 text-white text-sm px-3 py-1.5 rounded-lg shadow-lg whitespace-nowrap">
            Ask me anything about your health
          </div>
        </div>
      )}
    </>
  );
}
