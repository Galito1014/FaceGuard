// Conexión WebSocket: estado en vivo + invalidación automática de datos (sin recargar la página).
import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { useAuth } from "./auth";
import { useToast } from "./toast";
import { LEVEL_LABEL, fmtScore } from "./format";
import type { FGEvent, LiveStatus } from "./types";

interface RT {
  connected: boolean;
  status: LiveStatus | null;
  lastAlert: FGEvent | null;
}
const Ctx = createContext<RT>({ connected: false, status: null, lastAlert: null });

export function RealtimeProvider({ children }: { children: ReactNode }) {
  const { me } = useAuth();
  const qc = useQueryClient();
  const toast = useToast();
  const navigate = useNavigate();
  const [connected, setConnected] = useState(false);
  const [status, setStatus] = useState<LiveStatus | null>(null);
  const [lastAlert, setLastAlert] = useState<FGEvent | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!me || me.must_change_password) return;
    let stop = false;
    let retry = 1000;
    let ping: number | undefined;
    let timer: number | undefined;

    const connect = () => {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      const ws = new WebSocket(`${proto}://${location.host}/ws`);
      wsRef.current = ws;
      ws.onopen = () => {
        setConnected(true);
        retry = 1000;
        ping = window.setInterval(() => ws.readyState === 1 && ws.send("ping"), 25000);
      };
      ws.onmessage = (msg) => {
        const { type, data } = JSON.parse(msg.data);
        switch (type) {
          case "status":
            setStatus(data);
            break;
          case "camera":
            qc.invalidateQueries({ queryKey: ["camera"] });
            break;
          case "event":
            qc.invalidateQueries({ queryKey: ["events"] });
            qc.invalidateQueries({ queryKey: ["summary"] });
            qc.invalidateQueries({ queryKey: ["activity"] });
            break;
          case "alert": {
            const ev = data as FGEvent;
            setLastAlert(ev);
            qc.invalidateQueries({ queryKey: ["alerts"] });
            toast({
              kind: "alert",
              title: `${ev.is_simulated ? "[SIMULADO] " : ""}Posible coincidencia · nivel ${LEVEL_LABEL[ev.level ?? "bajo"]}`,
              body: `${ev.entry_name ?? "Registro"} — similitud ${fmtScore(ev.score)}. Requiere revisión humana.`,
              action: { label: "Revisar alerta", onClick: () => navigate(`/alertas?id=${ev.id}`) },
            });
            break;
          }
          case "alert_updated":
            qc.invalidateQueries({ queryKey: ["alerts"] });
            qc.invalidateQueries({ queryKey: ["events"] });
            qc.invalidateQueries({ queryKey: ["summary"] });
            break;
          case "settings":
            qc.invalidateQueries({ queryKey: ["settings"] });
            break;
        }
      };
      ws.onclose = (e) => {
        setConnected(false);
        window.clearInterval(ping);
        if (stop || e.code === 4401) return;
        timer = window.setTimeout(connect, retry);
        retry = Math.min(retry * 2, 15000);
      };
    };
    connect();
    return () => {
      stop = true;
      window.clearTimeout(timer);
      window.clearInterval(ping);
      wsRef.current?.close();
    };
  }, [me, qc, toast, navigate]);

  return <Ctx.Provider value={{ connected, status, lastAlert }}>{children}</Ctx.Provider>;
}

export const useRealtime = () => useContext(Ctx);
