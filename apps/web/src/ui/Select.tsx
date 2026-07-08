import { useEffect, useRef, useState } from "react";

export type SelectOption = { value: string; label: string };

const Chevron = () => (
  <svg className="ui-select-chevron" width="15" height="15" viewBox="0 0 24 24" fill="none"
       stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <path d="M6 9l6 6 6-6" />
  </svg>
);

const Check = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor"
       strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
    <path d="M20 6L9 17l-5-5" />
  </svg>
);

/** Select custom: dropdown con navegación por teclado y cierre al click afuera. */
export function Select({
  value,
  onChange,
  options,
  placeholder = "Seleccionar",
  disabled,
  style,
  className = "",
}: {
  value: string;
  onChange: (v: string) => void;
  options: SelectOption[];
  placeholder?: string;
  disabled?: boolean;
  style?: React.CSSProperties;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const current = options.find((o) => o.value === value);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onEsc);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onEsc);
    };
  }, [open]);

  useEffect(() => {
    if (open) setActive(Math.max(0, options.findIndex((o) => o.value === value)));
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!open) return;
    listRef.current
      ?.querySelector<HTMLElement>('[data-active="true"]')
      ?.scrollIntoView({ block: "nearest" });
  }, [active, open]);

  const choose = (v: string) => {
    onChange(v);
    setOpen(false);
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (disabled) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (!open) setOpen(true);
      else setActive((i) => Math.min(options.length - 1, i + 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      if (open) setActive((i) => Math.max(0, i - 1));
    } else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      if (open) options[active] && choose(options[active].value);
      else setOpen(true);
    } else if (e.key === "Tab") {
      setOpen(false);
    }
  };

  return (
    <div ref={rootRef} className={`ui-select ${className}`} style={style}>
      <button
        type="button"
        className={`ui-select-trigger ${open ? "open" : ""} ${!current ? "placeholder" : ""}`}
        onClick={() => !disabled && setOpen((o) => !o)}
        onKeyDown={onKeyDown}
        disabled={disabled}
      >
        <span className="ui-select-value">{current ? current.label : placeholder}</span>
        <Chevron />
      </button>
      {open && (
        <div ref={listRef} className="ui-popover" role="listbox">
          {options.map((o, i) => (
            <div
              key={o.value}
              role="option"
              aria-selected={o.value === value}
              data-active={i === active}
              className={`ui-option ${i === active ? "active" : ""} ${o.value === value ? "selected" : ""}`}
              onMouseEnter={() => setActive(i)}
              onClick={() => choose(o.value)}
            >
              <span>{o.label}</span>
              {o.value === value && <Check />}
            </div>
          ))}
          {options.length === 0 && <div className="ui-option muted-option">Sin opciones</div>}
        </div>
      )}
    </div>
  );
}
