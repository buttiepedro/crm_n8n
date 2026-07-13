/** Icono de robot (bot n8n) para los switches de silenciar/activar. */
export function BotIcon({ muted = false, size = 15 }: { muted?: boolean; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <line x1="12" y1="4.2" x2="12" y2="7.5" />
      <circle cx="12" cy="3" r="1.3" fill="currentColor" stroke="none" />
      <line x1="2.5" y1="13.5" x2="4.5" y2="13.5" />
      <line x1="19.5" y1="13.5" x2="21.5" y2="13.5" />
      <rect x="4.5" y="7.5" width="15" height="12.5" rx="3.5" />
      {muted ? (
        <>
          <line x1="8.7" y1="12.3" x2="10.7" y2="14.7" />
          <line x1="10.7" y1="12.3" x2="8.7" y2="14.7" />
          <line x1="13.3" y1="12.3" x2="15.3" y2="14.7" />
          <line x1="15.3" y1="12.3" x2="13.3" y2="14.7" />
        </>
      ) : (
        <>
          <circle cx="9.3" cy="13.7" r="1.15" fill="currentColor" stroke="none" />
          <circle cx="14.7" cy="13.7" r="1.15" fill="currentColor" stroke="none" />
        </>
      )}
      {muted && <line x1="1.8" y1="21.5" x2="21.5" y2="1.8" strokeWidth="2.2" />}
    </svg>
  );
}
