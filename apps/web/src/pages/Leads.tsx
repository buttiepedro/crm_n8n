/** Embudo de leads: kanban por pipeline con etapas configurables. */
import { useCallback, useEffect, useMemo, useState, type CSSProperties } from "react";
import { useNavigate } from "react-router-dom";
import { api, showError } from "../api";
import { useAuth } from "../auth";
import { CustomFieldsAdmin } from "../ui/CustomFieldsAdmin";
import { Select } from "../ui/Select";
import { Switch } from "../ui/Switch";
import { confirmDialog, promptDialog } from "../ui/dialogs";
import { LeadFormDialog, type FieldDef, type LeadFormValues } from "../ui/LeadFormDialog";

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
const UserIcon = () => (
  <svg {...ICON} aria-hidden>
    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
    <circle cx="12" cy="7" r="4" />
  </svg>
);
const ArchiveIcon = () => (
  <svg {...ICON} aria-hidden>
    <polyline points="21 8 21 21 3 21 3 8" />
    <rect x="1" y="3" width="22" height="5" />
    <line x1="10" y1="12" x2="14" y2="12" />
  </svg>
);
const UnarchiveIcon = () => (
  <svg {...ICON} aria-hidden>
    <polyline points="21 8 21 21 3 21 3 8" />
    <rect x="1" y="3" width="22" height="5" />
    <polyline points="9 15 12 12 15 15" />
    <line x1="12" y1="12" x2="12" y2="19" />
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
type UserLite = { id: string; name: string };
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
  ownerUserId: string | null;
  archivedAt: string | null;
};
type LeadHistoryEvent = { fromStageId: string | null; toStageId: string; movedBy: string; at: string };
type LeadNote = { id: string; body: string; authorSource: string; updatedAt: string };
type LeadDetail = Omit<Lead, "notes"> & {
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

function authorLabel(source: string) {
  return source === "n8n_webhook" ? "n8n" : "Usuario";
}

export default function Leads() {
  const { can, me } = useAuth();
  const navigate = useNavigate();
  const [pipelines, setPipelines] = useState<Pipeline[]>([]);
  const [pipelineId, setPipelineId] = useState<string>("");
  const [leads, setLeads] = useState<Lead[]>([]);
  const [q, setQ] = useState("");
  const [dragLead, setDragLead] = useState<Lead | null>(null);
  const [overStage, setOverStage] = useState<string | null>(null);
  const [detail, setDetail] = useState<LeadDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [editingLead, setEditingLead] = useState<LeadDetail | null>(null);
  const [users, setUsers] = useState<UserLite[]>([]);
  const [customFields, setCustomFields] = useState<FieldDef[]>([]);
  const [ownerFilter, setOwnerFilter] = useState<string | null>(null);
  const [showFieldsAdmin, setShowFieldsAdmin] = useState(false);
  const [showArchived, setShowArchived] = useState(false);

  const loadCustomFields = useCallback(() => {
    api.get<{ items: FieldDef[] }>("/lead-field-definitions").then((d) => setCustomFields(d.items)).catch(() => {});
  }, []);

  useEffect(() => {
    api.get<{ items: UserLite[] }>("/users").then((d) => setUsers(d.items)).catch(() => {});
    loadCustomFields();
  }, [loadCustomFields]);

  const load = useCallback(async () => {
    try {
      const p = await api.get<{ items: Pipeline[] }>("/pipelines");
      setPipelines(p.items);
      const current = pipelineId || p.items.find((x) => x.isDefault)?.id || p.items[0]?.id || "";
      if (!pipelineId && current) setPipelineId(current);
      if (current) {
        const params = new URLSearchParams({ pipelineId: current });
        if (q) params.set("q", q);
        if (showArchived) params.set("includeArchived", "true");
        const l = await api.get<{ items: Lead[] }>(`/leads?${params}`);
        setLeads(l.items);
      }
    } catch (e) {
      showError(e);
    }
  }, [pipelineId, q, showArchived]);

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

  const NO_OWNER = "__none__";
  const ownerName = (id: string | null) => (id ? users.find((u) => u.id === id)?.name || "…" : null);
  // Grupos por dueño derivados de los leads cargados: solo aparece quien tiene
  // leads; "Sin dueño" va último. La selección recordada cae a "Todos" si
  // quedó sin leads (mismo criterio que el filtro por etapa).
  const ownerGroups = useMemo(() => {
    const counts = new Map<string, number>();
    for (const l of leads) counts.set(l.ownerUserId || NO_OWNER, (counts.get(l.ownerUserId || NO_OWNER) || 0) + 1);
    const arr = [...counts.entries()]
      .filter(([k]) => k !== NO_OWNER)
      .map(([k, n]) => ({ key: k, label: ownerName(k) || "…", count: n }))
      .sort((a, b) => a.label.localeCompare(b.label));
    if (counts.has(NO_OWNER)) arr.push({ key: NO_OWNER, label: "Sin dueño", count: counts.get(NO_OWNER)! });
    return arr;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [leads, users]);
  const activeOwner = ownerFilter && ownerGroups.some((g) => g.key === ownerFilter) ? ownerFilter : null;
  const visibleLeads = activeOwner
    ? leads.filter((l) => (l.ownerUserId || NO_OWNER) === activeOwner)
    : leads;

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
  const canWrite = can("leads:write");

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
    const attributes: Record<string, string> = { ...values.custom, company: values.company.trim(), priority: values.priority };
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

  const assignOwner = async (leadId: string, ownerUserId: string) => {
    try {
      await api.patch(`/leads/${leadId}`, { ownerUserId: ownerUserId || null });
      setDetail((d) => (d && d.id === leadId ? { ...d, ownerUserId: ownerUserId || null } : d));
      await load();
    } catch (e) {
      showError(e);
    }
  };

  const goToConversation = (conversationId: string) => {
    navigate(`/?conversationId=${conversationId}`);
  };

  const setArchived = async (lead: LeadRef, archived: boolean) => {
    try {
      await api.patch(`/leads/${lead.id}/archive`, { archived });
      if (detail && detail.id === lead.id) {
        if (archived && !showArchived) closeDetail();
        else setDetail((d) => (d && d.id === lead.id ? { ...d, archivedAt: archived ? new Date().toISOString() : null } : d));
      }
      await load();
    } catch (e) {
      showError(e);
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
        <Switch checked={showArchived} onChange={setShowArchived} label="Mostrar archivados" />
        {can("pipelines:manage") && (
          <button className="btn-icon-label" onClick={addStage}>
            <PlusIcon /> Etapa
          </button>
        )}
        {can("pipelines:manage") && (
          <button className="btn-icon-label" onClick={() => setShowFieldsAdmin(true)}>
            ⚙ Campos
          </button>
        )}
      </div>

      {ownerGroups.length > 0 && (
        <div className="group-filter" style={{ padding: "0 0 16px", border: "none" }}>
          <button className={`group-chip ${!activeOwner ? "group-chip--active" : ""}`} onClick={() => setOwnerFilter(null)}>
            Todos <span className="group-chip__count">{leads.length}</span>
          </button>
          {ownerGroups.map((g) => (
            <button
              key={g.key}
              className={`group-chip ${activeOwner === g.key ? "group-chip--active" : ""}`}
              onClick={() => setOwnerFilter(g.key)}
            >
              {g.label} <span className="group-chip__count">{g.count}</span>
            </button>
          ))}
        </div>
      )}

      <div className="kanban">
        {pipeline?.stages.map((s, si) => {
          const stageLeads = visibleLeads.filter((l) => l.stageId === s.id);
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
                  const archived = !!l.archivedAt;
                  return (
                    <div
                      className={`kcard${dragLead?.id === l.id ? " dragging" : ""}${archived ? " kcard-archived" : ""}`}
                      key={l.id}
                      draggable={canDrag && !archived}
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
                        {canWrite && archived && (
                          <button
                            className="kcard-archive-btn" title="Desarchivar" aria-label="Desarchivar"
                            onClick={(e) => { e.stopPropagation(); setArchived(l, false); }}
                          >
                            <UnarchiveIcon />
                          </button>
                        )}
                        {canWrite && !archived && s.isTerminal && (
                          <button
                            className="kcard-archive-btn" title="Archivar" aria-label="Archivar"
                            onClick={(e) => { e.stopPropagation(); setArchived(l, true); }}
                          >
                            <ArchiveIcon />
                          </button>
                        )}
                      </div>
                      {archived && <div className="pill kcard-archived-pill">Archivado</div>}
                      {company && <div className="kcard-company">{company}</div>}
                      {(l.value != null || l.source === "n8n_webhook" || priority || l.ownerUserId) && (
                        <div className="kcard-foot">
                          {l.value != null && (
                            <span className="kcard-value">
                              {l.currency} {Number(l.value).toLocaleString()}
                            </span>
                          )}
                          {priority && <span className={PRIORITY_PILL_CLASS[priority]}>{PRIORITY_LABEL[priority]}</span>}
                          {l.source === "n8n_webhook" && <span className="pill">n8n</span>}
                          {l.ownerUserId && (
                            <span className="pill pill-owner"><UserIcon /> {ownerName(l.ownerUserId)}</span>
                          )}
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
          users={users}
          customFields={customFields}
          meId={me?.id ?? null}
          canMoveStage={canDrag}
          canEdit={canWrite}
          canDelete={can("leads:delete")}
          onClose={closeDetail}
          onMoveStage={(stageId) => detail && move(detail, stageId)}
          onEdit={() => detail && startEdit(detail)}
          onDelete={() => detail && removeLead(detail)}
          onAssignOwner={(userId) => detail && assignOwner(detail.id, userId)}
          onSetArchived={(archived) => detail && setArchived(detail, archived)}
          onGoToConversation={goToConversation}
        />
      )}

      {editingLead && (
        <LeadFormDialog
          mode="edit"
          contact={editingLead.contact}
          stages={pipeline?.stages ?? []}
          customFields={customFields}
          initial={{
            title: editingLead.title,
            company: getCompany(editingLead.attributes) ?? "",
            priority: getPriority(editingLead.attributes),
            stageId: editingLead.stageId,
            value: editingLead.value != null ? String(editingLead.value) : "",
            currency: editingLead.currency ?? "ARS",
            notes: "",
            custom: Object.fromEntries(
              customFields.map((f) => [f.key, String(editingLead.attributes[f.key] ?? "")]),
            ),
          }}
          onCancel={() => setEditingLead(null)}
          onSubmit={saveLeadEdit}
        />
      )}

      {showFieldsAdmin && (
        <CustomFieldsAdmin onClose={() => setShowFieldsAdmin(false)} onChanged={loadCustomFields} />
      )}
    </div>
  );
}

function LeadDetailModal({
  lead,
  loading,
  stageColorMap,
  stages,
  users,
  customFields,
  meId,
  canMoveStage,
  canEdit,
  canDelete,
  onClose,
  onMoveStage,
  onEdit,
  onDelete,
  onAssignOwner,
  onSetArchived,
  onGoToConversation,
}: {
  lead: LeadDetail | null;
  loading: boolean;
  stageColorMap: Record<string, string>;
  stages: Stage[];
  users: UserLite[];
  customFields: FieldDef[];
  meId: string | null;
  canMoveStage: boolean;
  canEdit: boolean;
  canDelete: boolean;
  onClose: () => void;
  onMoveStage: (stageId: string) => void;
  onEdit: () => void;
  onDelete: () => void;
  onAssignOwner: (userId: string) => void;
  onSetArchived: (archived: boolean) => void;
  onGoToConversation: (conversationId: string) => void;
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
  const archived = !!lead?.archivedAt;
  const isTerminalStage = lead ? stages.find((s) => s.id === lead.stageId)?.isTerminal ?? false : false;
  const HIDDEN_ATTR_KEYS = ["company", "empresa", "Company", "Empresa", "priority"];
  const fieldLabel = (key: string) => customFields.find((f) => f.key === key)?.label ?? key;
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
                  {archived && <span className="pill">Archivado</span>}
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

              {canEdit && (
                <section className="lead-modal-section">
                  <h4>Dueño</h4>
                  <div className="row" style={{ gap: 6 }}>
                    <Select
                      style={{ flex: 1 }}
                      value={lead.ownerUserId ?? ""}
                      onChange={onAssignOwner}
                      options={[{ value: "", label: "Sin dueño" }, ...users.map((u) => ({ value: u.id, label: u.name }))]}
                    />
                    {lead.ownerUserId !== meId && (
                      <button onClick={() => onAssignOwner(meId!)} title="Asignarme este lead">Asignarme</button>
                    )}
                  </div>
                </section>
              )}

              {lead.conversationId && (
                <section className="lead-modal-section">
                  <button className="btn-icon-label" onClick={() => onGoToConversation(lead.conversationId!)}>
                    Ver conversación →
                  </button>
                </section>
              )}

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
                      <span className="muted">{fieldLabel(k)}</span>
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
              {canEdit && archived && (
                <button className="btn-icon-label" onClick={() => onSetArchived(false)}>
                  <UnarchiveIcon /> Desarchivar
                </button>
              )}
              {canEdit && !archived && isTerminalStage && (
                <button className="btn-icon-label" onClick={() => onSetArchived(true)}>
                  <ArchiveIcon /> Archivar
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
