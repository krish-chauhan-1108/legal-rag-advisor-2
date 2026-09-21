import { createContext, useContext } from 'react';
import type { AuthUser } from '../types';

export const SESSION_EXPIRED_EVENT = 'trana:session-expired';
export const API_ONLINE_EVENT = 'trana:api-online';

export const notifyApiOnline = (sourceRegistryReady = false): void => {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent(API_ONLINE_EVENT, {
      detail: { sourceRegistryReady },
    }));
  }
};

export interface AuthContextValue {
  credential: string | null;
  user: AuthUser | null;
  signIn: (credential: string) => Promise<void>;
  signOut: () => void;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export const useAuth = (): AuthContextValue => {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used inside AuthProvider.');
  return context;
};

export const authHeaders = (credential: string | null): Record<string, string> => (
  credential ? { Authorization: `Bearer ${credential}` } : {}
);

/**
 * Make an authenticated request and notify the auth provider when Google has
 * rejected the ID token. The provider owns clearing storage and navigation so
 * every protected screen follows the same expiry behavior.
 */
export const authFetch = async (
  input: RequestInfo | URL,
  credential: string | null,
  init: RequestInit = {},
): Promise<Response> => {
  const response = await fetch(input, {
    ...init,
    headers: {
      ...authHeaders(credential),
      ...init.headers,
    },
  });

  if (response.status === 401 && typeof window !== 'undefined') {
    window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
  }

  if (response.ok) notifyApiOnline();

  return response;
};
