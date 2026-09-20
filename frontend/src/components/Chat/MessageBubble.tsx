import React, { useState, useEffect } from 'react';
import { User, Scale, ChevronDown, ChevronUp, Clock, Cpu, FileText, AlertTriangle, ShieldCheck, ListTodo } from 'lucide-react';
import { marked } from 'marked';
import type { ChatMessage } from '../../types';

interface MessageBubbleProps {
  message: ChatMessage;
  animate?: boolean;
}

const ExpandableQuote: React.FC<{ quote: string }> = ({ quote }) => {
  const [expanded, setExpanded] = useState(false);

  return (
    <div 
      className="text-sm text-slate-700 italic mb-3 p-3 bg-slate-200 border border-slate-300 rounded-md shadow-inner cursor-pointer hover:bg-slate-300 transition-colors duration-200"
      onClick={() => setExpanded(!expanded)}
    >
      <div className={`${expanded ? '' : 'line-clamp-2'}`}>
        "{quote}"
      </div>
    </div>
  );
};

export const MessageBubble: React.FC<MessageBubbleProps> = ({ message, animate = true }) => {
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const [expandedSources, setExpandedSources] = useState<Record<number, boolean>>({});
  const isUser = message.role === 'user';

  const [displayedContent, setDisplayedContent] = useState(!animate || isUser ? message.content : '');

  useEffect(() => {
    if (isUser || !animate) {
      setDisplayedContent(message.content);
      return;
    }

    let index = 0;
    const interval = setInterval(() => {
      index += 5;
      if (index >= message.content.length) {
        setDisplayedContent(message.content);
        clearInterval(interval);
      } else {
        setDisplayedContent(message.content.substring(0, index));
      }
    }, 15);

    return () => clearInterval(interval);
  }, [message.content, isUser]);

  const cleanContent = displayedContent.replace(/\|\n\n\|/g, '|\n|');
  const htmlContent = marked.parse(cleanContent) as string;

  const formatDocName = (name: string) => {
    if (name.includes('::')) {
      const parts = name.split('::');
      return `Case Document: ${parts[parts.length - 1]}`;
    }
    return name;
  };

  return (
    <div className={`flex w-full mb-6 ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div className={`flex max-w-[85%] ${isUser ? 'flex-row-reverse' : 'flex-row'} gap-4`}>
        {/* Avatar */}
        <div className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center mt-1 shadow-sm ${isUser ? 'bg-[#1E293B]' : 'bg-white border border-gray-200'}`}>
          {isUser ? <User size={16} color="white" /> : <Scale size={16} className="text-[#1E293B]" />}
        </div>
        
        {/* Bubble */}
        <div className={`flex flex-col ${isUser ? 'items-end' : 'items-start'} min-w-0`}>
          <div className={`px-5 py-4 rounded-2xl shadow-sm ${
            isUser 
              ? 'bg-[#1E293B] text-white rounded-tr-none' 
              : 'bg-white border border-gray-100 rounded-tl-none text-gray-800'
          }`}>
            {message.structuredContent ? (
              <div className="flex flex-col gap-8 text-base">
                {message.structuredContent.is_conversational && message.structuredContent.conversational_reply ? (
                   <div className="text-gray-800">{message.structuredContent.conversational_reply}</div>
                ) : (
                  <>
                    {/* General Analysis */}
                    {message.structuredContent.general_analysis && (
                      <div>
                        <div className="flex items-center gap-2 text-lg font-bold text-gray-800 mb-3 border-b-2 border-gray-100 pb-2">
                          <FileText size={20} className="text-blue-600" /> Legal Analysis
                        </div>
                        <div className="text-gray-700 leading-relaxed bg-blue-50 px-4 py-3 rounded-xl border border-blue-100 whitespace-pre-wrap">
                          {message.structuredContent.general_analysis}
                        </div>
                      </div>
                    )}

                    {/* Situation Meaning */}
                    {message.structuredContent.situation_meaning && (
                      <div>
                        <div className="flex items-center gap-2 text-lg font-bold text-gray-800 mb-3 border-b-2 border-gray-100 pb-2">
                          <FileText size={20} className="text-blue-600" /> 1. What the situation means
                        </div>
                        <div className="text-gray-700 leading-relaxed bg-blue-50 px-4 py-3 rounded-xl border border-blue-100">
                          {message.structuredContent.situation_meaning}
                        </div>
                      </div>
                    )}

                    {/* Bail Status */}
                    {message.structuredContent.bail_status && (
                      <div>
                        <div className="flex items-center gap-2 text-lg font-bold text-gray-800 mb-3 border-b-2 border-gray-100 pb-2">
                          <ShieldCheck size={20} className="text-emerald-600" /> 2. Bail Status
                        </div>
                        <div className="text-gray-700 bg-emerald-50 px-4 py-3 rounded-xl border border-emerald-100">
                          {message.structuredContent.bail_status}
                        </div>
                      </div>
                    )}

                    {/* Next 24 Hours */}
                    {message.structuredContent.next_24_hours && message.structuredContent.next_24_hours.length > 0 && (
                      <div>
                        <div className="flex items-center gap-2 text-lg font-bold text-gray-800 mb-3 border-b-2 border-gray-100 pb-2">
                          <ListTodo size={20} className="text-amber-600" /> 3. What to do in the next 24 hours
                        </div>
                        <ul className="list-none space-y-2">
                          {message.structuredContent.next_24_hours.map((action, idx) => (
                            <li key={idx} className="flex gap-3 text-gray-700 items-start">
                              <div className="mt-1 min-w-[6px] w-1.5 h-1.5 rounded-full bg-amber-500" />
                              <span>{action}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {/* Rights */}
                    {message.structuredContent.rights && message.structuredContent.rights.length > 0 && (
                      <div>
                        <div className="flex items-center gap-2 text-lg font-bold text-gray-800 mb-3 border-b-2 border-gray-100 pb-2">
                          <AlertTriangle size={20} className="text-indigo-600" /> 4. Your Rights
                        </div>
                        <ul className="list-none space-y-2">
                          {message.structuredContent.rights.map((right, idx) => (
                            <li key={idx} className="flex gap-3 text-gray-700 items-start">
                              <div className="mt-1 min-w-[6px] w-1.5 h-1.5 rounded-full bg-indigo-500" />
                              <span>{right}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {/* Handling Authority */}
                    {message.structuredContent.handling_authority && (
                      <div>
                        <div className="flex items-center gap-2 text-lg font-bold text-gray-800 mb-3 border-b-2 border-gray-100 pb-2">
                          <AlertTriangle size={20} className="text-indigo-600" /> 5. Which Authority handles this?
                        </div>
                        <div className="text-gray-700 bg-indigo-50 px-4 py-3 rounded-xl border border-indigo-100">
                          {message.structuredContent.handling_authority}
                        </div>
                      </div>
                    )}

                    {/* Applicable Laws */}
                    {message.structuredContent.applicable_laws && message.structuredContent.applicable_laws.length > 0 && (
                      <div>
                        <div className="flex items-center gap-2 text-lg font-bold text-gray-800 mb-4 border-b-2 border-gray-100 pb-2">
                          <Scale size={20} className="text-slate-700" /> Applicable Laws
                        </div>
                        <div className="flex flex-col gap-3">
                          {message.structuredContent.applicable_laws.map((law, idx) => (
                            <div key={idx} className="bg-slate-50 border border-slate-200 rounded-xl p-4 shadow-sm">
                              <div className="text-base font-bold text-slate-800 mb-2">{law.code} - {law.section}</div>
                              {law.quote && <ExpandableQuote quote={law.quote} />}
                              <div className="text-sm text-slate-700">{law.explanation}</div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}



                    {/* Lawyer Locator Footer */}
                    {message.structuredContent.suggest_lawyer && (
                      <div className="mt-6 pt-6 border-t border-gray-100 text-gray-800 italic">
                        <p className="mb-4"><strong>For serious matters, please consult a qualified criminal lawyer.</strong></p>
                        <p className="mb-4">We are building our verified lawyer network. For now, you can find a criminal lawyer by searching '[your district] criminal lawyer Bar Council' on Google, or call your nearest district court reception for a reference.</p>
                        <p>If you need a lawyer, just let me know and I will help you find one.</p>
                      </div>
                    )}
                  </>
                )}
              </div>
            ) : (
              <div 
                className={`prose prose-sm max-w-none ${isUser ? 'text-white' : 'text-gray-800'}`}
                dangerouslySetInnerHTML={{ __html: htmlContent }} 
              />
            )}
          </div>
          
          {/* Render Sources for AI Messages */}
          {!isUser && message.sources && message.sources.length > 0 && message.structuredContent?.requires_sources !== false && (
            <div className="mt-2 w-full">
              <button 
                className="flex items-center gap-1 text-xs font-medium text-gray-500 hover:text-gray-800 transition-colors bg-white border border-gray-200 px-3 py-1.5 rounded-full shadow-sm"
                onClick={() => setSourcesOpen(!sourcesOpen)}
              >
                {sourcesOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                {message.sources.length} Sources
              </button>
              
              {sourcesOpen && (
                <div className="mt-3 bg-[#E2E8F0] border border-[#CBD5E1] rounded-2xl shadow-sm w-full max-w-4xl overflow-hidden flex flex-col animate-slide-down-fade">
                  {message.sources.map((source, idx) => (
                    <div key={idx} className={`p-4 ${idx !== 0 ? 'border-t border-[#CBD5E1]' : ''}`}>
                      <div className="mb-2">
                        <span className="font-bold text-[#0F172A] flex items-center gap-1.5 text-sm break-words">
                          📄 {formatDocName(source.document_name)}
                        </span>
                      </div>
                      {source.section && source.section !== 'General' && (
                        <div className="text-xs text-slate-500 mb-2 font-medium">
                          Section: {source.section} {source.page_number ? `(Pg. ${source.page_number})` : ''}
                        </div>
                      )}
                      <div 
                        className={`text-slate-700 text-xs leading-relaxed pr-2 cursor-pointer transition-all ${
                          expandedSources[idx] ? 'max-h-[500px] overflow-y-auto custom-scrollbar' : 'line-clamp-3'
                        }`}
                        onClick={() => setExpandedSources(prev => ({ ...prev, [idx]: !prev[idx] }))}
                        title={expandedSources[idx] ? "Click to collapse" : "Click to expand"}
                      >
                        {source.content}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
          
          {/* Render Model Metadata */}
          {!isUser && message.model_used && (
            <div className="flex gap-4 mt-3 ml-1 text-xs text-gray-400 font-medium">
              <span className="flex items-center gap-1.5">
                <Cpu size={12} /> {message.model_used.includes('gemini') ? 'Quick Response' : 'Deep thinking'}
              </span>
              {message.processing_time_seconds && (
                <span className="flex items-center gap-1.5">
                  <Clock size={12} /> {message.processing_time_seconds.toFixed(2)}s
                </span>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
