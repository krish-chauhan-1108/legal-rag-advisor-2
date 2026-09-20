import React from 'react';
import { Database } from 'lucide-react';

interface SystemStatusProps {
  status: 'checking' | 'online' | 'offline';
  docCount: number;
  onRetry: () => void;
}

export const SystemStatus: React.FC<SystemStatusProps> = ({ status, docCount, onRetry }) => {
  const label = status === 'checking' ? 'Checking API…' : status === 'online' ? 'API Online' : 'API Offline';

  return (
    <div className="status-bar">
      <div className="status-bar__item">
        <div className={`status-dot ${status}`}></div>
        <span>{label}</span>
      </div>
      <div className="status-bar__item" title="Documents Indexed">
        <Database size={14} />
        <span>{docCount} chunks</span>
      </div>
      {status === 'offline' && (
        <button type="button" onClick={onRetry} className="text-xs text-gray-400 hover:text-white">
          Retry
        </button>
      )}
    </div>
  );
};
