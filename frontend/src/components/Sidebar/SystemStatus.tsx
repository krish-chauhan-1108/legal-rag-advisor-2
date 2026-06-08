import React from 'react';
import { Database } from 'lucide-react';

interface SystemStatusProps {
  isOnline: boolean;
  docCount: number;
}

export const SystemStatus: React.FC<SystemStatusProps> = ({ isOnline, docCount }) => {
  return (
    <div className="status-bar">
      <div className="status-bar__item">
        <div className={`status-dot ${isOnline ? 'online' : 'offline'}`}></div>
        <span>{isOnline ? 'API Online' : 'API Offline'}</span>
      </div>
      <div className="status-bar__item" title="Documents Indexed">
        <Database size={14} />
        <span>{docCount} chunks</span>
      </div>
    </div>
  );
};
