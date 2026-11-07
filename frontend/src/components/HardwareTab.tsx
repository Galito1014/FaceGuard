// Configuración → Hardware & Alarm Settings: LED rojo, buzzer, pruebas e historial de activaciones.
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { BellOff, CheckCircle2, Cpu, History, Lightbulb, PlugZap, Siren, Stethoscope, Volume2, XCircle } from "lucide-react";
import { get, post, qs } from "@/lib/api";
import { useToast } from "@/lib/toast";
import { fmtDateTime } from "@/lib/format";
import type { AlarmActivation, GpioStatus, HardwareInfo, HardwareTestKey, HardwareTestResult, Settings } from "@/lib/types";
import { Badge, Button, Card, Field, Input, Pagination, Select, Spinner, Table, Td, Toggle } from "@/components/ui";

type SetFn = <K extends keyof Settings>(k: K, v: Settings[K]) => void;

export function ModeBadge({ status }: { status: GpioStatus }) {
  if (status.mode === "hardware") return <Badge tone="green" dot>Hardware conectado</Badge>;
  if (status.mode === "error") return <Badge tone="red" dot>Error de hardware</Badge>;
  return <Badge tone="amber" dot>Modo simulado</Badge>;
}

function Lamp({ on, label, icon: Icon }: { on: boolean; label: string; icon: React.ElementType }) {
  return (
    <div className={clsx("flex items-center gap-2 rounded-lg border px-3 py-2 text-sm transition",
      on ? "border-alert-500/60 bg-alert-500/15 text-white" : "border-ink-700 bg-ink-900/40 text-ink-300")}>
      <Icon className={clsx("h-4 w-4", on ? "text-alert-400" : "text-ink-400")} />
      {label}<span className="ml-auto font-mono text-xs">{on ? "ENCENDIDO" : "apagado"}</span>
    </div>
  );
}

const STATE_TONE: Record<AlarmActivation["state"], "red" | "green" | "amber" | "slate"> = {
  activa: "red", completada: "green", silenciada: "amber", error: "red",
};
const SOURCE_LABEL: Record<AlarmActivation["source"], string> = {
  deteccion: "Detección real", simulada: "Alerta simulada", prueba: "Prueba manual",
};

export default function HardwareTab({ draft, set, editable, dirty, canSilence }: {
  draft: Settings; set: SetFn; editable: boolean; dirty: boolean; canSilence: boolean;
}) {
  const qc = useQueryClient();
  const toast = useToast();
  const [page, setPage] = useState(1);
  const [results, setResults] = useState<Partial<Record<HardwareTestKey, HardwareTestResult>>>({});
  const info = useQuery({
    queryKey: ["hardware"], queryFn: () => get<HardwareInfo>("/api/hardware"),
    refetchInterval: (q) => (q.state.data?.status.alarm_active ? 1000 : 5000),
  });
  const history = useQuery({
    queryKey: ["hardware-activations", page],
    queryFn: () => get<{ items: AlarmActivation[]; total: number; page_size: number }>(`/api/hardware/activations${qs({ page, page_size: 10 })}`),
  });
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["hardware"] });
    qc.invalidateQueries({ queryKey: ["hardware-activations"] });
  };
  const runTest = useMutation({
    mutationFn: (key: HardwareTestKey) => post<HardwareTestResult>(`/api/hardware/test/${key}`),
    onSuccess: (r) => { setResults((prev) => ({ ...prev, [r.test]: r })); refresh(); },
    onError: (e) => toast({ kind: "error", title: "No se pudo ejecutar la prueba", body: (e as Error).message }),
  });
  const silence = useMutation({
    mutationFn: () => post<{ silenced: boolean }>("/api/hardware/silence"),
    onSuccess: (r) => { toast({ kind: r.silenced ? "success" : "info", title: r.silenced ? "Alarma silenciada" : "No había una alarma activa" }); refresh(); },
  });

  if (!info.data) return <Spinner className="mt-10" />;
  const st = info.data.status;
  const pinLabel = (bcm: number) => `GPIO${bcm} · pin ${info.data.safe_pins.find((p) => p.bcm === bcm)?.physical ?? "?"}`;
  const pinOptions = (current: number) => [...new Set([current, ...info.data.safe_pins.map((p) => p.bcm)])].sort((a, b) => a - b);

  return (
    <div className="space-y-4">
      {/* ------------------------------------------------------------ estado */}
      <Card title="Estado del hardware" icon={Cpu}
        actions={<>
          <ModeBadge status={st} />
          {st.alarm_active && <Badge tone="red" dot>Alarma activa</Badge>}
          {canSilence && <Button size="sm" variant="danger" icon={BellOff} disabled={!st.alarm_active} loading={silence.isPending}
            onClick={() => silence.mutate()}>Silenciar</Button>}
        </>}>
        <div className="grid gap-3 sm:grid-cols-2">
          <Lamp on={st.led_on} label={`LED rojo · GPIO${st.led_pin} (pin ${st.led_physical})`} icon={Lightbulb} />
          <Lamp on={st.buzzer_on} label={`Buzzer ${st.buzzer_type} · GPIO${st.buzzer_pin} (pin ${st.buzzer_physical})`} icon={Volume2} />
        </div>
        {st.error && <p className={clsx("mt-3 text-xs leading-relaxed", st.mode === "error" ? "text-alert-400" : "text-ink-400")}>{st.error}</p>}
        {st.last_action && <p className="mt-1 text-xs text-ink-400">Última acción: {st.last_action}</p>}
      </Card>

      {/* ------------------------------------------------------ configuración */}
      <Card title="Alarma física" icon={Siren}>
        <div className="grid gap-6 lg:grid-cols-2">
          <div className="space-y-4">
            <Toggle checked={draft.gpio_enabled} disabled={!editable} onChange={(v) => set("gpio_enabled", v)}
              label="Usar GPIO" description="Activa el LED y el buzzer cuando se confirma una persona de la lista de alerta." />
            <Toggle checked={draft.led_enabled} disabled={!editable || !draft.gpio_enabled} onChange={(v) => set("led_enabled", v)}
              label="LED rojo" description="Queda encendido (fijo) durante el tiempo configurado." />
            <Toggle checked={draft.buzzer_enabled} disabled={!editable || !draft.gpio_enabled} onChange={(v) => set("buzzer_enabled", v)}
              label="Buzzer (alarma sonora)" />
            <p className="text-xs leading-relaxed text-ink-400">
              Una persona desconocida, una coincidencia por debajo del umbral o una persona autorizada nunca activan la alarma.
              Con <b>Alertas activas</b> apagado (pestaña Alertas) tampoco se activa.
            </p>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="LED encendido (s)"><Input type="number" min={1} max={60} value={draft.led_seconds} disabled={!editable} onChange={(e) => set("led_seconds", Number(e.target.value))} /></Field>
            <Field label="Buzzer sonando (s)"><Input type="number" min={1} max={60} value={draft.buzzer_seconds} disabled={!editable} onChange={(e) => set("buzzer_seconds", Number(e.target.value))} /></Field>
            <Field label="Cooldown por persona (s)" hint="Sin otra alerta ni alarma de la misma persona en este tiempo.">
              <Input type="number" min={5} max={3600} value={draft.dedup_seconds} disabled={!editable} onChange={(e) => set("dedup_seconds", Number(e.target.value))} />
            </Field>
            <Field label="Confirmaciones" hint="Análisis seguidos con coincidencia antes de activar.">
              <Input type="number" min={1} max={10} value={draft.confirm_frames} disabled={!editable} onChange={(e) => set("confirm_frames", Number(e.target.value))} />
            </Field>
            <Field label="Tipo de buzzer" hint="Si con 'activo' solo hace clic, es pasivo.">
              <Select value={draft.buzzer_type} disabled={!editable} onChange={(e) => set("buzzer_type", e.target.value as Settings["buzzer_type"])}>
                <option value="activo">Activo (oscilador interno)</option><option value="pasivo">Pasivo (PWM)</option>
              </Select>
            </Field>
            <Field label="Patrón del buzzer">
              <Select value={draft.buzzer_pattern} disabled={!editable} onChange={(e) => set("buzzer_pattern", e.target.value as Settings["buzzer_pattern"])}>
                <option value="intermitente">Intermitente</option><option value="continuo">Continuo</option>
              </Select>
            </Field>
            {draft.buzzer_type === "pasivo" && (
              <Field label="Frecuencia (Hz)" hint="2000-4000 Hz suele sonar más fuerte.">
                <Input type="number" min={200} max={8000} step={100} value={draft.buzzer_frequency} disabled={!editable} onChange={(e) => set("buzzer_frequency", Number(e.target.value))} />
              </Field>
            )}
            <Field label="Buzzer desde nivel">
              <Select value={draft.buzzer_min_level} disabled={!editable} onChange={(e) => set("buzzer_min_level", e.target.value as Settings["buzzer_min_level"])}>
                <option value="bajo">Bajo (toda coincidencia)</option><option value="medio">Medio</option><option value="alto">Alto</option>
              </Select>
            </Field>
            <Field label="Pin del LED (BCM)">
              <Select value={draft.led_pin} disabled={!editable} onChange={(e) => set("led_pin", Number(e.target.value))}>
                {pinOptions(draft.led_pin).map((p) => <option key={p} value={p} disabled={p === draft.buzzer_pin}>{pinLabel(p)}</option>)}
              </Select>
            </Field>
            <Field label="Pin del buzzer (BCM)">
              <Select value={draft.buzzer_pin} disabled={!editable} onChange={(e) => set("buzzer_pin", Number(e.target.value))}>
                {pinOptions(draft.buzzer_pin).map((p) => <option key={p} value={p} disabled={p === draft.led_pin}>{pinLabel(p)}</option>)}
              </Select>
            </Field>
          </div>
        </div>
      </Card>

      {/* --------------------------------------------------------- conexiones */}
      <Card title="Conexiones" icon={PlugZap}>
        <Table head={["Componente", "GPIO (BCM)", "Pin físico", "Conexión"]}>
          <tr><Td>LED rojo (+)</Td><Td mono>GPIO{st.led_pin}</Td><Td mono>{st.led_physical}</Td><Td>Resistencia 220-330 Ω → pata larga (ánodo)</Td></tr>
          <tr><Td>LED rojo (−)</Td><Td mono>GND</Td><Td mono>9</Td><Td>Pata corta (cátodo)</Td></tr>
          <tr><Td>Buzzer (+)</Td><Td mono>GPIO{st.buzzer_pin}</Td><Td mono>{st.buzzer_physical}</Td><Td>Pata marcada "+" (o la larga)</Td></tr>
          <tr><Td>Buzzer (−)</Td><Td mono>GND</Td><Td mono>14</Td><Td>Pata "−"</Td></tr>
          <tr><Td>Ventilador</Td><Td mono>—</Td><Td mono>2 / 4 y 6</Td><Td>5 V y GND: no usa ningún GPIO</Td></tr>
        </Table>
        <p className="mt-3 text-xs leading-relaxed text-ink-400">
          Un GPIO entrega 3,3 V y conviene no pasar de ~16 mA. Un buzzer piezoeléctrico consume pocos mA y se conecta directo;
          un buzzer magnético de 5 V necesita un transistor NPN (2N2222) con 1 kΩ en la base. Detalles en docs/hardware.md.
        </p>
      </Card>

      {/* --------------------------------------------------------- diagnóstico */}
      <Card title="Pruebas de diagnóstico" icon={Stethoscope}>
        {dirty && <p className="mb-3 rounded-lg border border-warn-500/40 bg-warn-500/10 px-3 py-2 text-xs text-warn-400">Guarde los cambios antes de probar: las pruebas usan la configuración guardada.</p>}
        <div className="space-y-2">
          {info.data.tests.map((t) => {
            const r = results[t.key];
            return (
              <div key={t.key} className="rounded-lg border border-ink-700 bg-ink-900/40 p-3">
                <div className="flex flex-wrap items-center gap-3">
                  {r ? (r.ok ? <CheckCircle2 className="h-4 w-4 text-ok-400" /> : <XCircle className="h-4 w-4 text-alert-400" />)
                    : <span className="h-4 w-4 rounded-full border border-ink-500" />}
                  <span className="text-sm font-medium text-ink-100">{t.title}</span>
                  {editable && <Button size="sm" className="ml-auto" loading={runTest.isPending && runTest.variables === t.key}
                    disabled={runTest.isPending} onClick={() => runTest.mutate(t.key)}>Ejecutar</Button>}
                </div>
                {r && <p className={clsx("mt-2 text-xs", r.ok ? "text-ink-200" : "text-alert-400")}>{r.message}</p>}
                {r?.hint && <p className="mt-1 text-[11px] leading-relaxed text-ink-400">{r.hint}</p>}
              </div>
            );
          })}
        </div>
        <p className="mt-3 text-[11px] text-ink-400">La prueba 4 genera una alerta marcada [SIMULADO] que puede descartar en Alertas.
          Por consola (con el servicio detenido): <span className="font-mono">python -m scripts.manage hardware-test todas</span></p>
      </Card>

      {/* ----------------------------------------------------------- historial */}
      <Card title="Historial de activaciones" icon={History}>
        <Table head={["Fecha y hora", "Origen", "Persona / alerta", "Salidas", "Modo", "Estado"]} loading={history.isLoading}
          empty={history.data?.items.length === 0}>
          {history.data?.items.map((a) => (
            <tr key={a.id}>
              <Td>{fmtDateTime(a.at)}</Td>
              <Td>{SOURCE_LABEL[a.source]}</Td>
              <Td>{a.entry_name ?? "—"}{a.event_uid && <span className="ml-2 font-mono text-[11px] text-ink-400">{a.event_uid}</span>}</Td>
              <Td className="text-xs">{[a.led ? `LED ${a.led_seconds} s` : null, a.buzzer ? `buzzer ${a.buzzer_seconds} s` : null].filter(Boolean).join(" · ") || "—"}</Td>
              <Td><span className="text-xs">{a.mode}</span></Td>
              <Td><Badge tone={STATE_TONE[a.state]}>{a.state}</Badge>
                {a.silenced_by && <span className="ml-2 text-[11px] text-ink-400">por {a.silenced_by}</span>}
                {a.error && <span className="ml-2 text-[11px] text-alert-400" title={a.error}>⚠</span>}</Td>
            </tr>
          ))}
        </Table>
        {history.data && history.data.total > history.data.page_size &&
          <Pagination page={page} pageSize={history.data.page_size} total={history.data.total} onPage={setPage} />}
      </Card>
    </div>
  );
}
