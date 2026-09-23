import React, { useState, useEffect } from 'react';
import { User, Scale, ChevronDown, ChevronUp, Clock, CalendarClock, ExternalLink, FileText } from 'lucide-react';
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

const INDIA_CODE_ACT_URLS = {
  bns: 'https://www.indiacode.nic.in/indiacode/handle/123456789/20062?col=123456789%2F1362&view_type=search',
  bnss: 'https://www.indiacode.nic.in/indiacode/handle/123456789/20099?view_type=browse',
  bsa: 'https://www.indiacode.nic.in/indiacode/handle/123456789/20063?col=123456789%2F1362&view_type=search',
} as const;

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

const formatActName = (source: SourceChunk): string =>
  source.act?.trim() || source.code?.trim() || formatDocName(source.document_name);

const formatSectionLabel = (source: SourceChunk): string =>
  formatSection(source.section, source.subsection) || 'General';

const formatQuoteStatus = (source: SourceChunk): string => {
  if (isVerifiedSource(source)) return 'Verified';
  if (source.quote_status?.trim().toLowerCase() === 'not_found') return 'Unavailable';
  return 'Not verified';
};

const getSourceText = (source: SourceChunk): string | null => {
  const text = source.exact_text ?? source.quote ?? source.content;
  return typeof text === 'string' && text.trim() ? text.trim() : null;
};

const getConciseExplanation = (source: SourceChunk): string | null => {
  const explanation = source.explanation?.trim().replace(/\s+/g, ' ');
  if (!explanation) return null;
  return explanation.length > 260 ? `${explanation.slice(0, 257)}...` : explanation;
};

const getIndiaCodeUrl = (source: SourceChunk): string | null => {
  const identity = [source.act, source.code, source.document_name].filter(Boolean).join(' ').toLowerCase();
  // Always use the canonical act landing page for BNS/BNSS/BSA. This also
  // repairs older persisted messages whose source_url points at a stale PDF
  // or an India Code route that now returns an Akamai error.
  if (identity.includes('bharatiya nyaya') || /\bbns\b/.test(identity)) return INDIA_CODE_ACT_URLS.bns;
  if (identity.includes('bharatiya nagarik') || /\bbnss\b/.test(identity)) return INDIA_CODE_ACT_URLS.bnss;
  if (identity.includes('bharatiya sakshya') || /\bbsa\b/.test(identity)) return INDIA_CODE_ACT_URLS.bsa;

  const suppliedUrl = source.source_url?.trim();
  if (suppliedUrl) {
    try {
      const parsed = new URL(suppliedUrl);
      const hostname = parsed.hostname.toLowerCase();
      const isIndiaCode = hostname === 'indiacode.nic.in' || hostname.endsWith('.indiacode.nic.in');
      if (parsed.protocol === 'https:' && isIndiaCode) return parsed.toString();
    } catch {
      // No safe official URL was supplied.
    }
  }

  return null;
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
            <div className="message-sources mt-2 w-full">
              <button 
                className="message-sources__toggle flex items-center gap-1.5 text-xs font-medium text-gray-600 hover:text-gray-900 transition-colors bg-white border border-gray-200 px-3 py-1.5 rounded-full shadow-sm"
                type="button"
                aria-expanded={sourcesOpen}
                onClick={() => setSourcesOpen(!sourcesOpen)}
              >
                {sourcesOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                {message.sources.length} {message.sources.length === 1 ? 'source' : 'sources'}
              </button>
              
              {sourcesOpen && (
                <div className="message-sources__list mt-3 w-full max-w-4xl animate-slide-down-fade">
                  {message.sources.map((source, idx) => (
                    <article key={idx} className="message-source-card">
                      <div className="message-source-card__header">
                        <div className="message-source-card__identity">
                          <FileText size={16} aria-hidden="true" />
                          <div className="min-w-0">
                            <div className="message-source-card__act">{formatActName(source)}</div>
                            <div className="message-source-card__section">Section {formatSectionLabel(source)}</div>
                          </div>
                        </div>
                        <span className={`message-source-card__badge ${isVerifiedSource(source) ? 'is-verified' : 'is-unverified'}`}>
                          {formatQuoteStatus(source)}
                        </span>
                      </div>
                      {getConciseExplanation(source) && (
                        <p className="message-source-card__explanation">{getConciseExplanation(source)}</p>
                      )}

                      {getSourceText(source) ? (
                        <details className="message-source-card__details">
                          <summary>{isVerifiedSource(source) ? 'View verified statutory text' : 'View source excerpt'}</summary>
                          <div className="message-source-card__text">{getVerifiedText(source) ?? getSourceText(source)}</div>
                        </details>
                      ) : !getConciseExplanation(source) ? (
                        <p className="message-source-card__empty">Exact statutory wording is not available for this reference.</p>
                      ) : null}

                      <div className="message-source-card__footer">
                        {getIndiaCodeUrl(source) ? (
                          <a
                            href={getIndiaCodeUrl(source) ?? undefined}
                            target="_blank"
                            rel="noreferrer"
                            className="message-source-card__link"
                          >
                            <ExternalLink size={13} aria-hidden="true" />
                            Open India Code
                          </a>
                        ) : (
                          <span className="message-source-card__no-link">Official link unavailable</span>
                        )}
                        {(source.source_version || source.source_hash) && (
                          <details className="message-source-card__technical">
                            <summary>Technical details</summary>
                            {source.source_version && <span>Version: {source.source_version}</span>}
                            {source.source_hash && <span className="break-all">Source hash: {source.source_hash}</span>}
                          </details>
                        )}
                      </div>
                    </article>
                  ))}
                </div>
              )}
            </div>
          )}
          
          {/* Message metadata */}
          {(formattedMessageTime || (!isUser && message.processing_time_seconds !== undefined)) && (
            <div className="message-bubble__metadata flex flex-wrap gap-x-4 gap-y-1 mt-3 ml-1 text-xs text-gray-400 font-medium">
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
