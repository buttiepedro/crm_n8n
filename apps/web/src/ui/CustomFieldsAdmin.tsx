import { useEffect, useState } from "react";
import { api, showError } from "../api";
import { confirmDialog } from "./dialogs";
import type { FieldDef } from "./LeadFormDialog";
import { Select } from "./Select";

const TrashIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
       strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <polyline points="3 6 5 6 21 6" />
    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
  </svg>
);
const CloseIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
       strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <line x1="18" y1="6" x2="6" y2="18" />
    <line x1="6" y1="6" x2="18" y2="18" />
  </svg>
);

const TYPE_OPTIONS = [
  { value: "text", label: "Texto" },
  { value: "number", label: "Número" },
  { value: "date", label: "Fecha" },
  { value: "select", label: "Lista (opciones)" },
];
const TYPE_LABEL: Record<string, string> = { text: "Texto", number: "Número", date: "Fecha", select: "Lista" };

/** Panel de admin para el catálogo de campos custom de lead (esquema): cada
 *  campo definido acá se renderiza solo en el form de alta/edición y en el
 *  detalle (ver LeadFormDialog.tsx / Leads.tsx). Los valores viven en
 *  lead.attributes[key] — esto solo define label/tipo. */
export function CustomFieldsAdmin({ onClose, onChanged }: { onClose: () => void; onChanged: () => void }) {
  const [fields, setFields] = useState<FieldDef[]>([]);
  const [loading, setLoading] = useState(true);
  const [label, setLabel] = useState("");
  const [type, setType] = useState<FieldDef["type"]>("text");
  const [optionsText, setOptionsText] = useState("");
  const [saving, setSaving] = useState(false);

  const load = () => {
    setLoading(true);
    api.get<{ items: FieldDef[] }>("/lead-field-definitions")
      .then((d) => setFields(d.items))
      .catch(showError)
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const create = async () => {
    if (!label.trim() || saving) return;
    setSaving(true);
    try {
      const options = type === "select"
        ? optionsText.split("\n").map((o) => o.trim()).filter(Boolean)
        : null;
      await api.post("/lead-field-definitions", { label: label.trim(), type, options });
      setLabel("");
      setOptionsText("");
      setType("text");
      load();
      onChanged();
    } catch (e) {
      showError(e);
    } finally {
      setSaving(false);
    }
  };

  const remove = async (f: FieldDef) => {
    const ok = await confirmDialog({
      title: "Borrar campo",
      message: `¿Borrar el campo "${f.label}"? Los valores ya guardados en leads existentes no se borran, pero dejan de mostrarse con este label.`,
      confirmLabel: "Borrar",
      danger: true,
    });
    if (!ok) return;
    try {
      await api.del(`/lead-field-definitions/${f.id}`);
      load();
      onChanged();
    } catch (e) {
      showError(e);
    }
  };

  return (
    <div className="dialog-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="dialog-box fields-admin-modal" role="dialog" aria-modal="true">
        <div className="lead-form-head">
          <h3 className="dialog-title">Campos custom de lead</h3>
          <button className="dialog-close" onClick={onClose} aria-label="Cerrar" title="Cerrar">
            <CloseIcon />
          </button>
        </div>

        <div className="field-def-list">
          {loading && <p className="muted">Cargando…</p>}
          {!loading && fields.length === 0 && (
            <p className="field-def-empty">Sin campos custom todavía. Se suman al form de alta/edición de leads.</p>
          )}
          {fields.map((f) => (
            <div key={f.id} className="field-def-row">
              <span className="field-def-label">{f.label}</span>
              <span className="field-def-type">{TYPE_LABEL[f.type] ?? f.type}</span>
              <button className="icon-btn" onClick={() => remove(f)} title="Borrar campo" aria-label={`Borrar ${f.label}`}>
                <TrashIcon />
              </button>
            </div>
          ))}
        </div>

        <div className="field-def-new form-grid">
          <label>
            Nombre del campo
            <input
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="Ej: Cantidad de empleados"
              autoFocus
            />
          </label>
          <label>
            Tipo
            <Select value={type} onChange={(v) => setType(v as FieldDef["type"])} options={TYPE_OPTIONS} />
          </label>
          {type === "select" && (
            <label>
              Opciones (una por línea)
              <textarea
                rows={3}
                style={{ resize: "vertical", fontFamily: "inherit" }}
                value={optionsText}
                onChange={(e) => setOptionsText(e.target.value)}
                placeholder={"Opción A\nOpción B"}
              />
            </label>
          )}
          <button className="primary" disabled={saving || !label.trim()} onClick={create}>
            {saving ? "Creando…" : "Agregar campo"}
          </button>
        </div>
      </div>
    </div>
  );
}
