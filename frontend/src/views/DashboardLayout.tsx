import React, { useEffect, useState } from 'react';
import { Outlet, useNavigate } from 'react-router-dom';
import { Scale, Database, Plus } from 'lucide-react';
import { SystemStatus } from '../components/Sidebar/SystemStatus';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export const DashboardLayout: React.FC = () => {
  const navigate = useNavigate();
  const [health, setHealth] = useState({ isOnline: false, docCount: 0, modelUsed: 'Loading...' });

  useEffect(() => {
    const checkHealth = () => {
      fetch(`${API_URL}/health`)
        .then(r => r.ok ? r.json() : null)
        .then(data => {
          if (data) setHealth({ isOnline: data.status === 'healthy', docCount: data.documents_indexed, modelUsed: 'gemma-4-31b-it' });
          else setHealth(h => ({ ...h, isOnline: false }));
        })
        .catch(() => setHealth(h => ({ ...h, isOnline: false })));
    };
    
    checkHealth();
    const interval = setInterval(checkHealth, 30000);
    return () => clearInterval(interval);
  }, []);

  const handleNewChat = () => {
    // For a stateless RAG, "New Chat" simply resets the current view by navigating to root
    // which triggers the ChatView to clear its state if it depended on route params,
    // or you could just refresh/reload.
    navigate('/');
    // To force reload the chat view if already on '/'
    window.location.reload();
  };

  return (
    <div className="flex h-screen bg-[#F9F9F8]">
      {/* Left Sidebar */}
      <aside className="w-72 bg-[#121212] text-white flex flex-col transition-all duration-300 flex-shrink-0">
        <div className="p-6 pb-2">
          <div className="flex items-center gap-3 mb-8 cursor-pointer" onClick={() => navigate('/')}>
            <Scale className="w-7 h-7 text-white" strokeWidth={1.5} />
            <h1 className="text-xl font-serif tracking-tight">LawLLM</h1>
          </div>
          
          <button 
            onClick={handleNewChat}
            className="w-full flex items-center gap-2 bg-[#1E293B] hover:bg-[#334155] text-white px-4 py-3 rounded-lg transition-colors text-sm font-medium border border-gray-700"
          >
            <Plus className="w-4 h-4" />
            New Chat
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-1 custom-scrollbar">
          {/* Stateless RAG: No chat history */}
        </div>

        <div className="p-4 border-t border-gray-800 space-y-2">
          <button
            onClick={() => navigate('/knowledge-base')}
            className="w-full flex items-center gap-3 px-3 py-2.5 text-sm text-gray-300 hover:text-white hover:bg-[#1E293B] rounded-md transition-colors text-left"
          >
            <Database className="w-4 h-4" />
            Knowledge Base
          </button>
          
          <div className="mt-4 px-2">
            <SystemStatus isOnline={health.isOnline} docCount={health.docCount} />
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="flex-1 flex flex-col overflow-hidden relative">
        <Outlet />
      </main>
    </div>
  );
};
