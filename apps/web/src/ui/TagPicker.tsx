import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api, showError } from "../api";

export type TagT = { id: string; color: string; name: string };

// Misma paleta de respaldo que STAGE_COLORS en Leads.tsx — coherencia visual
// entre "etapa" y "tag" como los dos sistemas de color-coding de la app.
const SWATCHES = ["#6366f1", "#0ea5e9", "#10b981", "#f59e0b", "#ec4899", "#8b5cf6", "#14b8a6", "#ef4444"];

const PlusIcon = () => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"
       strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <line x1="12" y1="5" x2="12" y2="19" />
    <line x1="5" y1="12" x2="19" y2="12" />
  </svg>
);
const XIcon = () => (
  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"
       strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <line x1="18" y1="6" x2="6" y2="18" />
    <line x1="6" y1="6" x2="18" y2="18" />
  </svg>
);
const CheckIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4"
       strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <path d="M20 6L9 17l-5-5" />
  </svg>
);

export function TagChip({ tag, onRemove }: { tag: TagT; onRemove?: () => void }) {
  return (
    <span className="tag-chip">
      <span className="tag-chip__dot" style={{ "--tag-color": tag.color } as React.CSSProperties} />
      {tag.name}
      {onRemove && (
        <button type="button" className="tag-chip__remove" onClick={onRemove} aria-label={`Sacar tag ${tag.name}`}>
          <XIcon />
        </button>
      )}
    </span>
  );
}

/** Popover para taggear una conversación: elegir de las existentes o crear una
 *  nueva (nombre + color). Portal a <body>, mismo criterio de posición que
 *  ui/Select.tsx (no se comparte el hook por ser el único otro caso hoy). */
export function TagPicker({
  conversationId,
  activeTags,
  canManage,
  onChanged,
}: {
  conversationId: string;
  activeTags: TagT[];
  canManage: boolean;
  onChanged: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [allTags, setAllTags] = useState<TagT[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [newColor, setNewColor] = useState(SWATCHES[0]);
  const [busy, setBusy] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);

  const activeIds = new Set(activeTags.map((t) => t.id));

  useEffect(() => {
    if (!open || loaded) return;
    api.get<{ items: TagT[] }>("/tags").then((d) => setAllTags(d.items)).catch(showError).finally(() => setLoaded(true));
  }, [open, loaded]);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      const t = e.target as Node;
      if (triggerRef.current?.contains(t) || popoverRef.current?.contains(t)) return;
      setOpen(false);
    };
    const onEsc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onEsc);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onEsc);
    };
  }, [open]);

  useLayoutEffect(() => {
    if (!open) return;
    const r = triggerRef.current?.getBoundingClientRect();
    if (r) setPos({ top: r.bottom + 6, left: r.left });
  }, [open]);

  const toggleTag = async (tag: TagT) => {
    if (busy) return;
    setBusy(true);
    try {
      if (activeIds.has(tag.id)) {
        await api.del(`/conversations/${conversationId}/tags/${tag.id}`);
      } else {
        await api.post(`/conversations/${conversationId}/tags`, { tagId: tag.id });
      }
      onChanged();
    } catch (e) {
      showError(e);
    } finally {
      setBusy(false);
    }
  };

  const createAndAttach = async () => {
    if (!newName.trim() || busy) return;
    setBusy(true);
    try {
      const tag = await api.post<TagT>("/tags", { name: newName.trim(), color: newColor });
      setAllTags((ts) => [...ts, tag].sort((a, b) => a.name.localeCompare(b.name)));
      await api.post(`/conversations/${conversationId}/tags`, { tagId: tag.id });
      setNewName("");
      setCreating(false);
      onChanged();
    } catch (e) {
      showError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        className="tag-add-btn"
        onClick={() => setOpen((o) => !o)}
      >
        <PlusIcon /> Tag
      </button>
      {open && pos &&
        createPortal(
          <div
            ref={popoverRef}
            className="ui-popover tag-picker-popover"
            style={{ position: "fixed", top: pos.top, left: pos.left }}
          >
            <div className="tag-picker-list">
              {!loaded && <div className="tag-picker-empty">Cargando…</div>}
              {loaded && allTags.length === 0 && <div className="tag-picker-empty">Sin tags todavía.</div>}
              {allTags.map((tag) => (
                <div key={tag.id} className={`tag-picker-item ${activeIds.has(tag.id) ? "checked" : ""}`}
                     onClick={() => toggleTag(tag)}>
                  <span className="tag-chip__dot" style={{ "--tag-color": tag.color } as React.CSSProperties} />
                  <span>{tag.name}</span>
                  {activeIds.has(tag.id) && <span className="check-space"><CheckIcon /></span>}
                </div>
              ))}
            </div>
            {canManage && (
              creating ? (
                <div className="tag-picker-new">
                  <input
                    autoFocus
                    placeholder="Nombre del tag"
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && createAndAttach()}
                  />
                  <div className="tag-swatches">
                    {SWATCHES.map((c) => (
                      <button
                        key={c}
                        type="button"
                        className={`tag-swatch ${newColor === c ? "selected" : ""}`}
                        style={{ background: c }}
                        onClick={() => setNewColor(c)}
                        aria-label={`Color ${c}`}
                      />
                    ))}
                  </div>
                  <button className="primary" disabled={busy || !newName.trim()} onClick={createAndAttach}>
                    Crear y agregar
                  </button>
                </div>
              ) : (
                <button
                  type="button"
                  style={{ width: "100%", display: "flex", justifyContent: "center", gap: 5, marginTop: 6 }}
                  onClick={() => setCreating(true)}
                >
                  <PlusIcon /> Nuevo tag
                </button>
              )
            )}
          </div>,
          document.body,
        )}
    </>
  );
}
