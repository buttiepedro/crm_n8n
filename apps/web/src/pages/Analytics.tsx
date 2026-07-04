/** Analytics de atención comercial.
 *  Paleta de series validada (CVD/contraste, light y dark):
 *  verde #16a34a = mensajes del cliente · índigo #6366f1 = nuestros.
 *  El color sigue a la entidad — idéntico en ambos temas. */
import { useEffect, useState } from "react";
import { api, showError } from "../api";

const C_IN = "#16a34a";
const C_OUT = "#6366f1";

type Summary = {
  days: number;
  current: Record<string, number | null>;
  previous: Record<string, number | null>;
  awaitingReply: number;
};
type TsPoint = { date: string; inbound: number; outbound: number; newConversations: number; leadsCreated: number };
type HourPoint = { hourUtc: number; count: number };
type AgentRow = { userId: string; name: string; outboundMessages: number; conversationsAssigned: number; leadsWon: number; wonValue: number };
type FunnelStage = { id: string; name: string; isTerminal: boolean; outcome: string | null; currentCount: number; enteredInPeriod: number; conversionFromPrev: number | null };

const nf = new Intl.NumberFormat("es-AR");
const fmt = (n: number | null | undefined) => (n == null ? "—" : nf.format(n));
const fmtMin = (m: number | null | undefined) => {
  if (m == null) return "—";
  if (m < 1) return "<1 min";
  if (m < 60) return `${Math.round(m)} min`;
  return `${Math.floor(m / 60)} h ${Math.round(m % 60)} m`;
};
const fmtMoney = (n: number | null | undefined) => (n ? `$ ${nf.format(Math.round(n))}` : "—");

function niceCeil(v: number): number {
  if (v <= 0) return 1;
  const pow = 10 ** Math.floor(Math.log10(v));
  for (const m of [1, 2, 5, 10]) if (v <= m * pow) return m * pow;
  return 10 * pow;
}

export default function Analytics() {
  const [days, setDays] = useState(30);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [ts, setTs] = useState<TsPoint[]>([]);
  const [hours, setHours] = useState<HourPoint[]>([]);
  const [agents, setAgents] = useState<AgentRow[]>([]);
  const [funnel, setFunnel] = useState<FunnelStage[]>([]);

  useEffect(() => {
    Promise.all([
      api.get<Summary>(`/analytics/summary?days=${days}`),
      api.get<{ items: TsPoint[] }>(`/analytics/timeseries?days=${days}`),
      api.get<{ items: HourPoint[] }>(`/analytics/hourly?days=${days}`),
      api.get<{ items: AgentRow[] }>(`/analytics/agents?days=${days}`),
      api.get<{ items: FunnelStage[] }>(`/analytics/funnel?days=${days}`),
    ])
      .then(([s, t, h, a, f]) => {
        setSummary(s);
        setTs(t.items);
        setHours(h.items);
        setAgents(a.items);
        setFunnel(f.items);
      })
      .catch(showError);
  }, [days]);

  if (!summary) return <div className="page">Cargando…</div>;
  const { current: c, previous: p } = summary;

  return (
    <div className="page" style={{ maxWidth: 1100 }}>
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 18 }}>
        <h2 style={{ margin: 0 }}>Analytics</h2>
        <div className="row" style={{ gap: 4 }}>
          {[7, 30, 90].map((d) => (
            <button key={d} className={days === d ? "primary" : ""} onClick={() => setDays(d)}>
              {d} días
            </button>
          ))}
        </div>
      </div>

      {/* ── Velocidad de atención ── */}
      <h3 className="section-title">Velocidad de atención</h3>
      <div className="stat-grid">
        <Tile label="1ª respuesta (mediana)" value={fmtMin(c.medianFirstResponseMin)}
              delta={pct(c.medianFirstResponseMin, p.medianFirstResponseMin)} goodWhenDown />
        <Tile label="Respondidas en <1 h" value={c.pctWithin1h == null ? "—" : `${c.pctWithin1h}%`}
              delta={diff(c.pctWithin1h, p.pctWithin1h, " pts")} />
        <Tile label="Tasa de respuesta" value={c.respondedRate == null ? "—" : `${c.respondedRate}%`}
              delta={diff(c.respondedRate, p.respondedRate, " pts")} />
        <Tile label="Esperando respuesta" value={fmt(summary.awaitingReply)} hint="ahora" alert={summary.awaitingReply > 0} />
      </div>

      {/* ── Demanda ── */}
      <h3 className="section-title">Demanda</h3>
      <div className="stat-grid">
        <Tile label="Conversaciones nuevas" value={fmt(c.newConversations)} delta={pct(c.newConversations, p.newConversations)} />
        <Tile label="Contactos nuevos" value={fmt(c.newContacts)} delta={pct(c.newContacts, p.newContacts)} />
        <Tile label="Mensajes recibidos" value={fmt(c.inbound)} delta={pct(c.inbound, p.inbound)} dot={C_IN} />
        <Tile label="Mensajes enviados" value={fmt(c.outbound)} delta={pct(c.outbound, p.outbound)} dot={C_OUT} />
      </div>

      {/* ── Resultado comercial ── */}
      <h3 className="section-title">Resultado comercial</h3>
      <div className="stat-grid">
        <Tile label="Leads creados" value={fmt(c.leadsCreated)} delta={pct(c.leadsCreated, p.leadsCreated)} />
        <Tile label="Leads ganados" value={fmt(c.leadsWon)} delta={pct(c.leadsWon, p.leadsWon)} />
        <Tile label="Tasa de cierre" value={c.winRate == null ? "—" : `${c.winRate}%`}
              delta={diff(c.winRate, p.winRate, " pts")} hint="ganados / cerrados" />
        <Tile label="Valor ganado" value={fmtMoney(c.wonValue)} delta={pct(c.wonValue, p.wonValue)} />
      </div>

      <div className="chart-card">
        <div className="chart-head">
          <h3>Mensajes por día</h3>
          <div className="legend">
            <span><i style={{ background: C_IN }} /> Recibidos</span>
            <span><i style={{ background: C_OUT }} /> Enviados</span>
          </div>
        </div>
        <MessagesLine data={ts} />
      </div>

      <div className="chart-2col">
        <div className="chart-card">
          <div className="chart-head"><h3>Entrantes por hora (hora local)</h3></div>
          <HourBars data={hours} />
        </div>
        <div className="chart-card">
          <div className="chart-head"><h3>Embudo — entradas por etapa</h3></div>
          <FunnelBars stages={funnel} />
        </div>
      </div>

      <div className="chart-card">
        <div className="chart-head"><h3>Rendimiento por agente</h3></div>
        {agents.length === 0 ? (
          <p className="muted">Sin actividad de agentes en el período.</p>
        ) : (
          <table>
            <thead>
              <tr><th>Agente</th><th>Msjs enviados</th><th>Conv. asignadas</th><th>Leads ganados</th><th>Valor ganado</th></tr>
            </thead>
            <tbody>
              {agents.map((a) => (
                <tr key={a.userId}>
                  <td>{a.name}</td>
                  <td className="num">{fmt(a.outboundMessages)}</td>
                  <td className="num">{fmt(a.conversationsAssigned)}</td>
                  <td className="num">{fmt(a.leadsWon)}</td>
                  <td className="num">{fmtMoney(a.wonValue)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

/* ── Deltas vs período anterior ─────────────────────────────────────── */

function pct(cur: number | null | undefined, prev: number | null | undefined) {
  if (cur == null || prev == null || prev === 0) return null;
  return { value: ((cur - prev) / prev) * 100, suffix: "%" };
}
function diff(cur: number | null | undefined, prev: number | null | undefined, suffix: string) {
  if (cur == null || prev == null) return null;
  return { value: cur - prev, suffix };
}

function Tile({ label, value, delta, hint, dot, alert, goodWhenDown }: {
  label: string;
  value: string;
  delta?: { value: number; suffix: string } | null;
  hint?: string;
  dot?: string;
  alert?: boolean;
  goodWhenDown?: boolean;
}) {
  let deltaEl = null;
  if (delta && Math.abs(delta.value) >= 0.05) {
    const up = delta.value > 0;
    const good = goodWhenDown ? !up : up;
    deltaEl = (
      <span className={`stat-delta ${good ? "good" : "bad"}`}>
        {up ? "▲" : "▼"} {Math.abs(delta.value).toFixed(delta.suffix === "%" ? 0 : 1)}{delta.suffix}
      </span>
    );
  }
  return (
    <div className="stat-tile">
      <div className="stat-label">
        {dot && <i className="stat-dot" style={{ background: dot }} />}
        {label}
      </div>
      <div className={`stat-value ${alert ? "alert" : ""}`}>{value}</div>
      <div className="stat-foot">
        {deltaEl}
        {hint && <span className="muted" style={{ fontSize: 11 }}>{hint}</span>}
      </div>
    </div>
  );
}

/* ── Línea: mensajes por día ────────────────────────────────────────── */

function MessagesLine({ data }: { data: TsPoint[] }) {
  if (data.length === 0) return <p className="muted">Sin datos.</p>;
  const W = 720, H = 200, PL = 40, PR = 10, PT = 10, PB = 22;
  const max = niceCeil(Math.max(1, ...data.map((d) => Math.max(d.inbound, d.outbound))));
  const x = (i: number) => PL + (i * (W - PL - PR)) / Math.max(1, data.length - 1);
  const y = (v: number) => PT + (H - PT - PB) * (1 - v / max);
  const path = (key: "inbound" | "outbound") =>
    data.map((d, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(d[key]).toFixed(1)}`).join(" ");
  const colW = (W - PL - PR) / Math.max(1, data.length - 1);
  const label = (iso: string) => iso.slice(8, 10) + "/" + iso.slice(5, 7);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto" }} role="img"
         aria-label="Mensajes recibidos y enviados por día">
      {[0.25, 0.5, 0.75, 1].map((f) => (
        <g key={f}>
          <line x1={PL} x2={W - PR} y1={y(max * f)} y2={y(max * f)} className="grid-line" />
          <text x={PL - 6} y={y(max * f) + 3} className="axis-text" textAnchor="end">
            {nf.format(max * f)}
          </text>
        </g>
      ))}
      <line x1={PL} x2={W - PR} y1={y(0)} y2={y(0)} className="axis-line" />
      {[0, Math.floor((data.length - 1) / 2), data.length - 1].map((i) => (
        <text key={i} x={x(i)} y={H - 6} className="axis-text" textAnchor="middle">
          {label(data[i].date)}
        </text>
      ))}
      <path d={path("inbound")} fill="none" stroke={C_IN} strokeWidth="2" strokeLinejoin="round" />
      <path d={path("outbound")} fill="none" stroke={C_OUT} strokeWidth="2" strokeLinejoin="round" />
      {data.length <= 31 &&
        data.map((d, i) => (
          <g key={d.date}>
            <circle cx={x(i)} cy={y(d.inbound)} r="2.5" fill={C_IN} className="pt" />
            <circle cx={x(i)} cy={y(d.outbound)} r="2.5" fill={C_OUT} className="pt" />
          </g>
        ))}
      {data.map((d, i) => (
        <rect key={d.date} x={x(i) - colW / 2} y={0} width={colW} height={H} fill="transparent">
          <title>{`${label(d.date)} — recibidos: ${d.inbound} · enviados: ${d.outbound} · conv. nuevas: ${d.newConversations}`}</title>
        </rect>
      ))}
    </svg>
  );
}

/* ── Barras: distribución horaria (hora local) ──────────────────────── */

function HourBars({ data }: { data: HourPoint[] }) {
  const offsetH = new Date().getTimezoneOffset() / 60; // AR: +3
  const local: { hour: number; count: number }[] = Array.from({ length: 24 }, (_, h) => ({ hour: h, count: 0 }));
  for (const d of data) {
    const h = ((d.hourUtc - offsetH) % 24 + 24) % 24;
    local[h].count += d.count;
  }
  const max = Math.max(1, ...local.map((d) => d.count));
  const W = 360, H = 150, PB = 18, bw = W / 24;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto" }} role="img"
         aria-label="Mensajes entrantes por hora del día">
      {local.map((d) => {
        const bh = ((H - PB - 8) * d.count) / max;
        return (
          <g key={d.hour}>
            <rect x={d.hour * bw + 1} y={H - PB - bh} width={bw - 2} height={Math.max(bh, d.count ? 2 : 0)}
                  rx="2" fill={C_OUT} className="bar" />
            <rect x={d.hour * bw} y={0} width={bw} height={H} fill="transparent">
              <title>{`${d.hour}:00 — ${d.count} mensajes`}</title>
            </rect>
          </g>
        );
      })}
      {[0, 6, 12, 18, 23].map((h) => (
        <text key={h} x={h * bw + bw / 2} y={H - 4} className="axis-text" textAnchor="middle">
          {h}h
        </text>
      ))}
    </svg>
  );
}

/* ── Embudo del pipeline ────────────────────────────────────────────── */

function FunnelBars({ stages }: { stages: FunnelStage[] }) {
  const flow = stages.filter((s) => !s.isTerminal);
  const terminal = stages.filter((s) => s.isTerminal);
  const max = Math.max(1, ...flow.map((s) => s.enteredInPeriod));

  return (
    <div>
      {flow.map((s) => (
        <div className="funnel-row" key={s.id} title={`${s.name}: ${s.enteredInPeriod} entradas en el período · ${s.currentCount} actualmente`}>
          <span className="funnel-label">{s.name}</span>
          <div className="funnel-track">
            <div className="funnel-bar" style={{ width: `${Math.max(4, (s.enteredInPeriod / max) * 100)}%` }} />
          </div>
          <span className="funnel-num">
            {nf.format(s.enteredInPeriod)}
            {s.conversionFromPrev != null && (
              <span className="muted" style={{ fontSize: 11 }}> · {s.conversionFromPrev}%</span>
            )}
          </span>
        </div>
      ))}
      {terminal.length > 0 && (
        <div className="row" style={{ marginTop: 10, gap: 6 }}>
          {terminal.map((s) => (
            <span key={s.id} className={`pill ${s.outcome === "won" ? "green" : "red"}`}>
              {s.outcome === "won" ? "✓" : "✕"} {s.name}: {nf.format(s.enteredInPeriod)}
            </span>
          ))}
        </div>
      )}
      <p className="muted" style={{ fontSize: 11, marginTop: 8 }}>
        Entradas por etapa en el período · % = conversión desde la etapa anterior.
      </p>
    </div>
  );
}
