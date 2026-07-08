import { useEffect, useRef, useState } from "react";

/** Reemplazo custom de window.confirm/prompt/alert: mismo modelo (Promise),
 *  pero con el diseño de la app. Se invoca fuera de React (ver api.ts) a
 *  través de un singleton que el <DialogHost/> registra al montarse. */

export type ConfirmOpts = { title?: string; message: string; confirmLabel?: string; cancelLabel?: string; danger?: boolean };
export type PromptOpts = { title?: string; message?: string; defaultValue?: string; placeholder?: string; password?: boolean; confirmLabel?: string; cancelLabel?: string };
export type AlertOpts = { title?: string; message: string; okLabel?: string; danger?: boolean };

type Req =
  | { kind: "confirm"; opts: ConfirmOpts; resolve: (v: boolean) => void }
  | { kind: "prompt"; opts: PromptOpts; resolve: (v: string | null) => void }
  | { kind: "alert"; opts: AlertOpts; resolve: () => void };

let push: ((r: Req) => void) | null = null;

export function confirmDialog(opts: ConfirmOpts | string): Promise<boolean> {
  const o: ConfirmOpts = typeof opts === "string" ? { message: opts } : opts;
  return new Promise((resolve) => {
    if (push) push({ kind: "confirm", opts: o, resolve });
    else resolve(window.confirm(o.message));
  });
}

export function promptDialog(opts: PromptOpts | string): Promise<string | null> {
  const o: PromptOpts = typeof opts === "string" ? { message: opts } : opts;
  return new Promise((resolve) => {
    if (push) push({ kind: "prompt", opts: o, resolve });
    else resolve(window.prompt(o.message ?? "", o.defaultValue));
  });
}

export function alertDialog(opts: AlertOpts | string): Promise<void> {
  const o: AlertOpts = typeof opts === "string" ? { message: opts } : opts;
  return new Promise((resolve) => {
    if (push) push({ kind: "alert", opts: o, resolve });
    else {
      window.alert(o.message);
      resolve();
    }
  });
}

const WarnIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
    <line x1="12" y1="9" x2="12" y2="13" />
    <line x1="12" y1="17" x2="12.01" y2="17" />
  </svg>
);
const InfoIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <circle cx="12" cy="12" r="9" />
    <line x1="12" y1="11" x2="12" y2="16" />
    <line x1="12" y1="8" x2="12.01" y2="8" />
  </svg>
);

/** Montar una sola vez en la raíz de la app (ver main.tsx). */
export function DialogHost() {
  const [req, setReq] = useState<Req | null>(null);
  const [value, setValue] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const primaryRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    push = (r) => setReq(r);
    return () => {
      push = null;
    };
  }, []);

  useEffect(() => {
    if (req?.kind === "prompt") setValue(req.opts.defaultValue ?? "");
  }, [req]);

  useEffect(() => {
    if (!req) return;
    document.body.style.overflow = "hidden";
    const t = setTimeout(() => {
      if (req.kind === "prompt") inputRef.current?.focus();
      else primaryRef.current?.focus();
    }, 0);
    return () => {
      document.body.style.overflow = "";
      clearTimeout(t);
    };
  }, [req]);

  if (!req) return null;

  const cancel = () => {
    if (req.kind === "confirm") req.resolve(false);
    else if (req.kind === "prompt") req.resolve(null);
    else req.resolve();
    setReq(null);
  };
  const submit = () => {
    if (req.kind === "confirm") req.resolve(true);
    else if (req.kind === "prompt") req.resolve(value);
    else req.resolve();
    setReq(null);
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      e.preventDefault();
      cancel();
    } else if (e.key === "Enter") {
      e.preventDefault();
      submit();
    }
  };

  const danger = !!(req.opts as ConfirmOpts | AlertOpts).danger;
  const title =
    req.opts.title ??
    (req.kind === "confirm" ? "Confirmar" : req.kind === "prompt" ? "Completar dato" : danger ? "Error" : "Aviso");

  return (
    <div className="dialog-backdrop" onMouseDown={(e) => e.target === e.currentTarget && cancel()}>
      <div className="dialog-box" role="dialog" aria-modal="true" onKeyDown={onKeyDown}>
        <div className={`dialog-icon ${danger ? "danger" : ""}`}>{danger ? <WarnIcon /> : <InfoIcon />}</div>
        <h3 className="dialog-title">{title}</h3>
        <p className="dialog-message">{req.opts.message}</p>
        {req.kind === "prompt" && (
          <input
            ref={inputRef}
            className="dialog-input"
            style={{ width: "100%" }}
            type={req.opts.password ? "password" : "text"}
            placeholder={req.opts.placeholder}
            value={value}
            onChange={(e) => setValue(e.target.value)}
          />
        )}
        <div className="dialog-actions">
          {req.kind !== "alert" && (
            <button onClick={cancel}>{(req.opts as ConfirmOpts | PromptOpts).cancelLabel ?? "Cancelar"}</button>
          )}
          <button ref={primaryRef} className={danger ? "danger" : "primary"} onClick={submit}>
            {req.kind === "alert"
              ? req.opts.okLabel ?? "Entendido"
              : req.kind === "prompt"
              ? req.opts.confirmLabel ?? "Aceptar"
              : req.opts.confirmLabel ?? "Confirmar"}
          </button>
        </div>
      </div>
    </div>
  );
}
