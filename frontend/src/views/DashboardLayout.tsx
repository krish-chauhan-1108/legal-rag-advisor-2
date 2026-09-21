import React, { useEffect, useState } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { Menu, Plus, Scale, Trash2, UserCircle, X } from 'lucide-react';
import { SystemStatus } from '../components/Sidebar/SystemStatus';
import type { ChatSession } from '../types';
import { authFetch, useAuth } from '../auth/auth';
import { API_URL } from '../config';
type ApiStatus = 'checking' | 'online' | 'offline';

export const DashboardLayout: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { credential, user } = useAuth();
  const [isMobileNavOpen, setIsMobileNavOpen] = useState(false);
  const [health, setHealth] = useState<{ status: ApiStatus; sourceRegistryReady: boolean }>({ status: 'checking', sourceRegistryReady: false });
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
            sourceRegistryReady: data.source_registry_ready !== false,
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
        const response = await authFetch(`${API_URL}/api/chats`, credential, {
          cache: 'no-store',
        });
        if (!response.ok) throw new Error(`Chat history failed: ${response.status}`);

        const data = await response.json() as ChatSession[];
        if (active) setChats(Array.isArray(data) ? data : []);
      } catch {
        // Keep the last good sidebar state during transient backend wake-ups.
        // A failed refresh should not make saved chats disappear.
      }
    };

    loadChats();
    const handleChatCreated = (event: Event) => {
      const chat = (event as CustomEvent<ChatSession>).detail;
      if (!chat?.id) return;
      setChats(current => [chat, ...current.filter(candidate => candidate.id !== chat.id)]);
    };

    const handleHistoryUpdated = () => {
      void loadChats();
    };

    window.addEventListener('chat-created', handleChatCreated);
    window.addEventListener('chat-history-updated', handleHistoryUpdated);
    return () => {
      active = false;
      window.removeEventListener('chat-created', handleChatCreated);
      window.removeEventListener('chat-history-updated', handleHistoryUpdated);
    };
  }, [credential]);

  const handleNewChat = () => {
    setIsMobileNavOpen(false);
    if (location.pathname === '/') {
      window.location.reload();
    } else {
      navigate('/');
    }
  };

  const handleDeleteChat = async (event: React.MouseEvent, chat: ChatSession) => {
    event.stopPropagation();
    if (!credential || !window.confirm(`Delete “${chat.title || 'New Chat'}”?`)) return;

    try {
      const response = await authFetch(`${API_URL}/api/chats/${chat.id}`, credential, {
        method: 'DELETE',
      });
      if (!response.ok) throw new Error(`Chat deletion failed: ${response.status}`);

      setChats(current => current.filter(candidate => candidate.id !== chat.id));
      if (location.pathname === `/chat/${chat.id}`) navigate('/');
    } catch {
      window.alert('Could not delete this chat. Please try again.');
    }
  };

  return (
    <div className="dashboard-shell flex h-screen bg-[#F9F9F8]">
      <div
        className={`dashboard-sidebar-backdrop ${isMobileNavOpen ? 'is-visible' : ''}`}
        onClick={() => setIsMobileNavOpen(false)}
        aria-hidden="true"
      />
      {/* Left Sidebar */}
      <aside
        id="trana-chat-sidebar"
        className={`dashboard-sidebar w-72 bg-[#121212] text-white flex flex-col transition-all duration-300 flex-shrink-0 ${isMobileNavOpen ? 'is-open' : ''}`}
      >
        <div className="p-6 pb-2">
          <div className="dashboard-sidebar__top flex items-center gap-3 mb-8 cursor-pointer" onClick={() => { setIsMobileNavOpen(false); navigate('/home'); }}>
            <Scale className="w-7 h-7 text-white" strokeWidth={1.5} />
            <h1 className="text-xl font-serif tracking-tight text-white">TRANA</h1>
            <button
              type="button"
              className="dashboard-sidebar__close"
              onClick={(event) => { event.stopPropagation(); setIsMobileNavOpen(false); }}
              aria-label="Close navigation"
            >
              <X className="h-5 w-5" />
            </button>
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
            <div
              key={chat.id}
              className="group relative flex items-center w-full rounded-md hover:bg-[#1E293B] transition-colors"
            >
              <button
                onClick={() => { setIsMobileNavOpen(false); navigate(`/chat/${chat.id}`); }}
                className="w-full text-left px-3 py-2.5 pr-10 text-sm text-gray-300 group-hover:text-white rounded-md transition-colors truncate"
                title={chat.title}
              >
                {chat.title || 'New Chat'}
              </button>
              <button
                type="button"
                onClick={(event) => handleDeleteChat(event, chat)}
                className="absolute right-2 rounded p-1 text-gray-500 opacity-0 group-hover:opacity-100 focus:opacity-100 hover:text-red-300 transition-opacity"
                title="Delete chat"
                aria-label={`Delete ${chat.title || 'New Chat'}`}
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          ))}
          {chats.length === 0 && (
            <p className="px-3 py-2 text-xs text-gray-500">No saved chats yet.</p>
          )}
        </div>

        <div className="p-4 border-t border-gray-800 space-y-2">
          <button
            onClick={() => { setIsMobileNavOpen(false); navigate('/account'); }}
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
        <SystemStatus status={health.status} sourceRegistryReady={health.sourceRegistryReady} onRetry={() => window.location.reload()} />
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="dashboard-main flex-1 flex flex-col overflow-hidden relative">
        <div className="dashboard-mobile-bar">
          <button
            type="button"
            className="dashboard-mobile-bar__menu"
            onClick={() => setIsMobileNavOpen(true)}
            aria-label="Open chats and navigation"
            aria-controls="trana-chat-sidebar"
            aria-expanded={isMobileNavOpen}
          >
            <Menu className="h-5 w-5" />
            <span>Chats</span>
          </button>
          <span className="dashboard-mobile-bar__spacer" />
          <button type="button" className="dashboard-mobile-bar__brand" onClick={() => navigate('/home')}>
            <Scale className="h-5 w-5" strokeWidth={1.5} />
            <span>TRANA</span>
          </button>
        </div>
        <div className="dashboard-outlet">
          <Outlet />
        </div>
      </main>
    </div>
  );
};
