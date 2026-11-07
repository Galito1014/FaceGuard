import { useEffect, useState, type FormEvent } from "react";
import {
  ArrowLeft, ArrowRight, Bell, Camera, CheckCircle2, Database, KeyRound, Lock, ScanFace, ShieldCheck, User,
} from "lucide-react";
import clsx from "clsx";
import { post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Button, ErrorNote, Field, Input, Select, Toggle } from "@/components/ui";
import Logo from "@/components/Logo";

export interface SetupStatus {
  needs_setup: boolean;
  code_required?: boolean;
  edition: "desktop" | "pi" | "server";
  version: string;
  defaults?: Record<string, number | boolean>;
}

interface Cam { index: number; path: string; name: string }

const STEPS = [
  { title: "Cuenta administradora", icon: User },
  { title: "Cámara", icon: Camera },
  { title: "Reconocimiento facial", icon: ScanFace },
  { title: "Base de datos", icon: Database },
  { title: "Alertas", icon: Bell },
  { title: "Privacidad", icon: ShieldCheck },
  { title: "Listo", icon: CheckCircle2 },
];

const PRESETS = [
  { value: 0.48, label: "Estricto", text: "Menos falsas coincidencias; puede no reconocer fotos de baja calidad." },
  { value: 0.42, label: "Equilibrado (recomendado)", text: "Umbral calibrado en las pruebas del proyecto." },
  { value: 0.38, label: "Sensible", text: "Reconoce más, pero habrá más alertas que revisar." },
];

const RESOLUTIONS = [
  [640, 480, "640 × 480 (recomendado en Raspberry Pi)"],
  [1280, 720, "1280 × 720 (HD)"],
  [320, 240, "320 × 240 (mínimo consumo)"],
] as const;

export default function SetupPage({ status }: { status: SetupStatus }) {
  const { refresh } = useAuth();
  const d = status.defaults ?? {};
  const [step, setStep] = useState(0);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);
  const [code, setCode] = useState("");
  const [codeOk, setCodeOk] = useState(!status.code_required);
  const [cams, setCams] = useState<Cam[] | null>(null);
  const [account, setAccount] = useState({ username: "admin", full_name: "", password: "", confirm: "" });
  const [ack, setAck] = useState(false);
  const [s, setS] = useState({
    camera_index: Number(d.camera_index ?? 0),
    camera_width: Number(d.camera_width ?? 640),
    camera_height: Number(d.camera_height ?? 480),
    monitoring_enabled: d.monitoring_enabled !== false,
    match_threshold: Number(d.match_threshold ?? 0.42),
    confirm_frames: Number(d.confirm_frames ?? 2),
    retention_days_events: Number(d.retention_days_events ?? 30),
    retention_days_snapshots: Number(d.retention_days_snapshots ?? 15),
    alerts_enabled: d.alerts_enabled !== false,
    alert_sound: d.alert_sound !== false,
    gpio_enabled: status.edition === "pi" ? d.gpio_enabled !== false : false,
    update_check: false,
  });
  const set = <K extends keyof typeof s>(k: K, v: (typeof s)[K]) => setS((p) => ({ ...p, [k]: v }));

  const loadCameras = async (c = code) => {
    const r = await post<{ cameras: Cam[] }>("/api/setup/cameras", { setup_code: c || null });
    setCams(r.cameras);
  };

  useEffect(() => {
    if (codeOk && cams === null) loadCameras().catch(() => setCams([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [codeOk]);

  const verifyCode = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await loadCameras(code);
      setCodeOk(true);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  };

  const accountError = (() => {
    if (!/^[A-Za-z0-9_.-]{3,64}$/.test(account.username)) return "Use de 3 a 64 letras, números, punto, guion o guion bajo.";
    if (!account.full_name.trim()) return "Escriba su nombre.";
    if (account.password.length < 10 || !/\d/.test(account.password) || !/[A-Za-z]/.test(account.password))
      return "La contraseña debe tener al menos 10 caracteres y combinar letras y números.";
    if (account.password !== account.confirm) return "Las contraseñas no coinciden.";
    return null;
  })();

  const canNext = step === 0 ? !accountError : step === 5 ? ack : true;

  const finish = async () => {
    setError(null);
    setLoading(true);
    try {
      await post("/api/setup", {
        setup_code: code || null,
        username: account.username.trim(),
        full_name: account.full_name.trim(),
        password: account.password,
        privacy_ack: ack,
        settings: s,
      });
      await refresh();
    } catch (err) {
      setError(err);
      setLoading(false);
    }
  };

  const shell = (children: React.ReactNode) => (
    <div className="grid-bg relative grid min-h-full place-items-center overflow-auto px-4 py-10">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-volt-500/60 to-transparent" />
      <div className="w-full max-w-2xl animate-fade-in">
        <div className="mb-6 flex items-center gap-3">
          <Logo className="h-11 w-11 drop-shadow-[0_0_24px_rgba(31,139,255,.45)]" />
          <div>
            <h1 className="text-xl font-bold tracking-tight text-white">Configuración inicial de FaceGuard <span className="text-volt-400">AI</span></h1>
            <p className="text-xs text-ink-300">
              {status.edition === "desktop" ? "Desktop" : status.edition === "pi" ? "Raspberry Pi" : "Servidor"} · versión {status.version}
            </p>
          </div>
        </div>
        {children}
      </div>
    </div>
  );

  if (!codeOk) {
    return shell(
      <form onSubmit={verifyCode} className="panel space-y-4 p-6">
        <div className="flex items-start gap-3">
          <KeyRound className="mt-0.5 h-5 w-5 shrink-0 text-volt-400" />
          <div className="text-sm text-ink-200">
            <p className="font-medium text-white">Escriba el código de configuración</p>
            <p className="mt-1 text-ink-300">
              Lo mostró el instalador al terminar. También puede verlo en el equipo donde está instalado FaceGuard AI con:
            </p>
            <code className="mt-2 block rounded bg-ink-900 px-2 py-1.5 font-mono text-xs text-ink-100">sudo cat /var/lib/faceguard/secret/setup_code.txt</code>
          </div>
        </div>
        <Field label="Código de configuración">
          <Input icon={Lock} autoFocus value={code} onChange={(e) => setCode(e.target.value.toUpperCase())}
            placeholder="ABCD-EFGH" className="font-mono tracking-widest" required />
        </Field>
        <ErrorNote error={error} />
        <Button type="submit" variant="primary" icon={ArrowRight} loading={loading} className="w-full">Continuar</Button>
      </form>,
    );
  }

  const Icon = STEPS[step].icon;
  return shell(
    <div className="panel overflow-hidden">
      <ol className="flex border-b border-ink-700 bg-ink-850/60 px-2 py-2 text-[11px]" aria-label="Pasos">
        {STEPS.map((st, i) => (
          <li key={st.title} className={clsx("flex flex-1 items-center justify-center gap-1 rounded px-1 py-1",
            i === step ? "bg-volt-500/15 text-volt-300" : i < step ? "text-ok-400" : "text-ink-400")}
            aria-current={i === step ? "step" : undefined}>
            <span className="font-mono">{i + 1}</span>
            <span className="hidden md:inline">{st.title}</span>
          </li>
        ))}
      </ol>

      <div className="space-y-5 p-6">
        <h2 className="flex items-center gap-2 text-base font-semibold text-white">
          <Icon className="h-5 w-5 text-volt-400" /> {STEPS[step].title}
        </h2>

        {step === 0 && (
          <div className="grid gap-4 sm:grid-cols-2">
            <p className="text-sm text-ink-300 sm:col-span-2">
              Esta cuenta tendrá control total (superadministrador). Después podrá crear usuarios con menos permisos.
            </p>
            <Field label="Usuario" required>
              <Input icon={User} value={account.username} autoComplete="username"
                onChange={(e) => setAccount({ ...account, username: e.target.value })} />
            </Field>
            <Field label="Nombre completo" required>
              <Input value={account.full_name} onChange={(e) => setAccount({ ...account, full_name: e.target.value })} />
            </Field>
            <Field label="Contraseña" required hint="Mínimo 10 caracteres, con letras y números.">
              <Input icon={Lock} type="password" autoComplete="new-password" value={account.password}
                onChange={(e) => setAccount({ ...account, password: e.target.value })} />
            </Field>
            <Field label="Repita la contraseña" required>
              <Input icon={Lock} type="password" autoComplete="new-password" value={account.confirm}
                onChange={(e) => setAccount({ ...account, confirm: e.target.value })} />
            </Field>
            {account.password && accountError && <p className="text-xs text-warn-400 sm:col-span-2">{accountError}</p>}
          </div>
        )}

        {step === 1 && (
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Cámara" hint={cams && cams.length === 0 ? "No se detectó ninguna cámara. Conéctela y pulse “Buscar de nuevo”, o continúe y elíjala luego en Configuración." : "Webcam integrada o cámara USB."}>
              <Select value={s.camera_index} onChange={(e) => set("camera_index", Number(e.target.value))}>
                {[...new Set([s.camera_index, ...(cams ?? []).map((c) => c.index)])].sort().map((i) => {
                  const cam = cams?.find((c) => c.index === i);
                  return <option key={i} value={i}>{cam ? `${cam.path} · ${cam.name}` : `Cámara ${i} (no detectada)`}</option>;
                })}
              </Select>
            </Field>
            <Field label="Resolución">
              <Select value={`${s.camera_width}x${s.camera_height}`} onChange={(e) => {
                const [w, h] = e.target.value.split("x").map(Number);
                setS((p) => ({ ...p, camera_width: w, camera_height: h }));
              }}>
                {RESOLUTIONS.map(([w, h, label]) => <option key={label} value={`${w}x${h}`}>{label}</option>)}
              </Select>
            </Field>
            <div className="sm:col-span-2 flex items-center justify-between gap-3">
              <Toggle checked={s.monitoring_enabled} onChange={(v) => set("monitoring_enabled", v)}
                label="Iniciar el monitoreo al terminar" description="Puede pausarlo cuando quiera desde Monitoreo en vivo." />
            </div>
            <Button variant="ghost" size="sm" icon={Camera} onClick={() => loadCameras().catch(setError)}>Buscar de nuevo</Button>
          </div>
        )}

        {step === 2 && (
          <div className="space-y-3">
            <p className="text-sm text-ink-300">
              El reconocimiento compara cada rostro con las fotos registradas y calcula una similitud. Elija qué tan exigente debe ser.
            </p>
            {PRESETS.map((p) => (
              <label key={p.value} className={clsx("flex cursor-pointer items-start gap-3 rounded-lg border p-3 transition",
                s.match_threshold === p.value ? "border-volt-500 bg-volt-500/10" : "border-ink-600 hover:border-ink-500")}>
                <input type="radio" name="preset" className="mt-1 accent-volt-500" checked={s.match_threshold === p.value}
                  onChange={() => set("match_threshold", p.value)} />
                <span>
                  <span className="block text-sm font-medium text-ink-100">{p.label} <span className="font-mono text-xs text-ink-400">umbral {p.value}</span></span>
                  <span className="block text-xs text-ink-300">{p.text}</span>
                </span>
              </label>
            ))}
            <Field label="Fotogramas para confirmar una coincidencia" hint="Más fotogramas = menos falsas alarmas, alerta un poco más lenta.">
              <Select value={s.confirm_frames} onChange={(e) => set("confirm_frames", Number(e.target.value))}>
                {[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n}</option>)}
              </Select>
            </Field>
          </div>
        )}

        {step === 3 && (
          <div className="space-y-4">
            <p className="text-sm text-ink-300">
              Los datos se guardan solo en este equipo, en una base de datos SQLite. Las plantillas biométricas se guardan cifradas.
              Nada se envía a servicios externos. La base de datos se crea automáticamente al terminar.
            </p>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Conservar el historial de eventos (días)" hint="Pasado este plazo se borran automáticamente.">
                <Input type="number" min={1} max={3650} value={s.retention_days_events}
                  onChange={(e) => set("retention_days_events", Number(e.target.value))} />
              </Field>
              <Field label="Conservar las capturas de alertas (días)">
                <Input type="number" min={1} max={3650} value={s.retention_days_snapshots}
                  onChange={(e) => set("retention_days_snapshots", Number(e.target.value))} />
              </Field>
            </div>
          </div>
        )}

        {step === 4 && (
          <div className="space-y-4">
            <Toggle checked={s.alerts_enabled} onChange={(v) => set("alerts_enabled", v)} label="Generar alertas"
              description="Avisa cuando un rostro se parece a una persona de la lista de alerta." />
            <Toggle checked={s.alert_sound} onChange={(v) => set("alert_sound", v)} label="Sonido en el panel"
              description="Reproduce un aviso sonoro en el navegador o en la ventana de FaceGuard AI." />
            {status.edition === "pi" && (
              <Toggle checked={s.gpio_enabled} onChange={(v) => set("gpio_enabled", v)} label="LED y buzzer (GPIO)"
                description="LED rojo en GPIO17 y buzzer en GPIO27. Si no están conectados, el sistema los simula." />
            )}
            <p className="rounded-lg border border-warn-500/30 bg-warn-500/10 p-3 text-xs text-ink-100">
              Una alerta es una <b>posible coincidencia</b>, no una identificación. Una persona debe revisarla y decidir.
              No use una alerta como única base para impedir el acceso de alguien.
            </p>
          </div>
        )}

        {step === 5 && (
          <div className="space-y-4 text-sm text-ink-200">
            <div className="max-h-64 space-y-2 overflow-auto rounded-lg border border-ink-600 bg-ink-900/60 p-4 text-xs leading-relaxed text-ink-300">
              <p className="font-semibold text-ink-100">Aviso de privacidad y uso responsable</p>
              <p>FaceGuard AI procesa imágenes del rostro, que en muchas jurisdicciones son <b>datos biométricos</b> con protección especial.</p>
              <p>Usted es responsable de: tener una base legal y, cuando la ley lo exija, el consentimiento de las personas registradas;
                colocar avisos visibles de videovigilancia; registrar en la lista de alerta solo a personas con un motivo documentado;
                limitar el acceso al panel; y borrar los datos cuando ya no sean necesarios.</p>
              <p>No use FaceGuard AI para vigilar espacios privados ajenos, para discriminar ni en lugares donde la ley lo prohíba.
                Consulte la guía legal incluida (docs/legal.md) y, ante dudas, a un abogado.</p>
              <p>Todas las imágenes y datos se quedan en este equipo. FaceGuard AI no los envía a ningún servicio externo.</p>
            </div>
            <Toggle checked={s.update_check} onChange={(v) => set("update_check", v)} label="Buscar actualizaciones"
              description="Consulta GitHub para avisar de nuevas versiones. Solo envía una petición de la versión; nunca imágenes ni datos." />
            <label className="flex cursor-pointer items-start gap-2">
              <input type="checkbox" className="mt-0.5 accent-volt-500" checked={ack} onChange={(e) => setAck(e.target.checked)} />
              <span>He leído el aviso y usaré FaceGuard AI de forma legal y responsable.</span>
            </label>
          </div>
        )}

        {step === 6 && (
          <div className="space-y-2 text-sm text-ink-200">
            <p>Todo listo. Al pulsar <b>Comenzar</b> se crea la cuenta <span className="font-mono">{account.username}</span>,
              se prepara la base de datos y se aplica la configuración.</p>
            <ul className="list-inside list-disc text-xs text-ink-300">
              <li>Cámara {s.camera_index} a {s.camera_width}×{s.camera_height}</li>
              <li>Umbral {s.match_threshold} · {s.confirm_frames} fotograma(s) para confirmar</li>
              <li>Historial {s.retention_days_events} días · capturas {s.retention_days_snapshots} días</li>
              <li>Alertas {s.alerts_enabled ? "activadas" : "desactivadas"} · búsqueda de actualizaciones {s.update_check ? "activada" : "desactivada"}</li>
            </ul>
            <p className="text-xs text-ink-400">Siguiente paso: registre personas en <b>Personas</b> con fotos autorizadas.</p>
          </div>
        )}

        <ErrorNote error={error} />
      </div>

      <div className="flex items-center justify-between border-t border-ink-700 px-6 py-4">
        <Button variant="ghost" icon={ArrowLeft} disabled={step === 0 || loading} onClick={() => setStep(step - 1)}>Atrás</Button>
        {step < STEPS.length - 1 ? (
          <Button variant="primary" disabled={!canNext} onClick={() => { setError(null); setStep(step + 1); }}>
            Siguiente <ArrowRight className="h-4 w-4" />
          </Button>
        ) : (
          <Button variant="primary" icon={CheckCircle2} loading={loading} onClick={finish}>Comenzar</Button>
        )}
      </div>
    </div>,
  );
}
