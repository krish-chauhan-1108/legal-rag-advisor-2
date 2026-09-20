import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import type { ReactNode } from 'react';
import type { ChatSession, ChatMessage } from '../types';
import { useAuth } from './AuthContext';

interface BackendChatMessage {
  role: 'user' | 'assistant';
  content: string;
  structured_content?: ChatMessage['structuredContent'];
  sources?: ChatMessage['sources'];
}

interface BackendChatSession {
  id: string;
  title: string;
  user_email: string;
  messages?: BackendChatMessage[];
  created_at: string;
  updated_at: string;
}

interface ChatContextType {
  chats: Record<string, ChatSession>;
  createChat: () => Promise<string>;
  deleteChat: (chatId: string) => Promise<void>;
  sendMessage: (chatId: string, content: string, ephemeralFile: File | null, modelPref: string) => Promise<void>;
}

const ChatContext = createContext<ChatContextType | undefined>(undefined);

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export const ChatProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const { user } = useAuth();
  const [chats, setChats] = useState<Record<string, ChatSession>>({});

  const getHeaders = useCallback(() => {
    return {
      'Content-Type': 'application/json',
      'X-User-Email': user?.email || 'anonymous',
    };
  }, [user]);

  const loadChats = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/chats`, {
        headers: getHeaders()
      });
      if (res.ok) {
        const data: BackendChatSession[] = await res.json();
        const chatsObj: Record<string, ChatSession> = {};
        for (const chat of data) {
          chatsObj[chat.id] = {
            id: chat.id,
            title: chat.title,
          messages: (chat.messages || []).map((msg) => ({
              role: msg.role,
              content: msg.content,
              structuredContent: msg.structured_content,
              sources: msg.sources
            })),
            isGenerating: false,
            createdAt: new Date(chat.created_at).getTime(),
            updatedAt: new Date(chat.updated_at).getTime()
          };
        }
        setChats(chatsObj);
      }
    } catch (e) {
      console.error("Failed to load chats from backend", e);
    }
  }, [getHeaders]);

  useEffect(() => {
    loadChats();
  }, [loadChats]);

  const createChat = async (): Promise<string> => {
    try {
      const res = await fetch(`${API_URL}/api/chats`, {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify({ title: 'New Chat' })
      });
      if (res.ok) {
          const chat: BackendChatSession = await res.json();
        const newChat: ChatSession = {
          id: chat.id,
          title: chat.title,
          messages: chat.messages || [],
          isGenerating: false,
          createdAt: new Date(chat.created_at).getTime(),
          updatedAt: new Date(chat.updated_at).getTime(),
        };
        setChats(prev => ({ ...prev, [newChat.id]: newChat }));
        return newChat.id;
      }
    } catch (e) {
      console.error("Failed to create chat on backend", e);
    }
    // Fallback if backend fails
    return crypto.randomUUID();
  };

  const deleteChat = async (chatId: string) => {
    try {
      const res = await fetch(`${API_URL}/api/chats/${chatId}`, {
        method: 'DELETE',
        headers: getHeaders()
      });
      if (res.ok) {
        setChats(prev => {
          const newChats = { ...prev };
          delete newChats[chatId];
          return newChats;
        });
      }
    } catch (e) {
      console.error("Failed to delete chat", e);
    }
  };

  const sendMessage = async (chatId: string, content: string, ephemeralFile: File | null, modelPref: string) => {
    // Optimistic UI update
    setChats(prev => {
      const chat = prev[chatId] || {
        id: chatId,
        title: content.slice(0, 30) || 'New Chat',
        messages: [],
        createdAt: Date.now(),
        updatedAt: Date.now(),
      };

      if (chat.title === 'New Chat' && content) {
        chat.title = content.length > 30 ? content.slice(0, 30) + '...' : content;
      }

      const newMessage: ChatMessage = { role: 'user', content };
      const updatedMessages = [...chat.messages, newMessage];
      
      return {
        ...prev,
        [chatId]: {
          ...chat,
          messages: updatedMessages,
          isGenerating: true,
          updatedAt: Date.now()
        }
      };
    });

    let ephemeralContext = null;

    if (ephemeralFile) {
      const formData = new FormData();
      formData.append('file', ephemeralFile);
      try {
        const res = await fetch(`${API_URL}/api/extract`, {
          method: 'POST',
          body: formData
        });
        if (res.ok) {
          const data = await res.json();
          ephemeralContext = data.text;
        }
      } catch (e) {
        console.error("Failed to extract ephemeral doc", e);
      }
    }

    try {
      const res = await fetch(`${API_URL}/api/analyze`, {
        method: 'POST',
        headers: getHeaders(),
        body: JSON.stringify({
          query: content || "Analyze the attached document.",
          chat_id: chatId,
          ephemeral_context: ephemeralContext,
          model_preference: modelPref
        })
      });

      if (res.ok) {
        const data = await res.json();
        const analysisData = data.analysis;
        const assistantMessage: ChatMessage = {
          role: 'assistant',
          content: typeof analysisData === 'string' ? analysisData : '',
          structuredContent: typeof analysisData === 'object' ? analysisData : undefined,
          sources: data.sources
        };
        
        setChats(prev => {
          const targetChat = prev[chatId];
          if (!targetChat) return prev;
          return {
            ...prev,
            [chatId]: {
              ...targetChat,
              messages: [...targetChat.messages, assistantMessage],
              isGenerating: false,
              updatedAt: Date.now()
            }
          };
        });
      } else {
        const err = await res.json().catch(() => ({}));
        console.error(err);
        
        let errorMsg = "An error occurred while generating the response.";
        if (err && err.detail) {
          const detailStr = typeof err.detail === 'string' ? err.detail.toLowerCase() : JSON.stringify(err.detail).toLowerCase();
          if (detailStr.includes("quota") || detailStr.includes("429") || detailStr.includes("exhausted") || detailStr.includes("api key")) {
            errorMsg = "The AI model is currently out of requests or quota. Please check your API keys or try again later.";
          } else {
            const displayDetail = typeof err.detail === 'string'
              ? err.detail
              : Array.isArray(err.detail)
                ? err.detail.map((d: any) => d.msg || JSON.stringify(d)).join(', ')
                : JSON.stringify(err.detail);
            errorMsg = `Server Error: ${displayDetail}`;
          }
        }
        
        setChats(prev => {
          const targetChat = prev[chatId];
          if (!targetChat) return prev;
          return {
            ...prev,
            [chatId]: {
              ...targetChat,
              messages: [...targetChat.messages, { role: 'assistant', content: errorMsg }],
              isGenerating: false,
              updatedAt: Date.now()
            }
          };
        });
      }
    } catch (e) {
      console.error(e);
      setChats(prev => {
        const targetChat = prev[chatId];
        if (!targetChat) return prev;
        return {
          ...prev,
          [chatId]: {
            ...targetChat,
            messages: [...targetChat.messages, { role: 'assistant', content: "Cannot connect to the server. Please ensure the backend API is running and the URL is correct." }],
            isGenerating: false,
            updatedAt: Date.now()
          }
        };
      });
    }
  };

  return (
    <ChatContext.Provider value={{ chats, createChat, deleteChat, sendMessage }}>
      {children}
    </ChatContext.Provider>
  );
};

export const useChats = () => {
  const context = useContext(ChatContext);
  if (context === undefined) {
    throw new Error('useChats must be used within a ChatProvider');
  }
  return context;
};
