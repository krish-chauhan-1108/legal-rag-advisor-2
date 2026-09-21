import React, { useState, useEffect } from 'react';
import { User, Scale, ChevronDown, ChevronUp, Clock, Cpu, CalendarClock } from 'lucide-react';
import { marked } from 'marked';
import type { ChatMessage, SourceChunk } from '../../types';

interface MessageBubbleProps {
  message: ChatMessage;
}

const formatMessageTime = (value: string): string | null => {
  // Older API records contain UTC timestamps without an offset.
  const normalizedValue = /(?:Z|[+-]\d{2}:?\d{2})$/.test(value) ? value : `${value}Z`;
  const date = new Date(normalizedValue);
  if (Number.isNaN(date.getTime())) return null;

  return `${new Intl.DateTimeFormat('en-IN', {
    timeZone: 'Asia/Kolkata',
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  }).format(date)} IST`;
};

const VERIFIED_QUOTE_STATUSES = new Set(['backend_verified', 'verified', 'source_verified']);

const isVerifiedSource = (source: SourceChunk): boolean => {
  const status = source.quote_status?.trim().toLowerCase();
  return source.verified === true && !!status && VERIFIED_QUOTE_STATUSES.has(status);
};

const getVerifiedText = (source: SourceChunk): string | null => {
  if (!isVerifiedSource(source)) return null;
  const text = source.exact_text ?? source.quote ?? source.content;
  return typeof text === 'string' && text.trim() ? text.trim() : null;
};

const formatDocName = (name?: string) => {
  if (!name) return 'Legal source';
  if (name.includes('::')) {
    const parts = name.split('::');
    return `Case Document: ${parts[parts.length - 1]}`;
  }
  return name;
};

const formatSection = (section?: string, subsection?: string | null): string => {
  if (!section) return subsection ? `(${subsection})` : '';
  return subsection ? `${section}(${subsection})` : section;
};

const formatCitationTitle = (source: SourceChunk): string => {
  const act = source.act ?? source.code ?? source.document_name;
  const section = formatSection(source.section, source.subsection);
  return [act, section].filter(Boolean).join(' — ') || formatDocName(source.document_name);
};

const formatQuoteStatus = (source: SourceChunk): string => {
  if (isVerifiedSource(source)) return 'Verified source';
  if (source.quote_status === 'not_found') return 'Source not found';
  return 'Unverified reference';
};

export const MessageBubble: React.FC<MessageBubbleProps> = ({ message }) => {
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const isUser = message.role === 'user';

  const [animatedContent, setAnimatedContent] = useState(isUser ? '' : message.content);

  useEffect(() => {
    if (isUser) {
      return;
    }

    let index = 0;
    const interval = setInterval(() => {
      index += 5;
      if (index >= message.content.length) {
        setAnimatedContent(message.content);
        clearInterval(interval);
      } else {
        setAnimatedContent(message.content.substring(0, index));
      }
    }, 15);

    return () => clearInterval(interval);
  }, [message.content, isUser]);

  const displayedContent = isUser ? message.content : animatedContent;
  const cleanContent = displayedContent.replace(/\|\n\n\|/g, '|\n|');
  const htmlContent = marked.parse(cleanContent) as string;
  const modelLabel = message.model_used?.toLowerCase().includes('gemini')
    ? 'Quick Thinking'
    : 'Deep Thinking';
  const formattedMessageTime = message.created_at
    ? formatMessageTime(message.created_at)
    : null;

  return (
    <div className={`message-bubble flex w-full mb-6 ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div className={`message-bubble__row flex max-w-[85%] ${isUser ? 'flex-row-reverse' : 'flex-row'} gap-4`}>
        {/* Avatar */}
        <div className={`message-bubble__avatar flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center mt-1 shadow-sm ${isUser ? 'bg-[#1E293B]' : 'bg-white border border-gray-200'}`}>
          {isUser ? <User size={16} color="white" /> : <Scale size={16} className="text-[#1E293B]" />}
        </div>
        
        {/* Bubble */}
        <div className={`message-bubble__content flex flex-col ${isUser ? 'items-end' : 'items-start'} min-w-0`}>
          <div className={`message-bubble__bubble px-5 py-4 rounded-2xl shadow-sm ${
            isUser 
              ? 'bg-[#1E293B] text-white rounded-tr-none' 
              : 'bg-white border border-gray-100 rounded-tl-none text-gray-800'
          }`}>
            <div
              className={`prose prose-sm max-w-none ${isUser ? 'text-white' : 'text-gray-800'}`}
              dangerouslySetInnerHTML={{ __html: htmlContent }}
            />
          </div>
          
          {/* Render Sources for AI Messages */}
          {!isUser && message.sources && message.sources.length > 0 && (
            <div className="mt-2 w-full">
              <button 
                className="flex items-center gap-1 text-xs font-medium text-gray-500 hover:text-gray-800 transition-colors bg-white border border-gray-200 px-3 py-1.5 rounded-full shadow-sm"
                onClick={() => setSourcesOpen(!sourcesOpen)}
              >
                {sourcesOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                {message.sources.length} Sources
              </button>
              
              {sourcesOpen && (
                <div className="mt-3 bg-[#E2E8F0] border border-[#CBD5E1] rounded-xl shadow-sm w-full max-w-4xl overflow-hidden flex flex-col animate-slide-down-fade">
                  {message.sources.map((source, idx) => (
                    <div key={idx} className={`p-4 ${idx !== 0 ? 'border-t border-[#CBD5E1]' : ''}`}>
                      <div className="mb-2 flex flex-wrap items-start justify-between gap-2">
                        <span className="font-bold text-[#0F172A] flex items-center gap-1.5 text-sm break-words">
                          📄 {formatCitationTitle(source)}
                        </span>
                        <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${isVerifiedSource(source) ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800'}`}>
                          {formatQuoteStatus(source)}
                        </span>
                      </div>
                      {source.section && source.section !== 'General' && (
                        <div className="text-xs text-slate-500 mb-2 font-medium">
                          Section: {source.section} {source.page_number ? `(Pg. ${source.page_number})` : ''}
                        </div>
                      )}
                      {source.explanation && (
                        <div className="mb-3 text-slate-700 text-xs leading-relaxed">
                          <div className="mb-1 font-semibold text-slate-500">Explanation</div>
                          {source.explanation}
                        </div>
                      )}
                      {getVerifiedText(source) ? (
                        <div className="text-slate-700 text-xs leading-relaxed max-h-40 overflow-y-auto custom-scrollbar pr-2">
                          <div className="mb-1 font-semibold text-emerald-800">Verified statutory text</div>
                          <div className="whitespace-pre-wrap">{getVerifiedText(source)}</div>
                        </div>
                      ) : source.exact_text ?? source.quote ?? source.content ? (
                        <div className="text-slate-700 text-xs leading-relaxed max-h-32 overflow-y-auto custom-scrollbar pr-2">
                          <div className="mb-1 font-semibold text-slate-500">Source excerpt</div>
                          <div className="whitespace-pre-wrap">{source.exact_text ?? source.quote ?? source.content}</div>
                        </div>
                      ) : !source.explanation ? (
                        <div className="text-xs italic text-slate-500">
                          Exact statutory wording could not be verified from the available source.
                        </div>
                      ) : null}
                      {(source.source_url || source.source_version || source.source_hash) && (
                        <div className="mt-3 flex flex-col gap-1 text-[11px] text-slate-500">
                          {source.source_url && /^https?:\/\//i.test(source.source_url) && (
                            <a href={source.source_url} target="_blank" rel="noreferrer" className="font-medium text-slate-700 underline underline-offset-2 hover:text-slate-900">
                              Open official source
                            </a>
                          )}
                          {source.source_version && <span>Version: {source.source_version}</span>}
                          {source.source_hash && <span className="break-all">Source hash: {source.source_hash}</span>}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
          
          {/* Message metadata */}
          {(formattedMessageTime || (!isUser && (message.model_used || message.processing_time_seconds !== undefined))) && (
            <div className="message-bubble__metadata flex flex-wrap gap-x-4 gap-y-1 mt-3 ml-1 text-xs text-gray-400 font-medium">
              {!isUser && message.model_used && (
                <span className="flex items-center gap-1.5">
                  <Cpu size={12} /> {modelLabel}
                </span>
              )}
              {!isUser && message.processing_time_seconds !== undefined && message.processing_time_seconds !== null && (
                <span className="flex items-center gap-1.5">
                  <Clock size={12} /> {message.processing_time_seconds.toFixed(2)}s time taken
                </span>
              )}
              {formattedMessageTime && (
                <span className="flex items-center gap-1.5">
                  <CalendarClock size={12} /> {isUser ? 'Prompt' : 'Sent'} {formattedMessageTime}
                </span>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
