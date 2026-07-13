import { useState } from "react";
import { createPortal } from "react-dom";

/** Adjuntos ricos para el hilo del chat: imagen con lightbox a pantalla
 *  completa y PDF con preview inline (iframe togglable). Misma URL de
 *  descarga que ya usaba el link plano — cookie de sesión same-origin, sin
 *  necesidad de fetch+blob. */

const CloseIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
       strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <line x1="18" y1="6" x2="6" y2="18" />
    <line x1="6" y1="6" x2="18" y2="18" />
  </svg>
);
const FileIcon = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
       strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
    <polyline points="14 2 14 8 20 8" />
  </svg>
);
const ChevronIcon = ({ open }: { open: boolean }) => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4"
       strokeLinecap="round" strokeLinejoin="round" aria-hidden
       style={{ transform: open ? "rotate(180deg)" : undefined, transition: "transform .15s" }}>
    <path d="M6 9l6 6 6-6" />
  </svg>
);

export function AttachmentImage({ id, fileName }: { id: string; fileName: string | null }) {
  const [lightbox, setLightbox] = useState(false);
  const src = `/api/v1/attachments/${id}/download`;
  return (
    <>
      <img
        src={src}
        alt={fileName || "imagen adjunta"}
        className="att-img-thumb"
        onClick={() => setLightbox(true)}
      />
      {lightbox &&
        createPortal(
          <div className="dialog-backdrop" onMouseDown={(e) => e.target === e.currentTarget && setLightbox(false)}>
            <div className="lightbox-content">
              <img src={src} alt={fileName || "imagen adjunta"} />
            </div>
            <button className="icon-btn lightbox-close" onClick={() => setLightbox(false)} aria-label="Cerrar">
              <CloseIcon />
            </button>
          </div>,
          document.body,
        )}
    </>
  );
}

export function AttachmentPdf({ id, fileName }: { id: string; fileName: string | null }) {
  const [open, setOpen] = useState(false);
  const src = `/api/v1/attachments/${id}/download`;
  return (
    <div className="att-pdf">
      <button type="button" className="att-pdf__bar" style={{ width: "100%" }} onClick={() => setOpen((o) => !o)}>
        <FileIcon />
        <span className="att-pdf__name">{fileName || "documento.pdf"}</span>
        <ChevronIcon open={open} />
      </button>
      {open && <iframe src={src} className="att-pdf__frame" title={fileName || "PDF"} />}
    </div>
  );
}
