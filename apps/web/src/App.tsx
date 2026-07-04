/**
 * Placeholder del panel CRM (P3): página de estado que verifica la conexión
 * con el backend a través del proxy /api. El panel de conversaciones, leads
 * y configuración se construyen en la fase 3 del roadmap.
 */
import { useEffect, useState } from "react";

type ApiState = "checking" | "ok" | "no-db" | "down";

const STATUS_LABEL: Record<ApiState, { text: string; color: string }> = {
  checking: { text: "Verificando…", color: "#a68b00" },
  ok: { text: "API y base de datos operativas", color: "#1a7f37" },
  "no-db": { text: "API viva, base de datos inaccesible", color: "#b54708" },
  down: { text: "API inaccesible", color: "#b42318" },
};

export default function App() {
  const [state, setState] = useState<ApiState>("checking");

  useEffect(() => {
    const check = async () => {
      try {
        const live = await fetch("/api/v1/health");
        if (!live.ok) return setState("down");
        const ready = await fetch("/api/v1/health/ready");
        setState(ready.ok ? "ok" : "no-db");
      } catch {
        setState("down");
      }
    };
    check();
    const interval = setInterval(check, 10_000);
    return () => clearInterval(interval);
  }, []);

  const status = STATUS_LABEL[state];

  return (
    <main
      style={{
        fontFamily: "system-ui, sans-serif",
        maxWidth: 640,
        margin: "10vh auto",
        padding: "0 24px",
        lineHeight: 1.6,
      }}
    >
      <h1 style={{ marginBottom: 8 }}>CRM WhatsApp ↔ n8n</h1>
      <p style={{ color: "#555", marginTop: 0 }}>
        Plataforma intermediaria entre WhatsApp Business Cloud API y n8n.
      </p>

      <div
        style={{
          border: "1px solid #ddd",
          borderRadius: 8,
          padding: "16px 20px",
          display: "flex",
          alignItems: "center",
          gap: 12,
        }}
      >
        <span
          aria-hidden
          style={{
            width: 12,
            height: 12,
            borderRadius: "50%",
            background: status.color,
            display: "inline-block",
          }}
        />
        <strong>{status.text}</strong>
      </div>

      <ul style={{ marginTop: 24 }}>
        <li>
          <a href="/api/docs">Documentación OpenAPI de la API</a>
        </li>
        <li>
          Hooks para n8n: <code>POST /api/v1/hooks/n8n/messages</code> ·{" "}
          <code>POST /api/v1/hooks/n8n/leads</code>
        </li>
      </ul>

      <p style={{ color: "#888", fontSize: 14 }}>
        Panel de conversaciones, leads y configuración: fase 3 del roadmap.
      </p>
    </main>
  );
}
