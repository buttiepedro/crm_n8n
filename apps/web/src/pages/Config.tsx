/** Panel técnico: exige step-up con la contraseña explícita del .env
 *  (ADMIN_PANEL_PASSWORD). Desde acá se configura TODO lo demás: tokens de
 *  Meta, cuentas WhatsApp, webhooks n8n, API keys, usuarios y logs. */
import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError, api, showError } from "../api";
import { useAuth } from "../auth";
import { Select } from "../ui/Select";
import { Switch } from "../ui/Switch";
import { alertDialog, confirmDialog, promptDialog } from "../ui/dialogs";

const fmt = (iso: string | null) => (iso ? new Date(iso).toLocaleString() : "—");

/** Muestra un secreto recién generado en un cuadro copiable (los alert() de
 *  Chrome no dejan copiar). Funciona también sobre HTTP (sin clipboard API). */
function SecretBox({
  label,
  value,
  hint,
  onClose,
}: {
  label: string;
  value: string;
  hint?: string;
  onClose: () => void;
}) {
  const ref = useRef<HTMLInputElement>(null);
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    ref.current?.select();
    let ok = false;
    try {
      await navigator.clipboard.writeText(value);
      ok = true;
    } catch {
      try {
        ok = document.execCommand("copy"); // fallback en HTTP
      } catch {
        ok = false;
      }
    }
    setCopied(ok);
    if (ok) setTimeout(() => setCopied(false), 2500);
  };

  return (
    <div
      className="card"
      style={{
        marginBottom: 16,
        borderColor: "var(--note-border)",
        background: "var(--note-bg)",
        color: "var(--note-text)",
      }}
    >
      <strong>{label}</strong>
      <p className="muted" style={{ margin: "6px 0" }}>
        {hint ?? "Guardalo ahora: no se vuelve a mostrar."}
      </p>
      <div className="row">
        <input
          ref={ref}
          readOnly
          value={value}
          onFocus={(e) => e.target.select()}
          style={{ flex: 1, fontFamily: "monospace", fontSize: 13 }}
        />
        <button className="primary" onClick={copy}>
          {copied ? "✓ Copiado" : "Copiar"}
        </button>
        <button onClick={onClose}>Listo, lo guardé</button>
      </div>
    </div>
  );
}

export default function Config() {
  const [unlocked, setUnlocked] = useState<boolean | null>(null);
  const [tab, setTab] = useState("plataforma");

  const check = useCallback(async () => {
    try {
      await api.get("/config/platform");
      setUnlocked(true);
    } catch (e) {
      if (e instanceof ApiError && e.code === "CONFIG_STEPUP_REQUIRED") setUnlocked(false);
      else if (e instanceof ApiError && e.status === 403) setUnlocked(false);
      else showError(e);
    }
  }, []);

  useEffect(() => {
    check();
  }, [check]);

  if (unlocked === null) return <div className="page">Verificando…</div>;
  if (!unlocked) return <StepUp onOk={() => setUnlocked(true)} />;

  return (
    <div className="page">
      <h2>Panel técnico</h2>
      <div className="tabs">
        {[
          ["plataforma", "WhatsApp / Meta"],
          ["cuentas", "Cuenta"],
          ["n8n", "n8n"],
          ["keys", "API Keys n8n"],
          ["usuarios", "Usuarios"],
          ["logs", "Logs"],
        ].map(([k, label]) => (
          <button key={k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>
            {label}
          </button>
        ))}
      </div>
      {tab === "plataforma" && <PlatformTab />}
      {tab === "cuentas" && <AccountsTab />}
      {tab === "n8n" && <N8nTestTab />}
      {tab === "keys" && <KeysTab />}
      {tab === "usuarios" && <UsersTab />}
      {tab === "logs" && <LogsTab />}
    </div>
  );
}

function StepUp({ onOk }: { onOk: () => void }) {
  const [password, setPassword] = useState("");
  const { refresh } = useAuth();
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await api.post("/auth/config-panel", { password });
      await refresh();
      onOk();
    } catch (err) {
      showError(err);
    }
  };
  return (
    <div className="login-wrap">
      <form className="card login-card" onSubmit={submit}>
        <h3 style={{ margin: 0 }}>🔒 Panel técnico</h3>
        <p className="muted" style={{ margin: 0 }}>
          Ingresá la contraseña del panel (definida en el .env del servidor). El acceso dura 15
          minutos.
        </p>
        <input
          type="password"
          placeholder="contraseña del panel"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoFocus
          required
        />
        <button className="primary">Desbloquear</button>
      </form>
    </div>
  );
}

/* ── WhatsApp / Meta ─────────────────────────────────────────────────── */

function PlatformTab() {
  const [data, setData] = useState<any>(null);
  const [appSecret, setAppSecret] = useState("");
  const [graphVersion, setGraphVersion] = useState("");
  const [n8nUrl, setN8nUrl] = useState("");
  const [n8nSecret, setN8nSecret] = useState("");
  const [openaiKey, setOpenaiKey] = useState("");
  const [reveal, setReveal] = useState<{ label: string; value: string; hint?: string } | null>(null);

  const load = async () => {
    const d = await api.get<any>("/config/platform");
    setData(d);
    setGraphVersion(d.graphApiVersion);
    setN8nUrl(d.n8nWebhookUrl ?? "");
  };
  useEffect(() => {
    load().catch(showError);
  }, []);

  if (!data) return null;

  const save = async () => {
    try {
      await api.put("/config/platform", {
        appSecret: appSecret || undefined,
        graphApiVersion: graphVersion || undefined,
        n8nWebhookUrl: n8nUrl !== (data.n8nWebhookUrl ?? "") ? n8nUrl : undefined,
        n8nWebhookSecret: n8nSecret || undefined,
        openaiApiKey: openaiKey || undefined,
      });
      setAppSecret("");
      setN8nSecret("");
      setOpenaiKey("");
      await load();
      await alertDialog("Guardado");
    } catch (e) {
      showError(e);
    }
  };

  const genToken = async () => {
    try {
      const r = await api.post<any>("/config/platform/generate-verify-token");
      await load();
      setReveal({
        label: "Verify token generado",
        value: r.verifyToken,
        hint: "Pegalo en la configuración del webhook de tu app de Meta (queda visible también en el campo de abajo).",
      });
    } catch (e) {
      showError(e);
    }
  };

  return (
    <div className="card" style={{ maxWidth: 640 }}>
      {reveal && (
        <SecretBox
          label={reveal.label}
          value={reveal.value}
          hint={reveal.hint}
          onClose={() => setReveal(null)}
        />
      )}
      <h3 style={{ marginTop: 0 }}>Credenciales de Meta (globales)</h3>
      <p className="muted">
        El webhook de Meta apunta a <code className="k">/api/v1/whatsapp/webhook</code> de esta
        plataforma. Configurá acá el verify token y el App Secret; se guardan cifrados en la base
        de datos.
      </p>
      <div className="form-grid">
        <label>
          Verify token (se pega también en Meta)
          <div className="row">
            <input readOnly value={data.verifyToken ?? "(no configurado)"} style={{ flex: 1 }} />
            <button onClick={genToken}>Generar</button>
          </div>
        </label>
        <label>
          App Secret {data.appSecretSet ? "✅ configurado" : "⚠️ falta"}
          <input
            type="password"
            placeholder={data.appSecretSet ? "(reemplazar…)" : "App secret de la app de Meta"}
            value={appSecret}
            onChange={(e) => setAppSecret(e.target.value)}
          />
        </label>
        <label>
          Versión de Graph API
          <input value={graphVersion} onChange={(e) => setGraphVersion(e.target.value)} />
        </label>
      </div>

      <h3>Webhook global hacia n8n</h3>
      <p className="muted">
        TODOS los mensajes entrantes (de todas las cuentas) se guardan y se reenvían a esta URL,
        incluyendo el payload crudo de WhatsApp en <code className="k">message.raw</code>. Si una
        cuenta define su propia URL, la pisa solo para esa cuenta.
      </p>
      <div className="form-grid">
        <label>
          URL del webhook de n8n (vacío = no reenviar)
          <input
            placeholder="https://n8n…/webhook/whatsapp-in"
            value={n8nUrl}
            onChange={(e) => setN8nUrl(e.target.value)}
          />
        </label>
        <label>
          Secreto HMAC {data.n8nWebhookSecretSet ? "✅ configurado" : "(opcional)"}
          <div className="row">
            <input
              type="password"
              style={{ flex: 1 }}
              placeholder={data.n8nWebhookSecretSet ? "(reemplazar…)" : "firma X-Signature-256"}
              value={n8nSecret}
              onChange={(e) => setN8nSecret(e.target.value)}
            />
            <button
              onClick={() => {
                const s = crypto.randomUUID().replace(/-/g, "");
                setN8nSecret(s);
                setReveal({
                  label: "Secreto HMAC generado para el webhook global",
                  value: s,
                  hint: "Guardalo para validar X-Signature-256 en n8n y tocá Guardar para aplicarlo acá.",
                });
              }}
            >
              Generar
            </button>
          </div>
        </label>
      </div>

      <h3>Transcripción de audio (OpenAI)</h3>
      <p className="muted">
        Key usada para transcribir los audios entrantes con{" "}
        <code className="k">gpt-4o-transcribe</code> apenas se bajan de WhatsApp. Sin key: el
        audio se guarda igual pero sin texto (el chat muestra "transcribiendo…" para siempre).
      </p>
      <div className="form-grid">
        <label>
          OpenAI API Key {data.openaiApiKeySet ? "✅ configurada" : "⚠️ falta"}
          <input
            type="password"
            placeholder={data.openaiApiKeySet ? "(reemplazar…)" : "sk-…"}
            value={openaiKey}
            onChange={(e) => setOpenaiKey(e.target.value)}
          />
        </label>
      </div>

      <button className="primary" onClick={save}>
        Guardar
      </button>
    </div>
  );
}

/* ── Cuentas WhatsApp ────────────────────────────────────────────────── */

function AccountsTab() {
  const [items, setItems] = useState<any[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [secret, setSecret] = useState<{ label: string; value: string; hint?: string } | null>(null);

  const load = () =>
    api.get<any>("/config/accounts")
      .then((d) => { setItems(d.items); setLoaded(true); })
      .catch(showError);
  useEffect(() => {
    load();
  }, []);

  return (
    <>
      {secret && (
        <SecretBox label={secret.label} value={secret.value} hint={secret.hint}
                   onClose={() => setSecret(null)} />
      )}
      {loaded && items.length === 0 && (
        <div className="card">
          <p className="muted" style={{ margin: 0 }}>
            Todavía no hay cuenta. Cuando llegue el primer mensaje de WhatsApp se crea sola
            (auto-registro) y acá solo completás el token para poder responder.
          </p>
        </div>
      )}
      {items.map((a) => (
        <AccountCard key={a.id} account={a} onChanged={load} onSecret={setSecret} />
      ))}
    </>
  );
}

function AccountCard({ account, onChanged, onSecret }: {
  account: any;
  onChanged: () => void;
  onSecret: (s: { label: string; value: string; hint?: string }) => void;
}) {
  const [f, setF] = useState({
    name: account.name,
    wabaId: account.wabaId ?? "",
    phoneNumberId: account.phoneNumberId ?? "",
    displayPhoneNumber: account.displayPhoneNumber ?? "",
    accessToken: "",
    n8nInboundWebhookUrl: account.n8nInboundWebhookUrl ?? "",
    n8nWebhookSecret: "",
  });

  const save = async () => {
    const body: any = {
      name: f.name,
      wabaId: f.wabaId || undefined,
      phoneNumberId: f.phoneNumberId || undefined,
      displayPhoneNumber: f.displayPhoneNumber || undefined,
    };
    if (f.accessToken) body.accessToken = f.accessToken;
    if (f.n8nWebhookSecret) body.n8nWebhookSecret = f.n8nWebhookSecret;
    if (f.n8nInboundWebhookUrl !== (account.n8nInboundWebhookUrl ?? "")) {
      if (f.n8nInboundWebhookUrl) body.n8nInboundWebhookUrl = f.n8nInboundWebhookUrl;
      else body.clearWebhookUrl = true;
    }
    try {
      await api.patch(`/config/accounts/${account.id}`, body);
      setF({ ...f, accessToken: "", n8nWebhookSecret: "" });
      onChanged();
    } catch (e) {
      showError(e);
    }
  };

  const act = (fn: () => Promise<unknown>) => async () => {
    try {
      await fn();
      onChanged();
    } catch (e) {
      showError(e);
    }
  };

  return (
    <div className="card" style={{ marginBottom: 16, maxWidth: 720 }}>
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 8 }}>
        <h3 style={{ margin: 0 }}>{account.name}</h3>
        <span className={`pill ${account.status === "active" ? "green" : account.status === "error" ? "red" : "yellow"}`}>
          {account.status}
        </span>
      </div>
      <div className="form-grid">
        <label>Nombre interno
          <input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
        </label>
        <label>Phone Number ID (Meta → WhatsApp → API Setup)
          <input value={f.phoneNumberId}
                 onChange={(e) => setF({ ...f, phoneNumberId: e.target.value })} />
        </label>
        <label>WABA ID
          <input value={f.wabaId} onChange={(e) => setF({ ...f, wabaId: e.target.value })} />
        </label>
        <label>Número visible
          <input placeholder="+54 9 11 …" value={f.displayPhoneNumber}
                 onChange={(e) => setF({ ...f, displayPhoneNumber: e.target.value })} />
        </label>
        <label>Access token {account.tokenSet ? "✅ configurado" : "⚠️ falta (no se puede responder)"}
          <input type="password"
                 placeholder={account.tokenSet ? "(reemplazar…)" : "token permanente de System User"}
                 value={f.accessToken}
                 onChange={(e) => setF({ ...f, accessToken: e.target.value })} />
        </label>
        <label>Webhook n8n propio (opcional; pisa el global)
          <input placeholder="vacío = usa el webhook global" value={f.n8nInboundWebhookUrl}
                 onChange={(e) => setF({ ...f, n8nInboundWebhookUrl: e.target.value })} />
        </label>
        <label>Secreto HMAC propio {account.hasWebhookSecret ? "✅" : "(opcional)"}
          <div className="row">
            <input type="password" style={{ flex: 1 }}
                   placeholder={account.hasWebhookSecret ? "(reemplazar…)" : "firma del webhook propio"}
                   value={f.n8nWebhookSecret}
                   onChange={(e) => setF({ ...f, n8nWebhookSecret: e.target.value })} />
            <button onClick={() => {
              const s = crypto.randomUUID().replace(/-/g, "");
              setF({ ...f, n8nWebhookSecret: s });
              onSecret({
                label: `Secreto HMAC — cuenta "${account.name}"`,
                value: s,
                hint: "Guardalo para validar X-Signature-256 en n8n y tocá Guardar para aplicarlo.",
              });
            }}>Generar</button>
          </div>
        </label>
      </div>
      <div className="row" style={{ gap: 6 }}>
        <button className="primary" onClick={save}>Guardar</button>
        <button onClick={act(async () => {
          const r = await api.post<any>(`/config/accounts/${account.id}/test`);
          await alertDialog(r.ok ? `Conexión OK: ${r.phone ?? ""}` : `Error: ${JSON.stringify(r.detail)}`);
        })}>Probar conexión</button>
        <button onClick={act(async () => {
          const r = await api.post<any>(`/config/accounts/${account.id}/subscribe`);
          await alertDialog(r.ok
            ? `WABA suscripta ✅ — apps: ${JSON.stringify(r.subscribedApps)}`
            : `Error ${r.status}: ${JSON.stringify(r.detail)}`);
        })}>Suscribir WABA</button>
        <button onClick={act(async () => {
          await api.post(`/config/accounts/${account.id}/test-webhook`);
          await alertDialog("Evento de prueba encolado hacia n8n (ver Logs → Entregas)");
        })}>Test n8n</button>
        <button onClick={act(() =>
          api.patch(`/config/accounts/${account.id}`,
                    { status: account.status === "paused" ? "active" : "paused" }))}>
          {account.status === "paused" ? "Activar" : "Pausar"}
        </button>
        <button className="danger" onClick={act(async () => {
          const ok = await confirmDialog({
            title: "Eliminar cuenta",
            message: `¿Borrar la cuenta "${account.name}"? Solo posible sin historial.`,
            confirmLabel: "Eliminar",
            danger: true,
          });
          if (!ok) return;
          await api.del(`/config/accounts/${account.id}`);
        })}>Eliminar</button>
      </div>
    </div>
  );
}

/* ── Chat de prueba (n8n) ────────────────────────────────────────────── */

function N8nTestTab() {
  const [sessionId, setSessionId] = useState(
    () => localStorage.getItem("n8nTestSessionId") || crypto.randomUUID().slice(0, 8)
  );
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [msgs, setMsgs] = useState<any[]>([]);
  const [deliveries, setDeliveries] = useState<any[]>([]);
  const [text, setText] = useState("");
  const [account, setAccount] = useState<any>(null);
  const [webhookUrl, setWebhookUrl] = useState("");
  const [webhookSecret, setWebhookSecret] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [lastSentAt, setLastSentAt] = useState<number | null>(null);
  const [waitingUntil, setWaitingUntil] = useState<number | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const [responseUrl, setResponseUrl] = useState(
    () => `${window.location.origin}/api/v1/hooks/n8n/messages`
  );
  const [urlCopied, setUrlCopied] = useState(false);
  const responseUrlRef = useRef<HTMLInputElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const WAIT_MS = 5 * 60 * 1000;

  const copyResponseUrl = async () => {
    responseUrlRef.current?.select();
    let ok = false;
    try {
      await navigator.clipboard.writeText(responseUrl);
      ok = true;
    } catch {
      try {
        ok = document.execCommand("copy");
      } catch {
        ok = false;
      }
    }
    setUrlCopied(ok);
    if (ok) setTimeout(() => setUrlCopied(false), 2000);
  };

  // Cada mensaje entrante genera una fila en webhook_deliveries (mismo m.id
  // que payload.message.id): así sabemos si YA llegó a n8n o sigue reintentando.
  const deliveryByMessageId = useMemo(() => {
    const map: Record<string, any> = {};
    for (const d of deliveries) {
      const msgId = d.payload?.message?.id;
      if (msgId) map[msgId] = d;
    }
    return map;
  }, [deliveries]);

  useEffect(() => {
    localStorage.setItem("n8nTestSessionId", sessionId);
  }, [sessionId]);

  const loadAccount = useCallback(() => {
    api
      .get<any>("/config/n8n-test/account")
      .then((a) => {
        setAccount(a);
        setWebhookUrl(a.n8nInboundWebhookUrl ?? "");
      })
      .catch(showError);
  }, []);

  useEffect(() => {
    loadAccount();
  }, [loadAccount]);

  const resolveSession = useCallback(async () => {
    try {
      const r = await api.get<{ conversationId: string | null }>(
        `/config/n8n-test/session/${encodeURIComponent(sessionId)}`
      );
      setConversationId(r.conversationId);
    } catch (e) {
      showError(e);
    }
  }, [sessionId]);

  useEffect(() => {
    setMsgs([]);
    setDeliveries([]);
    setConversationId(null);
    setLastSentAt(null);
    setWaitingUntil(null);
    resolveSession();
  }, [sessionId, resolveSession]);

  const loadThread = useCallback(async () => {
    if (!conversationId) return;
    try {
      const [m, d] = await Promise.all([
        api.get<{ items: any[] }>(`/conversations/${conversationId}/messages`),
        api.get<{ items: any[] }>(`/config/webhook-deliveries?conversationId=${conversationId}`),
      ]);
      setMsgs(m.items);
      setDeliveries(d.items);
    } catch {
      /* polling */
    }
  }, [conversationId]);

  useEffect(() => {
    loadThread();
    const t = setInterval(loadThread, 3000);
    return () => clearInterval(t);
  }, [loadThread]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView();
  }, [msgs.length]);

  // ¿Ya llegó una respuesta (mensaje outbound) posterior al último envío?
  const hasReplyAfterSend =
    lastSentAt != null &&
    msgs.some((m) => m.direction === "outbound" && new Date(m.createdAt).getTime() > lastSentAt);

  useEffect(() => {
    if (hasReplyAfterSend) setWaitingUntil(null);
  }, [hasReplyAfterSend]);

  // Tick de 1s solo mientras esperamos, para el contador — la búsqueda real
  // ya la hace el polling de arriba (cada 3s, bastante más seguido que 30s).
  useEffect(() => {
    if (waitingUntil === null) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [waitingUntil]);

  const waiting = waitingUntil !== null && !hasReplyAfterSend && now < waitingUntil;
  const timedOut = waitingUntil !== null && !hasReplyAfterSend && now >= waitingUntil;

  const send = async () => {
    if (!text.trim()) return;
    try {
      const r = await api.post<{ conversationId: string | null }>("/config/n8n-test/messages", {
        sessionId,
        body: text.trim(),
      });
      setText("");
      if (r.conversationId) setConversationId(r.conversationId);
      const sentAt = Date.now();
      setLastSentAt(sentAt);
      setWaitingUntil(sentAt + WAIT_MS);
      setNow(sentAt);
      await loadThread();
    } catch (e) {
      showError(e);
    }
  };

  const newSession = () => setSessionId(crypto.randomUUID().slice(0, 8));

  const saveWebhook = async () => {
    if (!account) return;
    try {
      const body: any = {};
      if (webhookUrl !== (account.n8nInboundWebhookUrl ?? "")) {
        if (webhookUrl) body.n8nInboundWebhookUrl = webhookUrl;
        else body.clearWebhookUrl = true;
      }
      if (webhookSecret) body.n8nWebhookSecret = webhookSecret;
      await api.patch(`/config/accounts/${account.id}`, body);
      setWebhookSecret("");
      loadAccount();
      await alertDialog("Guardado");
    } catch (e) {
      showError(e);
    }
  };

  return (
    <div className="row" style={{ alignItems: "flex-start", gap: 16, flexWrap: "wrap" }}>
      <div className="card" style={{ flex: "1 1 320px", maxWidth: 420 }}>
        <h3 style={{ marginTop: 0 }}>Webhook para que n8n te responda</h3>
        <p className="muted">
          En el nodo HTTP Request de n8n: método <code className="k">POST</code>, header{" "}
          <code className="k">Authorization: Bearer &lt;api_key&gt;</code> y body{" "}
          <code className="k">{'{ "conversationId": "…", "message": { "type": "text", "body": "…" } }'}</code>.
          El <code className="k">conversationId</code> viene en el payload que ya recibiste (
          <code className="k">conversation.id</code>).
        </p>
        <label>
          URL (asumida desde este navegador — corregila si tu API vive en otro dominio/puerto)
          <div className="row">
            <input
              ref={responseUrlRef}
              value={responseUrl}
              onChange={(e) => setResponseUrl(e.target.value)}
              onFocus={(e) => e.target.select()}
              style={{ flex: 1, fontFamily: "monospace", fontSize: 13 }}
            />
            <button onClick={copyResponseUrl}>{urlCopied ? "✓ Copiado" : "Copiar"}</button>
          </div>
        </label>
      </div>

      <div className="card" style={{ flex: "1 1 320px", maxWidth: 420 }}>
        <h3 style={{ marginTop: 0 }}>Webhook del canal de prueba</h3>
        <p className="muted">
          Los mensajes de acá abajo se guardan y se reenvían con el MISMO payload/firma que un
          mensaje real de WhatsApp (mismo <code className="k">ingest</code>). La respuesta de n8n
          llega por el hook de siempre (<code className="k">/hooks/n8n/messages</code>) y se
          guarda igual — solo que no se llama a la Graph API de Meta.
        </p>
        <div className="form-grid">
          <label>
            URL del webhook (vacío = usa el global de Plataforma)
            <input
              placeholder="https://n8n…/webhook/test"
              value={webhookUrl}
              onChange={(e) => setWebhookUrl(e.target.value)}
            />
          </label>
          <label>
            Secreto HMAC {account?.hasWebhookSecret ? "✅ configurado" : "(opcional)"}
            <input
              type="password"
              placeholder={account?.hasWebhookSecret ? "(reemplazar…)" : "firma X-Signature-256"}
              value={webhookSecret}
              onChange={(e) => setWebhookSecret(e.target.value)}
            />
          </label>
        </div>
        <button className="primary" onClick={saveWebhook}>
          Guardar
        </button>

        <h3>Sesión</h3>
        <p className="muted">
          El ID identifica la conversación de prueba (simula el número de WhatsApp del cliente).
          Cambialo para arrancar otra conversación desde cero; el mismo ID siempre vuelve a la
          misma sesión.
        </p>
        <div className="row">
          <input
            style={{ flex: 1 }}
            value={sessionId}
            onChange={(e) => setSessionId(e.target.value)}
          />
          <button onClick={newSession}>Nueva sesión</button>
        </div>
      </div>

      <div
        className="card"
        style={{ flex: "2 1 420px", display: "flex", flexDirection: "column", minHeight: 460, padding: 0 }}
      >
        <div className="pane-head">
          <strong>Chat de prueba</strong>
          <span className="pill yellow">canal test</span>
          <span className="muted">sesión: {sessionId}</span>
        </div>
        <div className="msgs">
          {msgs.map((m) => {
            const delivery = m.direction === "inbound" ? deliveryByMessageId[m.id] : null;
            return (
              <div key={m.id} className={`bubble ${m.direction === "inbound" ? "in" : "out"}`}>
                {m.body || <i>[{m.type}]</i>}
                <div className="meta">
                  {m.direction === "outbound" &&
                    `${m.origin === "n8n" ? "n8n" : "agente"} · ${m.status} · `}
                  {delivery && (
                    <span
                      className={`pill ${delivery.succeeded ? "green" : "yellow"}`}
                      style={{ marginRight: 6 }}
                      title={
                        delivery.succeeded
                          ? `Entregado a n8n (HTTP ${delivery.responseStatus})`
                          : `Reintentando — intento ${delivery.attempt}, último HTTP ${delivery.responseStatus ?? "sin respuesta"}`
                      }
                    >
                      {delivery.succeeded ? "✓ n8n" : `⏳ n8n (${delivery.attempt})`}
                    </span>
                  )}
                  {fmt(m.createdAt)}
                </div>
              </div>
            );
          })}
          {msgs.length === 0 && <p className="muted">Escribí algo para arrancar la sesión.</p>}
          <div ref={bottomRef} />
        </div>
        {waiting && (
          <div className="muted" style={{ padding: "0 12px 8px", fontSize: 12 }}>
            ⏳ Esperando respuesta de n8n… (se deja de buscar en{" "}
            {Math.max(0, Math.ceil((waitingUntil! - now) / 1000))}s)
          </div>
        )}
        {timedOut && (
          <div className="bot-warning" style={{ margin: "0 12px 8px" }}>
            ⚠ n8n no respondió en 5 min. El chat se sigue actualizando solo — revisá que el
            workflow esté activo/escuchando, o mirá el intento en "Entregas hacia n8n" abajo.
          </div>
        )}
        <div className="composer">
          <textarea
            placeholder="Escribí como si fueras el cliente… (Enter para enviar)"
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
          />
          <button className="primary" onClick={send} disabled={!text.trim()}>
            Enviar
          </button>
        </div>
      </div>

      <div className="card" style={{ flex: "1 1 100%" }}>
        <h3 style={{ marginTop: 0 }}>Entregas hacia n8n (esta sesión)</h3>
        <table>
          <thead>
            <tr>
              <th>Fecha</th>
              <th>Intentos</th>
              <th>HTTP</th>
              <th>Estado</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {deliveries.map((d) => (
              <Fragment key={d.id}>
                <tr>
                  <td>{fmt(d.createdAt)}</td>
                  <td>{d.attempt}</td>
                  <td>{d.responseStatus ?? "—"}</td>
                  <td>
                    {d.succeeded ? (
                      <span className="pill green">ok</span>
                    ) : (
                      <span className="pill red">pendiente</span>
                    )}
                  </td>
                  <td>
                    <button onClick={() => setExpanded(expanded === d.id ? null : d.id)}>
                      {expanded === d.id ? "ocultar" : "ver payload"}
                    </button>
                  </td>
                </tr>
                {expanded === d.id && (
                  <tr>
                    <td colSpan={5}>
                      <div className="row" style={{ alignItems: "flex-start", gap: 16 }}>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <strong>Payload enviado</strong>
                          <pre style={{ whiteSpace: "pre-wrap", fontSize: 12, overflowX: "auto" }}>
                            {JSON.stringify(d.payload, null, 2)}
                          </pre>
                        </div>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <strong>Respuesta de n8n</strong>
                          <pre style={{ whiteSpace: "pre-wrap", fontSize: 12, overflowX: "auto" }}>
                            {d.responseBody || "(sin respuesta todavía)"}
                          </pre>
                        </div>
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
            {deliveries.length === 0 && (
              <tr>
                <td colSpan={5} className="muted">
                  Sin entregas todavía.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ── API keys ────────────────────────────────────────────────────────── */

function KeysTab() {
  const [items, setItems] = useState<any[]>([]);
  const [name, setName] = useState("");
  const [newKey, setNewKey] = useState<string | null>(null);

  const load = () => api.get<any>("/config/api-keys").then((d) => setItems(d.items)).catch(showError);
  useEffect(() => {
    load();
  }, []);

  const create = async () => {
    try {
      const r = await api.post<any>("/config/api-keys", { name });
      setName("");
      await load();
      setNewKey(r.apiKey);
    } catch (e) {
      showError(e);
    }
  };

  return (
    <>
      {newKey && (
        <SecretBox
          label="API key creada"
          value={newKey}
          hint='Guardala ahora: no se vuelve a mostrar. En n8n: header Authorization con valor "Bearer <key>".'
          onClose={() => setNewKey(null)}
        />
      )}
      <div className="row" style={{ marginBottom: 14 }}>
        <input placeholder="Nombre (ej: n8n-produccion)" value={name} onChange={(e) => setName(e.target.value)} />
        <button className="primary" onClick={create} disabled={!name.trim()}>Crear API key</button>
      </div>
      <div className="card" style={{ marginBottom: 14, maxWidth: 640 }}>
        <h3 style={{ marginTop: 0 }}>Bajar el audio crudo desde n8n</h3>
        <p className="muted">
          El payload de <code className="k">message.received</code> ya trae{" "}
          <code className="k">attachments[0].transcript</code> con el texto transcripto — para el
          caso normal no hace falta pedir nada más. Esto es solo para cuando{" "}
          <code className="k">transcript</code> viene <code className="k">null</code> (falló la
          transcripción, ej. el audio no llegó en formato soportado) y necesitás el archivo
          original igual.
        </p>
        <p className="muted">
          <code className="k">GET /api/v1/hooks/n8n/attachments/&#123;attachmentId&#125;/download</code>
          {" "}con header <code className="k">Authorization: Bearer &lt;api_key&gt;</code> — la
          misma API key que ya usás para <code className="k">/hooks/n8n/messages</code>, no hace
          falta ningún login aparte. <code className="k">attachmentId</code> viene en{" "}
          <code className="k">attachments[0].id</code> del payload.
        </p>
        <p className="muted">
          Requiere el scope <code className="k">hooks:media</code>: las keys nuevas ya lo traen
          por default. Si tu key es de antes de este cambio, no lo tiene — creá una nueva (no hay
          forma de agregarle scopes a una existente).
        </p>
      </div>
      <table>
        <thead><tr><th>Nombre</th><th>Prefijo</th><th>Scopes</th><th>Último uso</th><th>Estado</th><th></th></tr></thead>
        <tbody>
          {items.map((k) => (
            <tr key={k.id}>
              <td>{k.name}</td>
              <td><code className="k">{k.prefix}…</code></td>
              <td>{k.scopes.join(", ")}</td>
              <td>{fmt(k.lastUsedAt)}</td>
              <td>{k.isActive ? <span className="pill green">activa</span> : <span className="pill red">revocada</span>}</td>
              <td>{k.isActive && (
                <button className="danger" onClick={async () => {
                  const ok = await confirmDialog({
                    title: "Revocar API key",
                    message: `¿Revocar "${k.name}"? n8n dejará de autenticar.`,
                    confirmLabel: "Revocar",
                    danger: true,
                  });
                  if (!ok) return;
                  try { await api.post(`/config/api-keys/${k.id}/revoke`); await load(); } catch (e) { showError(e); }
                }}>Revocar</button>
              )}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

/* ── Usuarios ────────────────────────────────────────────────────────── */

function UsersTab() {
  const [items, setItems] = useState<any[]>([]);
  const [form, setForm] = useState({ email: "", name: "", role: "agent", password: "" });

  const load = () => api.get<any>("/config/users").then((d) => setItems(d.items)).catch(showError);
  useEffect(() => {
    load();
  }, []);

  const create = async () => {
    try {
      await api.post("/config/users", form);
      setForm({ email: "", name: "", role: "agent", password: "" });
      await load();
    } catch (e) {
      showError(e);
    }
  };

  const patch = (id: string, body: any) => async () => {
    try {
      await api.patch(`/config/users/${id}`, body);
      await load();
    } catch (e) {
      showError(e);
    }
  };

  return (
    <>
      <div className="card" style={{ marginBottom: 16 }}>
        <h3 style={{ marginTop: 0 }}>Nuevo usuario</h3>
        <div className="form-grid">
          <label>Email<input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></label>
          <label>Nombre<input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
          <label>Rol
            <Select
              value={form.role}
              onChange={(v) => setForm({ ...form, role: v })}
              options={[
                { value: "agent", label: "Agente" },
                { value: "supervisor", label: "Supervisor" },
                { value: "admin", label: "Admin" },
              ]}
            />
          </label>
          <label>Contraseña inicial (mín. 10)<input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></label>
        </div>
        <button className="primary" onClick={create} disabled={!form.email || !form.name || form.password.length < 10}>
          Crear usuario
        </button>
      </div>
      <table>
        <thead><tr><th>Usuario</th><th>Rol</th><th>Último login</th><th>Estado</th><th>Acciones</th></tr></thead>
        <tbody>
          {items.map((u) => (
            <tr key={u.id}>
              <td>{u.name}<br /><span className="muted">{u.email}</span></td>
              <td>
                <Select
                  value={u.role}
                  onChange={(v) => patch(u.id, { role: v })()}
                  options={[
                    { value: "agent", label: "agente" },
                    { value: "supervisor", label: "supervisor" },
                    { value: "admin", label: "admin" },
                  ]}
                />
              </td>
              <td>{fmt(u.lastLoginAt)}</td>
              <td>{u.isActive ? <span className="pill green">activo</span> : <span className="pill red">inactivo</span>}</td>
              <td>
                <div className="row" style={{ gap: 4 }}>
                  <button onClick={patch(u.id, { isActive: !u.isActive })}>{u.isActive ? "Desactivar" : "Activar"}</button>
                  <button onClick={async () => {
                    const pw = await promptDialog({
                      title: "Restablecer contraseña",
                      message: "Nueva contraseña (mín. 10; cierra sus sesiones):",
                      password: true,
                    });
                    if (pw) await patch(u.id, { password: pw })();
                  }}>Reset clave</button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

/* ── Logs ────────────────────────────────────────────────────────────── */

function LogsTab() {
  const [sub, setSub] = useState("auditoria");
  return (
    <>
      <div className="tabs">
        <button className={sub === "auditoria" ? "on" : ""} onClick={() => setSub("auditoria")}>Auditoría</button>
        <button className={sub === "entregas" ? "on" : ""} onClick={() => setSub("entregas")}>Entregas n8n</button>
        <button className={sub === "fallidos" ? "on" : ""} onClick={() => setSub("fallidos")}>Mensajes fallidos</button>
      </div>
      {sub === "auditoria" && <EventLogs />}
      {sub === "entregas" && <Deliveries />}
      {sub === "fallidos" && <FailedMessages />}
    </>
  );
}

function EventLogs() {
  const [items, setItems] = useState<any[]>([]);
  const [action, setAction] = useState("");
  useEffect(() => {
    const params = action ? `?action=${encodeURIComponent(action)}` : "";
    api.get<any>(`/config/event-logs${params}`).then((d) => setItems(d.items)).catch(showError);
  }, [action]);
  return (
    <>
      <input placeholder="Filtrar por acción…" value={action} onChange={(e) => setAction(e.target.value)} style={{ marginBottom: 10 }} />
      <table>
        <thead><tr><th>Fecha</th><th>Actor</th><th>Acción</th><th>Entidad</th><th>Detalle</th></tr></thead>
        <tbody>
          {items.map((e) => (
            <tr key={e.id}>
              <td>{fmt(e.createdAt)}</td>
              <td>{e.actorType}</td>
              <td><code className="k">{e.action}</code></td>
              <td>{e.entityType ?? "—"}</td>
              <td><span className="muted">{JSON.stringify(e.metadata)}</span></td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

function Deliveries() {
  const [items, setItems] = useState<any[]>([]);
  const [onlyFailed, setOnlyFailed] = useState(false);
  const load = useCallback(() => {
    api.get<any>(`/config/webhook-deliveries?onlyFailed=${onlyFailed}`)
      .then((d) => setItems(d.items)).catch(showError);
  }, [onlyFailed]);
  useEffect(() => {
    load();
  }, [load]);
  return (
    <>
      <div style={{ marginBottom: 10 }}>
        <Switch checked={onlyFailed} onChange={setOnlyFailed} label="Solo fallidas" />
      </div>
      <table>
        <thead><tr><th>Fecha</th><th>Evento</th><th>Destino</th><th>Intentos</th><th>HTTP</th><th>Estado</th><th></th></tr></thead>
        <tbody>
          {items.map((d) => (
            <tr key={d.id}>
              <td>{fmt(d.createdAt)}</td>
              <td>{d.eventType}</td>
              <td style={{ maxWidth: 240, overflow: "hidden", textOverflow: "ellipsis" }}>{d.targetUrl}</td>
              <td>{d.attempt}</td>
              <td>{d.responseStatus ?? "—"}</td>
              <td>{d.succeeded ? <span className="pill green">ok</span> : <span className="pill red">pendiente</span>}</td>
              <td>{!d.succeeded && (
                <button onClick={async () => {
                  try { await api.post(`/config/webhook-deliveries/${d.id}/redeliver`); await alertDialog("Re-entrega encolada"); load(); } catch (e) { showError(e); }
                }}>Reintentar</button>
              )}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

function FailedMessages() {
  const [items, setItems] = useState<any[]>([]);
  const load = () => api.get<any>("/config/failed-messages").then((d) => setItems(d.items)).catch(showError);
  useEffect(() => {
    load();
  }, []);
  return (
    <table>
      <thead><tr><th>Fecha</th><th>Tipo</th><th>Texto</th><th>Error</th><th></th></tr></thead>
      <tbody>
        {items.map((m) => (
          <tr key={m.id}>
            <td>{fmt(m.createdAt)}</td>
            <td>{m.type}</td>
            <td>{m.body}</td>
            <td><span className="muted">{JSON.stringify(m.errorDetail)}</span></td>
            <td>
              <button onClick={async () => {
                try { await api.post(`/config/messages/${m.id}/requeue`); await alertDialog("Re-encolado"); load(); } catch (e) { showError(e); }
              }}>Re-encolar</button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
