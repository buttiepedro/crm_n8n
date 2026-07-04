/** Bandeja de conversaciones: lista + hilo + panel lateral (lead y notas).
 *  Tiempo real v1 por polling cada 5 s. */
import { useCallback, useEffect, useRef, useState } from "react";
import { api, showError } from "../api";
import { useAuth } from "../auth";

type Conv = {
  id: string;
  status: string;
  contact: { id: string; waId: string; profileName: string | null };
  account: { id: string; name: string };
  assignedUserId: string | null;
  lastMessageAt: string | null;
  lastMessagePreview: string;
  unreadCount: number;
  windowOpen: boolean;
  leadId: string | null;
};
type Msg = {
  id: string;
  direction: string;
  origin: string;
  type: string;
  body: string | null;
  status: string;
  createdAt: string;
  attachments: { id: string; mimeType: string; fileName: string | null; downloadStatus: string }[];
};
type NoteT = {
  id: string;
  body: string;
  authorSource: string;
  authorUserId: string | null;
  updatedAt: string;
};
type UserLite = { id: string; name: string };
type Pipeline = { id: string; name: string; isDefault: boolean; stages: StageT[] };
type StageT = { id: string; name: string; isTerminal: boolean };

const fmt = (iso: string | null) => (iso ? new Date(iso).toLocaleString() : "");

export default function Inbox() {
  const { me, can } = useAuth();
  const [convs, setConvs] = useState<Conv[]>([]);
  const [filters, setFilters] = useState({ q: "", status: "", unread: false });
  const [selected, setSelected] = useState<Conv | null>(null);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [notes, setNotes] = useState<NoteT[]>([]);
  const [users, setUsers] = useState<UserLite[]>([]);
  const [pipelines, setPipelines] = useState<Pipeline[]>([]);
  const [text, setText] = useState("");
  const [noteText, setNoteText] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);
  const selectedId = selected?.id ?? null;

  const loadConvs = useCallback(async () => {
    const params = new URLSearchParams();
    if (filters.q) params.set("q", filters.q);
    if (filters.status) params.set("status", filters.status);
    if (filters.unread) params.set("unread", "true");
    try {
      const data = await api.get<{ items: Conv[] }>(`/conversations?${params}`);
      setConvs(data.items);
      if (selectedId) {
        const fresh = data.items.find((c) => c.id === selectedId);
        if (fresh) setSelected(fresh);
      }
    } catch {
      /* polling: silenciar */
    }
  }, [filters, selectedId]);

  const loadThread = useCallback(async () => {
    if (!selectedId) return;
    try {
      const [m, n] = await Promise.all([
        api.get<{ items: Msg[] }>(`/conversations/${selectedId}/messages`),
        api.get<{ items: NoteT[] }>(`/conversations/${selectedId}/notes`),
      ]);
      setMsgs(m.items);
      setNotes(n.items);
    } catch {
      /* polling */
    }
  }, [selectedId]);

  useEffect(() => {
    loadConvs();
    const t = setInterval(loadConvs, 5000);
    return () => clearInterval(t);
  }, [loadConvs]);

  useEffect(() => {
    loadThread();
    const t = setInterval(loadThread, 5000);
    return () => clearInterval(t);
  }, [loadThread]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView();
  }, [msgs.length]);

  useEffect(() => {
    api.get<{ items: UserLite[] }>("/users").then((d) => setUsers(d.items)).catch(() => {});
    if (can("leads:read"))
      api.get<{ items: Pipeline[] }>("/pipelines").then((d) => setPipelines(d.items)).catch(() => {});
  }, [can]);

  const open = async (c: Conv) => {
    setSelected(c);
    setMsgs([]);
    setNotes([]);
    if (c.unreadCount > 0) api.post(`/conversations/${c.id}/read`).catch(() => {});
  };

  const send = async () => {
    if (!selected || !text.trim()) return;
    try {
      await api.post(`/conversations/${selected.id}/messages`, {
        type: "text",
        body: text.trim(),
      });
      setText("");
      await loadThread();
    } catch (e) {
      showError(e);
    }
  };

  const addNote = async () => {
    if (!selected || !noteText.trim()) return;
    try {
      await api.post(`/conversations/${selected.id}/notes`, { body: noteText.trim() });
      setNoteText("");
      await loadThread();
    } catch (e) {
      showError(e);
    }
  };

  const editNote = async (n: NoteT) => {
    const body = window.prompt("Editar nota:", n.body);
    if (body === null || body.trim() === "") return;
    try {
      await api.patch(`/notes/${n.id}`, { body: body.trim() });
      await loadThread();
    } catch (e) {
      showError(e);
    }
  };

  const createLead = async () => {
    if (!selected) return;
    try {
      await api.post("/leads", { conversationId: selected.id });
      await loadConvs();
    } catch (e) {
      showError(e);
    }
  };

  const assign = async (userId: string) => {
    if (!selected) return;
    try {
      await api.patch(`/conversations/${selected.id}`, userId ? { assignedUserId: userId } : { unassign: true });
      await loadConvs();
    } catch (e) {
      showError(e);
    }
  };

  const setStatus = async (status: string) => {
    if (!selected) return;
    try {
      await api.patch(`/conversations/${selected.id}`, { status });
      await loadConvs();
    } catch (e) {
      showError(e);
    }
  };

  const stages: StageT[] = pipelines.flatMap((p) => p.stages);

  return (
    <div className="inbox">
      {/* Lista */}
      <div className="pane">
        <div className="pane-head">
          <input
            style={{ flex: 1, minWidth: 120 }}
            placeholder="Buscar contacto…"
            value={filters.q}
            onChange={(e) => setFilters({ ...filters, q: e.target.value })}
          />
          <select
            value={filters.status}
            onChange={(e) => setFilters({ ...filters, status: e.target.value })}
          >
            <option value="">Todas</option>
            <option value="open">Abiertas</option>
            <option value="pending">Pendientes</option>
            <option value="closed">Cerradas</option>
          </select>
          <label style={{ fontSize: 12 }}>
            <input
              type="checkbox"
              checked={filters.unread}
              onChange={(e) => setFilters({ ...filters, unread: e.target.checked })}
            />{" "}
            No leídas
          </label>
        </div>
        <div className="pane-body">
          {convs.map((c) => {
            const display = c.contact.profileName || c.contact.waId;
            return (
              <div
                key={c.id}
                className={`conv-item ${selectedId === c.id ? "selected" : ""}`}
                onClick={() => open(c)}
              >
                <div className="conv-avatar" aria-hidden>
                  {display.charAt(0).toUpperCase()}
                </div>
                <div className="conv-main">
                  <div className="top">
                    <span className="name">{display}</span>
                    {c.unreadCount > 0 && <span className="badge">{c.unreadCount}</span>}
                  </div>
                  <div className="preview">{c.lastMessagePreview || "—"}</div>
                  <div className="row" style={{ marginTop: 5, gap: 4 }}>
                    <span className="pill">{c.account.name}</span>
                    <span className={`pill ${c.windowOpen ? "green" : "red"}`}>
                      {c.windowOpen ? "24h abierta" : "24h cerrada"}
                    </span>
                    {c.leadId && <span className="pill yellow">lead</span>}
                  </div>
                </div>
              </div>
            );
          })}
          {convs.length === 0 && <p className="muted" style={{ padding: 16 }}>Sin conversaciones.</p>}
        </div>
      </div>

      {/* Hilo */}
      <div className="thread">
        {!selected ? (
          <div style={{ margin: "auto" }} className="muted">
            Elegí una conversación
          </div>
        ) : (
          <>
            <div className="pane-head">
              <strong>{selected.contact.profileName || selected.contact.waId}</strong>
              <span className="muted">+{selected.contact.waId}</span>
              <span className="pill">{selected.status}</span>
              <div className="spacer" style={{ flex: 1 }} />
              {can("conversations:assign") && (
                <select value={selected.assignedUserId ?? ""} onChange={(e) => assign(e.target.value)}>
                  <option value="">Sin asignar</option>
                  {users.map((u) => (
                    <option key={u.id} value={u.id}>
                      {u.name}
                    </option>
                  ))}
                </select>
              )}
              {can("conversations:close") && selected.status !== "closed" && (
                <button onClick={() => setStatus("closed")}>Cerrar</button>
              )}
              {selected.status === "closed" && <button onClick={() => setStatus("open")}>Reabrir</button>}
            </div>
            <div className="msgs">
              {msgs.map((m) => (
                <div key={m.id} className={`bubble ${m.direction === "inbound" ? "in" : "out"}`}>
                  {m.body || <i>[{m.type}]</i>}
                  {m.attachments.map((a) => (
                    <div key={a.id} style={{ marginTop: 6 }}>
                      {a.downloadStatus === "done" ? (
                        <a href={`/api/v1/attachments/${a.id}/download`} target="_blank" rel="noopener noreferrer">
                          📎 {a.fileName || a.mimeType}
                        </a>
                      ) : (
                        <span className="muted">📎 {a.mimeType} ({a.downloadStatus})</span>
                      )}
                    </div>
                  ))}
                  <div className="meta">
                    {m.direction === "outbound" && `${m.origin === "n8n" ? "n8n" : "agente"} · ${m.status} · `}
                    {fmt(m.createdAt)}
                  </div>
                </div>
              ))}
              <div ref={bottomRef} />
            </div>
            <div className="composer">
              <textarea
                placeholder={
                  selected.windowOpen
                    ? "Escribí un mensaje… (Enter para enviar)"
                    : "Ventana de 24h cerrada: solo plantillas (vía n8n) hasta que el cliente escriba"
                }
                disabled={!selected.windowOpen || !can("conversations:send")}
                value={text}
                onChange={(e) => setText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    send();
                  }
                }}
              />
              <button className="primary" onClick={send} disabled={!selected.windowOpen || !text.trim()}>
                Enviar
              </button>
            </div>
          </>
        )}
      </div>

      {/* Panel lateral */}
      <div className="side">
        {selected && (
          <>
            <div>
              <h4>Lead</h4>
              {selected.leadId ? (
                <LeadBox leadId={selected.leadId} stages={stages} onChanged={loadConvs} />
              ) : can("leads:write") ? (
                <button onClick={createLead}>＋ Crear lead</button>
              ) : (
                <span className="muted">Sin lead</span>
              )}
            </div>
            <div>
              <h4>Notas internas</h4>
              {notes.map((n) => (
                <div key={n.id} className="note">
                  {n.body}
                  <div className="meta">
                    <span>{n.authorSource === "n8n_webhook" ? "n8n" : n.authorUserId === me?.id ? "vos" : "equipo"}</span>
                    <a
                      href="#"
                      onClick={(e) => {
                        e.preventDefault();
                        editNote(n);
                      }}
                    >
                      editar
                    </a>
                  </div>
                </div>
              ))}
              {can("notes:write") && (
                <div className="row" style={{ marginTop: 6 }}>
                  <input
                    style={{ flex: 1 }}
                    placeholder="Nueva nota…"
                    value={noteText}
                    onChange={(e) => setNoteText(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && addNote()}
                  />
                  <button onClick={addNote}>＋</button>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function LeadBox({ leadId, stages, onChanged }: { leadId: string; stages: StageT[]; onChanged: () => void }) {
  const { can } = useAuth();
  const [lead, setLead] = useState<any>(null);

  useEffect(() => {
    api.get(`/leads/${leadId}`).then(setLead).catch(() => {});
  }, [leadId]);

  if (!lead) return <span className="muted">…</span>;

  const move = async (stageId: string) => {
    try {
      await api.patch(`/leads/${leadId}/stage`, { stageId });
      setLead(await api.get(`/leads/${leadId}`));
      onChanged();
    } catch (e) {
      showError(e);
    }
  };

  return (
    <div className="card" style={{ padding: 12 }}>
      <div style={{ fontWeight: 600, fontSize: 14 }}>{lead.title}</div>
      {lead.value != null && (
        <div className="muted">
          {lead.currency} {Number(lead.value).toLocaleString()}
        </div>
      )}
      {can("leads:move_stage") && (
        <select style={{ width: "100%", marginTop: 8 }} value={lead.stageId} onChange={(e) => move(e.target.value)}>
          {stages.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
      )}
    </div>
  );
}
