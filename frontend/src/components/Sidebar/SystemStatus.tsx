import React from 'react';
import { ShieldCheck } from 'lucide-react';

interface SystemStatusProps {
  status: 'checking' | 'online' | 'offline';
  sourceRegistryReady: boolean;
  onRetry: () => void;
}

export const SystemStatus: React.FC<SystemStatusProps> = ({ status, sourceRegistryReady, onRetry }) => {
  const label = status === 'checking' ? 'Checking API…' : status === 'online' ? 'API Online' : 'API Offline';

  return (
    <div className="status-bar">
      <div className="status-bar__item">
        <div className={`status-dot ${status}`}></div>
        <span>{label}</span>
      </div>
      <div className="status-bar__item" title="Verified legal-source registry">
        <ShieldCheck size={14} />
        <span>{sourceRegistryReady ? 'Legal sources ready' : 'Sources unavailable'}</span>
      </div>
      {status === 'offline' && (
        <button type="button" onClick={onRetry} className="text-xs text-gray-400 hover:text-white">
          Retry
        </button>
      )}
    </div>
  );
};
