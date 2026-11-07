import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import {
  BellRing, BrainCircuit, Cctv, Cpu, Database, FlaskConical, HardDrive, RefreshCw, RotateCcw, Save, Server,
  Settings as SettingsIcon, Trash2,
} from "lucide-react";
import { get, post, put } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useToast } from "@/lib/toast";
import { fmtDateTime, fmtUptime } from "@/lib/format";
import type { EngineStatus, GpioStatus, Settings, SystemSnapshot } from "@/lib/types";
import HardwareTab from "@/components/HardwareTab";
import { Badge, Button, Card, ConfirmDialog, ErrorNote, Field, Input, PageHeader, Select, Spinner, Toggle } from "@/components/ui";

interface SettingsResp { values: Settings; cameras: { index: number; path: string; name: string }[]; gpio: GpioStatus; camera_prefix?: string; can_edit: boolean }
interface SysInfo {
  device: { model: string; is_raspberry_pi: boolean; os: string; python: string; arch: string; hostname: string; throttled: string | null };
  status: SystemSnapshot; engine: EngineStatus; app_version: string; db_size_kb: number; data_dir: string;
  storage: { db_path: string; media_dir: string; log_dir: string; free_gb: number; total_gb: number };
  migrations: { version: string; applied_at: string }[];
}

const TABS = [
  { key: "recon", label: "Reconocimiento", icon: BrainCircuit },
  { key: "camera", label: "Cámara", icon: Cctv },
  { key: "alerts", label: "Alertas", icon: BellRing },
  { key: "hardware", label: "Hardware & Alarm Settings", icon: Cpu },
  { key: "retention", label: "Conservación", icon: Database },
  { key: "system", label: "Sistema", icon: Server },
  { key: "demo", label: "Demostración", icon: FlaskConical },
] as const;

function Range({ label, value, min, max, step, onChange, disabled, fmt, hint }: {
  label: string; value: number; min: number; max: number; step: number; onChange: (v: number) => void; disabled?: boolean;
  fmt?: (v: number) => string; hint?: React.ReactNode;
}) {
  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between text-xs">
        <span className="font-medium text-ink-200">{label}</span>
        <span className="font-mono text-volt-300">{fmt ? fmt(value) : value}</span>
      </div>
      <input type="range" className="w-full" min={min} max={max} step={step} value={value} disabled={disabled} onChange={(e) => onChange(Number(e.target.value))} />
      {hint && <p className="mt-1 text-[11px] text-ink-400">{hint}</p>}
    </div>
  );
}

export default function SettingsPage() {
  const { can } = useAuth();
  const qc = useQueryClient();
  const toast = useToast();
  const [tab, setTab] = useState<(typeof TABS)[number]["key"]>("recon");
  const q = useQuery({ queryKey: ["settings"], queryFn: () => get<SettingsResp>("/api/settings") });
  const [draft, setDraft] = useState<Settings | null>(null);
  useEffect(() => { if (q.data) setDraft(q.data.values); }, [q.data]);

  const save = useMutation({
    mutationFn: (changes: Partial<Settings>) => put<{ changed: Partial<Settings> }>("/api/settings", changes),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["settings"] });
      const n = Object.keys(r.changed).length;
      toast({ kind: "success", title: n ? "Configuración guardada" : "Sin cambios", body: n ? `${n} parámetro(s) actualizado(s) y aplicados en caliente.` : undefined });
    },
    onError: (e) => toast({ kind: "error", title: "Configuración no válida", body: (e as Error).message }),
  });

  if (!q.data || !draft) return <Spinner className="mt-20" />;
  const editable = q.data.can_edit;
  const set = <K extends keyof Settings>(k: K, v: Settings[K]) => setDraft({ ...draft, [k]: v });
  const changes = Object.fromEntries(Object.entries(draft).filter(([k, v]) => q.data.values[k as keyof Settings] !== v)) as Partial<Settings>;
  const dirty = Object.keys(changes).length > 0;

  return (
    <>
      <PageHeader title="Configuración del sistema" subtitle={editable ? "Los cambios se aplican sin reiniciar el servicio" : "Solo lectura — únicamente el superadministrador puede modificar"}
        icon={SettingsIcon}
        actions={editable && tab !== "system" && tab !== "demo" && <>
          <Button variant="ghost" icon={RotateCcw} disabled={!dirty} onClick={() => setDraft(q.data.values)}>Descartar</Button>
          <Button variant="primary" icon={Save} disabled={!dirty} loading={save.isPending} onClick={() => save.mutate(changes)}>Guardar cambios</Button>
        </>} />

      <div className="grid gap-4 lg:grid-cols-[220px_1fr]">
        <nav className="panel h-fit p-2">
          {TABS.map((t) => (
            <button key={t.key} onClick={() => setTab(t.key)}
              className={clsx("flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-sm font-medium transition",
                tab === t.key ? "bg-volt-500/10 text-white" : "text-ink-300 hover:bg-ink-750 hover:text-white")}>
              <t.icon className={clsx("h-4 w-4", tab === t.key ? "text-volt-400" : "text-ink-400")} /> {t.label}
            </button>
          ))}
        </nav>

        <div className="min-w-0">
          {tab === "recon" && (
            <Card title="Motor de reconocimiento" icon={BrainCircuit}>
              <div className="grid gap-6 md:grid-cols-2">
                <Range label="Umbral de coincidencia (similitud coseno)" value={draft.match_threshold} min={0.3} max={0.8} step={0.01} disabled={!editable}
                  onChange={(v) => set("match_threshold", v)} fmt={(v) => v.toFixed(2)}
                  hint="Más alto = menos falsos positivos pero más coincidencias perdidas. OpenCV recomienda ≥ 0,363 para SFace; por defecto 0,42." />
                <Range label="Confianza mínima del detector" value={draft.detection_confidence} min={0.5} max={0.99} step={0.01} disabled={!editable}
                  onChange={(v) => set("detection_confidence", v)} fmt={(v) => v.toFixed(2)} hint="Descarta detecciones dudosas de YuNet." />
                <Range label="Fotogramas para confirmar" value={draft.confirm_frames} min={1} max={6} step={1} disabled={!editable}
                  onChange={(v) => set("confirm_frames", v)} hint="La misma persona debe coincidir en N análisis seguidos antes de alertar." />
                <Range label="Tamaño mínimo de rostro" value={draft.min_face_size} min={30} max={200} step={5} disabled={!editable}
                  onChange={(v) => set("min_face_size", v)} fmt={(v) => `${v} px`} hint="Rostros más pequeños (lejanos) se ignoran." />
                <Range label="Frecuencia de procesamiento" value={draft.process_interval_ms} min={100} max={2000} step={50} disabled={!editable}
                  onChange={(v) => set("process_interval_ms", v)} fmt={(v) => `${v} ms · ${(1000 / v).toFixed(1)} análisis/s`}
                  hint="Intervalos más largos reducen el uso de CPU y la temperatura." />
                <Range label="Ancho de imagen analizada" value={draft.process_width} min={320} max={960} step={32} disabled={!editable}
                  onChange={(v) => set("process_width", v)} fmt={(v) => `${v} px`} hint="Se reduce el fotograma antes de analizarlo." />
                <Range label="Cooldown por persona" value={draft.dedup_seconds} min={5} max={600} step={5} disabled={!editable}
                  onChange={(v) => set("dedup_seconds", v)} fmt={(v) => `${v} s`} hint="Una misma persona no genera otra alerta ni otra alarma física dentro de este tiempo." />
                <Range label="Agrupación de detecciones" value={draft.detection_log_seconds} min={5} max={300} step={5} disabled={!editable}
                  onChange={(v) => set("detection_log_seconds", v)} fmt={(v) => `${v} s`} hint="Detecciones sin coincidencia se registran como máximo una vez por periodo (sin imagen)." />
              </div>
            </Card>
          )}

          {tab === "camera" && (
            <Card title="Cámara USB" icon={Cctv}>
              <div className="grid max-w-2xl gap-4 sm:grid-cols-2">
                <Field label="Dispositivo">
                  <Select value={draft.camera_index} disabled={!editable} onChange={(e) => set("camera_index", Number(e.target.value))}>
                    {[...new Set([draft.camera_index, ...q.data.cameras.map((c) => c.index)])].map((i) => (
                      <option key={i} value={i}>{q.data.camera_prefix ?? "/dev/video"}{i} {q.data.cameras.find((c) => c.index === i)?.name ?? "(no detectado)"}</option>
                    ))}
                  </Select>
                </Field>
                <Field label="Resolución de captura">
                  <Select value={`${draft.camera_width}x${draft.camera_height}`} disabled={!editable}
                    onChange={(e) => { const [w, h] = e.target.value.split("x").map(Number); setDraft({ ...draft, camera_width: w, camera_height: h }); }}>
                    {["320x240", "640x480", "800x600", "1280x720"].map((r) => <option key={r} value={r}>{r.replace("x", " × ")}</option>)}
                  </Select>
                </Field>
                <div className="sm:col-span-2">
                  <Toggle checked={draft.monitoring_enabled} disabled={!editable} onChange={(v) => set("monitoring_enabled", v)}
                    label="Monitoreo al iniciar" description="Si está activo, la captura comienza automáticamente al encender la Raspberry Pi." />
                </div>
              </div>
            </Card>
          )}

          {tab === "alerts" && <AlertsTab draft={draft} set={set} editable={editable} gpio={q.data.gpio} onHardware={() => setTab("hardware")} />}
          {tab === "hardware" && <HardwareTab draft={draft} set={set} editable={editable} dirty={dirty} canSilence={can("alerts.review")} />}
          {tab === "retention" && (
            <Card title="Periodos de conservación" icon={Database}>
              <div className="grid max-w-3xl gap-4 sm:grid-cols-3">
                <Field label="Eventos (días)" hint="Las alertas pendientes no se borran hasta revisarse.">
                  <Input type="number" min={1} max={3650} value={draft.retention_days_events} disabled={!editable} onChange={(e) => set("retention_days_events", Number(e.target.value))} />
                </Field>
                <Field label="Imágenes de alertas (días)" hint="Borrado seguro del archivo cifrado.">
                  <Input type="number" min={1} max={3650} value={draft.retention_days_snapshots} disabled={!editable} onChange={(e) => set("retention_days_snapshots", Number(e.target.value))} />
                </Field>
                <Field label="Autorizadas vencidas (días)" hint="Después se borra su biometría.">
                  <Input type="number" min={1} max={3650} value={draft.retention_days_expired_authorized} disabled={!editable} onChange={(e) => set("retention_days_expired_authorized", Number(e.target.value))} />
                </Field>
                <Field label="Auditoría (días)" hint="Mínimo 30 días.">
                  <Input type="number" min={30} max={3650} value={draft.retention_days_audit} disabled={!editable} onChange={(e) => set("retention_days_audit", Number(e.target.value))} />
                </Field>
              </div>
              <p className="mt-4 max-w-3xl text-xs leading-relaxed text-ink-300">
                La limpieza automática se ejecuta cada hora. También desactiva los registros de la lista de alerta cuya fecha de revisión venció.
                El sistema nunca guarda imágenes de personas sin coincidencia.
              </p>
            </Card>
          )}
          {tab === "system" && <SystemTab canControl={can("system.control")} />}
          {tab === "demo" && <DemoTab demoMode={q.data.values.demo_mode} editable={editable} onToggle={(v) => save.mutate({ demo_mode: v })} />}
        </div>
      </div>
    </>
  );
}

function AlertsTab({ draft, set, editable, gpio, onHardware }: {
  draft: Settings; set: <K extends keyof Settings>(k: K, v: Settings[K]) => void; editable: boolean; gpio: GpioStatus; onHardware: () => void;
}) {
  return (
    <div className="space-y-4">
      <Card title="Notificaciones" icon={BellRing}>
        <Toggle checked={draft.alert_sound} disabled={!editable} onChange={(v) => set("alert_sound", v)}
          label="Aviso sonoro en el panel" description="Suena en el navegador al llegar una alerta." />
        <Toggle checked={draft.alerts_enabled} disabled={!editable} onChange={(v) => set("alerts_enabled", v)}
          label="Alertas activas" description="Si se desactivan, las coincidencias se registran en el historial pero no generan notificación, LED ni buzzer." />
      </Card>
      <Card title="LED rojo y buzzer" icon={Cpu}
        actions={<>{gpio.mode === "hardware" ? <Badge tone="green">Hardware conectado</Badge> : gpio.mode === "error" ? <Badge tone="red">Error de hardware</Badge> : <Badge tone="amber">Modo simulado</Badge>}
          <Button size="sm" onClick={onHardware}>Abrir Hardware & Alarm Settings</Button></>}>
        <p className="text-xs text-ink-300">Pines, duraciones, tipo de buzzer, pruebas de diagnóstico e historial de activaciones.</p>
      </Card>
    </div>
  );
}

function SystemTab({ canControl }: { canControl: boolean }) {
  const toast = useToast();
  const info = useQuery({ queryKey: ["sysinfo"], queryFn: () => get<SysInfo>("/api/system/info"), refetchInterval: 10000 });
  const logs = useQuery({ queryKey: ["syslogs"], queryFn: () => get<{ lines: string[] }>("/api/system/logs?lines=150"), enabled: canControl });
  const restart = useMutation({
    mutationFn: () => post<{ engine_ready: boolean; gallery_size: number; error: string | null }>("/api/system/engine/restart"),
    onSuccess: (r) => toast({ kind: r.engine_ready ? "success" : "error", title: r.engine_ready ? "Motor reiniciado" : "El motor no pudo cargarse", body: r.error ?? `${r.gallery_size} plantillas cargadas.` }),
  });
  const retention = useMutation({
    mutationFn: () => post<Record<string, number>>("/api/system/retention/run"),
    onSuccess: (r) => toast({ kind: "success", title: "Limpieza ejecutada", body: `Eventos: ${r.events_deleted} · imágenes: ${r.snapshots_deleted} · registros vencidos: ${r.entries_expired}` }),
  });
  const d = info.data;
  return (
    <div className="space-y-4">
      <Card title="Raspberry Pi" icon={HardDrive}
        actions={canControl && <>
          <Button size="sm" icon={RefreshCw} loading={restart.isPending} onClick={() => restart.mutate()}>Reiniciar motor facial</Button>
          <Button size="sm" icon={Trash2} loading={retention.isPending} onClick={() => retention.mutate()}>Ejecutar limpieza</Button>
        </>}>
        {!d ? <Spinner /> : (
          <dl className="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2 xl:grid-cols-3">
            {[
              ["Modelo", d.device.model], ["Sistema operativo", d.device.os], ["Arquitectura", d.device.arch],
              ["Nombre de equipo", d.device.hostname], ["Python", d.device.python], ["FaceGuard AI", `v${d.app_version}`],
              ["CPU", `${d.status.cpu_count} núcleos · ${d.status.cpu_percent.toFixed(0)} % · carga ${d.status.load_avg.join(" / ")}`],
              ["Memoria", `${d.status.ram_used_mb} / ${d.status.ram_total_mb} MB (${d.status.ram_percent} %)`],
              ["Temperatura", d.status.temperature_c != null ? `${d.status.temperature_c} °C` : "No disponible"],
              ["Disco libre", `${d.status.disk_free_gb} GB (${d.status.disk_percent} % usado)`],
              ["Encendido", fmtUptime(d.status.uptime_s)],
              ["Estado de energía (throttled)", d.device.throttled ?? "No disponible"],
              ["Motor", `${d.engine.label} · ${d.engine.models}`],
              ["Base de datos", `SQLite · ${d.db_size_kb} KB`],
              ["Ruta de la base de datos", d.storage.db_path],
              ["Carpeta de imágenes", d.storage.media_dir],
              ["Espacio libre", `${d.storage.free_gb} GB de ${d.storage.total_gb} GB`],
              ["Migraciones", d.migrations.map((m) => `${m.version} (${fmtDateTime(m.applied_at)})`).join(", ")],
            ].map(([k, v]) => (
              <div key={k}><dt className="text-[11px] uppercase tracking-wider text-ink-400">{k}</dt><dd className="mt-0.5 break-words text-ink-100">{v}</dd></div>
            ))}
          </dl>
        )}
        <div className="mt-3"><ErrorNote error={restart.error ?? retention.error} /></div>
      </Card>
      {canControl && (
        <Card title="Registro del sistema" icon={Server} actions={<Button size="sm" variant="ghost" icon={RefreshCw} onClick={() => logs.refetch()}>Actualizar</Button>}>
          <pre className="max-h-[420px] overflow-auto rounded-lg border border-ink-700 bg-black/60 p-3 font-mono text-[11px] leading-relaxed text-ink-200">
            {logs.data?.lines.length ? logs.data.lines.join("") : "Sin registros."}
          </pre>
        </Card>
      )}
    </div>
  );
}

function DemoTab({ demoMode, editable, onToggle }: { demoMode: boolean; editable: boolean; onToggle: (v: boolean) => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const { can } = useAuth();
  const [confirmClear, setConfirmClear] = useState(false);
  const invalidate = () => ["blacklist", "events", "alerts", "summary", "activity"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
  const seed = useMutation({
    mutationFn: () => post<{ blacklist: number; events: number }>("/api/demo/seed"),
    onSuccess: (r) => { invalidate(); toast({ kind: "success", title: "Datos de demostración cargados", body: `${r.blacklist} registros ficticios y ${r.events} eventos simulados.` }); },
  });
  const clear = useMutation({
    mutationFn: () => post<{ blacklist: number; events: number }>("/api/demo/clear"),
    onSuccess: (r) => { invalidate(); setConfirmClear(false); toast({ kind: "success", title: "Datos simulados eliminados", body: `${r.blacklist} registros y ${r.events} eventos.` }); },
  });
  const alert = useMutation({ mutationFn: () => post("/api/demo/alert") });
  return (
    <Card title="Modo demostración" icon={FlaskConical}>
      <div className="max-w-3xl space-y-5">
        <p className="text-sm leading-relaxed text-ink-300">
          Permite presentar y probar todas las pantallas sin cámara ni personas reales. El video se reemplaza por siluetas generadas,
          las detecciones son simuladas y todo dato creado se marca como <Badge tone="violet">SIMULADO</Badge>. Los registros ficticios no
          tienen plantilla biométrica, por lo que nunca coinciden con personas reales.
        </p>
        <div className="rounded-lg border border-ink-700 p-4">
          <Toggle checked={demoMode} disabled={!editable} onChange={onToggle} label="Video y detecciones simuladas"
            description={editable ? "Reemplaza la cámara USB por la fuente simulada." : "Solo el superadministrador puede activarlo."} />
        </div>
        {can("demo.control") && (
          <div className="flex flex-wrap gap-2">
            <Button variant="primary" icon={Database} loading={seed.isPending} onClick={() => seed.mutate()}>Cargar registros y eventos ficticios</Button>
            <Button icon={BellRing} loading={alert.isPending} onClick={() => alert.mutate()}>Generar alerta de prueba</Button>
            <Button variant="danger" icon={Trash2} onClick={() => setConfirmClear(true)}>Eliminar datos simulados</Button>
          </div>
        )}
        <ErrorNote error={seed.error ?? clear.error ?? alert.error} />
      </div>
      <ConfirmDialog open={confirmClear} danger title="Eliminar datos simulados" confirmLabel="Eliminar" loading={clear.isPending}
        onClose={() => setConfirmClear(false)} onConfirm={() => clear.mutate()}
        message="Se eliminarán todos los registros y eventos marcados como SIMULADO. Los datos reales no se modifican." />
    </Card>
  );
}
