import React, { useEffect, useRef } from 'react';
import { MessageBubble } from './MessageBubble';
import type { ChatMessage } from '../../types';

interface MessageListProps {
  messages: ChatMessage[];
  isLoading: boolean;
  onQuickPrompt: (prompt: string) => void;
}

export const MessageList: React.FC<MessageListProps> = ({ messages, isLoading, onQuickPrompt }) => {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTo({
        top: containerRef.current.scrollHeight,
        behavior: 'smooth'
      });
    }
  }, [messages, isLoading]);

  if (messages.length === 0) {
    return (
      <div className="messages-container">
        <div className="empty-state animate-fade-in-down">
          <div className="empty-state__icon" style={{ fontSize: '2.5rem' }}>💬</div>
          <div className="empty-state__title" style={{ fontSize: '1.25rem', fontWeight: 600, color: 'var(--text-primary)' }}>Ask a legal question</div>
          <div className="empty-state__subtitle" style={{ color: 'var(--text-secondary)', maxWidth: '400px' }}>
            Upload a legal document first, then ask questions about clauses,
            obligations, risks, or compliance issues.
          </div>
          <div className="quick-prompts">
            <button className="quick-prompt-btn" onClick={() => onQuickPrompt("What are the key obligations of each party?")}>Key obligations</button>
            <button className="quick-prompt-btn" onClick={() => onQuickPrompt("Summarize the termination and exit clauses.")}>Termination clauses</button>
            <button className="quick-prompt-btn" onClick={() => onQuickPrompt("Identify any potential risks or liabilities.")}>Risks & liabilities</button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="messages-container" ref={containerRef}>
      {messages.map((msg, idx) => (
        <MessageBubble key={idx} message={msg} />
      ))}
      
      {isLoading && (
        <div className="message message--ai animate-fade-in">
          <div className="message__avatar" style={{ background: 'linear-gradient(135deg, var(--accent-cyan), var(--accent-emerald))' }}>
            <span style={{ color: 'white', fontSize: '12px' }}>AI</span>
          </div>
          <div className="message__bubble" style={{ display: 'flex', alignItems: 'center', gap: '4px', padding: '1rem' }}>
            <div style={{ width: '6px', height: '6px', borderRadius: '50%', background: 'var(--accent-violet)', animation: 'typingBounce 1.4s infinite 0s' }} />
            <div style={{ width: '6px', height: '6px', borderRadius: '50%', background: 'var(--accent-violet)', animation: 'typingBounce 1.4s infinite 0.2s' }} />
            <div style={{ width: '6px', height: '6px', borderRadius: '50%', background: 'var(--accent-violet)', animation: 'typingBounce 1.4s infinite 0.4s' }} />
          </div>
        </div>
      )}
    </div>
  );
};
