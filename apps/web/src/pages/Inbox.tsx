/** Bandeja de conversaciones: lista + hilo + panel lateral (lead y notas).
 *  Tiempo real v1 por polling cada 5 s. */
import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, showError } from "../api";
import { useAuth } from "../auth";
import { Select } from "../ui/Select";
import { Switch } from "../ui/Switch";
import { confirmDialog, promptDialog } from "../ui/dialogs";
import { AudioPlayer } from "../ui/AudioPlayer";
import { AttachmentImage, AttachmentPdf } from "../ui/AttachmentPreview";
import { LeadFormDialog, type FieldDef, type LeadFormValues } from "../ui/LeadFormDialog";
import { TagChip, TagPicker, type TagT } from "../ui/TagPicker";

type Conv = {
  id: string;
  status: string;
  contact: { id: string; waId: string; profileName: string | null };
  account: { id: string; name: string; isTest: boolean };
  assignedUserId: string | null;
  lastMessageAt: string | null;
  lastMessagePreview: string;
  unreadCount: number;
  windowOpen: boolean;
  botPaused: boolean;
  leadId: string | null;
  tags: TagT[];
};

const VIEWS = [
  { key: "recent", label: "Recientes" },
  { key: "person", label: "Por persona" },
  { key: "tag", label: "Por tag" },
] as const;
type ViewKey = (typeof VIEWS)[number]["key"];
type Group = { key: string; label: string; color: string | null; items: Conv[] };

function groupConversations(convs: Conv[], view: ViewKey, users: { id: string; name: string }[]): Group[] | null {
  if (view === "recent") return null;
  if (view === "person") {
    const groups = new Map<string, Group>();
    const RESIDUAL = "￿";
    for (const c of convs) {
      const key = c.assignedUserId || RESIDUAL;
      if (!groups.has(key)) {
        const label = c.assignedUserId ? users.find((u) => u.id === c.assignedUserId)?.name || "…" : "Sin asignar";
        groups.set(key, { key, label, color: null, items: [] });
      }
      groups.get(key)!.items.push(c);
    }
    return [...groups.values()].sort((a, b) => a.key.localeCompare(b.key));
  }
  // view === "tag"
  const groups = new Map<string, Group>();
  const residual: Group = { key: "￿", label: "Sin etiqueta", color: null, items: [] };
  for (const c of convs) {
    if (c.tags.length === 0) {
      residual.items.push(c);
      continue;
    }
    for (const t of c.tags) {
      if (!groups.has(t.id)) groups.set(t.id, { key: t.id, label: t.name, color: t.color, items: [] });
      groups.get(t.id)!.items.push(c);
    }
  }
  const arr = [...groups.values()].sort((a, b) => a.label.localeCompare(b.label));
  if (residual.items.length) arr.push(residual);
  return arr;
}
type Msg = {
  id: string;
  direction: string;
  origin: string;
  type: string;
  body: string | null;
  status: string;
  createdAt: string;
  attachments: {
    id: string;
    mimeType: string;
    fileName: string | null;
    downloadStatus: string;
    transcript: string | null;
  }[];
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
  const [searchParams, setSearchParams] = useSearchParams();
  const [convs, setConvs] = useState<Conv[]>([]);
  const [filters, setFilters] = useState({ q: "", status: "", unread: false });
  const [selected, setSelected] = useState<Conv | null>(null);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [notes, setNotes] = useState<NoteT[]>([]);
  const [users, setUsers] = useState<UserLite[]>([]);
  const [pipelines, setPipelines] = useState<Pipeline[]>([]);
  const [customFields, setCustomFields] = useState<FieldDef[]>([]);
  const [text, setText] = useState("");
  const [noteText, setNoteText] = useState("");
  const [expandedAudio, setExpandedAudio] = useState<Set<string>>(new Set());
  const [showCreateLead, setShowCreateLead] = useState(false);
  const [showTest, setShowTest] = useState(false);
  const [view, setView] = useState<ViewKey>(() => (localStorage.getItem("crm-web:inbox:view") as ViewKey) || "recent");
  const [groupFilter, setGroupFilter] = useState<string | null>(() => {
    const v = (localStorage.getItem("crm-web:inbox:view") as ViewKey) || "recent";
    return v === "recent" ? null : localStorage.getItem(`crm-web:inbox:filter:${v}`);
  });
  const bottomRef = useRef<HTMLDivElement>(null);
  const selectedId = selected?.id ?? null;

  const changeView = (v: ViewKey) => {
    setView(v);
    localStorage.setItem("crm-web:inbox:view", v);
    setGroupFilter(v === "recent" ? null : localStorage.getItem(`crm-web:inbox:filter:${v}`));
  };
  const changeGroupFilter = (key: string | null) => {
    setGroupFilter(key);
    if (view === "recent") return;
    if (key) localStorage.setItem(`crm-web:inbox:filter:${view}`, key);
    else localStorage.removeItem(`crm-web:inbox:filter:${view}`);
  };

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
    if (can("leads:read")) {
      api.get<{ items: Pipeline[] }>("/pipelines").then((d) => setPipelines(d.items)).catch(() => {});
      api.get<{ items: FieldDef[] }>("/lead-field-definitions").then((d) => setCustomFields(d.items)).catch(() => {});
    }
  }, [can]);

  // Deep-link desde el detalle de un lead ("Ver conversación →", Leads.tsx):
  // ?conversationId=<id> selecciona el hilo apenas carga la lista, y limpia
  // el query param para que la URL quede prolija.
  useEffect(() => {
    const conversationId = searchParams.get("conversationId");
    if (!conversationId || convs.length === 0) return;
    const conv = convs.find((c) => c.id === conversationId);
    if (conv) open(conv);
    setSearchParams({}, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [convs, searchParams]);

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
    const body = await promptDialog({ title: "Editar nota", message: "Contenido:", defaultValue: n.body });
    if (body === null || body.trim() === "") return;
    try {
      await api.patch(`/notes/${n.id}`, { body: body.trim() });
      await loadThread();
    } catch (e) {
      showError(e);
    }
  };

  const deleteNote = async (n: NoteT) => {
    const ok = await confirmDialog({ title: "Borrar nota", message: "¿Borrar esta nota?", confirmLabel: "Borrar", danger: true });
    if (!ok) return;
    try {
      await api.del(`/notes/${n.id}`);
      await loadThread();
    } catch (e) {
      showError(e);
    }
  };

  const analyzeConversation = async (): Promise<Partial<LeadFormValues>> => {
    if (!selected) return {};
    try {
      const r = await api.post<{ title: string | null; company: string | null; notes: string | null; stageId: string | null }>(
        "/leads/analyze-conversation",
        { conversationId: selected.id },
      );
      const out: Partial<LeadFormValues> = {};
      if (r.title) out.title = r.title;
      if (r.company) out.company = r.company;
      if (r.notes) out.notes = r.notes;
      if (r.stageId) out.stageId = r.stageId;
      return out;
    } catch (e) {
      showError(e);
      throw e;
    }
  };

  const createLead = async (values: LeadFormValues) => {
    if (!selected) return;
    const attributes: Record<string, string> = { ...values.custom };
    if (values.company.trim()) attributes.company = values.company.trim();
    if (values.priority) attributes.priority = values.priority;
    try {
      await api.post("/leads", {
        conversationId: selected.id,
        title: values.title.trim(),
        stageId: values.stageId || undefined,
        value: values.value.trim() ? Number(values.value) : null,
        currency: values.currency,
        attributes,
      });
      if (values.notes.trim()) {
        await api.post(`/conversations/${selected.id}/notes`, { body: values.notes.trim() });
      }
      setShowCreateLead(false);
      await loadConvs();
    } catch (e) {
      showError(e);
      throw e;
    }
  };

  const bulkBotPause = async (paused: boolean) => {
    const ok = await confirmDialog({
      title: paused ? "Pausar todos los bots" : "Reanudar todos los bots",
      message: paused
        ? "Esto silencia el bot en TODAS las conversaciones (nadie va a recibir respuesta automática hasta que lo reactives)."
        : "Esto reactiva el bot en todas las conversaciones que estaban silenciadas.",
      confirmLabel: paused ? "Pausar todo" : "Reanudar todo",
      danger: paused,
    });
    if (!ok) return;
    try {
      await api.post("/conversations/bulk-bot-pause", { paused });
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

  const toggleBot = async () => {
    if (!selected) return;
    const next = !selected.botPaused;
    if (next && !selected.windowOpen) {
      const ok = await confirmDialog({
        title: "Silenciar bot",
        message:
          "Ventana de 24h cerrada: el cliente no escribió en las últimas 24h.\n" +
          "Si silenciás el bot NO vas a poder responder manualmente (WhatsApp solo " +
          "permite plantillas aprobadas fuera de la ventana) hasta que el cliente " +
          "vuelva a escribir.\n¿Silenciar igual?",
        confirmLabel: "Silenciar igual",
        danger: true,
      });
      if (!ok) return;
    }
    try {
      await api.patch(`/conversations/${selected.id}`, { botPaused: next });
      await loadConvs();
    } catch (e) {
      showError(e);
    }
  };

  const stages: StageT[] = pipelines.flatMap((p) => p.stages);

  const testCount = convs.filter((c) => c.account.isTest).length;
  const visibleConvs = showTest ? convs : convs.filter((c) => !c.account.isTest);
  const groups = groupConversations(visibleConvs, view, users);
  const activeGroup = groupFilter && groups?.some((g) => g.key === groupFilter) ? groupFilter : null;
  const shownGroups = groups ? (activeGroup ? groups.filter((g) => g.key === activeGroup) : groups) : null;

  const renderConvItem = (c: Conv, keyPrefix = "") => {
    const display = c.contact.profileName || c.contact.waId;
    return (
      <div
        key={`${keyPrefix}${c.id}`}
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
            {c.account.isTest && <span className="pill yellow">test</span>}
            {c.leadId && <span className="pill yellow">lead</span>}
          </div>
          {c.tags.length > 0 && (
            <div className="tag-row">
              {c.tags.map((t) => <TagChip key={t.id} tag={t} />)}
            </div>
          )}
        </div>
      </div>
    );
  };

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
          <Select
            style={{ width: 130 }}
            value={filters.status}
            onChange={(v) => setFilters({ ...filters, status: v })}
            options={[
              { value: "", label: "Todas" },
              { value: "open", label: "Abiertas" },
              { value: "pending", label: "Pendientes" },
              { value: "closed", label: "Cerradas" },
            ]}
          />
          <Switch
            checked={filters.unread}
            onChange={(v) => setFilters({ ...filters, unread: v })}
            label="No leídas"
          />
        </div>

        {(testCount > 0 || can("conversations:bulk_pause")) && (
          <div className="pane-head" style={{ borderTop: "none" }}>
            {testCount > 0 && (
              <button className={showTest ? "primary" : ""} onClick={() => setShowTest((v) => !v)}>
                {showTest ? "Ocultar cuentas de prueba" : `Mostrar cuentas de prueba (${testCount})`}
              </button>
            )}
            {can("conversations:bulk_pause") && (
              <>
                <div className="spacer" style={{ flex: 1 }} />
                <button className="btn-icon-label" title="Silenciar el bot en todas las conversaciones"
                        onClick={() => bulkBotPause(true)}>
                  ⏸ Pausar todos
                </button>
                <button className="btn-icon-label" title="Reactivar el bot en todas las conversaciones"
                        onClick={() => bulkBotPause(false)}>
                  ▶ Reanudar todos
                </button>
              </>
            )}
          </div>
        )}

        <div className="tabs" style={{ margin: "0 12px" }}>
          {VIEWS.map((v) => (
            <button key={v.key} className={view === v.key ? "on" : ""} onClick={() => changeView(v.key)}>
              {v.label}
            </button>
          ))}
        </div>

        {groups && groups.length > 0 && (
          <div className="group-filter">
            <button className={`group-chip ${!activeGroup ? "group-chip--active" : ""}`} onClick={() => changeGroupFilter(null)}>
              Todos <span className="group-chip__count">{visibleConvs.length}</span>
            </button>
            {groups.map((g) => (
              <button
                key={g.key}
                className={`group-chip ${activeGroup === g.key ? "group-chip--active" : ""}`}
                onClick={() => changeGroupFilter(g.key)}
              >
                {view === "tag" && <span className="group-chip__dot" style={{ background: g.color || "var(--text-muted)" }} />}
                {g.label} <span className="group-chip__count">{g.items.length}</span>
              </button>
            ))}
          </div>
        )}

        <div className="pane-body">
          {!shownGroups && visibleConvs.map((c) => renderConvItem(c))}
          {shownGroups && shownGroups.map((g) => (
            <div key={g.key}>
              {!activeGroup && (
                <div className="conv-group__header">
                  {view === "tag" && <span className="conv-group__dot" style={{ background: g.color || "var(--text-muted)" }} />}
                  {g.label} <span className="group-chip__count">{g.items.length}</span>
                </div>
              )}
              {g.items.map((c) => renderConvItem(c, `${g.key}:`))}
            </div>
          ))}
          {visibleConvs.length === 0 && (
            <p className="muted" style={{ padding: 16 }}>
              {convs.length === 0 ? "Sin conversaciones." : "No hay chats para mostrar."}
            </p>
          )}
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
              {selected.account.isTest && <span className="pill yellow">test</span>}
              {can("conversations:send") && (
                <button
                  onClick={toggleBot}
                  className={selected.botPaused ? "primary" : ""}
                  title={
                    selected.botPaused
                      ? "El bot no responde en esta conversación. Click para reactivarlo."
                      : "El bot responde automáticamente. Click para silenciarlo y responder vos."
                  }
                >
                  {selected.botPaused ? "🔇 Bot silenciado" : "🤖 Bot activo"}
                </button>
              )}
              <div className="spacer" style={{ flex: 1 }} />
              {can("conversations:assign") && (
                <>
                  <Select
                    style={{ width: 160 }}
                    value={selected.assignedUserId ?? ""}
                    onChange={assign}
                    options={[
                      { value: "", label: "Sin asignar" },
                      ...users.map((u) => ({ value: u.id, label: u.name })),
                    ]}
                  />
                  {selected.assignedUserId !== me?.id && (
                    <button onClick={() => assign(me!.id)} title="Asignarme esta conversación">Asignarme</button>
                  )}
                </>
              )}
              {can("conversations:close") && selected.status !== "closed" && (
                <button onClick={() => setStatus("closed")}>Cerrar</button>
              )}
              {selected.status === "closed" && <button onClick={() => setStatus("open")}>Reabrir</button>}
            </div>
            {can("conversations:tag") && (
              <div className="pane-head" style={{ borderTop: "none", paddingTop: 0 }}>
                {selected.tags.map((t) => <TagChip key={t.id} tag={t} />)}
                <TagPicker
                  conversationId={selected.id}
                  activeTags={selected.tags}
                  canManage={can("tags:manage")}
                  onChanged={loadConvs}
                />
              </div>
            )}
            <div className="msgs">
              {msgs.map((m) => (
                <div key={m.id} className={`bubble ${m.direction === "inbound" ? "in" : "out"}`}>
                  {m.body || <i>[{m.type}]</i>}
                  {m.attachments.map((a) =>
                    a.mimeType.startsWith("audio/") ? (
                      <div key={a.id} style={{ marginTop: 6 }}>
                        <div>
                          🎤 {a.transcript ?? <i className="muted">transcribiendo…</i>}
                        </div>
                        {a.downloadStatus === "done" && (
                          <>
                            {expandedAudio.has(a.id) ? (
                              <AudioPlayer autoPlay src={`/api/v1/attachments/${a.id}/download`} />
                            ) : (
                              <button
                                style={{ marginTop: 4, fontSize: "0.85em", padding: "2px 8px" }}
                                onClick={() =>
                                  setExpandedAudio((prev) => new Set(prev).add(a.id))
                                }
                              >
                                ▶ escuchar audio
                              </button>
                            )}
                          </>
                        )}
                      </div>
                    ) : a.downloadStatus !== "done" ? (
                      <div key={a.id} style={{ marginTop: 6 }}>
                        <span className="muted">📎 {a.mimeType} ({a.downloadStatus})</span>
                      </div>
                    ) : a.mimeType.startsWith("image/") ? (
                      <AttachmentImage key={a.id} id={a.id} fileName={a.fileName} />
                    ) : a.mimeType === "application/pdf" ? (
                      <AttachmentPdf key={a.id} id={a.id} fileName={a.fileName} />
                    ) : (
                      <div key={a.id} style={{ marginTop: 6 }}>
                        <a href={`/api/v1/attachments/${a.id}/download`} target="_blank" rel="noopener noreferrer">
                          📎 {a.fileName || a.mimeType}
                        </a>
                      </div>
                    )
                  )}
                  <div className="meta">
                    {m.direction === "outbound" &&
                      `${m.origin === "n8n" ? "n8n" : m.origin === "system" ? "auto" : "agente"} · ${m.status} · `}
                    {fmt(m.createdAt)}
                  </div>
                </div>
              ))}
              <div ref={bottomRef} />
            </div>
            {selected.botPaused && !selected.windowOpen && (
              <div className="bot-warning">
                ⚠ Bot silenciado y ventana de 24h cerrada: no se puede responder manualmente
                (solo plantillas vía n8n) hasta que el cliente vuelva a escribir.
              </div>
            )}
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
                <button onClick={() => setShowCreateLead(true)}>＋ Crear lead</button>
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
                    <span className="row" style={{ gap: 8 }}>
                      <a
                        href="#"
                        onClick={(e) => {
                          e.preventDefault();
                          editNote(n);
                        }}
                      >
                        editar
                      </a>
                      {(n.authorUserId === me?.id || can("notes:edit:any")) && (
                        <a
                          href="#"
                          onClick={(e) => {
                            e.preventDefault();
                            deleteNote(n);
                          }}
                        >
                          borrar
                        </a>
                      )}
                    </span>
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

      {showCreateLead && selected && (
        <LeadFormDialog
          mode="create"
          contact={selected.contact}
          stages={stages}
          initial={{
            title: `Lead ${selected.contact.profileName || selected.contact.waId}`,
            company: "",
            priority: "",
            stageId: stages[0]?.id ?? "",
            value: "",
            currency: "ARS",
            notes: "",
            custom: {},
          }}
          customFields={customFields}
          onAnalyze={can("leads:write") ? analyzeConversation : undefined}
          onCancel={() => setShowCreateLead(false)}
          onSubmit={createLead}
        />
      )}
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
        <Select
          style={{ width: "100%", marginTop: 8 }}
          value={lead.stageId}
          onChange={move}
          options={stages.map((s) => ({ value: s.id, label: s.name }))}
        />
      )}
    </div>
  );
}
