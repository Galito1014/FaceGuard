import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Eye, EyeOff, Lock, ShieldCheck, ShieldX, XCircle } from "lucide-react";
import { get, post } from "@/lib/api";
import { useToast } from "@/lib/toast";
import { fmtDateTime, fmtScore } from "@/lib/format";
import type { EventDetail, ReviewStatus } from "@/lib/types";
import { Badge, Button, ErrorNote, Field, LevelBadge, Modal, ReviewBadge, SimBadge, Spinner, Textarea } from "./ui";

function ProtectedImage({ src, label }: { src: string; label: string }) {
  const [show, setShow] = useState(false);
  const [failed, setFailed] = useState(false);
  return (
    <figure>
      <div className="relative grid aspect-square place-items-center overflow-hidden rounded-lg border border-ink-700 bg-ink-900">
        {show && !failed ? (
          <img src={src} alt={label} onError={() => setFailed(true)} className="h-full w-full object-contain" />
        ) : failed ? (
          <p className="px-4 text-center text-xs text-ink-400">Imagen no disponible (pudo vencer su periodo de conservación).</p>
        ) : (
          <Button size="sm" icon={Eye} onClick={() => setShow(true)}>Mostrar imagen</Button>
        )}
        {show && !failed && (
          <button onClick={() => setShow(false)} className="absolute right-2 top-2 rounded-md bg-black/60 p-1.5 text-ink-100 hover:text-white" title="Ocultar">
            <EyeOff className="h-3.5 w-3.5" />
          </button>
        )}
      </div>
      <figcaption className="mt-1.5 text-center text-[11px] text-ink-300">{label}</figcaption>
    </figure>
  );
}

const ACTIONS: { status: ReviewStatus; label: string; icon: React.ElementType; variant: "danger" | "success" | "secondary" }[] = [
  { status: "confirmada", label: "Confirmar coincidencia", icon: ShieldCheck, variant: "danger" },
  { status: "falso_positivo", label: "Descartar", icon: ShieldX, variant: "success" },
  { status: "cerrada", label: "Cerrar", icon: XCircle, variant: "secondary" },
];

export default function EventDetailModal({ id, onClose }: { id: number; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const q = useQuery({ queryKey: ["events", "detail", id], queryFn: () => get<EventDetail>(`/api/events/${id}`) });
  const [notes, setNotes] = useState("");
  const e = q.data;

  const review = useMutation({
    mutationFn: (status: ReviewStatus) => post(`/api/alerts/${id}/review`, { status, notes }),
    onSuccess: (_, status) => {
      qc.invalidateQueries({ queryKey: ["alerts"] });
      qc.invalidateQueries({ queryKey: ["events"] });
      qc.invalidateQueries({ queryKey: ["summary"] });
      toast({ kind: "success", title: "Revisión registrada", body: `Estado: ${ACTIONS.find((a) => a.status === status)?.label ?? status}` });
      setNotes("");
    },
  });

  const isAlert = e?.type === "coincidencia";
  return (
    <Modal open onClose={onClose} size="lg"
      title={e ? <span className="flex flex-wrap items-center gap-2"><span className="font-mono">{e.uid}</span> · {e.type_label} {e.is_simulated && <SimBadge />}</span> : "Cargando…"}>
      {q.isLoading && <Spinner />}
      <ErrorNote error={q.error} />
      {e && (
        <div className="space-y-5">
          {isAlert && (
            <div className="flex items-start gap-3 rounded-lg border border-warn-500/30 bg-warn-500/5 p-3 text-xs text-ink-200">
              <Lock className="mt-0.5 h-4 w-4 shrink-0 text-warn-400" />
              Coincidencia preliminar generada automáticamente. Verifique visualmente y, si corresponde, en persona antes de actuar.
              El sistema no toma decisiones sobre la persona: cualquier acción depende del protocolo del edificio.
            </div>
          )}
          <div className="grid gap-5 md:grid-cols-2">
            <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
              {[
                ["Fecha y hora", fmtDateTime(e.occurred_at)],
                ["Cámara", e.camera],
                ["Tipo", e.type_label],
                ["Rostros", e.faces_count],
                ["Posible coincidencia", e.entry_name ?? "—"],
                ["Similitud", <span className="font-mono">{fmtScore(e.score)}</span>],
                ["Nivel", <LevelBadge level={e.level} />],
                ["Estado de revisión", <ReviewBadge status={e.review_status} />],
                ["Responsable", e.reviewer_name ?? "—"],
                ["Revisado", fmtDateTime(e.reviewed_at)],
              ].map(([k, v], i) => (
                <div key={i}><dt className="text-[11px] uppercase tracking-wider text-ink-400">{k}</dt><dd className="mt-0.5 text-ink-100">{v}</dd></div>
              ))}
              <div className="col-span-2"><dt className="text-[11px] uppercase tracking-wider text-ink-400">Descripción</dt><dd className="mt-0.5 text-ink-200">{e.message || "—"}</dd></div>
              {e.entry && (
                <div className="col-span-2 rounded-lg border border-ink-700 bg-ink-900/60 p-3">
                  <dt className="text-[11px] uppercase tracking-wider text-ink-400">Registro en lista · {e.entry.uid}</dt>
                  <dd className="mt-1 text-xs text-ink-200">{e.entry.reason}</dd>
                  <dd className="mt-1"><Badge>{e.entry.status}</Badge></dd>
                </div>
              )}
            </dl>
            <div>
              {e.can_view_images ? (
                isAlert ? (
                  <div className="grid grid-cols-2 gap-3">
                    {e.has_snapshot ? <ProtectedImage src={`/api/events/${e.id}/snapshot`} label="Imagen detectada" /> : <NoImg label="Imagen detectada" />}
                    {e.entry?.has_photo ? <ProtectedImage src={`/api/alerts/${e.id}/registered-photo`} label="Fotografía registrada" /> : <NoImg label="Fotografía registrada" />}
                  </div>
                ) : e.has_snapshot ? <ProtectedImage src={`/api/events/${e.id}/snapshot`} label="Captura" />
                  : <p className="rounded-lg border border-ink-700 p-4 text-center text-xs text-ink-400">Este evento no guarda imágenes: el sistema no almacena fotos de personas sin coincidencia.</p>
              ) : (
                <p className="rounded-lg border border-ink-700 p-4 text-center text-xs text-ink-400"><Lock className="mx-auto mb-2 h-5 w-5" />Las imágenes solo están disponibles para operadores y administradores autorizados.</p>
              )}
              <p className="mt-2 text-center text-[11px] text-ink-400">Cada visualización de imagen queda registrada en la auditoría.</p>
            </div>
          </div>
          {e.notes && (
            <div>
              <p className="mb-1 text-[11px] uppercase tracking-wider text-ink-400">Observaciones</p>
              <pre className="whitespace-pre-wrap rounded-lg border border-ink-700 bg-ink-900 p-3 font-sans text-xs text-ink-200">{e.notes}</pre>
            </div>
          )}
          {isAlert && e.can_review && (
            <div className="rounded-lg border border-ink-700 bg-ink-900/50 p-4">
              <p className="mb-3 flex items-center gap-2 text-sm font-semibold text-white"><CheckCircle2 className="h-4 w-4 text-volt-400" /> Revisión del operador</p>
              <Field label="Observaciones de la verificación" hint="Obligatorio para confirmar o descartar (mín. 5 caracteres).">
                <Textarea value={notes} onChange={(ev) => setNotes(ev.target.value)} maxLength={1000} placeholder="Ej.: verificado con el guardia en portería; no corresponde a la persona registrada." />
              </Field>
              <div className="mt-3 flex flex-wrap gap-2">
                {ACTIONS.map((a) => (
                  <Button key={a.status} variant={a.variant} icon={a.icon} loading={review.isPending && review.variables === a.status}
                    disabled={e.review_status === a.status || (a.status !== "cerrada" && notes.trim().length < 5)}
                    onClick={() => review.mutate(a.status)}>{a.label}</Button>
                ))}
              </div>
              <div className="mt-3"><ErrorNote error={review.error} /></div>
            </div>
          )}
        </div>
      )}
    </Modal>
  );
}

function NoImg({ label }: { label: string }) {
  return (
    <figure>
      <div className="grid aspect-square place-items-center rounded-lg border border-ink-700 bg-ink-900 px-3 text-center text-xs text-ink-400">Sin imagen</div>
      <figcaption className="mt-1.5 text-center text-[11px] text-ink-300">{label}</figcaption>
    </figure>
  );
}
