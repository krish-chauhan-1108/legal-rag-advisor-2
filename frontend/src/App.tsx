import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { DashboardLayout } from './views/DashboardLayout';
import { ChatView } from './views/ChatView';
import { AccountView } from './views/AccountView';

const AppContent = () => {
  return (
    <Routes>
      <Route path="/" element={<DashboardLayout />}>
        {/* Default dashboard view */}
        <Route index element={<ChatView />} />
        <Route path="chat/:id" element={<ChatView />} />
        <Route path="account" element={<AccountView />} />
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
