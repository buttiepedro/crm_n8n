import type { ReactNode } from "react";

/** Switch custom (reemplaza <input type="checkbox">). */
export function Switch({
  checked,
  onChange,
  label,
  disabled,
  className = "",
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label?: ReactNode;
  disabled?: boolean;
  className?: string;
}) {
  return (
    <label className={`ui-switch-label ${disabled ? "disabled" : ""} ${className}`}>
      <input
        type="checkbox"
        className="ui-switch-input"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span className="ui-switch-track">
        <span className="ui-switch-thumb" />
      </span>
      {label != null && <span>{label}</span>}
    </label>
  );
}
