// Gráficas de actividad (Recharts). Paleta validada para la superficie oscura:
// detecciones #1f8bff, alertas #f43f4e (CVD ΔE ≥ 26, contraste ≥ 3:1).
import { Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export const SERIES = { detecciones: "#1f8bff", alertas: "#f43f4e" };

const axis = { stroke: "#4a5a6e", fontSize: 11, tickLine: false, axisLine: false } as const;

function Tip({ active, payload, label, unit }: { active?: boolean; payload?: { value: number; color: string; name: string }[]; label?: string; unit: string }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-ink-600 bg-ink-900/95 px-3 py-2 text-xs shadow-xl">
      <p className="mb-1 font-medium text-ink-200">{label}</p>
      {payload.map((p) => (
        <p key={p.name} className="flex items-center gap-2 text-ink-100">
          <span className="h-2 w-2 rounded-sm" style={{ background: p.color }} />
          <span className="font-mono font-semibold tabular-nums">{p.value}</span> {unit}
        </p>
      ))}
    </div>
  );
}

type Row = { label: string; detecciones: number; alertas: number };

export function DetectionsChart({ data }: { data: Row[] }) {
  return (
    <ResponsiveContainer width="100%" height={220}>
      <AreaChart data={data} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
        <defs>
          <linearGradient id="g-det" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor={SERIES.detecciones} stopOpacity={0.35} />
            <stop offset="1" stopColor={SERIES.detecciones} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke="#18212c" vertical={false} />
        <XAxis dataKey="label" {...axis} interval="preserveStartEnd" minTickGap={18} />
        <YAxis {...axis} allowDecimals={false} />
        <Tooltip content={<Tip unit="detecciones" />} cursor={{ stroke: "#7b8a9e", strokeDasharray: "3 3" }} />
        <Area type="monotone" dataKey="detecciones" name="Detecciones" stroke={SERIES.detecciones} strokeWidth={2}
          fill="url(#g-det)" activeDot={{ r: 4, stroke: "#0b0f15", strokeWidth: 2 }} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function AlertsChart({ data }: { data: Row[] }) {
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data} margin={{ top: 8, right: 8, left: -18, bottom: 0 }} barCategoryGap={2}>
        <CartesianGrid stroke="#18212c" vertical={false} />
        <XAxis dataKey="label" {...axis} interval="preserveStartEnd" minTickGap={18} />
        <YAxis {...axis} allowDecimals={false} />
        <Tooltip content={<Tip unit="alertas" />} cursor={{ fill: "rgba(244,63,78,.08)" }} />
        <Bar dataKey="alertas" name="Alertas" fill={SERIES.alertas} radius={[4, 4, 0, 0]} maxBarSize={22} />
      </BarChart>
    </ResponsiveContainer>
  );
}
