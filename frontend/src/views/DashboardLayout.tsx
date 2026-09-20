import React, { useEffect, useState } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { Scale, Database, Plus, LogOut, MessageSquare, Trash2 } from 'lucide-react';
import { SystemStatus } from '../components/Sidebar/SystemStatus';
import { useAuth } from '../context/AuthContext';
import { useChats } from '../context/ChatContext';

export const DashboardLayout: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuth();
  const { chats, createChat, deleteChat } = useChats();
  const [health, setHealth] = useState({ isOnline: false, docCount: 0, modelUsed: 'Loading...' });

  useEffect(() => {
    const checkHealth = () => {
      const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
      fetch(`${apiUrl}/health`)
        .then(r => r.ok ? r.json() : null)
        .then(data => {
          if (data) setHealth({ isOnline: data.status === 'healthy', docCount: data.documents_indexed, modelUsed: 'Deep thinking' });
          else setHealth(h => ({ ...h, isOnline: false }));
        })
        .catch(() => setHealth(h => ({ ...h, isOnline: false })));
    };
    
    checkHealth();
    const interval = setInterval(checkHealth, 30000);
    return () => clearInterval(interval);
  }, []);

  const handleNewChat = async () => {
    const newId = await createChat();
    navigate(`/chat/${newId}`);
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
            className="w-full flex items-center gap-2 bg-[#1E293B] hover:bg-[#334155] text-white px-4 py-3 rounded-xl transition-colors text-sm font-medium border border-gray-700"
          >
            <Plus className="w-4 h-4" />
            New Chat
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-1 custom-scrollbar">
          {Object.values(chats).sort((a, b) => b.updatedAt - a.updatedAt).map(chat => (
            <div key={chat.id} className="group relative">
              <button
                onClick={() => navigate(`/chat/${chat.id}`)}
                className={`w-full flex items-center gap-3 px-3 py-2.5 text-sm rounded-xl transition-colors text-left ${
                  location.pathname === `/chat/${chat.id}` ? 'bg-[#1E293B] text-white' : 'text-gray-400 hover:text-white hover:bg-[#1E293B]/50'
                }`}
              >
                <MessageSquare className="w-4 h-4 flex-shrink-0" />
                <span className="truncate flex-1">{chat.title}</span>
              </button>
              <button 
                onClick={(e) => { e.stopPropagation(); deleteChat(chat.id); if(location.pathname === `/chat/${chat.id}`) navigate('/'); }}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-gray-500 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity"
                title="Delete Chat"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          ))}
        </div>

        <div className="p-4 border-t border-gray-800 space-y-2">
          <button
            onClick={() => navigate('/knowledge-base')}
            className="w-full flex items-center gap-3 px-3 py-2.5 text-sm text-gray-300 hover:text-white hover:bg-[#1E293B] rounded-xl transition-colors text-left"
          >
            <Database className="w-4 h-4" />
            Knowledge Base
          </button>
          
          <div className="mt-4 px-2">
            <SystemStatus isOnline={health.isOnline} docCount={health.docCount} />
          </div>

          {user && (
            <div className="mt-4 pt-4 border-t border-gray-800 flex items-center justify-between">
              <div className="flex items-center gap-3 overflow-hidden">
                {user.picture ? (
                  <img src={user.picture} alt="Profile" className="w-8 h-8 rounded-full border border-gray-700 flex-shrink-0 bg-gray-800" />
                ) : (
                  <div className="w-8 h-8 rounded-full bg-gray-800 border border-gray-700 flex-shrink-0" />
                )}
                <div className="flex flex-col overflow-hidden">
                  <span className="text-sm font-medium text-white truncate">{user.name}</span>
                  <span className="text-xs text-gray-400 truncate">{user.email}</span>
                </div>
              </div>
              <button 
                onClick={() => { logout(); navigate('/login'); }} 
                className="text-gray-400 hover:text-white p-2 hover:bg-gray-800 rounded-full transition-colors flex-shrink-0" 
                title="Logout"
              >
                <LogOut size={16} />
              </button>
            </div>
          )}
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="flex-1 flex flex-col overflow-hidden relative">
        <Outlet />
      </main>
    </div>
  );
};
