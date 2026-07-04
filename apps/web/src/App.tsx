import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth";
import Config from "./pages/Config";
import Inbox from "./pages/Inbox";
import Leads from "./pages/Leads";
import Login from "./pages/Login";

const ICON = { width: 18, height: 18, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 2, strokeLinecap: "round", strokeLinejoin: "round" } as const;

const ChatIcon = () => (
  <svg {...ICON} aria-hidden>
    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
  </svg>
);
const FunnelIcon = () => (
  <svg {...ICON} aria-hidden>
    <path d="M22 3H2l8 9.46V19l4 2v-8.54L22 3z" />
  </svg>
);
const GearIcon = () => (
  <svg {...ICON} aria-hidden>
    <circle cx="12" cy="12" r="3" />
    <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
  </svg>
);
const LogoutIcon = () => (
  <svg {...ICON} aria-hidden>
    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
    <polyline points="16 17 21 12 16 7" />
    <line x1="21" y1="12" x2="9" y2="12" />
  </svg>
);

export default function App() {
  const { me, loading, logout, can } = useAuth();

  if (loading) return <div className="login-wrap">Cargando…</div>;
  if (!me) return <Login />;

  return (
    <div className="layout">
      <nav className="sidebar">
        <div className="brand">
          CRM <em>WhatsApp</em>
        </div>
        <NavLink to="/" end>
          <ChatIcon /> Conversaciones
        </NavLink>
        {can("leads:read") && (
          <NavLink to="/leads">
            <FunnelIcon /> Leads
          </NavLink>
        )}
        {can("config:access") && (
          <NavLink to="/config">
            <GearIcon /> Panel técnico
          </NavLink>
        )}
        <div className="spacer" />
        <div className="who">
          <strong style={{ color: "var(--text-secondary)" }}>{me.name}</strong>
          <br />
          {me.role}
        </div>
        <a
          href="#"
          onClick={(e) => {
            e.preventDefault();
            logout();
          }}
        >
          <LogoutIcon /> Salir
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
