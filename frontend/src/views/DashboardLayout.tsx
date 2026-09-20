import React, { useEffect, useState } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { Scale, Plus, UserCircle } from 'lucide-react';
import { SystemStatus } from '../components/Sidebar/SystemStatus';
import type { ChatSession } from '../types';
import { authHeaders, useAuth } from '../auth/auth';

const CONFIGURED_API_URL = import.meta.env.VITE_BACKEND_URL || import.meta.env.VITE_API_URL || 'http://localhost:8000';
// Production uses Vercel's same-origin proxy so browser extensions cannot block the Render hostname.
const API_URL = import.meta.env.PROD ? '' : CONFIGURED_API_URL;
type ApiStatus = 'checking' | 'online' | 'offline';

export const DashboardLayout: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { credential, user } = useAuth();
  const [health, setHealth] = useState<{ status: ApiStatus; docCount: number }>({ status: 'checking', docCount: 0 });
  const [chats, setChats] = useState<ChatSession[]>([]);

  useEffect(() => {
    let active = true;
    let requestInFlight = false;

    const checkHealth = async () => {
      if (requestInFlight) return;
      requestInFlight = true;

      if (active) setHealth(current => ({ ...current, status: 'checking' }));

      try {
        const response = await fetch(`${API_URL}/health?ts=${Date.now()}`, { cache: 'no-store' });
        if (!response.ok) throw new Error(`Health check failed: ${response.status}`);

        const data = await response.json();
        if (active) {
          setHealth({
            status: data.status === 'healthy' ? 'online' : 'offline',
            docCount: Number(data.documents_indexed) || 0,
          });
        }
      } catch {
        if (active) setHealth(current => ({ ...current, status: 'offline' }));
      } finally {
        requestInFlight = false;
      }
    };

    checkHealth();
    const interval = setInterval(checkHealth, 30000);
    return () => {
      active = false;
      clearInterval(interval);
    };
  }, []);

  useEffect(() => {
    let active = true;

    const loadChats = async () => {
      if (!credential) {
        if (active) setChats([]);
        return;
      }
      try {
        const response = await fetch(`${API_URL}/api/chats`, {
          headers: authHeaders(credential),
          cache: 'no-store',
        });
        if (!response.ok) throw new Error(`Chat history failed: ${response.status}`);

        const data = await response.json() as ChatSession[];
        if (active) setChats(Array.isArray(data) ? data : []);
      } catch {
        if (active) setChats([]);
      }
    };

    loadChats();
    window.addEventListener('chat-history-updated', loadChats);
    return () => {
      active = false;
      window.removeEventListener('chat-history-updated', loadChats);
    };
  }, [credential, location.pathname]);

  const handleNewChat = () => {
    if (location.pathname === '/') {
      window.location.reload();
    } else {
      navigate('/');
    }
  };

  return (
    <div className="flex h-screen bg-[#F9F9F8]">
      {/* Left Sidebar */}
      <aside className="w-72 bg-[#121212] text-white flex flex-col transition-all duration-300 flex-shrink-0">
        <div className="p-6 pb-2">
          <div className="flex items-center gap-3 mb-8 cursor-pointer" onClick={() => navigate('/')}>
            <Scale className="w-7 h-7 text-white" strokeWidth={1.5} />
            <h1 className="text-xl font-serif tracking-tight">TRANA</h1>
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
          {chats.map((chat) => (
            <button
              key={chat.id}
              onClick={() => navigate(`/chat/${chat.id}`)}
              className="w-full text-left px-3 py-2.5 text-sm text-gray-300 hover:text-white hover:bg-[#1E293B] rounded-md transition-colors truncate"
              title={chat.title}
            >
              {chat.title || 'New Chat'}
            </button>
          ))}
          {chats.length === 0 && (
            <p className="px-3 py-2 text-xs text-gray-500">No saved chats yet.</p>
          )}
        </div>

        <div className="p-4 border-t border-gray-800 space-y-2">
          <button
            onClick={() => navigate('/account')}
            className="w-full flex items-center gap-3 px-3 py-2.5 text-sm text-gray-300 hover:text-white hover:bg-[#1E293B] rounded-md transition-colors text-left"
          >
            {user?.picture ? (
              <img src={user.picture} alt="" className="w-4 h-4 rounded-full" />
            ) : (
              <UserCircle className="w-4 h-4" />
            )}
            {user?.name || 'Account'}
          </button>
          
          <div className="mt-4 px-2">
            <SystemStatus status={health.status} docCount={health.docCount} onRetry={() => window.location.reload()} />
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
