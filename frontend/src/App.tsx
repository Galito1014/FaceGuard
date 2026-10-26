import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./lib/auth";
import { RealtimeProvider } from "./lib/realtime";
import Layout from "./components/Layout";
import { Spinner } from "./components/ui";
import LoginPage from "./pages/Login";
import ChangePasswordPage from "./pages/ChangePassword";
import DashboardPage from "./pages/Dashboard";
import MonitorPage from "./pages/Monitor";
import BlacklistPage from "./pages/Blacklist";
import AlertsPage from "./pages/Alerts";
import EventsPage from "./pages/Events";
import UsersPage from "./pages/Users";
import AuditPage from "./pages/Audit";
import SettingsPage from "./pages/Settings";
import NotFoundPage from "./pages/NotFound";

function Guard({ perm, children }: { perm: string; children: JSX.Element }) {
  const { can } = useAuth();
  return can(perm) ? children : <NotFoundPage forbidden />;
}

export default function App() {
  const { me, loading } = useAuth();
  if (loading) return <div className="grid h-full place-items-center"><Spinner /></div>;
  if (!me) {
    return (
      <Routes>
        <Route path="*" element={<LoginPage />} />
      </Routes>
    );
  }
  if (me.must_change_password) return <ChangePasswordPage forced />;
  return (
    <RealtimeProvider>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<DashboardPage />} />
          <Route path="monitoreo" element={<Guard perm="camera.view"><MonitorPage /></Guard>} />
          <Route path="lista" element={<Guard perm="blacklist.view"><BlacklistPage /></Guard>} />
          <Route path="alertas" element={<Guard perm="alerts.view"><AlertsPage /></Guard>} />
          <Route path="historial" element={<Guard perm="events.view"><EventsPage /></Guard>} />
          <Route path="usuarios" element={<Guard perm="users.manage"><UsersPage /></Guard>} />
          <Route path="auditoria" element={<Guard perm="audit.view"><AuditPage /></Guard>} />
          <Route path="configuracion" element={<Guard perm="settings.view"><SettingsPage /></Guard>} />
          <Route path="cuenta" element={<ChangePasswordPage />} />
          <Route path="login" element={<Navigate to="/" replace />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </RealtimeProvider>
  );
}
