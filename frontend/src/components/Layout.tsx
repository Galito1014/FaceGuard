import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import clsx from "clsx";
import {
  Bell, Cctv, FileClock, FlaskConical, KeyRound, LayoutDashboard, LogOut, Menu, ScrollText, Settings, ShieldAlert,
  Siren, Thermometer, UserCog, Wifi, WifiOff, X,
} from "lucide-react";
import { useAuth } from "@/lib/auth";
import { useRealtime } from "@/lib/realtime";
import Logo from "./Logo";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, perm: "dashboard.view", end: true },
  { to: "/monitoreo", label: "Monitoreo en vivo", icon: Cctv, perm: "camera.view" },
  { to: "/alertas", label: "Alertas", icon: Siren, perm: "alerts.view", badge: true },
  { to: "/lista", label: "Lista de alerta", icon: ShieldAlert, perm: "blacklist.view" },
  { to: "/historial", label: "Historial", icon: FileClock, perm: "events.view" },
  { section: "Administración" },
  { to: "/usuarios", label: "Usuarios", icon: UserCog, perm: "users.manage" },
  { to: "/auditoria", label: "Auditoría", icon: ScrollText, perm: "audit.view" },
  { to: "/configuracion", label: "Configuración", icon: Settings, perm: "settings.view" },
] as const;

function Clock() {
  const [now, setNow] = useState(new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  return (
    <div className="hidden text-right leading-tight md:block">
      <p className="font-mono text-sm font-semibold tabular-nums text-white">{now.toLocaleTimeString("es-BO", { hour12: false })}</p>
      <p className="text-[11px] capitalize text-ink-300">{now.toLocaleDateString("es-BO", { weekday: "long", day: "numeric", month: "long" })}</p>
    </div>
  );
}

export default function Layout() {
  const { me, logout, can } = useAuth();
  const { connected, status } = useRealtime();
  const [open, setOpen] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();
  useEffect(() => setOpen(false), [location.pathname]);

  const pending = status?.pending_alerts ?? 0;
  const temp = status?.system.temperature_c;

  const sidebar = (
    <aside className="flex h-full w-64 flex-col border-r border-ink-700/80 bg-ink-900/95 backdrop-blur">
      <div className="flex h-16 items-center gap-2.5 border-b border-ink-700/80 px-5">
        <Logo className="h-8 w-8" />
        <div>
          <p className="text-[15px] font-bold tracking-tight text-white">FaceGuard <span className="text-volt-400">AI</span></p>
          <p className="text-[10px] uppercase tracking-[0.18em] text-ink-400">Security Operations</p>
        </div>
      </div>
      <nav className="flex-1 space-y-0.5 overflow-y-auto px-3 py-4">
        {NAV.map((item, i) => {
          if ("section" in item) {
            return <p key={i} className="px-3 pb-1.5 pt-5 text-[10px] font-semibold uppercase tracking-[0.18em] text-ink-400">{item.section}</p>;
          }
          if (!can(item.perm)) return null;
          const Icon = item.icon;
          return (
            <NavLink
              key={item.to}
              to={item.to}
              end={"end" in item}
              className={({ isActive }) =>
                clsx(
                  "group relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition",
                  isActive ? "bg-volt-500/10 text-white" : "text-ink-300 hover:bg-ink-750 hover:text-ink-100",
                )
              }
            >
              {({ isActive }) => (
                <>
                  {isActive && <span className="absolute left-0 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-r bg-volt-500 shadow-glow" />}
                  <Icon className={clsx("h-[18px] w-[18px]", isActive ? "text-volt-400" : "text-ink-400 group-hover:text-ink-200")} />
                  <span className="flex-1">{item.label}</span>
                  {"badge" in item && pending > 0 && (
                    <span className="rounded-full bg-alert-500 px-1.5 py-px font-mono text-[10px] font-bold text-white">{pending}</span>
                  )}
                </>
              )}
            </NavLink>
          );
        })}
      </nav>
      <div className="border-t border-ink-700/80 p-3">
        <div className="flex items-center gap-3 rounded-lg bg-ink-800 px-3 py-2.5">
          <div className="grid h-8 w-8 place-items-center rounded-full bg-volt-500/15 text-sm font-bold text-volt-300">
            {me?.full_name.slice(0, 1).toUpperCase()}
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium text-white">{me?.full_name}</p>
            <p className="truncate text-[11px] text-ink-300">{me?.role_label}</p>
          </div>
        </div>
        <div className="mt-2 grid grid-cols-2 gap-1.5">
          <button onClick={() => navigate("/cuenta")} className="flex items-center justify-center gap-1.5 rounded-md py-1.5 text-xs text-ink-300 hover:bg-ink-750 hover:text-white">
            <KeyRound className="h-3.5 w-3.5" /> Contraseña
          </button>
          <button onClick={logout} className="flex items-center justify-center gap-1.5 rounded-md py-1.5 text-xs text-ink-300 hover:bg-alert-500/10 hover:text-alert-400">
            <LogOut className="h-3.5 w-3.5" /> Salir
          </button>
        </div>
      </div>
    </aside>
  );

  return (
    <div className="flex h-full">
      <div className="fixed inset-y-0 left-0 z-30 hidden lg:block">{sidebar}</div>
      {open && (
        <div className="fixed inset-0 z-40 bg-black/60 lg:hidden" onClick={() => setOpen(false)}>
          <div className="h-full w-64 animate-slide-in" onClick={(e) => e.stopPropagation()}>{sidebar}</div>
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col lg:pl-64">
        {status?.demo_mode && (
          <div className="flex items-center justify-center gap-2 border-b border-fuchsia-500/30 bg-fuchsia-500/10 px-4 py-1.5 text-xs font-medium text-fuchsia-200">
            <FlaskConical className="h-3.5 w-3.5" />
            MODO DEMOSTRACIÓN ACTIVO — el video y las detecciones nuevas son simulados y se marcan como SIMULADO.
          </div>
        )}
        <header className="sticky top-0 z-20 flex h-16 items-center gap-3 border-b border-ink-700/80 bg-ink-950/80 px-4 backdrop-blur lg:px-6">
          <button className="rounded-md p-2 text-ink-200 hover:bg-ink-750 lg:hidden" onClick={() => setOpen(true)} aria-label="Menú">
            {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
          <div className="flex flex-1 flex-wrap items-center gap-x-5 gap-y-1 text-xs">
            <span className={clsx("inline-flex items-center gap-1.5", connected ? "text-ok-400" : "text-alert-400")}>
              {connected ? <Wifi className="h-3.5 w-3.5" /> : <WifiOff className="h-3.5 w-3.5" />}
              {connected ? "Tiempo real conectado" : "Reconectando…"}
            </span>
            {status && (
              <>
                <span className={clsx("hidden items-center gap-1.5 sm:inline-flex", status.camera.connected ? "text-ink-200" : "text-alert-400")}>
                  <Cctv className="h-3.5 w-3.5" />
                  {status.camera.connected ? (status.camera.synthetic ? "Cámara simulada" : "Cámara en línea") : status.camera.running ? "Cámara sin señal" : "Monitoreo detenido"}
                </span>
                {temp != null && (
                  <span className={clsx("hidden items-center gap-1.5 sm:inline-flex",
                    status.system.temperature_status === "normal" ? "text-ink-200" : "text-warn-400")}>
                    <Thermometer className="h-3.5 w-3.5" /> {temp.toFixed(1)} °C
                  </span>
                )}
              </>
            )}
          </div>
          <Clock />
          <button
            onClick={() => navigate("/alertas?status=pendiente")}
            className={clsx("relative rounded-lg border p-2 transition",
              pending ? "border-alert-500/50 bg-alert-500/10 text-alert-400 animate-pulse-ring" : "border-ink-600 text-ink-300 hover:text-white")}
            aria-label="Alertas pendientes"
            title={`${pending} alertas pendientes de revisión`}
          >
            <Bell className="h-4 w-4" />
            {pending > 0 && (
              <span className="absolute -right-1.5 -top-1.5 rounded-full bg-alert-500 px-1.5 font-mono text-[10px] font-bold text-white">{pending}</span>
            )}
          </button>
        </header>
        <main className="flex-1 px-4 py-6 lg:px-6">
          <Outlet />
        </main>
        <footer className="border-t border-ink-800 px-6 py-3 text-[11px] text-ink-400">
          FaceGuard AI v1.0 · Procesamiento 100 % local · Toda coincidencia es preliminar y requiere revisión humana.
        </footer>
      </div>
    </div>
  );
}
