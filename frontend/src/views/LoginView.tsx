import React from 'react';
import { GoogleLogin } from '@react-oauth/google';
import { jwtDecode } from 'jwt-decode';
import { useNavigate, Navigate } from 'react-router-dom';
import { Scale } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

export const LoginView: React.FC = () => {
  const { login, isAuthenticated } = useAuth();
  const navigate = useNavigate();

  if (isAuthenticated) {
    return <Navigate to="/" replace />;
  }

  const handleSuccess = (credentialResponse: any) => {
    if (credentialResponse.credential) {
      const decoded: any = jwtDecode(credentialResponse.credential);
      login({
        email: decoded.email,
        name: decoded.name,
        picture: decoded.picture,
      });
      navigate('/');
    }
  };

  const handleError = () => {
    console.error('Google Login Failed');
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#F2F0EB]">
      <div className="bg-white p-10 rounded-[2.5rem] shadow-lg border border-gray-100 max-w-md w-full text-center flex flex-col items-center">
        <div className="w-16 h-16 bg-[#1E293B] rounded-[2rem] flex items-center justify-center mb-6 shadow-md">
          <Scale className="w-8 h-8 text-white" strokeWidth={1.5} />
        </div>
        <h1 className="text-3xl font-serif text-[#121212] mb-2 tracking-tight">Welcome to LawLLM</h1>
        <p className="text-gray-500 mb-10 text-sm">Sign in to access advanced legal analysis and tools.</p>
        
        <div className="w-full flex justify-center">
          <GoogleLogin
            onSuccess={handleSuccess}
            onError={handleError}
            useOneTap
            shape="rectangular"
            theme="outline"
            size="large"
          />
        </div>
      </div>
    </div>
  );
};
