import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { DashboardLayout } from './views/DashboardLayout';
import { ChatView } from './views/ChatView';
import { KnowledgeBaseView } from './views/KnowledgeBaseView';
import { LoginView } from './views/LoginView';
import { useAuth } from './context/AuthContext';

const ProtectedRoute = ({ children }: { children: React.ReactNode }) => {
  const { isAuthenticated } = useAuth();
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }
  return <>{children}</>;
};

const AppContent = () => {
  return (
    <Routes>
      <Route path="/login" element={<LoginView />} />
      <Route path="/" element={<ProtectedRoute><DashboardLayout /></ProtectedRoute>}>
        {/* Default dashboard view */}
        <Route index element={<ChatView />} />
        <Route path="chat/:id" element={<ChatView />} />
        <Route path="knowledge-base" element={<KnowledgeBaseView />} />
      </Route>
    </Routes>
  );
};

export default function App() {
  return (
    <BrowserRouter>
      <AppContent />
    </BrowserRouter>
  );
}
