import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  Activity, BellRing, BrainCircuit, CalendarClock, Cctv, Cpu, LayoutDashboard, Lightbulb, MemoryStick, ScanFace,
  ShieldAlert, Thermometer, Timer, Users,
} from "lucide-react";
import clsx from "clsx";
import { get, post, qs } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useRealtime } from "@/lib/realtime";
import { fmtRelative, fmtScore, fmtTime, fmtUptime } from "@/lib/format";
import type { Activity as ActivityT, LiveStatus, Summary } from "@/lib/types";
import { Badge, Button, Card, EmptyState, LevelBadge, Meter, PageHeader, ReviewBadge, SimBadge, Spinner, StatCard, StatusDot, Table, Td } from "@/components/ui";
import { AlertsChart, DetectionsChart, SERIES } from "@/components/charts";
import LiveVideo from "@/components/LiveVideo";
import { ModeBadge } from "@/components/HardwareTab";

function HealthRow({ icon: Icon, label, children }: { icon: React.ElementType; label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-3 py-2.5">
      <Icon className="h-4 w-4 shrink-0 text-ink-400" />
      <span className="w-28 shrink-0 text-xs text-ink-300">{label}</span>
      <div className="min-w-0 flex-1 text-sm text-ink-100">{children}</div>
    </div>
  );
}

function AlarmStatus({ gpio }: { gpio: LiveStatus["gpio"] }) {
  const { can } = useAuth();
  const silence = useMutation({ mutationFn: () => post("/api/hardware/silence") });
  return (
    <span className="flex flex-wrap items-center gap-2 text-sm">
      <ModeBadge status={gpio} />
      {gpio.alarm_active && <Badge tone="red" dot>Alarma activa</Badge>}
      {gpio.alarm_active && can("alerts.review") &&
        <Button size="sm" variant="danger" loading={silence.isPending} onClick={() => silence.mutate()}>Silenciar</Button>}
    </span>
  );
}

export function SystemHealth({ s }: { s: LiveStatus }) {
  const t = s.system.temperature_c;
  return (
    <div className="divide-y divide-ink-700/60">
      <HealthRow icon={Cctv} label="Cámara USB">
        <StatusDot ok={s.camera.connected} warn={!s.camera.running}
          label={s.camera.connected ? `${s.camera.synthetic ? "Simulada" : "Conectada"} · ${s.camera.resolution} · ${s.camera.capture_fps} fps`
            : s.camera.running ? (s.camera.error ?? "Sin señal") : "Monitoreo detenido"} />
      </HealthRow>
      <HealthRow icon={BrainCircuit} label="Motor facial">
        <StatusDot ok={s.engine.state === "activo" || s.engine.state === "demo"} warn={s.engine.state === "detenido" || s.engine.state === "esperando"}
          label={<span className="truncate">{s.engine.label} · {s.engine.processing_fps} FPS</span>} />
      </HealthRow>
      <HealthRow icon={Cpu} label="CPU">
        <div className="flex items-center gap-3"><Meter value={s.system.cpu_percent} /><span className="w-12 text-right font-mono text-xs">{s.system.cpu_percent.toFixed(0)} %</span></div>
      </HealthRow>
      <HealthRow icon={MemoryStick} label="Memoria RAM">
        <div className="flex items-center gap-3"><Meter value={s.system.ram_percent} /><span className="w-12 text-right font-mono text-xs">{s.system.ram_percent.toFixed(0)} %</span></div>
        <p className="mt-0.5 text-[11px] text-ink-400">{s.system.ram_used_mb} / {s.system.ram_total_mb} MB</p>
      </HealthRow>
      <HealthRow icon={Thermometer} label="Temperatura">
        {t == null ? <span className="text-ink-400">No disponible en este equipo</span> : (
          <div className="flex items-center gap-3">
            <Meter value={t} max={85} />
            <span className={clsx("w-14 text-right font-mono text-xs", s.system.temperature_status !== "normal" && "text-warn-400")}>{t.toFixed(1)} °C</span>
          </div>
        )}
      </HealthRow>
      <HealthRow icon={Lightbulb} label="LED / buzzer">
        <AlarmStatus gpio={s.gpio} />
      </HealthRow>
      <HealthRow icon={Timer} label="Encendido">{fmtUptime(s.system.uptime_s)}</HealthRow>
    </div>
  );
}

export default function DashboardPage() {
  const { can } = useAuth();
  const { status } = useRealtime();
  const navigate = useNavigate();
  const [range, setRange] = useState<"day" | "week">("day");
  const summary = useQuery({ queryKey: ["summary"], queryFn: () => get<Summary>("/api/dashboard/summary"), refetchInterval: 30000 });
  const activity = useQuery({ queryKey: ["activity", range], queryFn: () => get<ActivityT>(`/api/dashboard/activity${qs({ range })}`), refetchInterval: 60000 });

  if (summary.isLoading || !summary.data) return <Spinner className="mt-20" />;
  const d = summary.data;
  const live: LiveStatus = status ?? d;
  const totalDet = activity.data?.series.reduce((a, b) => a + b.detecciones, 0) ?? 0;
  const totalAl = activity.data?.series.reduce((a, b) => a + b.alertas, 0) ?? 0;

  return (
    <>
      <PageHeader title="Centro de monitoreo" subtitle="Vista general del sistema y la actividad del día" icon={LayoutDashboard}
        actions={<Badge tone={live.engine.state === "error" ? "red" : "green"} dot>{live.engine.label}</Badge>} />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
        <StatCard label="Rostros detectados hoy" value={d.faces_today} icon={ScanFace}
          hint={<>En cuadro ahora: <span className="font-mono text-ink-100">{live.engine.faces_now}</span></>} />
        <StatCard label="Personas registradas" value={d.persons_total} icon={Users} tone="slate"
          hint={`${d.authorized_active} autorizadas activas · ${live.engine.templates} plantillas · BD ${d.database.ok ? "correcta" : "con error"}`} />
        <StatCard label="En la blacklist" value={d.blacklist_active} icon={ShieldAlert} tone="slate"
          hint={`${d.blacklist_total} registros en total`} />
        <StatCard label="Alertas pendientes" value={live.pending_alerts} icon={BellRing} tone={live.pending_alerts ? "red" : "green"}
          pulse={live.pending_alerts > 0} hint={`${d.alerts_today} posibles coincidencias hoy`} />
        <StatCard label="Eventos hoy" value={d.events_today} icon={CalendarClock} tone="amber"
          hint={`${d.confirmed} confirmadas · ${d.false_positives} descartadas (histórico)`} />
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-5">
        {can("camera.view") ? (
          <Card title="Cámara en vivo" icon={Cctv} className="xl:col-span-3" bodyClass="p-3"
            actions={<button onClick={() => navigate("/monitoreo")} className="text-xs font-medium text-volt-400 hover:text-volt-300">Abrir monitoreo →</button>}>
            <LiveVideo status={live} compact />
          </Card>
        ) : (
          <Card title="Cámara en vivo" icon={Cctv} className="xl:col-span-3">
            <EmptyState title="Video no disponible para su rol" text="El rol Auditor puede consultar eventos, pero no ver la transmisión en vivo." />
          </Card>
        )}
        <Card title="Estado de la Raspberry Pi" icon={Activity} className="xl:col-span-2" bodyClass="px-4 py-1">
          <SystemHealth s={live} />
        </Card>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <Card title="Actividad de detección" icon={ScanFace}
          actions={
            <div className="flex rounded-lg border border-ink-600 p-0.5 text-xs">
              {(["day", "week"] as const).map((r) => (
                <button key={r} onClick={() => setRange(r)}
                  className={clsx("rounded-md px-2.5 py-1 font-medium", range === r ? "bg-volt-500/20 text-volt-300" : "text-ink-300 hover:text-white")}>
                  {r === "day" ? "24 horas" : "7 días"}
                </button>
              ))}
            </div>
          }>
          <p className="mb-2 flex items-center gap-2 text-xs text-ink-300">
            <span className="h-2 w-2 rounded-sm" style={{ background: SERIES.detecciones }} />
            Detecciones registradas · <span className="font-mono text-ink-100">{totalDet}</span> en el periodo
          </p>
          {activity.data ? <DetectionsChart data={activity.data.series} /> : <Spinner className="h-[220px] items-center" />}
        </Card>
        <Card title="Posibles coincidencias" icon={BellRing}>
          <p className="mb-2 flex items-center gap-2 text-xs text-ink-300">
            <span className="h-2 w-2 rounded-sm" style={{ background: SERIES.alertas }} />
            Alertas generadas · <span className="font-mono text-ink-100">{totalAl}</span> en el periodo ({range === "day" ? "24 horas" : "7 días"})
          </p>
          {activity.data ? <AlertsChart data={activity.data.series} /> : <Spinner className="h-[220px] items-center" />}
        </Card>
      </div>

      <Card title="Últimas detecciones" icon={Activity} className="mt-4" bodyClass="p-2"
        actions={<button onClick={() => navigate("/historial")} className="text-xs font-medium text-volt-400 hover:text-volt-300">Ver historial →</button>}>
        <Table head={["Hora", "Evento", "Tipo", "Coincidencia", "Similitud", "Nivel", "Estado"]} empty={d.recent.length === 0}>
          {d.recent.map((e) => (
            <tr key={e.id} className="row-hover" onClick={() => navigate(e.type === "coincidencia" ? `/alertas?id=${e.id}` : `/historial?id=${e.id}`)}>
              <Td><span className="font-mono text-xs">{fmtTime(e.occurred_at)}</span><span className="ml-2 text-[11px] text-ink-400">{fmtRelative(e.occurred_at)}</span></Td>
              <Td mono>{e.uid} {e.is_simulated && <SimBadge />}</Td>
              <Td>{e.type_label}{e.type === "deteccion" && <span className="text-ink-400"> · {e.faces_count} rostro(s)</span>}</Td>
              <Td>{e.entry_name ?? <span className="text-ink-400">Sin coincidencia</span>}</Td>
              <Td mono>{fmtScore(e.score)}</Td>
              <Td><LevelBadge level={e.level} /></Td>
              <Td><ReviewBadge status={e.review_status} /></Td>
            </tr>
          ))}
        </Table>
      </Card>
    </>
  );
}
