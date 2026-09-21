import React, { useState, useRef, useEffect } from 'react';
import { useLocation, useNavigate, useParams } from 'react-router-dom';

import { Send, Paperclip, FileText, X, Scale, AlertTriangle } from 'lucide-react';
import { MessageBubble } from '../components/Chat/MessageBubble';
import type { ApplicableLaw, ChatMessage, ChatSession, StructuredAnalysis } from '../types';
import { authFetch, authHeaders, notifyApiOnline, useAuth } from '../auth/auth';
import { API_URL } from '../config';
const loadingSynonyms = ['Thinking...', 'Analyzing...', 'Reviewing...', 'Almost there...'];

const VERIFIED_QUOTE_STATUSES = new Set(['backend_verified', 'verified', 'source_verified']);

const isVerifiedLaw = (law: ApplicableLaw): boolean => {
  const status = law.quote_status?.trim().toLowerCase();
  return law.verified === true && !!status && VERIFIED_QUOTE_STATUSES.has(status);
};

const formatSection = (section?: string | null, subsection?: string | null): string => {
  if (!section) return subsection ? `(${subsection})` : '';
  return subsection ? `${section}(${subsection})` : section;
};

const formatSourceReference = (law: ApplicableLaw): string | null => {
  if (!isVerifiedLaw(law)) return null;

  const act = law.act ?? law.code;
  const section = formatSection(law.section, law.subsection);
  const reference = [act, section].filter(Boolean).join(' — ');
  if (!reference) return null;

  if (law.source_url && /^https?:\/\//i.test(law.source_url)) {
    return `[${reference}](${law.source_url})`;
  }
  return reference;
};

const formatLegalLaw = (law: ApplicableLaw): string => {
  const title = [law.act ?? law.code, formatSection(law.section, law.subsection)]
    .filter(Boolean)
    .join(' — ') || 'Applicable law';
  const parts = [`### ${title}`];

  if (law.explanation?.trim()) {
    const explanation = law.explanation.trim().replace(/\s+/g, ' ');
    parts.push(`**Explanation**\n\n${explanation.length > 280 ? `${explanation.slice(0, 277)}…` : explanation}`);
  }

  const sourceReference = formatSourceReference(law);
  if (sourceReference) {
    parts.push(`**Verified source:** ${sourceReference}`);
  }

  return parts.join('\n\n');
};

const formatAnalysis = (analysis: unknown): string => {
  if (typeof analysis === 'string') return analysis;
  if (!analysis || typeof analysis !== 'object') return 'The backend returned an empty analysis.';

  const result = analysis as StructuredAnalysis;
  const sections: string[] = [];

  if (result.conversational_reply) sections.push(result.conversational_reply);
  if (result.general_analysis) sections.push(`## General Legal Analysis\n${result.general_analysis}`);
  if (result.situation_meaning) sections.push(`## What This Situation Means\n${result.situation_meaning}`);
  if (result.bail_status) sections.push(`## Bail Status\n${result.bail_status}`);
  if (result.next_24_hours?.length) {
    sections.push(`## What To Do Next\n${result.next_24_hours.map(item => `- ${item}`).join('\n')}`);
  }
  if (result.rights?.length) {
    sections.push(`## Your Rights\n${result.rights.map(item => `- ${item}`).join('\n')}`);
  }
  if (result.handling_authority) sections.push(`## Relevant Authority\n${result.handling_authority}`);
  if (result.applicable_laws?.length) {
    const laws = result.applicable_laws.map(formatLegalLaw);
    sections.push(`## Applicable Laws\n${laws.join('\n\n')}`);
  }
  if (result.suggest_lawyer) {
    sections.push('> Consider consulting a qualified lawyer for advice about your specific situation.');
  }

  return sections.join('\n\n') || 'The backend returned an analysis without readable content.';
};

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

const ChatLoadingScreen: React.FC = () => (
  <div className="h-full flex flex-col items-center justify-center text-gray-500 animate-fade-in">
    <div className="w-12 h-12 rounded-full border-4 border-gray-200 border-t-[#1E293B] animate-spin mb-5" />
    <p className="text-base font-medium text-gray-700">Loading your chat...</p>
    <p className="mt-2 text-sm text-gray-400 text-center max-w-xs">
      The free backend may take a moment to wake up.
    </p>
  </div>
);

export const ChatView: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { id: routeChatId } = useParams<{ id: string }>();
  const { credential, user } = useAuth();
  const preloadedMessages = (location.state as { preloadedMessages?: ChatMessage[] } | null)?.preloadedMessages;
  const [messages, setMessages] = useState<ChatMessage[]>(() => preloadedMessages ?? []);
  const [input, setInput] = useState('');
  const [modelPref, setModelPref] = useState('deep');
  const [isLoading, setIsLoading] = useState(false);
  const [isChatLoading, setIsChatLoading] = useState(false);
  const [quickUnavailable, setQuickUnavailable] = useState(false);
  const [ephemeralFile, setEphemeralFile] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let active = true;

    if (!routeChatId || !credential) {
      return () => {
        active = false;
      };
    }

    if (preloadedMessages && preloadedMessages.length > 0) {
      const historyState = window.history.state;
      if (historyState && typeof historyState === 'object') {
        window.history.replaceState(
          { ...(historyState as Record<string, unknown>), usr: null },
          '',
          window.location.href,
        );
      }
      return () => {
        active = false;
      };
    }

    const loadChat = async () => {
      setIsChatLoading(true);
      setMessages([]);
      try {
        const response = await authFetch(`${API_URL}/api/chats/${encodeURIComponent(routeChatId)}`, credential, {
          cache: 'no-store',
        });
        if (!response.ok) throw new Error(`Chat history failed: ${response.status}`);

        const chat = await response.json() as ChatSession;
        if (!active) return;

        setMessages((chat.messages ?? []).map((message) => ({
          role: message.role,
          content: message.role === 'assistant' && message.structured_content
            ? formatAnalysis(message.structured_content)
            : message.content,
          sources: message.sources ?? undefined,
          model_used: message.model_used ?? undefined,
          processing_time_seconds: message.processing_time_seconds ?? undefined,
          created_at: message.created_at,
        })));
      } catch (error) {
        console.error('Failed to load chat history', error);
      } finally {
        if (active) setIsChatLoading(false);
      }
    };

    loadChat();
    return () => {
      active = false;
    };
  }, [credential, routeChatId, location.state, preloadedMessages]);

  const shouldShowChatLoading = Boolean(routeChatId && credential && isChatLoading);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async () => {
    if ((!input.trim() && !ephemeralFile) || isLoading || shouldShowChatLoading) return;
    if (!credential) {
      navigate('/account');
      return;
    }

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
          notifyApiOnline();
          const data = await res.json();
          ephemeralContext = data.text;
        }
      } catch (e) {
        console.error("Failed to extract ephemeral doc", e);
      }
      setEphemeralFile(null); // clear after sending
    }

    const newMessage: ChatMessage = { role: 'user', content: input, created_at: new Date().toISOString() };
    setMessages(prev => [...prev, newMessage]);
    setInput('');

    try {
      let activeChatId = routeChatId;
      if (!activeChatId) {
        const createResponse = await authFetch(`${API_URL}/api/chats`, credential, {
          method: 'POST',
          headers: { ...authHeaders(credential), 'Content-Type': 'application/json' },
          body: JSON.stringify({ title: 'New Chat' }),
        });
        if (!createResponse.ok) throw new Error('Could not create a chat session.');
        const createdChat = await createResponse.json() as ChatSession;
        activeChatId = createdChat.id;
        window.dispatchEvent(new CustomEvent('chat-created', { detail: createdChat }));
      }

      const res = await authFetch(`${API_URL}/api/analyze`, credential, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: newMessage.content || "Analyze the attached document.",
          ephemeral_context: ephemeralContext,
          model_preference: modelPref,
          chat_id: activeChatId,
        })
      });

      if (res.ok) {
        notifyApiOnline(true);
        const data = await res.json();
        const assistantMessage: ChatMessage = {
          role: 'assistant',
          content: formatAnalysis(data.analysis),
          sources: data.sources,
          model_used: data.model_used,
          processing_time_seconds: data.processing_time_seconds,
          created_at: new Date().toISOString(),
        };
        setMessages(prev => [...prev, assistantMessage]);
        if (!routeChatId && activeChatId) {
          navigate(`/chat/${activeChatId}`, {
            replace: true,
            state: { preloadedMessages: [...messages, newMessage, assistantMessage] },
          });
        }
      } else {
        let detail = 'The backend could not complete the analysis.';
        let errorCode = '';
        try {
          const err = await res.json() as { detail?: unknown };
          if (typeof err.detail === 'string') {
            detail = err.detail;
          } else if (err.detail && typeof err.detail === 'object') {
            const structuredDetail = err.detail as { code?: unknown; message?: unknown };
            errorCode = typeof structuredDetail.code === 'string' ? structuredDetail.code : '';
            if (typeof structuredDetail.message === 'string') detail = structuredDetail.message;
          }
        } catch {
          // Keep the user-facing fallback when the proxy returns a non-JSON error.
        }

        const quickIsUnavailable = res.status === 429 && (
          errorCode === 'QUICK_MODEL_UNAVAILABLE' ||
          detail.toLowerCase().includes('quick thinking')
        );
        if (quickIsUnavailable) {
          setQuickUnavailable(true);
          setModelPref('deep');
          detail = 'Quick Thinking is temporarily unavailable because Gemini Flash has reached its limit on all configured API keys. Deep Thinking is still available.';
        }
        setMessages(prev => [...prev, {
          role: 'assistant',
          content: `I couldn't complete that analysis. ${detail} Please try again in a moment.`
        }]);
      }
    } catch {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: 'I couldn\'t reach the analysis service. It may be waking up; please try again in a moment.'
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="chat-view flex flex-col h-full bg-[#F2F0EB] relative">
      {/* Header */}
      <header className="chat-view__header h-16 border-b border-gray-100 flex items-center justify-between px-6 flex-shrink-0 z-10 bg-white/80 backdrop-blur-sm">
        <h2 className="text-lg font-serif tracking-tight text-[#121212]">Legal Analysis</h2>
        <div className="chat-view__model flex items-center gap-2">
          <span className="text-xs font-medium text-gray-500 uppercase tracking-wider">Model:</span>
          <select
            value={modelPref}
            onChange={e => setModelPref(e.target.value)}
            className="text-sm bg-white border border-gray-200 rounded-md px-3 py-1.5 outline-none text-gray-700 shadow-sm hover:border-gray-300 focus:border-[#1E293B] focus:ring-1 focus:ring-[#1E293B] transition-all cursor-pointer"
          >
            <option value="deep">Deep Thinking</option>
            <option value="quick" disabled={quickUnavailable}>
              {quickUnavailable ? 'Quick Thinking (temporarily unavailable)' : 'Quick Thinking'}
            </option>
          </select>
        </div>
        {quickUnavailable && (
          <div className="chat-view__alert mt-2 flex items-center justify-end gap-1.5 text-xs text-amber-700" role="status">
            <AlertTriangle className="h-3.5 w-3.5" />
            Quick Thinking is temporarily unavailable. Please use Deep Thinking for now.
          </div>
        )}
      </header>

      {/* Messages */}
      <div className="chat-view__messages flex-1 overflow-y-auto p-6 space-y-6">
        {shouldShowChatLoading ? (
          <ChatLoadingScreen />
        ) : messages.length === 0 && (
          <div className="h-full flex flex-col items-center justify-center text-gray-400">
            <Scale className="w-12 h-12 mb-4 opacity-20" />
            <p className="text-sm">{user ? 'Start a new legal inquiry...' : 'Sign in with Google to start chatting.'}</p>
            {!user && (
              <button type="button" onClick={() => navigate('/account')} className="mt-4 rounded-lg bg-[#1E293B] px-4 py-2 text-sm text-white hover:bg-[#0F172A]">
                Open Account
              </button>
            )}
          </div>
        )}
        {messages.map((msg, idx) => (
          <MessageBubble key={idx} message={msg} />
        ))}
        {isLoading && <ThinkingAnimation />}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="chat-view__composer p-4 bg-white border-t border-gray-100">
        <div className="max-w-3xl mx-auto">
          {ephemeralFile && (
            <div className="chat-view__file-chip mb-3 flex items-center gap-2 bg-[#F9F9F8] border border-gray-200 text-sm py-2 px-3 rounded-md w-max">
              <FileText className="w-4 h-4 text-blue-500" />
              <span className="text-gray-700 font-medium truncate max-w-[200px]">{ephemeralFile.name}</span>
              <button onClick={() => setEphemeralFile(null)} className="text-gray-400 hover:text-gray-600 ml-2">
                <X className="w-4 h-4" />
              </button>
            </div>
          )}
          
          <div className="chat-view__input-shell flex items-center gap-3 bg-white border border-gray-300 rounded-xl px-4 py-3 shadow-sm focus-within:ring-2 focus-within:ring-[#1E293B] focus-within:border-transparent transition-all">
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
              className="chat-view__attach-button text-gray-400 hover:text-[#1E293B] transition-colors p-1"
              onClick={() => fileInputRef.current?.click()}
              disabled={!user || shouldShowChatLoading}
              title="Attach document for this query only"
            >
              <Paperclip className="w-5 h-5" />
            </button>
            
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSend()}
              placeholder={user ? 'Ask a legal question or attach a document for immediate analysis...' : 'Sign in to ask TRANA a question...'}
              disabled={!user || shouldShowChatLoading}
              className="flex-1 bg-transparent border-none focus:ring-0 text-[#121212] placeholder-gray-400 text-sm min-w-0 outline-none"
            />
            
            <button
              className="chat-view__send-button bg-[#1E293B] text-white p-2 rounded-lg hover:bg-[#0F172A] disabled:opacity-50 transition-colors"
              onClick={handleSend}
              disabled={!user || isLoading || (!input.trim() && !ephemeralFile)}
            >
              <Send className="w-4 h-4" />
            </button>
          </div>
          <p className="text-center text-xs text-gray-400 mt-2">
            Documents attached here are ephemeral and are not added to TRANA's indexed documents.
          </p>
        </div>
      </div>
    </div>
  );
};
