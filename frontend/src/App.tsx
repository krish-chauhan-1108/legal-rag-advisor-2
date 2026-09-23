import { BrowserRouter, Routes, Route, useLocation } from 'react-router-dom';
import { DashboardLayout } from './views/DashboardLayout';
import { ChatView } from './views/ChatView';
import { AccountView } from './views/AccountView';
import { LegalPage } from './views/LegalPage';
import { HomePage } from './views/HomePage';
import { AdminView } from './views/AdminView';

const AppContent = () => {
  const location = useLocation();

  return (
    <Routes>
      <Route path="/privacy" element={<LegalPage />} />
      <Route path="/terms" element={<LegalPage />} />
      <Route path="/home" element={<HomePage />} />
      <Route path="/" element={<DashboardLayout />}>
        {/* Default dashboard view */}
        <Route index element={<ChatView key={location.pathname} />} />
        <Route path="chat/:id" element={<ChatView key={location.pathname} />} />
        <Route path="account" element={<AccountView />} />
        <Route path="admin" element={<AdminView />} />
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
