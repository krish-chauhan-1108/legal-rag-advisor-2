import React, { useState, useRef, useEffect } from 'react';
import { useLocation, useNavigate, useParams } from 'react-router-dom';

import { Send, Paperclip, FileText, Image as ImageIcon, X, Scale, AlertTriangle } from 'lucide-react';
import { MessageBubble } from '../components/Chat/MessageBubble';
import type { ApplicableLaw, ChatMessage, ChatSession, StructuredAnalysis } from '../types';
import { authFetch, authHeaders, notifyApiOnline, useAuth } from '../auth/auth';
import { API_URL } from '../config';
const loadingSynonyms = ['Thinking...', 'Analyzing...', 'Reviewing...', 'Almost there...'];
const WELCOME_MESSAGE = "I'm TRANA\u2014your friendly legal assistant. How can I help you today?";

interface ChatAttachment {
  id: string;
  filename: string;
  content_type: string;
  size?: number;
  created_at?: string;
}

const isImageFile = (file: Pick<File, 'type' | 'name'>): boolean =>
  file.type.startsWith('image/') || /\.(jpe?g|png|webp|gif|heic|heif)$/i.test(file.name);

const readAttachments = (payload: unknown): ChatAttachment[] => {
  if (!payload || typeof payload !== 'object') return [];
  const attachments = (payload as { attachments?: unknown }).attachments;
  if (!Array.isArray(attachments)) return [];
  return attachments.filter((item): item is ChatAttachment => Boolean(
    item && typeof item === 'object' &&
    typeof (item as ChatAttachment).id === 'string' &&
    typeof (item as ChatAttachment).filename === 'string' &&
    typeof (item as ChatAttachment).content_type === 'string'
  ));
};

const createWelcomeMessage = (): ChatMessage => ({
  role: 'assistant',
  content: WELCOME_MESSAGE,
  created_at: new Date().toISOString(),
});

const formatSection = (section?: string | null, subsection?: string | null): string => {
  if (!section) return subsection ? `(${subsection})` : '';
  return subsection ? `${section}(${subsection})` : section;
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

  return parts.join('\n\n');
};

const formatAnalysis = (
  analysis: unknown,
  options: { includeLegacyLawSummary?: boolean } = {},
): string => {
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
  // Current responses render authoritative sources in MessageBubble. Keep a
  // plain law summary only for older persisted messages that have no separate
  // `sources` array, so legacy chats remain readable without duplicate links.
  if (options.includeLegacyLawSummary && result.applicable_laws?.length) {
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
  const [messages, setMessages] = useState<ChatMessage[]>(() => (
    preloadedMessages ?? (routeChatId ? [] : [createWelcomeMessage()])
  ));
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isChatLoading, setIsChatLoading] = useState(false);
  const [quickUnavailable, setQuickUnavailable] = useState(false);
  const [pendingFiles, setPendingFiles] = useState<File[]>([]);
  const [chatAttachments, setChatAttachments] = useState<ChatAttachment[]>([]);
  const [attachmentError, setAttachmentError] = useState('');
  const [previewUrls, setPreviewUrls] = useState<Record<string, string>>({});
  const [isUploadingAttachments, setIsUploadingAttachments] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const chatInputRef = useRef<HTMLInputElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const pendingChatIdRef = useRef<string | null>(null);

  // Handle clipboard content anywhere inside the open chat. Plain text keeps
  // native caret insertion when the composer is focused; elsewhere it is
  // appended to the composer. Clipboard images join the normal upload queue.
  const handleChatPaste = (event: React.ClipboardEvent<HTMLDivElement>) => {
    const clipboard = event.clipboardData;
    const images = Array.from(clipboard.items)
      .filter((item) => item.kind === 'file' && item.type.startsWith('image/'))
      .map((item) => item.getAsFile())
      .filter((file): file is File => file !== null);
    const text = clipboard.getData('text/plain');
    const composerFocused = event.target === chatInputRef.current;
    if (!images.length && composerFocused) return;
    if (images.length) {
      event.preventDefault();
      const namedImages = images.map((file, index) => new File(
        [file], file.name || `clipboard-image-${Date.now()}-${index + 1}.${file.type.split('/')[1] || 'png'}`,
        { type: file.type, lastModified: Date.now() },
      ));
      setPendingFiles((files) => [...files, ...namedImages]);
      setAttachmentError('');
    }
    if (text && (!composerFocused || images.length > 0)) {
      event.preventDefault();
      setInput((current) => {
        if (!current) return text;
        if (!composerFocused) return `${current}\n${text}`;
        const inputElement = chatInputRef.current;
        const start = inputElement?.selectionStart ?? current.length;
        const end = inputElement?.selectionEnd ?? start;
        return `${current.slice(0, start)}${text}${current.slice(end)}`;
      });
    }
  };

  useEffect(() => {
    const urls: Record<string, string> = {};
    pendingFiles.forEach((file) => {
      if (isImageFile(file)) urls[`${file.name}:${file.size}:${file.lastModified}`] = URL.createObjectURL(file);
    });
    setPreviewUrls(urls);
    return () => Object.values(urls).forEach((url) => URL.revokeObjectURL(url));
  }, [pendingFiles]);

  useEffect(() => {
    let active = true;
    if (!routeChatId || !credential) {
      setChatAttachments([]);
      return () => { active = false; };
    }
    const loadAttachments = async () => {
      try {
        const response = await authFetch(`${API_URL}/api/chats/${encodeURIComponent(routeChatId)}/attachments`, credential, { cache: 'no-store' });
        if (!response.ok) throw new Error(`Attachment list failed: ${response.status}`);
        const payload: unknown = await response.json();
        if (active) setChatAttachments(readAttachments(payload));
      } catch (error) {
        console.error('Failed to load chat attachments', error);
        if (active) setAttachmentError('Could not load this chat’s attachments. Reload the chat to try again.');
      }
    };
    setAttachmentError('');
    loadAttachments();
    return () => { active = false; };
  }, [credential, routeChatId]);

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

        setMessages((chat.messages ?? []).map((message) => {
          const sources = message.sources ?? undefined;
          return {
            role: message.role,
            content: message.role === 'assistant' && message.structured_content
              ? formatAnalysis(message.structured_content, { includeLegacyLawSummary: !sources?.length })
              : message.content,
            sources,
            model_used: message.model_used ?? undefined,
            processing_time_seconds: message.processing_time_seconds ?? undefined,
            created_at: message.created_at,
          };
        }));
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
    if ((!input.trim() && pendingFiles.length === 0) || isLoading || shouldShowChatLoading) return;
    if (!credential) {
      navigate('/account');
      return;
    }

    setIsLoading(true);
    const newMessage: ChatMessage = { role: 'user', content: input, created_at: new Date().toISOString() };
    setAttachmentError('');
    let uploadComplete = pendingFiles.length === 0;

    try {
      let activeChatId = routeChatId ?? pendingChatIdRef.current;
      if (!activeChatId) {
        const createResponse = await authFetch(`${API_URL}/api/chats`, credential, {
          method: 'POST',
          headers: { ...authHeaders(credential), 'Content-Type': 'application/json' },
          body: JSON.stringify({ title: 'New Chat' }),
        });
        if (!createResponse.ok) throw new Error('Could not create a chat session.');
        const createdChat = await createResponse.json() as ChatSession;
        activeChatId = createdChat.id;
        pendingChatIdRef.current = activeChatId;
        window.dispatchEvent(new CustomEvent('chat-created', { detail: createdChat }));
      }

      if (pendingFiles.length > 0) {
        setIsUploadingAttachments(true);
        const formData = new FormData();
        pendingFiles.forEach((file) => formData.append('files', file, file.name));
        const uploadResponse = await authFetch(`${API_URL}/api/chats/${encodeURIComponent(activeChatId)}/attachments`, credential, {
          method: 'POST',
          body: formData,
        });
        if (!uploadResponse.ok) {
          let detail = 'The files could not be uploaded. Your selected files are still here; please try again.';
          try {
            const body = await uploadResponse.json() as { detail?: unknown };
            if (typeof body.detail === 'string') detail = body.detail;
          } catch { /* Keep the actionable fallback. */ }
          throw new Error(detail);
        }
        const uploaded: unknown = await uploadResponse.json();
        const uploadedAttachments = readAttachments(uploaded);
        if (uploadedAttachments.length !== pendingFiles.length) {
          throw new Error('The server did not confirm every attachment. Your selected files are still here; please retry.');
        }
        setChatAttachments((current) => {
          const ids = new Set(current.map((attachment) => attachment.id));
          return [...current, ...uploadedAttachments.filter((attachment) => !ids.has(attachment.id))];
        });
        setPendingFiles([]);
        uploadComplete = true;
      }

      setMessages(prev => [...prev, newMessage]);
      setInput('');

      const res = await authFetch(`${API_URL}/api/analyze`, credential, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: newMessage.content || "Analyze the attached document.",
          model_preference: 'quick',
          chat_id: activeChatId,
        })
      });

      if (res.ok) {
        notifyApiOnline(true);
        const data = await res.json();
        const sources = Array.isArray(data.sources) ? data.sources : undefined;
        const assistantMessage: ChatMessage = {
          role: 'assistant',
          content: formatAnalysis(data.analysis, { includeLegacyLawSummary: !sources?.length }),
          sources,
          model_used: data.model_used,
          processing_time_seconds: data.processing_time_seconds,
          created_at: new Date().toISOString(),
        };
        setMessages(prev => [...prev, assistantMessage]);
        if (!routeChatId && activeChatId) {
          const messagesForNavigation = messages.length > 0
            ? messages
            : [createWelcomeMessage()];
          navigate(`/chat/${activeChatId}`, {
            replace: true,
            state: { preloadedMessages: [...messagesForNavigation, newMessage, assistantMessage] },
          });
          pendingChatIdRef.current = null;
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
          detail = 'Quick Thinking is temporarily unavailable because all configured Quick Thinking providers are rate-limited.';
        }
        setMessages(prev => [...prev, {
          role: 'assistant',
          content: `I couldn't complete that analysis. ${detail} Please try again in a moment.`
        }]);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'I couldn’t send this message. Please try again.';
      if (!uploadComplete) {
        setAttachmentError(message);
      } else {
        setMessages(prev => [...prev, {
          role: 'assistant',
          content: 'I couldn\'t reach the analysis service. It may be waking up; please try again in a moment.'
        }]);
      }
    } finally {
      setIsUploadingAttachments(false);
      setIsLoading(false);
    }
  };

  return (
    <div className="chat-view flex flex-col h-full bg-[#F2F0EB] relative" onPaste={handleChatPaste}>
      {/* Header */}
      <header className="chat-view__header h-16 border-b border-gray-100 flex items-center justify-between px-6 flex-shrink-0 z-10 bg-white/80 backdrop-blur-sm">
        <h2 className="text-lg font-serif tracking-tight text-[#121212]">Legal Analysis</h2>
        {quickUnavailable && (
          <div className="chat-view__alert mt-2 flex items-center justify-end gap-1.5 text-xs text-amber-700" role="status">
            <AlertTriangle className="h-3.5 w-3.5" />
            Quick Thinking is temporarily unavailable. Please try again shortly.
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
          {(chatAttachments.length > 0 || pendingFiles.length > 0) && (
            <div className="mb-3 flex flex-wrap gap-2" aria-label="Chat attachments">
              {chatAttachments.map((attachment) => (
                <div key={attachment.id} className="flex items-center gap-2 bg-[#F9F9F8] border border-gray-200 text-xs py-1.5 px-2.5 rounded-lg max-w-full" title={`${attachment.filename} (saved in this chat)`}>
                  {attachment.content_type.startsWith('image/') ? <ImageIcon className="w-4 h-4 text-violet-500 shrink-0" /> : <FileText className="w-4 h-4 text-blue-500 shrink-0" />}
                  <span className="text-gray-700 font-medium truncate max-w-[180px]">{attachment.filename}</span>
                  <span className="text-gray-400">Saved</span>
                </div>
              ))}
              {pendingFiles.map((file, index) => {
                const key = `${file.name}:${file.size}:${file.lastModified}`;
                const preview = previewUrls[key];
                return (
                  <div key={`${key}:${index}`} className="flex items-center gap-2 bg-[#F9F9F8] border border-gray-200 text-xs py-1.5 px-2.5 rounded-lg max-w-full">
                    {preview ? <img src={preview} alt="" className="w-7 h-7 object-cover rounded" /> : <FileText className="w-4 h-4 text-blue-500 shrink-0" />}
                    <span className="text-gray-700 font-medium truncate max-w-[180px]">{file.name}</span>
                    <button type="button" aria-label={`Remove ${file.name}`} onClick={() => setPendingFiles((files) => files.filter((_, i) => i !== index))} disabled={isLoading} className="text-gray-400 hover:text-gray-600 disabled:opacity-40">
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                );
              })}
            </div>
          )}
          {attachmentError && <p role="alert" className="mb-2 text-sm text-red-700">{attachmentError}</p>}
          {isUploadingAttachments && <p role="status" className="mb-2 text-sm text-gray-500">Saving attachments to this chat…</p>}
          
          <div className="chat-view__input-shell flex items-center gap-3 bg-white border border-gray-300 rounded-xl px-4 py-3 shadow-sm focus-within:ring-2 focus-within:ring-[#1E293B] focus-within:border-transparent transition-all">
            <input 
              type="file"
              ref={fileInputRef}
              onChange={(e) => {
                const chosen = Array.from(e.target.files ?? []);
                if (chosen.length) {
                  setPendingFiles((files) => {
                    const existing = new Set(files.map((file) => `${file.name}:${file.size}:${file.lastModified}`));
                    return [...files, ...chosen.filter((file) => !existing.has(`${file.name}:${file.size}:${file.lastModified}`))];
                  });
                  setAttachmentError('');
                }
                e.currentTarget.value = '';
              }}
              className="hidden"
              accept="application/pdf,.pdf,image/*,.jpg,.jpeg,.png,.webp,.gif,.heic,.heif"
              multiple
            />
            <button
              className="chat-view__attach-button text-gray-400 hover:text-[#1E293B] transition-colors p-1"
              onClick={() => fileInputRef.current?.click()}
              disabled={!user || shouldShowChatLoading}
              title="Attach PDFs or photos to this chat"
            >
              <Paperclip className="w-5 h-5" />
            </button>
            
            <input
              ref={chatInputRef}
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSend()}
              placeholder={user ? 'Ask a legal question or attach PDFs and photos...' : 'Sign in to ask TRANA a question...'}
              disabled={!user || shouldShowChatLoading}
              className="flex-1 bg-transparent border-none focus:ring-0 text-[#121212] placeholder-gray-400 text-sm min-w-0 outline-none"
            />
            
            <button
              className="chat-view__send-button bg-[#1E293B] text-white p-2 rounded-lg hover:bg-[#0F172A] disabled:opacity-50 transition-colors"
              onClick={handleSend}
              disabled={!user || isLoading || (!input.trim() && pendingFiles.length === 0)}
            >
              <Send className="w-4 h-4" />
            </button>
          </div>
          <p className="text-center text-xs text-gray-400 mt-2">
            PDFs and photos are saved with this chat for follow-up questions. They are not added to TRANA’s shared legal library.
          </p>
        </div>
      </div>
    </div>
  );
};
