import React, { useRef, useEffect } from 'react';
import { X, Upload, Send } from 'lucide-react';
import type { ChatMessage } from '../../types';
import { marked } from 'marked';

interface ChatDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  messages: ChatMessage[];
  onSendMessage: (query: string) => void;
  isLoading: boolean;
  modelPreference: string;
  setModelPreference: (pref: string) => void;
  onUpload: (file: File) => Promise<void>;
  isUploading: boolean;
  uploadProgress: number;
}

export const ChatDrawer: React.FC<ChatDrawerProps> = ({
  isOpen, onClose, messages, onSendMessage, isLoading, modelPreference, setModelPreference, onUpload, isUploading, uploadProgress
}) => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isLoading]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      onUpload(e.target.files[0]);
    }
  };

  const handleSend = () => {
    if (inputRef.current && inputRef.current.value.trim() && !isLoading) {
      onSendMessage(inputRef.current.value.trim());
      inputRef.current.value = '';
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <>
      {/* Overlay */}
      <div className={`chat-overlay ${isOpen ? 'open' : ''}`} onClick={onClose} />
      
      {/* Drawer */}
      <div className={`chat-drawer ${isOpen ? 'open' : ''}`}>
        
        <div className="chat-header">
          <h2>Legal Assistant Workspace</h2>
          <button className="close-btn" onClick={onClose}>
            <X size={20} />
          </button>
        </div>

        {/* Upload Zone */}
        <div className="drawer-upload">
          <div className="upload-zone" onClick={() => fileInputRef.current?.click()}>
            <input 
              type="file" 
              accept="application/pdf" 
              ref={fileInputRef} 
              onChange={handleFileChange}
              disabled={isUploading}
            />
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.75rem', color: 'var(--text-secondary)' }}>
              <Upload size={18} />
              <span style={{ fontSize: '0.85rem' }}>Upload Legal Document (PDF)</span>
            </div>
          </div>
          {isUploading && (
            <div className="progress-track">
              <div className="progress-fill" style={{ width: `${uploadProgress}%` }} />
            </div>
          )}
        </div>

        {/* Transcript Area */}
        <div className="transcript-area" ref={scrollRef}>
          {messages.length === 0 ? (
            <div style={{ textAlign: 'center', color: 'var(--text-muted)', marginTop: '2rem', fontSize: '0.9rem' }}>
              Upload a document above and begin your inquiry.
            </div>
          ) : (
            messages.map((msg, idx) => {
              const isUser = msg.role === 'user';
              const cleanContent = msg.content.replace(/\|\n\n\|/g, '|\n|');
              const htmlContent = marked.parse(cleanContent) as string;

              return (
                <div key={idx} className={`transcript-entry ${isUser ? 'transcript-entry--user' : ''}`}>
                  <div className="transcript-entry__author">
                    {isUser ? 'Client Query' : 'Legal Assistant'}
                  </div>
                  <div 
                    className="transcript-entry__content" 
                    dangerouslySetInnerHTML={{ __html: htmlContent }} 
                  />
                  {!isUser && msg.sources && msg.sources.length > 0 && (
                    <div className="source-ref">
                      <strong style={{ fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Citations:</strong>
                      {msg.sources.map((src, i) => (
                        <div key={i} className="source-item">
                          <span className="source-item__doc">[{i + 1}] {src.document_name}</span>
                          <span style={{ color: 'var(--text-muted)' }}>{src.section !== 'General' ? src.section : ''}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            })
          )}
          {isLoading && (
            <div className="transcript-entry">
              <div className="transcript-entry__author">Legal Assistant</div>
              <div className="transcript-entry__content" style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>
                Analyzing documents and drafting response...
              </div>
            </div>
          )}
        </div>

        {/* Input Area */}
        <div className="drawer-input-container">
          <select 
            className="model-select"
            value={modelPreference} 
            onChange={(e) => setModelPreference(e.target.value)}
          >
            <option value="deep">Deep Analysis (Gemma 31B)</option>
            <option value="quick">Quick Response (Flash 2.5)</option>
          </select>
          <div className="transcript-input">
            <textarea 
              ref={inputRef}
              placeholder="Enter your inquiry..."
              onKeyDown={handleKeyDown}
              disabled={isLoading}
            />
            <button 
              className="send-btn-minimal" 
              onClick={handleSend}
              disabled={isLoading}
            >
              <Send size={20} />
            </button>
          </div>
        </div>

      </div>
    </>
  );
};
