import React, { useState, useRef, useEffect } from 'react';

import { Send, Paperclip, FileText, X, Scale } from 'lucide-react';
import { MessageBubble } from '../components/Chat/MessageBubble';
import type { ChatMessage } from '../types';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const loadingSynonyms = ['Thinking...', 'Analyzing...', 'Reviewing...', 'Almost there...'];

const ThinkingAnimation: React.FC = () => {
  const [index, setIndex] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => {
      setIndex((prev) => (prev + 1) % loadingSynonyms.length);
    }, 2000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="flex gap-4 animate-fade-in">
      <div className="w-8 h-8 rounded-full bg-[#1E293B] flex items-center justify-center flex-shrink-0 shadow-sm">
        <Scale className="w-4 h-4 text-white" />
      </div>
      <div className="bg-white border border-gray-100 rounded-2xl rounded-tl-none px-4 py-3 flex items-center gap-3 w-fit shadow-sm">
        <div className="flex gap-1.5 items-center justify-center h-5">
          <div className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-pulse-dot" style={{ animationDelay: '0ms' }}></div>
          <div className="w-1.5 h-1.5 bg-red-400 rounded-full animate-pulse-dot" style={{ animationDelay: '200ms' }}></div>
          <div className="w-1.5 h-1.5 bg-yellow-400 rounded-full animate-pulse-dot" style={{ animationDelay: '400ms' }}></div>
        </div>
        <div className="relative h-5 overflow-hidden min-w-[100px]">
          {loadingSynonyms.map((synonym, i) => {
            let positionClass = 'translate-y-full opacity-0';
            if (i === index) {
              positionClass = 'translate-y-0 opacity-100';
            } else if (i === (index - 1 + loadingSynonyms.length) % loadingSynonyms.length) {
              positionClass = '-translate-y-full opacity-0';
            }
            
            return (
              <span
                key={synonym}
                className={`absolute inset-0 flex items-center transition-all duration-500 ease-in-out text-sm font-medium text-gray-500 bg-clip-text text-transparent bg-gradient-to-r from-gray-600 to-gray-400 whitespace-nowrap ${positionClass}`}
              >
                {synonym}
              </span>
            );
          })}
        </div>
      </div>
    </div>
  );
};

export const ChatView: React.FC = () => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [modelPref, setModelPref] = useState('deep');
  const [isLoading, setIsLoading] = useState(false);
  const [ephemeralFile, setEphemeralFile] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);



  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async () => {
    if ((!input.trim() && !ephemeralFile) || isLoading) return;

    let ephemeralContext = null;

    setIsLoading(true);

    if (ephemeralFile) {
      const formData = new FormData();
      formData.append('file', ephemeralFile);
      try {
        const res = await fetch(`${API_URL}/api/extract`, {
          method: 'POST',
          body: formData
        });
        if (res.ok) {
          const data = await res.json();
          ephemeralContext = data.text;
        }
      } catch (e) {
        console.error("Failed to extract ephemeral doc", e);
      }
      setEphemeralFile(null); // clear after sending
    }

    const newMessage: ChatMessage = { role: 'user', content: input };
    setMessages(prev => [...prev, newMessage]);
    setInput('');

    try {
      const res = await fetch(`${API_URL}/api/analyze`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          query: newMessage.content || "Analyze the attached document.",
          ephemeral_context: ephemeralContext,
          model_preference: modelPref
        })
      });

      if (res.ok) {
        const data = await res.json();
        const assistantMessage: ChatMessage = {
          role: 'assistant',
          content: data.analysis,
          sources: data.sources
        };
        setMessages(prev => [...prev, assistantMessage]);
      } else {
        const err = await res.json();
        console.error(err);
      }
    } catch (e) {
      console.error(e);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-full bg-[#F2F0EB] relative">
      {/* Header */}
      <header className="h-16 border-b border-gray-100 flex items-center justify-between px-6 flex-shrink-0 z-10 bg-white/80 backdrop-blur-sm">
        <h2 className="text-lg font-serif tracking-tight text-[#121212]">Legal Analysis</h2>
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-gray-500 uppercase tracking-wider">Model:</span>
          <select
            value={modelPref}
            onChange={e => setModelPref(e.target.value)}
            className="text-sm bg-white border border-gray-200 rounded-md px-3 py-1.5 outline-none text-gray-700 shadow-sm hover:border-gray-300 focus:border-[#1E293B] focus:ring-1 focus:ring-[#1E293B] transition-all cursor-pointer"
          >
            <option value="deep">Gemma 4 (31B)</option>
            <option value="quick">Gemini 2.5 Flash</option>
          </select>
        </div>
      </header>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {messages.length === 0 && (
          <div className="h-full flex flex-col items-center justify-center text-gray-400">
            <Scale className="w-12 h-12 mb-4 opacity-20" />
            <p className="text-sm">Start a new legal inquiry...</p>
          </div>
        )}
        {messages.map((msg, idx) => (
          <MessageBubble key={idx} message={msg} />
        ))}
        {isLoading && <ThinkingAnimation />}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="p-4 bg-white border-t border-gray-100">
        <div className="max-w-3xl mx-auto">
          {ephemeralFile && (
            <div className="mb-3 flex items-center gap-2 bg-[#F9F9F8] border border-gray-200 text-sm py-2 px-3 rounded-md w-max">
              <FileText className="w-4 h-4 text-blue-500" />
              <span className="text-gray-700 font-medium truncate max-w-[200px]">{ephemeralFile.name}</span>
              <button onClick={() => setEphemeralFile(null)} className="text-gray-400 hover:text-gray-600 ml-2">
                <X className="w-4 h-4" />
              </button>
            </div>
          )}
          
          <div className="flex items-center gap-3 bg-white border border-gray-300 rounded-xl px-4 py-3 shadow-sm focus-within:ring-2 focus-within:ring-[#1E293B] focus-within:border-transparent transition-all">
            <input 
              type="file"
              ref={fileInputRef}
              onChange={(e) => {
                if (e.target.files && e.target.files[0]) {
                  setEphemeralFile(e.target.files[0]);
                }
              }}
              className="hidden"
              accept=".pdf,.docx"
            />
            <button 
              onClick={() => fileInputRef.current?.click()}
              className="text-gray-400 hover:text-[#1E293B] transition-colors p-1"
              title="Attach document for this query only"
            >
              <Paperclip className="w-5 h-5" />
            </button>
            
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSend()}
              placeholder="Ask a legal question or attach a document for immediate analysis..."
              className="flex-1 bg-transparent border-none focus:ring-0 text-[#121212] placeholder-gray-400 text-sm min-w-0 outline-none"
            />
            
            <button
              onClick={handleSend}
              disabled={isLoading || (!input.trim() && !ephemeralFile)}
              className="bg-[#1E293B] text-white p-2 rounded-lg hover:bg-[#0F172A] disabled:opacity-50 transition-colors"
            >
              <Send className="w-4 h-4" />
            </button>
          </div>
          <p className="text-center text-xs text-gray-400 mt-2">
            Documents attached here are ephemeral and NOT saved to your permanent Knowledge Base.
          </p>
        </div>
      </div>
    </div>
  );
};
