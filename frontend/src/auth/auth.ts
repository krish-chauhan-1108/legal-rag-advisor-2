import { createContext, useContext } from 'react';
import type { AuthUser } from '../types';

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
