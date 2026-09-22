import React, { useEffect, useMemo, useRef, useState } from 'react';
import type { AuthUser } from '../types';
import { AuthContext, SESSION_EXPIRED_EVENT } from './auth';
import type { AuthContextValue } from './auth';
import { API_URL } from '../config';
const STORAGE_KEY = 'trana.auth';

type StoredSession = { credential: string; user: AuthUser; sessionExpiresAt?: string };
type AuthResponse = { user: AuthUser; session_token?: string; session_expires_at?: string };

const readStoredSession = (): StoredSession | null => {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (!stored) return null;
    const parsed = JSON.parse(stored) as { credential?: string; user?: AuthUser; sessionExpiresAt?: string };
    if (parsed.credential && parsed.user) {
      return { credential: parsed.credential, user: parsed.user, sessionExpiresAt: parsed.sessionExpiresAt };
    }
  } catch {
    localStorage.removeItem(STORAGE_KEY);
  }
  return null;
};

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const stored = readStoredSession();
  const storedCredential = stored?.credential;
  const storedSessionExpiresAt = stored?.sessionExpiresAt;
  const [credential, setCredential] = useState<string | null>(stored?.credential ?? null);
  const [user, setUser] = useState<AuthUser | null>(stored?.user ?? null);
  const [sessionExpiresAt, setSessionExpiresAt] = useState<string | null>(stored?.sessionExpiresAt ?? null);
  const expiryHandled = useRef(false);

  useEffect(() => {
    const handleSessionExpired = () => {
      if (expiryHandled.current) return;
      expiryHandled.current = true;

      localStorage.removeItem(STORAGE_KEY);
      setCredential(null);
      setUser(null);
      setSessionExpiresAt(null);

      if (window.location.pathname !== '/home') {
        window.alert('Your session expired. Please sign in again.');
        window.location.replace('/home?reason=session_expired');
      }
    };

    window.addEventListener(SESSION_EXPIRED_EVENT, handleSessionExpired);
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, handleSessionExpired);
  }, []);

  useEffect(() => {
    // Seamlessly migrate sessions created before TRANA issued its own token.
    if (!storedCredential || storedSessionExpiresAt) return;

    let cancelled = false;
    void fetch(`${API_URL}/api/auth/session`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ credential: storedCredential }),
    })
      .then(async (response) => {
        if (!response.ok) return null;
        return await response.json() as AuthResponse;
      })
      .then((data) => {
        if (!data || cancelled) return;
        if (!data.session_token || !data.session_expires_at) return;
        const nextSession = {
          credential: data.session_token,
          user: data.user,
          sessionExpiresAt: data.session_expires_at,
        };
        localStorage.setItem(STORAGE_KEY, JSON.stringify(nextSession));
        setCredential(data.session_token);
        setUser(data.user);
        setSessionExpiresAt(data.session_expires_at);
      })
      .catch(() => {
        // The existing credential remains usable until Google expires it.
      });

    return () => {
      cancelled = true;
    };
  }, [storedCredential, storedSessionExpiresAt]);

  const value = useMemo<AuthContextValue>(() => ({
    credential,
    user,
    sessionExpiresAt,
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
      const data = await response.json() as AuthResponse;
      const sessionCredential = data.session_token ?? nextCredential;
      const session = {
        credential: sessionCredential,
        user: data.user,
        ...(data.session_expires_at ? { sessionExpiresAt: data.session_expires_at } : {}),
      };
      localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
      setCredential(sessionCredential);
      setUser(data.user);
      setSessionExpiresAt(data.session_expires_at ?? null);
    },
    signOut: () => {
      if (credential) {
        void fetch(`${API_URL}/api/auth/logout`, {
          method: 'POST',
          headers: { Authorization: `Bearer ${credential}` },
        }).catch(() => undefined);
      }
      localStorage.removeItem(STORAGE_KEY);
      setCredential(null);
      setUser(null);
      setSessionExpiresAt(null);
    },
  }), [credential, sessionExpiresAt, user]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};
