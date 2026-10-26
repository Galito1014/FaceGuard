import { useEffect, useState } from "react";
import { CameraOff, Loader2, ScanFace } from "lucide-react";
import clsx from "clsx";
import type { LiveStatus } from "@/lib/types";

/** Video MJPEG con recuadros de detección dibujados por el backend. */
export default function LiveVideo({ status, compact }: { status: LiveStatus | null; compact?: boolean }) {
  const connected = !!status?.camera.connected;
  const [key, setKey] = useState(0);
  const [loaded, setLoaded] = useState(false);

  // Reabre la transmisión cuando la cámara se reconecta.
  useEffect(() => {
    if (connected) {
      setLoaded(false);
      setKey((k) => k + 1);
    }
  }, [connected, status?.camera.resolution, status?.camera.synthetic]);

  return (
    <div className={clsx("relative overflow-hidden rounded-lg border border-ink-700 bg-black", compact ? "aspect-video" : "aspect-[4/3] lg:aspect-video")}>
      {connected ? (
        <>
          <img
            key={key}
            src={`/api/camera/stream?k=${key}`}
            alt="Transmisión en vivo de la cámara"
            onLoad={() => setLoaded(true)}
            onError={() => setTimeout(() => setKey((k) => k + 1), 2000)}
            className="h-full w-full object-contain"
          />
          {!loaded && <div className="absolute inset-0 grid place-items-center"><Loader2 className="h-6 w-6 animate-spin text-volt-400" /></div>}
          <div className="pointer-events-none absolute inset-x-0 h-px animate-scan bg-gradient-to-r from-transparent via-volt-400/50 to-transparent" />
          <div className="absolute left-3 top-3 flex items-center gap-2 rounded-md bg-black/60 px-2 py-1 text-[11px] font-semibold text-white backdrop-blur">
            <span className="h-2 w-2 animate-pulse rounded-full bg-alert-500" /> EN VIVO
            {status?.camera.synthetic && <span className="text-fuchsia-300">· SIMULADO</span>}
          </div>
          <div className="absolute bottom-3 right-3 flex items-center gap-1.5 rounded-md bg-black/60 px-2 py-1 font-mono text-[11px] text-ink-100 backdrop-blur">
            <ScanFace className="h-3.5 w-3.5 text-volt-400" /> {status?.engine.faces_now ?? 0} · {status?.engine.processing_fps ?? 0} FPS
          </div>
        </>
      ) : (
        <div className="grid-bg absolute inset-0 flex flex-col items-center justify-center gap-2 text-center">
          <CameraOff className="h-8 w-8 text-ink-400" />
          <p className="text-sm font-medium text-ink-200">{status?.camera.running ? "Sin señal de la cámara" : "Monitoreo detenido"}</p>
          <p className="max-w-xs text-xs text-ink-400">
            {status?.camera.running ? `${status.camera.error ?? "Reintentando conexión…"} (reintentos: ${status.camera.reconnects})` : "Inicie el monitoreo para ver la transmisión."}
          </p>
        </div>
      )}
    </div>
  );
}
