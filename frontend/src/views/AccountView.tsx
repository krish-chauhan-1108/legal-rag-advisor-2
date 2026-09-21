import React, { useEffect, useState } from 'react';
import { GoogleLogin } from '@react-oauth/google';
import { ExternalLink, LogOut, ShieldCheck, UserCircle } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/auth';
import { getAdminAccess } from '../api/admin';

const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID || '';

export const AccountView: React.FC = () => {
  const navigate = useNavigate();
  const { credential, user, signIn, signOut } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const [isSigningIn, setIsSigningIn] = useState(false);
  const [isAdmin, setIsAdmin] = useState(false);

  useEffect(() => {
    let active = true;
    if (!credential) {
      queueMicrotask(() => {
        if (active) setIsAdmin(false);
      });
      return () => { active = false; };
    }

    void getAdminAccess(credential)
      .then((access) => {
        if (active) setIsAdmin(access.authorized);
      })
      .catch(() => {
        if (active) setIsAdmin(false);
      });

    return () => { active = false; };
  }, [credential]);

  const handleGoogleSuccess = async (credential?: string) => {
    if (!credential) return;
    setError(null);
    setIsSigningIn(true);
    try {
      await signIn(credential);
      navigate('/');
    } catch (signInError) {
      setError(signInError instanceof Error ? signInError.message : 'Google sign-in failed.');
    } finally {
      setIsSigningIn(false);
    }
  };

  return (
    <div className="flex flex-col h-full bg-white overflow-y-auto">
      <header className="h-16 border-b border-gray-100 flex items-center px-8 flex-shrink-0">
        <h2 className="text-xl font-serif tracking-tight text-[#121212]">Account</h2>
      </header>

      <div className="p-8 max-w-xl mx-auto w-full">
        <div className="border border-gray-200 rounded-2xl p-8 shadow-sm">
          {user ? (
            <>
              <div className="flex items-center gap-4 mb-8">
                {user.picture ? (
                  <img src={user.picture} alt="" className="w-14 h-14 rounded-full" />
                ) : (
                  <UserCircle className="w-14 h-14 text-gray-400" />
                )}
                <div>
                  <h3 className="text-lg font-medium text-gray-900">{user.name || 'TRANA user'}</h3>
                  <p className="text-sm text-gray-500">{user.email}</p>
                </div>
              </div>
              <div className="flex items-start gap-3 rounded-lg bg-green-50 p-4 text-sm text-green-800 mb-6">
                <ShieldCheck className="w-5 h-5 flex-shrink-0" />
                <p>Your chats are associated with this Google account.</p>
              </div>
              {isAdmin && (
                <button
                  type="button"
                  onClick={() => navigate('/admin')}
                  className="mb-6 flex w-full items-center justify-between rounded-lg border border-gray-200 px-4 py-3 text-left text-sm text-gray-700 transition-colors hover:border-gray-400 hover:bg-gray-50"
                >
                  <span className="flex items-center gap-2"><ShieldCheck className="w-4 h-4" /> Admin console</span>
                  <ExternalLink className="w-4 h-4 text-gray-400" />
                </button>
              )}
              <button
                type="button"
                onClick={() => { signOut(); navigate('/'); }}
                className="flex items-center gap-2 text-sm text-gray-600 hover:text-gray-900"
              >
                <LogOut className="w-4 h-4" />
                Sign out
              </button>
            </>
          ) : (
            <>
              <h3 className="text-lg font-medium text-gray-900 mb-2">Sign in to TRANA</h3>
              <p className="text-sm text-gray-500 mb-6">
                Sign in with Google to save and access your chat history across devices.
              </p>
              {!GOOGLE_CLIENT_ID ? (
                <p className="text-sm text-amber-700 bg-amber-50 rounded-lg p-4">
                  Google sign-in is not configured for this deployment yet.
                </p>
              ) : (
                <div className={isSigningIn ? 'opacity-50 pointer-events-none' : ''}>
                  <GoogleLogin
                    onSuccess={(response) => void handleGoogleSuccess(response.credential)}
                    onError={() => setError('Google sign-in was cancelled or could not start.')}
                  />
                </div>
              )}
              {error && <p className="text-sm text-red-600 mt-4">{error}</p>}
            </>
          )}
        </div>
      </div>
    </div>
  );
};
