import React, { useState } from 'react';
import { GoogleLogin } from '@react-oauth/google';
import { ArrowRight, BookOpen, MessageSquareText, Scale, ShieldCheck, Sparkles } from 'lucide-react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/auth';

const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID || '';

export const HomePage: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, signIn } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const sessionExpired = new URLSearchParams(location.search).get('reason') === 'session_expired';
  const [isSigningIn, setIsSigningIn] = useState(false);

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
    <div className="min-h-screen bg-[#F2F0EB] text-[#121212]">
      <header className="sticky top-0 z-20 border-b border-gray-200/80 bg-[#F2F0EB]/90 backdrop-blur">
        <div className="mx-auto flex h-20 max-w-6xl items-center justify-between px-6 lg:px-10">
          <button type="button" onClick={() => navigate('/home')} className="flex items-center gap-3">
            <Scale className="h-7 w-7 text-[#1E293B]" strokeWidth={1.5} />
            <span className="font-serif text-xl tracking-tight">TRANA</span>
          </button>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => navigate('/')}
              className="hidden rounded-lg px-4 py-2 text-sm text-gray-600 transition-colors hover:bg-white hover:text-[#121212] sm:inline-flex"
            >
              Open chats
            </button>
            {user ? (
              <button
                type="button"
                onClick={() => navigate('/')}
                className="rounded-lg bg-[#1E293B] px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-[#0F172A]"
              >
                Continue as {user.name?.split(' ')[0] || 'user'}
              </button>
            ) : !GOOGLE_CLIENT_ID ? (
              <button
                type="button"
                onClick={() => setError('Google sign-in is not configured for this deployment yet.')}
                className="rounded-lg bg-[#1E293B] px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-[#0F172A]"
              >
                Sign in
              </button>
            ) : (
              <div className={isSigningIn ? 'pointer-events-none opacity-50' : ''}>
                <GoogleLogin
                  onSuccess={(response) => void handleGoogleSuccess(response.credential)}
                  onError={() => setError('Google sign-in was cancelled or could not start.')}
                  theme="filled_black"
                  size="medium"
                  shape="rectangular"
                />
              </div>
            )}
          </div>
        </div>
      </header>

      {sessionExpired && (
        <div role="alert" className="mx-auto mt-5 max-w-6xl px-6 lg:px-10">
          <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
            Your session expired. Please sign in with Google again to continue.
          </div>
        </div>
      )}

      <main>
        <section className="mx-auto grid max-w-6xl gap-12 px-6 pb-20 pt-16 lg:grid-cols-[1.05fr_0.95fr] lg:items-center lg:px-10 lg:pb-28 lg:pt-24">
          <div>
            <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-gray-300 bg-white/60 px-3 py-1.5 text-xs font-medium uppercase tracking-[0.16em] text-gray-600">
              <Sparkles className="h-3.5 w-3.5 text-[#1E293B]" />
              Legal clarity, grounded in context
            </div>
            <h1 className="max-w-3xl font-serif text-5xl font-normal leading-[1.05] tracking-tight text-[#121212] sm:text-6xl lg:text-7xl">
              Understand the law before you take the next step.
            </h1>
            <p className="mt-7 max-w-xl text-lg leading-8 text-gray-600">
              TRANA helps you explore legal situations with structured analysis, relevant Indian legal sources, and a private chat history tied to your Google account.
            </p>
            <div className="mt-9 flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={() => navigate('/')}
                className="inline-flex items-center gap-2 rounded-lg bg-[#1E293B] px-5 py-3 text-sm font-medium text-white transition-colors hover:bg-[#0F172A]"
              >
                {user ? 'Open your chats' : 'Start a temporary chat'}
                <ArrowRight className="h-4 w-4" />
              </button>
              <button
                type="button"
                onClick={() => navigate('/')}
                className="rounded-lg border border-[#1E293B] px-5 py-3 text-sm font-medium text-[#1E293B] transition-colors hover:bg-white"
              >
                Explore the chat
              </button>
            </div>
          </div>

          <div className="relative overflow-hidden rounded-2xl bg-[#121212] p-7 text-white shadow-xl shadow-slate-900/10 sm:p-9">
            <div className="absolute -right-16 -top-16 h-48 w-48 rounded-full border border-white/10" />
            <div className="absolute -bottom-24 -left-10 h-56 w-56 rounded-full border border-white/10" />
            <div className="relative">
              <p className="text-xs font-medium uppercase tracking-[0.18em] text-slate-400">A calmer way to reason</p>
              <div className="mt-10 space-y-5">
                <div className="flex gap-4 border-b border-white/10 pb-5">
                  <MessageSquareText className="mt-1 h-5 w-5 flex-shrink-0 text-slate-300" />
                  <div>
                    <p className="font-serif text-xl">Ask in plain language</p>
                    <p className="mt-1 text-sm leading-6 text-slate-400">Turn a confusing situation into a focused legal question.</p>
                  </div>
                </div>
                <div className="flex gap-4 border-b border-white/10 pb-5">
                  <BookOpen className="mt-1 h-5 w-5 flex-shrink-0 text-slate-300" />
                  <div>
                    <p className="font-serif text-xl">See the reasoning</p>
                    <p className="mt-1 text-sm leading-6 text-slate-400">Get structured analysis with the relevant context surfaced.</p>
                  </div>
                </div>
                <div className="flex gap-4">
                  <ShieldCheck className="mt-1 h-5 w-5 flex-shrink-0 text-slate-300" />
                  <div>
                    <p className="font-serif text-xl">Return to your history</p>
                    <p className="mt-1 text-sm leading-6 text-slate-400">Your saved conversations stay connected to your account.</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section id="sign-in" className="border-y border-gray-200 bg-white/70">
          <div className="mx-auto grid max-w-6xl gap-10 px-6 py-16 lg:grid-cols-[1fr_auto] lg:items-center lg:px-10">
            <div>
              <p className="text-xs font-medium uppercase tracking-[0.18em] text-gray-500">Your starting point</p>
              <h2 className="mt-3 font-serif text-3xl font-normal text-[#121212] sm:text-4xl">Keep your legal conversations in one place.</h2>
              <p className="mt-3 max-w-2xl text-sm leading-7 text-gray-600">Sign in to create chats, revisit previous questions, and continue where you left off.</p>
            </div>
            <div className="min-w-[220px]">
              {user ? (
                <button
                  type="button"
                  onClick={() => navigate('/')}
                  className="w-full rounded-lg bg-[#1E293B] px-5 py-3 text-sm font-medium text-white hover:bg-[#0F172A]"
                >
                  Go to chats
                </button>
              ) : !GOOGLE_CLIENT_ID ? (
                <p className="rounded-lg bg-amber-50 p-4 text-sm text-amber-700">Google sign-in is not configured for this deployment yet.</p>
              ) : (
                <div className={isSigningIn ? 'pointer-events-none opacity-50' : ''}>
                  <GoogleLogin
                    onSuccess={(response) => void handleGoogleSuccess(response.credential)}
                    onError={() => setError('Google sign-in was cancelled or could not start.')}
                  />
                </div>
              )}
              {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
            </div>
          </div>
        </section>
      </main>

      <footer className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-6 py-8 text-xs text-gray-500 lg:px-10">
        <span>TRANA · Legal analysis, made clearer.</span>
        <div className="flex gap-4">
          <button type="button" onClick={() => navigate('/privacy')} className="hover:text-[#121212]">Privacy</button>
          <button type="button" onClick={() => navigate('/terms')} className="hover:text-[#121212]">Terms</button>
        </div>
      </footer>
    </div>
  );
};
