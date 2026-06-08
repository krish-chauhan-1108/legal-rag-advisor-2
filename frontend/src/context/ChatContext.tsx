import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import type { ChatSession, ChatMessage } from '../types';
import { useAuth } from './AuthContext';

interface ChatContextType {
  chats: Record<string, ChatSession>;
  createChat: () => string;
  deleteChat: (chatId: string) => void;
  sendMessage: (chatId: string, content: string, ephemeralFile: File | null, modelPref: string) => Promise<void>;
}

const ChatContext = createContext<ChatContextType | undefined>(undefined);

export const ChatProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const { user } = useAuth();
  const [chats, setChats] = useState<Record<string, ChatSession>>({});

  const getStorageKey = () => user ? `chats_${user.email}` : 'chats_anonymous';

  useEffect(() => {
    const savedChats = localStorage.getItem(getStorageKey());
    if (savedChats) {
      setChats(JSON.parse(savedChats));
    } else {
      setChats({});
    }
  }, [user]);

  const saveChats = (newChats: Record<string, ChatSession>) => {
    setChats(newChats);
    localStorage.setItem(getStorageKey(), JSON.stringify(newChats));
  };

  const createChat = () => {
    const newId = crypto.randomUUID();
    const newChat: ChatSession = {
      id: newId,
      title: 'New Chat',
      messages: [
        {
          role: 'assistant',
          content: "I'm Trana—your friendly legal assistant. How can I help you today?"
        }
      ],
      isGenerating: false,
      createdAt: Date.now(),
      updatedAt: Date.now(),
    };
    saveChats({ ...chats, [newId]: newChat });
    return newId;
  };

  const deleteChat = (chatId: string) => {
    const newChats = { ...chats };
    delete newChats[chatId];
    saveChats(newChats);
  };

  const sendMessage = async (chatId: string, content: string, ephemeralFile: File | null, modelPref: string) => {
    const currentChats = JSON.parse(localStorage.getItem(getStorageKey()) || '{}');
    const chat = currentChats[chatId] || {
      id: chatId,
      title: content.slice(0, 30) || 'New Chat',
      messages: [],
      createdAt: Date.now(),
    };

    if (chat.title === 'New Chat' && content) {
      chat.title = content.length > 30 ? content.slice(0, 30) + '...' : content;
    }

    const newMessage: ChatMessage = { role: 'user', content };
    chat.messages.push(newMessage);
    chat.isGenerating = true;
    chat.updatedAt = Date.now();

    currentChats[chatId] = chat;
    saveChats(currentChats);

    let ephemeralContext = null;

    if (ephemeralFile) {
      const formData = new FormData();
      formData.append('file', ephemeralFile);
      try {
        const res = await fetch('http://localhost:8000/api/extract', {
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
      const res = await fetch('http://localhost:8000/api/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: newMessage.content || "Analyze the attached document.",
          ephemeral_context: ephemeralContext,
          model_preference: modelPref
        })
      });

      // We need to fetch the latest state from storage because other chats might have updated it
      const latestChats = JSON.parse(localStorage.getItem(getStorageKey()) || '{}');
      const targetChat = latestChats[chatId];
      if (!targetChat) return;

      if (res.ok) {
        const data = await res.json();
        const analysisData = data.analysis;
        const assistantMessage: ChatMessage = {
          role: 'assistant',
          content: typeof analysisData === 'string' ? analysisData : '',
          structuredContent: typeof analysisData === 'object' ? analysisData : undefined,
          sources: data.sources
        };
        targetChat.messages.push(assistantMessage);
      } else {
        const err = await res.json();
        console.error(err);
        targetChat.messages.push({ role: 'assistant', content: "An error occurred while generating the response." });
      }

      targetChat.isGenerating = false;
      targetChat.updatedAt = Date.now();
      latestChats[chatId] = targetChat;
      saveChats(latestChats);

    } catch (e) {
      console.error(e);
      const latestChats = JSON.parse(localStorage.getItem(getStorageKey()) || '{}');
      const targetChat = latestChats[chatId];
      if (targetChat) {
        targetChat.messages.push({ role: 'assistant', content: "Network error occurred." });
        targetChat.isGenerating = false;
        targetChat.updatedAt = Date.now();
        latestChats[chatId] = targetChat;
        saveChats(latestChats);
      }
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
