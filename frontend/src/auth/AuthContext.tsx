import React, { useEffect, useMemo, useRef, useState } from 'react';
import type { AuthUser } from '../types';
import { AuthContext, SESSION_EXPIRED_EVENT } from './auth';
import type { AuthContextValue } from './auth';
import { API_URL } from '../config';
const STORAGE_KEY = 'trana.auth';

const readStoredSession = (): { credential: string; user: AuthUser } | null => {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (!stored) return null;
    const parsed = JSON.parse(stored) as { credential?: string; user?: AuthUser };
    if (parsed.credential && parsed.user) return { credential: parsed.credential, user: parsed.user };
  } catch {
    localStorage.removeItem(STORAGE_KEY);
  }
  return null;
};

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const stored = readStoredSession();
  const [credential, setCredential] = useState<string | null>(stored?.credential ?? null);
  const [user, setUser] = useState<AuthUser | null>(stored?.user ?? null);
  const expiryHandled = useRef(false);

  useEffect(() => {
    const handleSessionExpired = () => {
      if (expiryHandled.current) return;
      expiryHandled.current = true;

      localStorage.removeItem(STORAGE_KEY);
      setCredential(null);
      setUser(null);

      if (window.location.pathname !== '/home') {
        window.alert('Your session expired. Please sign in again.');
        window.location.replace('/home?reason=session_expired');
      }
    };

    window.addEventListener(SESSION_EXPIRED_EVENT, handleSessionExpired);
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, handleSessionExpired);
  }, []);

  const value = useMemo<AuthContextValue>(() => ({
    credential,
    user,
    signIn: async (nextCredential: string) => {
      const response = await fetch(`${API_URL}/api/auth/google`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ credential: nextCredential }),
      });
      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(typeof error.detail === 'string' ? error.detail : 'Google sign-in failed.');
      }
      const data = await response.json() as { user: AuthUser };
      const session = { credential: nextCredential, user: data.user };
      localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
      setCredential(nextCredential);
      setUser(data.user);
    },
    signOut: () => {
      localStorage.removeItem(STORAGE_KEY);
      setCredential(null);
      setUser(null);
    },
  }), [credential, user]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};
