/** Embudo de leads: kanban por pipeline con etapas configurables. */
import { useCallback, useEffect, useState } from "react";
import { api, showError } from "../api";
import { useAuth } from "../auth";
import { Select } from "../ui/Select";
import { confirmDialog, promptDialog } from "../ui/dialogs";

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
  contact: { profileName: string | null; waId: string } | null;
  conversationId: string | null;
};

export default function Leads() {
  const { can } = useAuth();
  const [pipelines, setPipelines] = useState<Pipeline[]>([]);
  const [pipelineId, setPipelineId] = useState<string>("");
  const [leads, setLeads] = useState<Lead[]>([]);
  const [q, setQ] = useState("");
  const [expandedNotes, setExpandedNotes] = useState<Record<string, boolean>>({});

  const toggleNotes = (leadId: string) =>
    setExpandedNotes((prev) => ({ ...prev, [leadId]: !prev[leadId] }));

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

  const move = async (lead: Lead, stageId: string) => {
    try {
      await api.patch(`/leads/${lead.id}/stage`, { stageId });
      await load();
    } catch (e) {
      showError(e);
    }
  };

  const editLead = async (lead: Lead) => {
    const title = await promptDialog({ title: "Editar lead", message: "Título:", defaultValue: lead.title });
    if (title === null) return;
    const valueStr = await promptDialog({
      title: "Editar lead",
      message: "Valor (vacío = sin valor):",
      defaultValue: lead.value?.toString() ?? "",
    });
    if (valueStr === null) return;
    try {
      await api.patch(`/leads/${lead.id}`, {
        title: title.trim() || undefined,
        value: valueStr.trim() ? Number(valueStr) : null,
      });
      await load();
    } catch (e) {
      showError(e);
    }
  };

  const removeLead = async (lead: Lead) => {
    const ok = await confirmDialog({
      title: "Borrar lead",
      message: `¿Borrar el lead "${lead.title}"?`,
      confirmLabel: "Borrar",
      danger: true,
    });
    if (!ok) return;
    try {
      await api.del(`/leads/${lead.id}`);
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
        {can("pipelines:manage") && <button onClick={addStage}>＋ Etapa</button>}
      </div>

      <div className="kanban">
        {pipeline?.stages.map((s) => (
          <div className="kcol" key={s.id}>
            <h4>
              <span>
                {s.name} <span className="muted">({s.leadCount})</span>
              </span>
              {can("pipelines:manage") && (
                <span>
                  <a href="#" onClick={(e) => { e.preventDefault(); renameStage(s); }}>✎</a>{" "}
                  <a href="#" onClick={(e) => { e.preventDefault(); deleteStage(s); }}>🗑</a>
                </span>
              )}
            </h4>
            {s.totalValue > 0 && (
              <div className="muted" style={{ marginBottom: 6, fontSize: 12 }}>
                Σ {s.totalValue.toLocaleString()}
              </div>
            )}
            {leads
              .filter((l) => l.stageId === s.id)
              .map((l) => (
                <div className="kcard" key={l.id}>
                  <div className="t">{l.title}</div>
                  <div className="sub">
                    {l.contact?.profileName || l.contact?.waId}
                    {l.value != null && ` · ${l.currency} ${Number(l.value).toLocaleString()}`}
                    {l.source === "n8n_webhook" && " · n8n"}
                  </div>
                  {l.notes.length > 0 && (
                    <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
                      <div>{l.notes[0]}</div>
                      {l.notes.length > 1 && expandedNotes[l.id] && (
                        <div style={{ marginTop: 2 }}>
                          {l.notes.slice(1).map((n, i) => (
                            <div key={i} style={{ marginTop: 2 }}>
                              {n}
                            </div>
                          ))}
                        </div>
                      )}
                      {l.notes.length > 1 && (
                        <a
                          href="#"
                          style={{ display: "block", marginTop: 2 }}
                          onClick={(e) => {
                            e.preventDefault();
                            toggleNotes(l.id);
                          }}
                        >
                          {expandedNotes[l.id] ? "Ver menos" : `+${l.notes.length - 1} más`}
                        </a>
                      )}
                    </div>
                  )}
                  {can("leads:move_stage") && (
                    <Select
                      style={{ width: "100%", marginTop: 8 }}
                      value={l.stageId}
                      onChange={(v) => move(l, v)}
                      options={pipeline.stages.map((x) => ({ value: x.id, label: x.name }))}
                    />
                  )}
                  <div className="row" style={{ marginTop: 6, gap: 4 }}>
                    {can("leads:write") && <button onClick={() => editLead(l)}>Editar</button>}
                    {can("leads:delete") && (
                      <button className="danger" onClick={() => removeLead(l)}>
                        Borrar
                      </button>
                    )}
                  </div>
                </div>
              ))}
          </div>
        ))}
      </div>
    </div>
  );
}
