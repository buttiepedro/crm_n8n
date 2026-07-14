/** Analytics de atención comercial.
 *  Paleta de series validada (CVD/contraste, light y dark):
 *  verde #16a34a = mensajes del cliente · índigo #6366f1 = nuestros.
 *  El color sigue a la entidad — idéntico en ambos temas. */
import { useEffect, useState } from "react";
import { api, showError } from "../api";
import { Select } from "../ui/Select";

const C_IN = "#16a34a";
const C_OUT = "#6366f1";

const RANGES = [
  { label: "Histórico", value: 0 },
  { label: "7 días", value: 7 },
  { label: "30 días", value: 30 },
  { label: "90 días", value: 90 },
];

type PipelineLite = { id: string; name: string; isDefault: boolean };
type Summary = {
  days: number;
  current: Record<string, number | null>;
  previous: Record<string, number | null>;
  awaitingReply: number;
  openLeads: number;
};
type TsPoint = { date: string; inbound: number; outbound: number; newConversations: number; leadsCreated: number };
type HourPoint = { hourUtc: number; count: number };
type AgentRow = { userId: string; name: string; outboundMessages: number; conversationsAssigned: number; leadsWon: number; wonValue: number };
type FunnelStage = { id: string; name: string; isTerminal: boolean; outcome: string | null; currentCount: number; enteredInPeriod: number; conversionFromPrev: number | null };

const nf = new Intl.NumberFormat("es-AR");
const fmt = (n: number | null | undefined) => (n == null ? "—" : nf.format(n));
const fmtMoney = (n: number | null | undefined) => (n ? `$ ${nf.format(Math.round(n))}` : "—");
const conversionHint = (c: Record<string, number | null>) =>
  c.newConversations ? `${Math.round((c.leadsCreated ?? 0) / c.newConversations * 100)}% de conversión` : undefined;

function niceCeil(v: number): number {
  if (v <= 0) return 1;
  const pow = 10 ** Math.floor(Math.log10(v));
  for (const m of [1, 2, 5, 10]) if (v <= m * pow) return m * pow;
  return 10 * pow;
}

export default function Analytics() {
  const [days, setDays] = useState(0);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [ts, setTs] = useState<TsPoint[]>([]);
  const [hours, setHours] = useState<HourPoint[]>([]);
  const [agents, setAgents] = useState<AgentRow[]>([]);
  const [funnel, setFunnel] = useState<FunnelStage[]>([]);
  const [pipelines, setPipelines] = useState<PipelineLite[]>([]);
  const [pipelineId, setPipelineId] = useState("");

  useEffect(() => {
    api.get<{ items: PipelineLite[] }>("/pipelines").then((p) => {
      setPipelines(p.items);
      setPipelineId((cur) => cur || p.items.find((x) => x.isDefault)?.id || p.items[0]?.id || "");
    }).catch(showError);
  }, []);

  useEffect(() => {
    if (!pipelineId) return;
    Promise.all([
      api.get<Summary>(`/analytics/summary?days=${days}`),
      api.get<{ items: TsPoint[] }>(`/analytics/timeseries?days=${days}`),
      api.get<{ items: HourPoint[] }>(`/analytics/hourly?days=${days}`),
      api.get<{ items: AgentRow[] }>(`/analytics/agents?days=${days}`),
      api.get<{ items: FunnelStage[] }>(`/analytics/funnel?days=${days}&pipelineId=${pipelineId}`),
    ])
      .then(([s, t, h, a, f]) => {
        setSummary(s);
        setTs(t.items);
        setHours(h.items);
        setAgents(a.items);
        setFunnel(f.items);
      })
      .catch(showError);
  }, [days, pipelineId]);

  if (!summary) return <div className="page">Cargando…</div>;
  const { current: c } = summary;

  return (
    <div className="page" style={{ maxWidth: 1100 }}>
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 18 }}>
        <h2 style={{ margin: 0 }}>Analytics</h2>
        <div className="row" style={{ gap: 4 }}>
          {RANGES.map((r) => (
            <button key={r.value} className={days === r.value ? "primary" : ""} onClick={() => setDays(r.value)}>
              {r.label}
            </button>
          ))}
        </div>
      </div>

      {/* ── Resumen ── */}
      <div className="stat-grid stat-grid-simple">
        <SimpleTile label="Consultas" value={fmt(c.newConversations)}
                    hint={`${fmt((c.inbound ?? 0) + (c.outbound ?? 0))} mensajes`} />
        <SimpleTile label="Leads generados" value={fmt(c.leadsCreated)} hint={conversionHint(c)} />
        <SimpleTile label="Ganados" value={fmt(c.leadsWon)} tone="good" hint={fmtMoney(c.wonValue)} />
        <SimpleTile label="Perdidos" value={fmt(c.leadsLost)} tone="bad" />
        <SimpleTile label="Tasa de cierre" value={c.winRate == null ? "—" : `${c.winRate}%`}
                    hint={`${fmt(summary.openLeads)} abiertos`} />
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
          <div className="chart-head">
            <h3>Embudo — leads por etapa</h3>
            {pipelines.length > 1 && (
              <Select
                style={{ width: 160 }}
                value={pipelineId}
                onChange={setPipelineId}
                options={pipelines.map((p) => ({ value: p.id, label: `${p.name}${p.isDefault ? " ★" : ""}` }))}
              />
            )}
          </div>
          <FunnelBars stages={funnel} historic={days === 0} />
        </div>
      </div>

      <div className="chart-card">
        <div className="chart-head"><h3>Rendimiento por agente</h3></div>
        {agents.length === 0 ? (
          <p className="muted">Sin actividad de agentes en el período.</p>
        ) : (
          <table>
            <thead>
              <tr><th>Agente</th><th className="num">Msjs enviados</th><th className="num">Conv. asignadas</th><th className="num">Leads ganados</th><th className="num">Valor ganado</th></tr>
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

/* ── Resumen simplificado ──────────────────────────────────────────── */

function SimpleTile({ label, value, hint, tone }: {
  label: string;
  value: string;
  hint?: string;
  tone?: "good" | "bad";
}) {
  return (
    <div className="stat-tile">
      <div className={`stat-value ${tone ?? ""}`}>{value}</div>
      <div className="stat-label">{label}</div>
      {hint && <div className="stat-hint">{hint}</div>}
    </div>
  );
}

/* ── Barras: mensajes por día ──────────────────────────────────────── */

function MessagesLine({ data }: { data: TsPoint[] }) {
  if (data.length === 0) return <p className="muted">Sin datos.</p>;
  const W = 720, H = 200, PL = 40, PR = 10, PT = 10, PB = 22;
  const max = niceCeil(Math.max(1, ...data.map((d) => Math.max(d.inbound, d.outbound))));
  const y = (v: number) => PT + (H - PT - PB) * (1 - v / max);
  const colW = (W - PL - PR) / data.length;
  const barW = Math.min(14, colW / 2 - 2);
  const groupX = (i: number) => PL + i * colW + colW / 2;
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
        <text key={i} x={groupX(i)} y={H - 6} className="axis-text" textAnchor="middle">
          {label(data[i].date)}
        </text>
      ))}
      {data.map((d, i) => (
        <g key={d.date}>
          <rect x={groupX(i) - barW - 1} y={y(d.inbound)} width={barW} height={Math.max(0, y(0) - y(d.inbound))}
                rx="1.5" fill={C_IN} className="bar" />
          <rect x={groupX(i) + 1} y={y(d.outbound)} width={barW} height={Math.max(0, y(0) - y(d.outbound))}
                rx="1.5" fill={C_OUT} className="bar" />
          <rect x={PL + i * colW} y={0} width={colW} height={H} fill="transparent">
            <title>{`${label(d.date)} — recibidos: ${d.inbound} · enviados: ${d.outbound} · conv. nuevas: ${d.newConversations}`}</title>
          </rect>
        </g>
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

function FunnelBars({ stages, historic }: { stages: FunnelStage[]; historic: boolean }) {
  const flow = stages.filter((s) => !s.isTerminal);
  const terminal = stages.filter((s) => s.isTerminal);
  const max = Math.max(1, ...flow.map((s) => s.currentCount));
  const countLabel = historic ? "actualmente" : "entraron a la etapa en el período";

  return (
    <div>
      {flow.map((s) => (
        <div className="funnel-row" key={s.id} title={`${s.name}: ${s.currentCount} ${countLabel}`}>
          <span className="funnel-label">{s.name}</span>
          <div className="funnel-track">
            <div className="funnel-bar" style={{ width: `${Math.max(4, (s.currentCount / max) * 100)}%` }} />
          </div>
          <span className="funnel-num">
            {nf.format(s.currentCount)}
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
        {historic
          ? "Cantidad de leads actualmente en cada etapa (todo el historial)."
          : "Leads que llegaron a su etapa actual dentro del período seleccionado."}
        {" "}% = conversión desde la etapa anterior (entradas en el período).
      </p>
    </div>
  );
}
