import React, { useState, useEffect } from 'react';
import { User, Scale, ChevronDown, ChevronUp, Clock, Cpu } from 'lucide-react';
import { marked } from 'marked';
import type { ChatMessage } from '../../types';

interface MessageBubbleProps {
  message: ChatMessage;
}

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
                      <div className="text-slate-700 text-xs leading-relaxed max-h-32 overflow-y-auto custom-scrollbar pr-2">
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
                <Cpu size={12} /> {message.model_used}
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
