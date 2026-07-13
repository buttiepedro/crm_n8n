/** Embudo de leads: kanban por pipeline con etapas configurables. */
import { useCallback, useEffect, useMemo, useState, type CSSProperties } from "react";
import { api, showError } from "../api";
import { useAuth } from "../auth";
import { Select } from "../ui/Select";
import { confirmDialog, promptDialog } from "../ui/dialogs";
import { LeadFormDialog, type LeadFormValues } from "../ui/LeadFormDialog";

const ICON = { width: 14, height: 14, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 2, strokeLinecap: "round", strokeLinejoin: "round" } as const;

const PencilIcon = () => (
  <svg {...ICON} aria-hidden>
    <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5z" />
  </svg>
);
const TrashIcon = () => (
  <svg {...ICON} aria-hidden>
    <polyline points="3 6 5 6 21 6" />
    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
    <line x1="10" y1="11" x2="10" y2="17" />
    <line x1="14" y1="11" x2="14" y2="17" />
  </svg>
);
const PlusIcon = () => (
  <svg {...ICON} aria-hidden>
    <line x1="12" y1="5" x2="12" y2="19" />
    <line x1="5" y1="12" x2="19" y2="12" />
  </svg>
);
const CloseIcon = () => (
  <svg {...ICON} aria-hidden>
    <line x1="18" y1="6" x2="6" y2="18" />
    <line x1="6" y1="6" x2="18" y2="18" />
  </svg>
);

type Stage = {
  id: string;
  name: string;
  position: number;
  color: string | null;
  isTerminal: boolean;
  outcome: string | null;
  leadCount: number;
  totalValue: number;
};
type Pipeline = { id: string; name: string; isDefault: boolean; stages: Stage[] };
type Lead = {
  id: string;
  title: string;
  notes: string[];
  value: number | null;
  currency: string | null;
  stageId: string;
  source: string;
  attributes: Record<string, unknown>;
  contact: { profileName: string | null; waId: string } | null;
  conversationId: string | null;
};
type LeadHistoryEvent = { fromStageId: string | null; toStageId: string; movedBy: string; at: string };
type LeadNote = { id: string; body: string; authorSource: string; updatedAt: string };
type LeadDetail = Omit<Lead, "notes"> & {
  ownerUserId: string | null;
  createdAt: string;
  updatedAt: string;
  externalKey: string | null;
  history: LeadHistoryEvent[];
  notes: LeadNote[];
};

/* Forma mínima que comparten Lead (lista) y LeadDetail (modal) para las
 * acciones — evita acoplar move/editLead/removeLead al shape de notas. */
type LeadRef = { id: string; title: string; value: number | null; stageId: string };

/* Paleta de respaldo cuando la etapa no tiene color asignado */
const STAGE_COLORS = ["#6366f1", "#0ea5e9", "#10b981", "#f59e0b", "#ec4899", "#8b5cf6", "#14b8a6", "#ef4444"];

function getCompany(attrs: Record<string, unknown> | undefined): string | null {
  const v = attrs?.company ?? attrs?.empresa ?? attrs?.Company ?? attrs?.Empresa;
  return typeof v === "string" && v.trim() ? v.trim() : null;
}

function getPriority(attrs: Record<string, unknown> | undefined): "" | "baja" | "media" | "alta" {
  const v = attrs?.priority;
  return v === "baja" || v === "media" || v === "alta" ? v : "";
}

const PRIORITY_PILL_CLASS: Record<string, string> = { alta: "pill red", media: "pill yellow", baja: "pill" };
const PRIORITY_LABEL: Record<string, string> = { alta: "Alta", media: "Media", baja: "Baja" };

function formatDate(iso: string) {
  return new Date(iso).toLocaleString("es-AR", {
    day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

function movedByLabel(movedBy: string) {
  if (movedBy.startsWith("webhook:")) return "n8n";
  if (movedBy.startsWith("user:")) return "Usuario";
  return movedBy;
}

function authorLabel(source: string) {
  return source === "n8n_webhook" ? "n8n" : "Usuario";
}

export default function Leads() {
  const { can } = useAuth();
  const [pipelines, setPipelines] = useState<Pipeline[]>([]);
  const [pipelineId, setPipelineId] = useState<string>("");
  const [leads, setLeads] = useState<Lead[]>([]);
  const [q, setQ] = useState("");
  const [dragLead, setDragLead] = useState<Lead | null>(null);
  const [overStage, setOverStage] = useState<string | null>(null);
  const [detail, setDetail] = useState<LeadDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [editingLead, setEditingLead] = useState<LeadDetail | null>(null);

  const load = useCallback(async () => {
    try {
      const p = await api.get<{ items: Pipeline[] }>("/pipelines");
      setPipelines(p.items);
      const current = pipelineId || p.items.find((x) => x.isDefault)?.id || p.items[0]?.id || "";
      if (!pipelineId && current) setPipelineId(current);
      if (current) {
        const params = new URLSearchParams({ pipelineId: current });
        if (q) params.set("q", q);
        const l = await api.get<{ items: Lead[] }>(`/leads?${params}`);
        setLeads(l.items);
      }
    } catch (e) {
      showError(e);
    }
  }, [pipelineId, q]);

  useEffect(() => {
    load();
  }, [load]);

  const pipeline = pipelines.find((p) => p.id === pipelineId);

  // Color estable por etapa: el propio (config) o uno de la paleta de respaldo
  // por posición — se reutiliza en la columna y en el recorrido del modal.
  const stageColorMap = useMemo(() => {
    const map: Record<string, string> = {};
    pipeline?.stages.forEach((s, i) => {
      map[s.id] = s.color || STAGE_COLORS[i % STAGE_COLORS.length];
    });
    return map;
  }, [pipeline]);

  const move = async (lead: LeadRef, stageId: string) => {
    if (lead.stageId === stageId) return;
    // Optimista: la tarjeta cambia de columna al instante; se revierte si el PATCH falla.
    const prev = leads;
    setLeads((ls) => ls.map((x) => (x.id === lead.id ? { ...x, stageId } : x)));
    setDetail((d) => (d && d.id === lead.id ? { ...d, stageId } : d));
    try {
      await api.patch(`/leads/${lead.id}/stage`, { stageId });
      await load();
    } catch (e) {
      setLeads(prev);
      setDetail((d) => (d && d.id === lead.id ? { ...d, stageId: lead.stageId } : d));
      showError(e);
    }
  };

  const canDrag = can("leads:move_stage");

  const onDrop = (stageId: string) => {
    if (dragLead) move(dragLead, stageId);
    setDragLead(null);
    setOverStage(null);
  };

  const openLead = async (lead: Lead) => {
    setDetailLoading(true);
    try {
      const full = await api.get<LeadDetail>(`/leads/${lead.id}`);
      setDetail(full);
    } catch (e) {
      showError(e);
    } finally {
      setDetailLoading(false);
    }
  };

  const closeDetail = () => setDetail(null);

  const startEdit = (lead: LeadDetail) => {
    setEditingLead(lead);
    closeDetail();
  };

  const saveLeadEdit = async (values: LeadFormValues) => {
    if (!editingLead) return;
    const attributes: Record<string, string> = { company: values.company.trim(), priority: values.priority };
    try {
      await api.patch(`/leads/${editingLead.id}`, {
        title: values.title.trim(),
        value: values.value.trim() ? Number(values.value) : null,
        currency: values.currency,
        attributes,
      });
      if (values.stageId !== editingLead.stageId) {
        await move(editingLead, values.stageId);
      }
      setEditingLead(null);
      await load();
    } catch (e) {
      showError(e);
      throw e;
    }
  };

  const removeLead = async (lead: LeadRef) => {
    const ok = await confirmDialog({
      title: "Borrar lead",
      message: `¿Borrar el lead "${lead.title}"?`,
      confirmLabel: "Borrar",
      danger: true,
    });
    if (!ok) return;
    try {
      await api.del(`/leads/${lead.id}`);
      if (detail && detail.id === lead.id) closeDetail();
      await load();
    } catch (e) {
      showError(e);
    }
  };

  const addStage = async () => {
    const name = await promptDialog({ title: "Nueva etapa", message: "Nombre de la nueva etapa:" });
    if (!name?.trim() || !pipelineId) return;
    try {
      await api.post(`/pipelines/${pipelineId}/stages`, { name: name.trim() });
      await load();
    } catch (e) {
      showError(e);
    }
  };

  const renameStage = async (s: Stage) => {
    const name = await promptDialog({ title: "Renombrar etapa", message: "Nuevo nombre:", defaultValue: s.name });
    if (!name?.trim()) return;
    try {
      await api.patch(`/stages/${s.id}`, {
        name: name.trim(),
        color: s.color,
        isTerminal: s.isTerminal,
        outcome: s.outcome,
      });
      await load();
    } catch (e) {
      showError(e);
    }
  };

  const deleteStage = async (s: Stage) => {
    if (!pipeline) return;
    let target = "";
    if (s.leadCount > 0) {
      const others = pipeline.stages.filter((x) => x.id !== s.id);
      const names = others.map((x, i) => `${i + 1}. ${x.name}`).join("\n");
      const pick = await promptDialog({
        title: "Eliminar etapa",
        message: `La etapa tiene ${s.leadCount} leads. ¿A qué etapa moverlos?\n${names}\n(número)`,
      });
      if (!pick) return;
      const idx = Number(pick) - 1;
      if (!others[idx]) return;
      target = `?moveLeadsToStageId=${others[idx].id}`;
    } else {
      const ok = await confirmDialog({
        title: "Eliminar etapa",
        message: `¿Eliminar la etapa "${s.name}"?`,
        confirmLabel: "Eliminar",
        danger: true,
      });
      if (!ok) return;
    }
    try {
      await api.del(`/stages/${s.id}${target}`);
      await load();
    } catch (e) {
      showError(e);
    }
  };

  return (
    <div className="page" style={{ maxWidth: "none" }}>
      <h2>Leads</h2>
      <div className="row" style={{ marginBottom: 16 }}>
        <Select
          style={{ width: 220 }}
          value={pipelineId}
          onChange={setPipelineId}
          options={pipelines.map((p) => ({ value: p.id, label: `${p.name}${p.isDefault ? " ★" : ""}` }))}
        />
        <input placeholder="Buscar…" value={q} onChange={(e) => setQ(e.target.value)} />
        {can("pipelines:manage") && (
          <button className="btn-icon-label" onClick={addStage}>
            <PlusIcon /> Etapa
          </button>
        )}
      </div>

      <div className="kanban">
        {pipeline?.stages.map((s, si) => {
          const stageLeads = leads.filter((l) => l.stageId === s.id);
          const total = stageLeads.reduce((acc, l) => acc + (l.value != null ? Number(l.value) : 0), 0);
          const color = stageColorMap[s.id] || STAGE_COLORS[si % STAGE_COLORS.length];
          const isOver = overStage === s.id && dragLead != null && dragLead.stageId !== s.id;
          return (
            <div
              className={`kcol${isOver ? " drag-over" : ""}`}
              key={s.id}
              style={{ "--stage-color": color } as CSSProperties}
              onDragOver={(e) => {
                if (!dragLead) return;
                e.preventDefault();
                e.dataTransfer.dropEffect = "move";
                if (overStage !== s.id) setOverStage(s.id);
              }}
              onDragLeave={(e) => {
                if (!e.currentTarget.contains(e.relatedTarget as Node)) setOverStage(null);
              }}
              onDrop={(e) => {
                e.preventDefault();
                onDrop(s.id);
              }}
            >
              <div className="kcol-rail" />
              <h4>
                <span className="kcol-title">
                  <i className="kcol-dot" />
                  {s.name}
                  <span className="kcol-count">{stageLeads.length}</span>
                </span>
                {can("pipelines:manage") && (
                  <span className="kcol-actions">
                    <button title="Renombrar etapa" aria-label="Renombrar etapa" onClick={() => renameStage(s)}>
                      <PencilIcon />
                    </button>
                    <button title="Eliminar etapa" aria-label="Eliminar etapa" onClick={() => deleteStage(s)}>
                      <TrashIcon />
                    </button>
                  </span>
                )}
              </h4>
              {total > 0 && <div className="kcol-sum">Σ {total.toLocaleString()}</div>}
              <div className="kcol-body">
                {stageLeads.map((l) => {
                  const name = l.contact?.profileName || l.contact?.waId || l.title;
                  const company = getCompany(l.attributes);
                  const priority = getPriority(l.attributes);
                  return (
                    <div
                      className={`kcard${dragLead?.id === l.id ? " dragging" : ""}`}
                      key={l.id}
                      draggable={canDrag}
                      role="button"
                      tabIndex={0}
                      onClick={() => openLead(l)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          openLead(l);
                        }
                      }}
                      onDragStart={(e) => {
                        e.dataTransfer.setData("text/plain", l.id);
                        e.dataTransfer.effectAllowed = "move";
                        setDragLead(l);
                      }}
                      onDragEnd={() => {
                        setDragLead(null);
                        setOverStage(null);
                      }}
                    >
                      <div className="kcard-head">
                        <div className="kcard-avatar" aria-hidden>
                          {name.charAt(0).toUpperCase()}
                        </div>
                        <div className="kcard-id">
                          <div className="t">{name}</div>
                          {l.contact?.waId && <div className="kcard-phone">+{l.contact.waId}</div>}
                        </div>
                      </div>
                      {company && <div className="kcard-company">{company}</div>}
                      {(l.value != null || l.source === "n8n_webhook" || priority) && (
                        <div className="kcard-foot">
                          {l.value != null && (
                            <span className="kcard-value">
                              {l.currency} {Number(l.value).toLocaleString()}
                            </span>
                          )}
                          {priority && <span className={PRIORITY_PILL_CLASS[priority]}>{PRIORITY_LABEL[priority]}</span>}
                          {l.source === "n8n_webhook" && <span className="pill">n8n</span>}
                        </div>
                      )}
                    </div>
                  );
                })}
                {isOver && <div className="kcol-drop-hint">Soltar aquí</div>}
                {stageLeads.length === 0 && !isOver && (
                  <div className="kcol-empty">{canDrag ? "Arrastra leads aquí" : "Sin leads"}</div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {(detail || detailLoading) && (
        <LeadDetailModal
          lead={detail}
          loading={detailLoading}
          stageColorMap={stageColorMap}
          stages={pipeline?.stages ?? []}
          canMoveStage={canDrag}
          canEdit={can("leads:write")}
          canDelete={can("leads:delete")}
          onClose={closeDetail}
          onMoveStage={(stageId) => detail && move(detail, stageId)}
          onEdit={() => detail && startEdit(detail)}
          onDelete={() => detail && removeLead(detail)}
        />
      )}

      {editingLead && (
        <LeadFormDialog
          mode="edit"
          contact={editingLead.contact}
          stages={pipeline?.stages ?? []}
          initial={{
            title: editingLead.title,
            company: getCompany(editingLead.attributes) ?? "",
            priority: getPriority(editingLead.attributes),
            stageId: editingLead.stageId,
            value: editingLead.value != null ? String(editingLead.value) : "",
            currency: editingLead.currency ?? "ARS",
            notes: "",
          }}
          onCancel={() => setEditingLead(null)}
          onSubmit={saveLeadEdit}
        />
      )}
    </div>
  );
}

function LeadDetailModal({
  lead,
  loading,
  stageColorMap,
  stages,
  canMoveStage,
  canEdit,
  canDelete,
  onClose,
  onMoveStage,
  onEdit,
  onDelete,
}: {
  lead: LeadDetail | null;
  loading: boolean;
  stageColorMap: Record<string, string>;
  stages: Stage[];
  canMoveStage: boolean;
  canEdit: boolean;
  canDelete: boolean;
  onClose: () => void;
  onMoveStage: (stageId: string) => void;
  onEdit: () => void;
  onDelete: () => void;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [onClose]);

  const name = lead?.contact?.profileName || lead?.contact?.waId || lead?.title || "";
  const company = getCompany(lead?.attributes);
  const priority = getPriority(lead?.attributes);
  const currentStageColor = lead ? stageColorMap[lead.stageId] : undefined;
  const HIDDEN_ATTR_KEYS = ["company", "empresa", "Company", "Empresa", "priority"];
  const extraAttrs = lead
    ? Object.entries(lead.attributes).filter(
        ([k, v]) => !HIDDEN_ATTR_KEYS.includes(k) && v != null && v !== ""
      )
    : [];

  return (
    <div className="dialog-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="dialog-box lead-modal" role="dialog" aria-modal="true">
        {loading || !lead ? (
          <div className="lead-modal-loading muted">Cargando…</div>
        ) : (
          <>
            <div className="lead-modal-head">
              <div className="kcard-avatar lead-modal-avatar" aria-hidden>
                {name.charAt(0).toUpperCase()}
              </div>
              <div className="lead-modal-id">
                <h3 className="dialog-title">{name}</h3>
                <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
                  {lead.contact?.waId && <span className="kcard-phone">+{lead.contact.waId}</span>}
                  {company && <span className="pill">{company}</span>}
                  {priority && <span className={PRIORITY_PILL_CLASS[priority]}>{PRIORITY_LABEL[priority]}</span>}
                  {lead.value != null && (
                    <span className="pill green">
                      {lead.currency} {Number(lead.value).toLocaleString()}
                    </span>
                  )}
                  <span
                    className="pill pill-stage"
                    style={{ "--stage-color": currentStageColor } as CSSProperties}
                  >
                    {stages.find((s) => s.id === lead.stageId)?.name ?? "—"}
                  </span>
                </div>
              </div>
              <button className="dialog-close" onClick={onClose} aria-label="Cerrar" title="Cerrar">
                <CloseIcon />
              </button>
            </div>

            <div className="lead-modal-body">
              {canMoveStage && (
                <section className="lead-modal-section">
                  <h4>Etapa</h4>
                  <Select
                    style={{ width: "100%" }}
                    value={lead.stageId}
                    onChange={onMoveStage}
                    options={stages.map((x) => ({ value: x.id, label: x.name }))}
                  />
                </section>
              )}

              <section className="lead-modal-section">
                <h4>Recorrido</h4>
                {lead.history.length === 0 ? (
                  <p className="muted">Sin movimientos registrados.</p>
                ) : (
                  <ul className="lead-timeline">
                    {lead.history.map((ev, i) => (
                      <li key={i} className="lead-timeline-item">
                        <span
                          className="lead-timeline-dot"
                          style={{ background: stageColorMap[ev.toStageId] ?? "var(--color-primary)" }}
                        />
                        <div className="lead-timeline-main">
                          <span className="lead-timeline-stage">
                            {stages.find((s) => s.id === ev.toStageId)?.name ?? "—"}
                          </span>
                          <span className="muted"> · {movedByLabel(ev.movedBy)} · {formatDate(ev.at)}</span>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </section>

              <section className="lead-modal-section">
                <h4>Notas</h4>
                {lead.notes.length === 0 ? (
                  <p className="muted">Sin notas.</p>
                ) : (
                  lead.notes.map((n) => (
                    <div className="note" key={n.id}>
                      <div>{n.body}</div>
                      <div className="meta">
                        <span>{authorLabel(n.authorSource)}</span>
                        <span>{formatDate(n.updatedAt)}</span>
                      </div>
                    </div>
                  ))
                )}
              </section>

              <section className="lead-modal-section">
                <h4>Detalle</h4>
                <div className="lead-detail-grid">
                  <div><span className="muted">Fuente</span><div>{lead.source === "n8n_webhook" ? "n8n" : "Manual"}</div></div>
                  <div><span className="muted">Creado</span><div>{formatDate(lead.createdAt)}</div></div>
                  <div><span className="muted">Actualizado</span><div>{formatDate(lead.updatedAt)}</div></div>
                  {lead.externalKey && (
                    <div><span className="muted">Clave externa</span><div><code className="k">{lead.externalKey}</code></div></div>
                  )}
                  {extraAttrs.map(([k, v]) => (
                    <div key={k}>
                      <span className="muted">{k}</span>
                      <div>{String(v)}</div>
                    </div>
                  ))}
                </div>
              </section>
            </div>

            <div className="dialog-actions">
              {canEdit && (
                <button className="btn-icon-label" onClick={onEdit}>
                  <PencilIcon /> Editar
                </button>
              )}
              {canDelete && (
                <button className="btn-icon-label danger" onClick={onDelete}>
                  <TrashIcon /> Borrar
                </button>
              )}
              <button className="primary" onClick={onClose}>Cerrar</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
