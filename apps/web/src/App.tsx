import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth";
import Config from "./pages/Config";
import Inbox from "./pages/Inbox";
import Leads from "./pages/Leads";
import Login from "./pages/Login";

export default function App() {
  const { me, loading, logout, can } = useAuth();

  if (loading) return <div className="login-wrap">Cargando…</div>;
  if (!me) return <Login />;

  return (
    <div className="layout">
      <nav className="sidebar">
        <div className="brand">CRM WhatsApp</div>
        <NavLink to="/" end>
          💬 Conversaciones
        </NavLink>
        {can("leads:read") && <NavLink to="/leads">📊 Leads</NavLink>}
        {can("config:access") && <NavLink to="/config">⚙️ Panel técnico</NavLink>}
        <div className="spacer" />
        <div className="who">
          {me.name}
          <br />
          <span style={{ opacity: 0.7 }}>{me.role}</span>
        </div>
        <a
          href="#"
          onClick={(e) => {
            e.preventDefault();
            logout();
          }}
        >
          Salir
        </a>
      </nav>
      <main className="content">
        <Routes>
          <Route path="/" element={<Inbox />} />
          <Route path="/leads" element={<Leads />} />
          <Route path="/config" element={<Config />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}
