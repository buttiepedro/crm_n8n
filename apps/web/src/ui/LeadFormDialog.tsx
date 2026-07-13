import { useEffect, useState } from "react";
import { Select } from "./Select";

/** Dialog "Crear/Editar lead": mismo formulario en ambos modos.
 *  Crear se dispara desde una conversación (nombre/teléfono de contexto,
 *  de solo lectura); Editar se dispara desde el kanban con los valores
 *  actuales del lead precargados. */

export type FieldDef = {
  id: string;
  key: string;
  label: string;
  type: "text" | "number" | "date" | "select";
  options: string[] | null;
};

export type LeadFormValues = {
  title: string;
  company: string;
  priority: "" | "baja" | "media" | "alta";
  stageId: string;
  value: string;
  currency: string;
  notes: string;
  custom: Record<string, string>;
};

const PRIORITY_OPTIONS = [
  { value: "", label: "Sin definir" },
  { value: "baja", label: "Baja" },
  { value: "media", label: "Media" },
  { value: "alta", label: "Alta" },
];

const CloseIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
       strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <line x1="18" y1="6" x2="6" y2="18" />
    <line x1="6" y1="6" x2="18" y2="18" />
  </svg>
);
const SparkleIcon = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
       strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M18.4 5.6l-2.8 2.8M8.4 15.6l-2.8 2.8" />
  </svg>
);
const CheckIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4"
       strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <path d="M20 6L9 17l-5-5" />
  </svg>
);

export function LeadFormDialog({
  mode,
  contact,
  channelLabel = "whatsapp",
  stages,
  initial,
  customFields = [],
  onAnalyze,
  onCancel,
  onSubmit,
}: {
  mode: "create" | "edit";
  contact: { profileName: string | null; waId: string } | null;
  channelLabel?: string;
  stages: { id: string; name: string }[];
  initial: LeadFormValues;
  customFields?: FieldDef[];
  /** Solo tiene efecto en mode="create": analiza la conversación con IA y
   *  devuelve valores sugeridos para prellenar el form (el usuario revisa
   *  antes de guardar). */
  onAnalyze?: () => Promise<Partial<LeadFormValues>>;
  onCancel: () => void;
  onSubmit: (values: LeadFormValues) => Promise<void>;
}) {
  const [values, setValues] = useState<LeadFormValues>(initial);
  const [saving, setSaving] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [analyzed, setAnalyzed] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !saving) onCancel();
    };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [onCancel, saving]);

  const set = <K extends keyof LeadFormValues>(key: K, v: LeadFormValues[K]) =>
    setValues((s) => ({ ...s, [key]: v }));
  const setCustom = (key: string, v: string) =>
    setValues((s) => ({ ...s, custom: { ...s.custom, [key]: v } }));

  const analyze = async () => {
    if (!onAnalyze || analyzing) return;
    setAnalyzing(true);
    try {
      const suggested = await onAnalyze();
      setValues((s) => ({ ...s, ...suggested, custom: { ...s.custom, ...suggested.custom } }));
      setAnalyzed(true);
    } catch {
      // onAnalyze ya reportó el error (showError)
    } finally {
      setAnalyzing(false);
    }
  };

  const submit = async () => {
    if (!values.title.trim() || saving) return;
    setSaving(true);
    try {
      await onSubmit(values);
    } catch {
      // onSubmit ya reportó el error (showError); el dialog queda abierto para reintentar.
    } finally {
      setSaving(false);
    }
  };

  const name = contact?.profileName || contact?.waId || "—";

  return (
    <div className="dialog-backdrop" onMouseDown={(e) => e.target === e.currentTarget && !saving && onCancel()}>
      <div className="dialog-box lead-form-modal" role="dialog" aria-modal="true">
        <div className="lead-form-head">
          <h3 className="dialog-title">{mode === "create" ? "Crear lead desde conversación" : "Editar lead"}</h3>
          <button className="dialog-close" onClick={onCancel} aria-label="Cerrar" title="Cerrar" disabled={saving}>
            <CloseIcon />
          </button>
        </div>

        {contact && (
          <div className="lead-form-context">
            {mode === "create" ? "Conversación" : "Contacto"}: <strong>{name}</strong>
            {contact.waId && <span className="muted"> · +{contact.waId}</span>}
            <span className="muted"> · {channelLabel}</span>
          </div>
        )}

        <div className="lead-form-body">
          {mode === "create" && onAnalyze && (
            analyzed ? (
              <div className="ai-analyzed-note"><CheckIcon /> Campos prellenados por IA — revisá antes de guardar</div>
            ) : (
              <button type="button" className="ai-analyze-btn" disabled={analyzing} onClick={analyze}>
                <SparkleIcon /> {analyzing ? "Analizando conversación…" : "Analizar conversación con IA"}
              </button>
            )
          )}
        </div>

        <div className="lead-form-body form-grid">
          <label style={{ gridColumn: "1 / -1" }}>
            Título del lead
            <input value={values.title} onChange={(e) => set("title", e.target.value)} autoFocus />
          </label>

          <label>
            Empresa
            <input
              value={values.company}
              onChange={(e) => set("company", e.target.value)}
              placeholder="Opcional"
            />
          </label>
          <label>
            Prioridad
            <Select
              value={values.priority}
              onChange={(v) => set("priority", v as LeadFormValues["priority"])}
              options={PRIORITY_OPTIONS}
            />
          </label>

          <label>
            {mode === "create" ? "Etapa inicial" : "Etapa"}
            <Select value={values.stageId} onChange={(v) => set("stageId", v)} options={stages.map((s) => ({ value: s.id, label: s.name }))} />
          </label>
          <label>
            Valor esperado (opcional)
            <input
              type="number"
              inputMode="decimal"
              className="no-spinner"
              value={values.value}
              onChange={(e) => set("value", e.target.value)}
              placeholder="0"
            />
          </label>

          {customFields.map((f) => (
            <label key={f.id}>
              {f.label}
              {f.type === "select" ? (
                <Select
                  value={values.custom[f.key] ?? ""}
                  onChange={(v) => setCustom(f.key, v)}
                  options={(f.options ?? []).map((o) => ({ value: o, label: o }))}
                />
              ) : (
                <input
                  type={f.type === "number" ? "number" : f.type === "date" ? "date" : "text"}
                  value={values.custom[f.key] ?? ""}
                  onChange={(e) => setCustom(f.key, e.target.value)}
                />
              )}
            </label>
          ))}

          {mode === "create" && (
            <label style={{ gridColumn: "1 / -1" }}>
              Notas
              <textarea
                rows={3}
                style={{ resize: "vertical", fontFamily: "inherit" }}
                value={values.notes}
                onChange={(e) => set("notes", e.target.value)}
                placeholder="Contexto inicial del lead (opcional)"
              />
            </label>
          )}
        </div>

        <div className="dialog-actions">
          <button onClick={onCancel} disabled={saving}>Cancelar</button>
          <button className="primary" onClick={submit} disabled={saving || !values.title.trim()}>
            {saving ? "Guardando…" : mode === "create" ? "Crear lead" : "Guardar cambios"}
          </button>
        </div>
      </div>
    </div>
  );
}
