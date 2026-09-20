import React from 'react';
import { Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { AppLayout } from './components/AppLayout';
import { Login } from './pages/Login';
import { Overview } from './pages/Overview';
import { Accounts } from './pages/Accounts';
import { Statements } from './pages/Statements';
import { DraftReview } from './pages/DraftReview';
import { EmailCenter } from './pages/EmailCenter';
import { MailboxConfig } from './pages/MailboxConfig';
import { ModelConfig } from './pages/ModelConfig';
import { Jobs } from './pages/Jobs';
import { Devices } from './pages/Devices';
import { AuditLogs } from './pages/AuditLogs';

const AuthGuard: React.FC<{ children: React.ReactElement }> = ({ children }) => {
  const location = useLocation();
  const csrfToken = sessionStorage.getItem('cardcue_csrf');
  if (!csrfToken) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }
  return children;
};

export const App: React.FC = () => {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        path="/"
        element={
          <AuthGuard>
            <AppLayout />
          </AuthGuard>
        }
      >
        <Route index element={<Overview />} />
        <Route path="accounts" element={<Accounts />} />
        <Route path="statements" element={<Statements />} />
        <Route path="drafts" element={<DraftReview />} />
        <Route path="emails" element={<EmailCenter />} />
        <Route path="mailboxes" element={<MailboxConfig />} />
        <Route path="models" element={<ModelConfig />} />
        <Route path="jobs" element={<Jobs />} />
        <Route path="devices" element={<Devices />} />
        <Route path="audit" element={<AuditLogs />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
};
