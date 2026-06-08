import React from 'react';
import { Scale } from 'lucide-react';

interface NavbarProps {
  onOpenChat: () => void;
  isOnline: boolean;
}

export const Navbar: React.FC<NavbarProps> = ({ onOpenChat, isOnline }) => {
  return (
    <header className="navbar">
      <div className="navbar__brand">
        <Scale size={24} color="var(--action-primary)" />
        Antigravity Legal
      </div>
      <div className="navbar__actions">
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.85rem', color: 'var(--text-secondary)', marginRight: '1rem' }}>
          <div className={`status-dot ${isOnline ? 'online' : 'offline'}`} />
          {isOnline ? 'System Online' : 'System Offline'}
        </div>
        <button className="btn-primary" onClick={onOpenChat}>
          Legal AI Assistant
        </button>
      </div>
    </header>
  );
};
