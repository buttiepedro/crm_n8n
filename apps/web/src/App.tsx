import { useState } from "react";
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
const CollapseIcon = ({ collapsed }: { collapsed: boolean }) => (
  <svg {...ICON} aria-hidden>
    {collapsed ? (
      <>
        <polyline points="13 17 18 12 13 7" />
        <polyline points="6 17 11 12 6 7" />
      </>
    ) : (
      <>
        <polyline points="11 17 6 12 11 7" />
        <polyline points="18 17 13 12 18 7" />
      </>
    )}
  </svg>
);

export default function App() {
  const { me, loading, logout, can } = useAuth();
  const [collapsed, setCollapsed] = useState(
    () => localStorage.getItem("sidebar-collapsed") === "1",
  );

  const toggle = () => {
    const next = !collapsed;
    setCollapsed(next);
    localStorage.setItem("sidebar-collapsed", next ? "1" : "0");
  };

  if (loading) return <div className="login-wrap">Cargando…</div>;
  if (!me) return <Login />;

  return (
    <div className="layout">
      <nav className={`sidebar ${collapsed ? "collapsed" : ""}`}>
        <div className="sidebar-top">
          <div className="brand">
            CRM <em>WhatsApp</em>
          </div>
          <button
            className="collapse-btn"
            onClick={toggle}
            title={collapsed ? "Expandir menú" : "Ocultar menú"}
            aria-label={collapsed ? "Expandir menú" : "Ocultar menú"}
          >
            <CollapseIcon collapsed={collapsed} />
          </button>
        </div>
        <NavLink to="/" end title="Conversaciones">
          <ChatIcon /> <span className="label">Conversaciones</span>
        </NavLink>
        {can("leads:read") && (
          <NavLink to="/leads" title="Leads">
            <FunnelIcon /> <span className="label">Leads</span>
          </NavLink>
        )}
        {can("config:access") && (
          <NavLink to="/config" title="Panel técnico">
            <GearIcon /> <span className="label">Panel técnico</span>
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
          title="Salir"
          onClick={(e) => {
            e.preventDefault();
            logout();
          }}
        >
          <LogoutIcon /> <span className="label">Salir</span>
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
