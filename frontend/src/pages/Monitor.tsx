import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Camera, Cctv, Gauge, MonitorPlay, Play, Square, Timer } from "lucide-react";
import { get, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useRealtime } from "@/lib/realtime";
import { useToast } from "@/lib/toast";
import type { CameraStatus, EngineStatus } from "@/lib/types";
import { Badge, Button, Card, ErrorNote, Field, Modal, PageHeader, Select, StatusDot, Textarea } from "@/components/ui";
import LiveVideo from "@/components/LiveVideo";

interface CamResp { camera: CameraStatus; engine: EngineStatus; devices: { index: number; path: string; name: string }[]; resolutions: string[] }

function Metric({ label, value, icon: Icon }: { label: string; value: React.ReactNode; icon: React.ElementType }) {
  return (
    <div className="rounded-lg border border-ink-700 bg-ink-900/60 p-3">
      <p className="flex items-center gap-1.5 text-[11px] uppercase tracking-wider text-ink-300"><Icon className="h-3.5 w-3.5" /> {label}</p>
      <p className="mt-1 font-mono text-lg font-semibold tabular-nums text-white">{value}</p>
    </div>
  );
}

export default function MonitorPage() {
  const { can } = useAuth();
  const { status } = useRealtime();
  const qc = useQueryClient();
  const toast = useToast();
  const cam = useQuery({ queryKey: ["camera"], queryFn: () => get<CamResp>("/api/camera/status"), refetchInterval: 10000 });
  const [captureOpen, setCaptureOpen] = useState(false);
  const [reason, setReason] = useState("");

  const live = status ?? (cam.data ? { camera: cam.data.camera, engine: cam.data.engine } : null);
  const camera = live?.camera;
  const engine = live?.engine;

  const toggle = useMutation({
    mutationFn: (start: boolean) => post(start ? "/api/camera/start" : "/api/camera/stop"),
    onSuccess: (_, start) => {
      qc.invalidateQueries({ queryKey: ["camera"] });
      toast({ kind: "info", title: start ? "Monitoreo iniciado" : "Monitoreo detenido" });
    },
    onError: (e) => toast({ kind: "error", title: "No se pudo cambiar el monitoreo", body: String((e as Error).message) }),
  });
  const resolution = useMutation({
    mutationFn: (r: string) => post("/api/camera/resolution", { resolution: r }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["camera"] }); toast({ kind: "success", title: "Resolución actualizada", body: "La cámara se reinició con la nueva resolución." }); },
    onError: (e) => toast({ kind: "error", title: "Error", body: (e as Error).message }),
  });
  const capture = useMutation({
    mutationFn: () => post<{ uid: string }>("/api/camera/capture", { reason }),
    onSuccess: (r) => { setCaptureOpen(false); setReason(""); toast({ kind: "success", title: "Captura guardada (cifrada)", body: `Evento ${r.uid} · registrada en auditoría.` }); },
  });

  return (
    <>
      <PageHeader title="Monitoreo en vivo" subtitle="Transmisión de la cámara USB con detección facial en tiempo real" icon={MonitorPlay}
        actions={can("camera.control") && (
          camera?.running
            ? <Button variant="danger" icon={Square} loading={toggle.isPending} onClick={() => toggle.mutate(false)}>Detener monitoreo</Button>
            : <Button variant="primary" icon={Play} loading={toggle.isPending} onClick={() => toggle.mutate(true)}>Iniciar monitoreo</Button>
        )} />

      <div className="grid gap-4 xl:grid-cols-4">
        <div className="xl:col-span-3">
          <Card bodyClass="p-3">
            <LiveVideo status={status} />
            <div className="mt-3 flex flex-wrap items-center justify-between gap-3 px-1">
              <div className="flex flex-wrap items-center gap-4 text-xs text-ink-300">
                <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-[#3cc85a]" /> Sin coincidencia</span>
                <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-[#ffaa00]" /> Verificando (confirmación temporal)</span>
                <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-[#eb2828]" /> Posible coincidencia</span>
              </div>
              {can("camera.capture") && (
                <Button size="sm" icon={Camera} disabled={!camera?.connected} onClick={() => setCaptureOpen(true)}>Captura autorizada</Button>
              )}
            </div>
          </Card>
        </div>

        <div className="space-y-4">
          <Card title="Procesamiento" icon={Gauge}>
            <div className="mb-3 flex items-center justify-between">
              <StatusDot ok={engine?.state === "activo" || engine?.state === "demo"} warn={engine?.state !== "error"} label={engine?.label ?? "—"} />
              {engine?.running && <Badge tone="volt">Procesando</Badge>}
            </div>
            <div className="grid grid-cols-2 gap-2">
              <Metric label="Rostros" value={engine?.faces_now ?? 0} icon={Cctv} />
              <Metric label="FPS análisis" value={engine?.processing_fps ?? 0} icon={Gauge} />
              <Metric label="FPS cámara" value={camera?.capture_fps ?? 0} icon={MonitorPlay} />
              <Metric label="Latencia" value={`${engine?.latency_ms ?? 0} ms`} icon={Timer} />
            </div>
            <p className="mt-3 text-[11px] leading-relaxed text-ink-400">Modelos: {engine?.models}. Plantillas activas en memoria: {engine?.gallery_size ?? 0}.</p>
          </Card>

          <Card title="Cámara" icon={Cctv}>
            <div className="space-y-3">
              <StatusDot ok={!!camera?.connected} warn={!camera?.running}
                label={camera?.connected ? (camera.synthetic ? "Fuente simulada" : `Conectada (/dev/video${camera.index})`) : camera?.running ? "Desconectada" : "Detenida"} />
              {camera?.error && camera.running && <ErrorNote error={camera.error} />}
              <Field label="Resolución" hint="Menor resolución = menos carga de CPU en la Raspberry Pi.">
                <Select value={camera?.resolution ?? ""} disabled={!can("camera.control") || resolution.isPending}
                  onChange={(e) => resolution.mutate(e.target.value)}>
                  {cam.data?.resolutions.map((r) => <option key={r} value={r}>{r.replace("x", " × ")}</option>)}
                </Select>
              </Field>
              <div className="text-xs text-ink-300">
                <p className="mb-1 font-medium text-ink-200">Dispositivos detectados</p>
                {cam.data?.devices.length ? cam.data.devices.map((d) => <p key={d.path} className="font-mono">{d.path} · {d.name}</p>)
                  : <p className="text-ink-400">Ningún /dev/video* en este equipo.</p>}
              </div>
              <p className="text-[11px] text-ink-400">Reconexiones automáticas: {camera?.reconnects ?? 0}</p>
            </div>
          </Card>
        </div>
      </div>

      <Modal open={captureOpen} onClose={() => setCaptureOpen(false)} title="Captura autorizada"
        footer={<>
          <Button variant="ghost" onClick={() => setCaptureOpen(false)}>Cancelar</Button>
          <Button variant="primary" icon={Camera} loading={capture.isPending} disabled={reason.trim().length < 5} onClick={() => capture.mutate()}>Guardar captura</Button>
        </>}>
        <p className="mb-4 text-sm text-ink-300">La imagen se guarda cifrada, con su usuario y motivo, y se elimina automáticamente al vencer el periodo de conservación.</p>
        <Field label="Motivo de la captura" required hint="Ej.: incidente reportado por residente del departamento 4B.">
          <Textarea value={reason} onChange={(e) => setReason(e.target.value)} maxLength={300} />
        </Field>
        <div className="mt-3"><ErrorNote error={capture.error} /></div>
      </Modal>
    </>
  );
}
