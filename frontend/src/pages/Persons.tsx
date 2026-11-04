import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Ban, CalendarX, CheckCircle2, CircleX, Eye, ImagePlus, ImageUp, Pencil, Plus, Power, Search, ShieldAlert, Star, Trash2, TriangleAlert, Users, UserX,
} from "lucide-react";
import { del, get, post, postForm, qs } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useToast } from "@/lib/toast";
import { fmtDate, fmtDateTime, fmtScore, toDateInput } from "@/lib/format";
import type { BlacklistDetail, BlacklistEntry, Classification, DuplicateMatch, Level, Paged, QualityReport } from "@/lib/types";
import {
  Badge, Button, Card, ConfirmDialog, ErrorNote, Field, Input, LevelBadge, Modal, PageHeader, Pagination, ReviewBadge,
  Select, SimBadge, Table, Td, Textarea,
} from "@/components/ui";
import { ApiError } from "@/lib/api";

type ListResp = Paged<BlacklistEntry> & { stats: { alert_level: Level; status: string; classification: Classification; n: number }[] };

export const ClassificationBadge = ({ value }: { value: Classification }) =>
  value === "no_autorizada" ? <Badge tone="red" dot>No autorizada</Badge> : <Badge tone="green" dot>Autorizada</Badge>;

const statusBadge = (s: BlacklistEntry["status"]) =>
  s === "activo" ? <Badge tone="green" dot>Activo</Badge> : s === "vencido" ? <Badge tone="amber" dot>Vencido</Badge> : <Badge dot>Inactivo</Badge>;

export default function PersonsPage({ blacklistOnly = false }: { blacklistOnly?: boolean }) {
  const { can } = useAuth();
  const qc = useQueryClient();
  const toast = useToast();
  const [filters, setFilters] = useState({ q: "", level: "", status: "", simulated: "", classification: blacklistOnly ? "no_autorizada" : "" });
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<number | null>(null);
  const [editing, setEditing] = useState<BlacklistEntry | "new" | null>(null);
  const [search, setSearch] = useState("");

  useEffect(() => {
    const t = setTimeout(() => { setFilters((f) => ({ ...f, q: search })); setPage(1); }, 300);
    return () => clearTimeout(t);
  }, [search]);

  const list = useQuery({
    queryKey: ["persons", filters, page],
    queryFn: () => get<ListResp>(`/api/persons${qs({ ...filters, page, page_size: 15 })}`),
  });

  const counts = useMemo(() => {
    const c = { activo: 0, alto: 0, vencido: 0, blacklist: 0 };
    list.data?.stats.forEach((s) => {
      if (s.status === "activo") c.activo += s.n;
      if (s.status === "activo" && s.alert_level === "alto" && s.classification === "no_autorizada") c.alto += s.n;
      if (s.status === "activo" && s.classification === "no_autorizada") c.blacklist += s.n;
      if (s.status === "vencido") c.vencido += s.n;
    });
    return c;
  }, [list.data]);

  const expire = useMutation({
    mutationFn: () => post<{ entries_expired: number }>("/api/persons/deactivate-expired"),
    onSuccess: (r) => { qc.invalidateQueries({ queryKey: ["persons"] }); toast({ kind: "success", title: "Revisión de vencimientos completada", body: `${r.entries_expired} registro(s) desactivado(s).` }); },
  });

  const setF = (k: keyof typeof filters, v: string) => { setFilters((f) => ({ ...f, [k]: v })); setPage(1); };

  return (
    <>
      <PageHeader title={blacklistOnly ? "Blacklist" : "Personas registradas"} icon={blacklistOnly ? ShieldAlert : Users}
        subtitle={blacklistOnly ? "Personas no autorizadas, con motivo y autorización legal documentados" : "Personas autorizadas y no autorizadas. Un rostro desconocido nunca se clasifica solo."}
        actions={can("blacklist.edit") && <>
          <Button icon={CalendarX} loading={expire.isPending} onClick={() => expire.mutate()}>Desactivar vencidos</Button>
          <Button variant="primary" icon={Plus} onClick={() => setEditing("new")}>Añadir persona</Button>
        </>} />

      <div className="mb-4 grid grid-cols-3 gap-3">
        <div className="panel p-3"><p className="text-[11px] uppercase tracking-wider text-ink-300">Activos</p><p className="font-mono text-xl font-semibold text-white">{counts.activo}</p></div>
        <div className="panel p-3"><p className="text-[11px] uppercase tracking-wider text-ink-300">Nivel alto activos</p><p className="font-mono text-xl font-semibold text-alert-400">{counts.alto}</p></div>
        <div className="panel p-3"><p className="text-[11px] uppercase tracking-wider text-ink-300">Vencidos</p><p className="font-mono text-xl font-semibold text-warn-400">{counts.vencido}</p></div>
      </div>

      <Card bodyClass="p-3">
        <div className={`mb-3 grid gap-2 ${blacklistOnly ? "md:grid-cols-[1fr_190px_190px_200px]" : "lg:grid-cols-[minmax(180px,1fr)_repeat(4,195px)] md:grid-cols-2"}`}>
          <Input icon={Search} placeholder="Buscar por nombre o identificador…" value={search} onChange={(e) => setSearch(e.target.value)} />
          {!blacklistOnly && (
            <Select value={filters.classification} onChange={(e) => setF("classification", e.target.value)}>
              <option value="">Todas las clasificaciones</option><option value="autorizada">Autorizadas</option><option value="no_autorizada">No autorizadas</option>
            </Select>
          )}
          <Select value={filters.level} onChange={(e) => setF("level", e.target.value)}>
            <option value="">Todos los niveles</option><option value="alto">Alto</option><option value="medio">Medio</option><option value="bajo">Bajo</option>
          </Select>
          <Select value={filters.status} onChange={(e) => setF("status", e.target.value)}>
            <option value="">Todos los estados</option><option value="activo">Activo</option><option value="inactivo">Inactivo</option><option value="vencido">Vencido</option>
          </Select>
          <Select value={filters.simulated} onChange={(e) => setF("simulated", e.target.value)}>
            <option value="">Reales y simulados</option><option value="0">Solo reales</option><option value="1">Solo simulados</option>
          </Select>
        </div>
        <Table head={["Identificador", "Nombre", "Clasificación", "Nivel", "Estado", "Fotos", "Registro", "Próxima revisión", ""]} loading={list.isLoading}
          empty={list.data?.items.length === 0}>
          {list.data?.items.map((e) => (
            <tr key={e.id} className="row-hover" onClick={() => setSelected(e.id)}>
              <Td mono>{e.uid}</Td>
              <Td><span className="font-medium">{e.full_name}</span> {e.is_simulated && <SimBadge />}</Td>
              <Td><ClassificationBadge value={e.classification} /></Td>
              <Td>{e.classification === "no_autorizada" ? <LevelBadge level={e.alert_level} /> : <span className="text-ink-400">—</span>}</Td>
              <Td>{statusBadge(e.status)}</Td>
              <Td mono>{e.sample_count}</Td>
              <Td className="text-ink-200">{fmtDate(e.registered_at)}</Td>
              <Td className={new Date(e.expires_at) < new Date() ? "text-warn-400" : "text-ink-200"}>{fmtDate(e.expires_at)}</Td>
              <Td><Eye className="h-4 w-4 text-ink-400" /></Td>
            </tr>
          ))}
        </Table>
        {list.data && <Pagination page={page} pageSize={list.data.page_size} total={list.data.total} onPage={setPage} />}
      </Card>

      {selected !== null && (
        <EntryDetail id={selected} onClose={() => setSelected(null)} onEdit={(e) => { setSelected(null); setEditing(e); }} />
      )}
      {editing && <EntryForm entry={editing === "new" ? null : editing} defaultClassification="no_autorizada" onClose={() => setEditing(null)} />}
    </>
  );
}

/* --------------------------------------------------------------- detalle */
function EntryDetail({ id, onClose, onEdit }: { id: number; onClose: () => void; onEdit: (e: BlacklistEntry) => void }) {
  const { can } = useAuth();
  const qc = useQueryClient();
  const toast = useToast();
  const q = useQuery({ queryKey: ["persons", "detail", id], queryFn: () => get<BlacklistDetail>(`/api/persons/${id}`) });
  const [confirm, setConfirm] = useState<"delete" | "toggle" | null>(null);
  const [showPhoto, setShowPhoto] = useState(false);
  const e = q.data;

  const remove = useMutation({
    mutationFn: () => del(`/api/persons/${id}`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["persons"] }); toast({ kind: "success", title: "Registro eliminado", body: "La fotografía y la plantilla se borraron de forma segura." }); onClose(); },
  });
  const toggle = useMutation({
    mutationFn: () => {
      const f = new FormData();
      f.set("status", e!.status === "activo" ? "inactivo" : "activo");
      return postForm(`/api/persons/${id}`, f, "PUT");
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["persons"] }); setConfirm(null); toast({ kind: "success", title: "Estado actualizado" }); },
    onError: (err) => { setConfirm(null); toast({ kind: "error", title: "No se pudo cambiar el estado", body: (err as Error).message }); },
  });

  return (
    <Modal open onClose={onClose} size="lg" title={e ? <span className="flex items-center gap-2">{e.full_name} {e.is_simulated && <SimBadge />}</span> : "Cargando…"}
      footer={e && can("blacklist.edit") && <>
        <Button variant="danger" icon={Trash2} onClick={() => setConfirm("delete")}>Eliminar</Button>
        <Button icon={e.status === "activo" ? Ban : Power} onClick={() => setConfirm("toggle")}>{e.status === "activo" ? "Desactivar" : "Activar"}</Button>
        <Button variant="primary" icon={Pencil} onClick={() => onEdit(e)}>Editar</Button>
      </>}>
      {!e ? <ErrorNote error={q.error} /> : (
        <div className="grid gap-5 md:grid-cols-[200px_1fr]">
          <div>
            <div className="grid aspect-[4/5] place-items-center overflow-hidden rounded-lg border border-ink-700 bg-ink-900">
              {e.can_view_photo && e.has_photo ? (
                showPhoto ? <img src={`/api/persons/${e.id}/photo`} alt={`Fotografía registrada de ${e.full_name}`} className="h-full w-full object-cover" />
                  : <Button size="sm" icon={Eye} onClick={() => setShowPhoto(true)}>Mostrar fotografía</Button>
              ) : <div className="p-4 text-center text-xs text-ink-400"><UserX className="mx-auto mb-2 h-8 w-8" />{e.has_photo ? "Fotografía restringida a administradores" : "Sin fotografía"}</div>}
            </div>
            <p className="mt-2 text-center text-[11px] text-ink-400">{e.has_template ? `${e.template_count} plantilla(s) biométrica(s) cifrada(s)` : "Sin plantilla (no participa en el reconocimiento)"}</p>
          </div>
          <div className="space-y-4 text-sm">
            <dl className="grid grid-cols-2 gap-x-4 gap-y-3">
              {[
                ["Identificador", <span className="font-mono">{e.uid}</span>],
                ["Clasificación", <ClassificationBadge value={e.classification} />],
                ["Estado", statusBadge(e.status)],
                ...(e.classification === "no_autorizada" ? [["Nivel de alerta", <LevelBadge level={e.alert_level} />]] : []),
                ["Fecha de registro", fmtDateTime(e.registered_at)],
                ["Próxima revisión / vencimiento", fmtDate(e.expires_at)],
                ["Última modificación", fmtDateTime(e.updated_at)],
              ].map(([k, v], i) => (
                <div key={i}><dt className="text-[11px] uppercase tracking-wider text-ink-400">{k}</dt><dd className="mt-0.5 text-ink-100">{v}</dd></div>
              ))}
            </dl>
            <div><p className="text-[11px] uppercase tracking-wider text-ink-400">{e.classification === "autorizada" ? "Tipo de registro" : "Motivo documentado"}</p><p className="mt-0.5 text-ink-100">{e.reason}</p></div>
            <div><p className="text-[11px] uppercase tracking-wider text-ink-400">{e.classification === "autorizada" ? "Consentimiento" : "Base legal / autorización"}</p><p className="mt-0.5 text-ink-100">{e.legal_basis}</p></div>
            {e.info && <div><p className="text-[11px] uppercase tracking-wider text-ink-400">Información adicional</p><p className="mt-0.5 whitespace-pre-wrap text-ink-200">{e.info}</p></div>}
            {e.notes && <div><p className="text-[11px] uppercase tracking-wider text-ink-400">Observaciones</p><p className="mt-0.5 whitespace-pre-wrap text-ink-200">{e.notes}</p></div>}
          </div>
          <div className="md:col-span-2">
            {e.can_view_photo && <SamplesPanel person={e} editable={can("blacklist.edit")} />}
            <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-300">Alertas asociadas</h4>
            {e.alerts.length === 0 ? <p className="text-xs text-ink-400">Sin alertas registradas.</p> : (
              <div className="space-y-1">{e.alerts.map((a) => (
                <div key={a.uid} className="flex items-center gap-3 text-xs"><span className="font-mono text-ink-200">{a.uid}</span><span className="text-ink-300">{fmtDateTime(a.occurred_at)}</span><span className="font-mono">{fmtScore(a.score)}</span><ReviewBadge status={a.review_status} /></div>
              ))}</div>
            )}
            <h4 className="mb-2 mt-5 text-xs font-semibold uppercase tracking-wider text-ink-300">Historial de modificaciones</h4>
            <ol className="relative space-y-3 border-l border-ink-600 pl-4">
              {e.history.map((h, i) => (
                <li key={i} className="text-xs">
                  <span className="absolute -left-[5px] mt-1 h-2.5 w-2.5 rounded-full border-2 border-ink-850 bg-volt-500" />
                  <p className="text-ink-100"><span className="font-semibold capitalize">{h.action}</span> · {h.username ?? "sistema"} · <span className="text-ink-400">{fmtDateTime(h.at)}</span></p>
                  {h.changes && h.changes !== "{}" && <p className="mt-0.5 break-all font-mono text-[11px] text-ink-400">{h.changes}</p>}
                </li>
              ))}
            </ol>
          </div>
        </div>
      )}
      <ConfirmDialog open={confirm === "delete"} danger title="Eliminar registro" confirmLabel="Eliminar definitivamente" loading={remove.isPending}
        onClose={() => setConfirm(null)} onConfirm={() => remove.mutate()}
        message={<>Se eliminará <b>{e?.full_name}</b> ({e?.uid}) y se borrarán de forma segura sus fotografías y sus plantillas biométricas. Esta acción no se puede deshacer y quedará registrada en la auditoría.</>} />
      <ConfirmDialog open={confirm === "toggle"} title={e?.status === "activo" ? "Desactivar registro" : "Activar registro"} loading={toggle.isPending}
        onClose={() => setConfirm(null)} onConfirm={() => toggle.mutate()}
        message={e?.status === "activo" ? "El registro dejará de participar en el reconocimiento facial, pero se conservará con su historial." : "El registro volverá a participar en el reconocimiento facial."} />
    </Modal>
  );
}

/* ------------------------------------------------------- muestras faciales */
function SamplesPanel({ person, editable }: { person: BlacklistDetail; editable: boolean }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [show, setShow] = useState(false);
  const [pending, setPending] = useState<File | null>(null);
  const [duplicates, setDuplicates] = useState<DuplicateMatch[]>([]);
  const refresh = () => qc.invalidateQueries({ queryKey: ["persons"] });
  const fail = (title: string) => (err: unknown) => toast({ kind: "error", title, body: (err as Error).message });

  const upload = useMutation({
    mutationFn: ({ file, confirm }: { file: File; confirm: boolean }) => {
      const f = new FormData();
      f.set("photo", file);
      f.set("confirm_duplicate", String(confirm));
      return postForm(`/api/persons/${person.id}/samples`, f);
    },
    onSuccess: () => { setPending(null); setDuplicates([]); refresh(); toast({ kind: "success", title: "Fotografía añadida" }); },
    onError: (err, vars) => {
      const d = err instanceof ApiError ? (err.detail as { duplicates?: DuplicateMatch[] }) : null;
      if (d?.duplicates) { setPending(vars.file); setDuplicates(d.duplicates); return; }
      fail("No se pudo añadir la fotografía")(err);
    },
  });
  const primary = useMutation({
    mutationFn: (id: number) => post(`/api/persons/${person.id}/samples/${id}/primary`),
    onSuccess: refresh, onError: fail("No se pudo cambiar la fotografía principal"),
  });
  const remove = useMutation({
    mutationFn: (id: number) => del(`/api/persons/${person.id}/samples/${id}`),
    onSuccess: refresh, onError: fail("No se pudo eliminar la fotografía"),
  });

  return (
    <div className="mb-5">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h4 className="text-xs font-semibold uppercase tracking-wider text-ink-300">Fotografías ({person.samples.length})</h4>
        <div className="flex gap-2">
          {!show && <Button size="sm" icon={Eye} onClick={() => setShow(true)}>Mostrar</Button>}
          {editable && (
            <label className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg border border-ink-600 px-2.5 py-1 text-xs text-ink-100 hover:border-volt-500/60">
              <ImagePlus className="h-3.5 w-3.5" />Añadir
              <input type="file" accept="image/jpeg,image/png" className="hidden" disabled={upload.isPending}
                onChange={(e) => { const file = e.target.files?.[0]; e.target.value = ""; if (file) upload.mutate({ file, confirm: false }); }} />
            </label>
          )}
        </div>
      </div>
      <p className="mb-2 text-[11px] text-ink-400">Varias fotos con distintos ángulos o iluminación mejoran el reconocimiento.</p>
      {pending && duplicates.length > 0 && (
        <div className="mb-2 rounded-lg border border-warn-500/30 bg-warn-500/5 p-3 text-xs text-ink-200">
          <p className="mb-1 font-semibold text-warn-400">La fotografía se parece a otra persona registrada</p>
          {duplicates.map((d) => <p key={d.entry_id}>{d.full_name} <span className="font-mono text-ink-400">{d.uid} · {fmtScore(d.score)}</span></p>)}
          <div className="mt-2 flex gap-2">
            <Button size="sm" variant="primary" onClick={() => upload.mutate({ file: pending, confirm: true })}>Es esta persona: añadir</Button>
            <Button size="sm" variant="ghost" onClick={() => { setPending(null); setDuplicates([]); }}>Cancelar</Button>
          </div>
        </div>
      )}
      {show && (
        <div className="grid grid-cols-3 gap-2 sm:grid-cols-5">
          {person.samples.map((s) => (
            <div key={s.id} className="overflow-hidden rounded-lg border border-ink-700 bg-ink-900">
              <img src={`/api/persons/${person.id}/samples/${s.id}/photo`} alt="Fotografía registrada" className="aspect-square w-full object-cover" />
              <div className="flex items-center justify-between p-1.5 text-[10px] text-ink-300">
                {s.is_primary ? <span className="text-volt-400">Principal</span> : editable ? (
                  <button aria-label="Usar como principal" onClick={() => primary.mutate(s.id)} className="hover:text-volt-400"><Star className="h-3.5 w-3.5" /></button>
                ) : <span />}
                {editable && person.samples.length > 1 && (
                  <button aria-label="Eliminar fotografía" onClick={() => remove.mutate(s.id)} className="hover:text-alert-400"><Trash2 className="h-3.5 w-3.5" /></button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------- formulario */
function EntryForm({ entry, defaultClassification, onClose }: { entry: BlacklistEntry | null; defaultClassification: Classification; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const defaultExp = new Date(Date.now() + 180 * 864e5).toISOString();
  const [form, setForm] = useState({
    full_name: entry?.full_name ?? "", classification: (entry?.classification ?? defaultClassification) as Classification,
    reason: entry?.classification === "autorizada" ? "" : entry?.reason ?? "",
    legal_basis: entry?.classification === "autorizada" ? "" : entry?.legal_basis ?? "",
    alert_level: entry?.alert_level ?? "medio", expires_at: toDateInput(entry?.expires_at ?? defaultExp),
    info: entry?.info ?? "", notes: entry?.notes ?? "",
  });
  const [photo, setPhoto] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [report, setReport] = useState<QualityReport | null>(null);
  const [checking, setChecking] = useState(false);
  const [consent, setConsent] = useState(false);
  const [sameAnyway, setSameAnyway] = useState(false);
  const restricted = form.classification === "no_autorizada";
  const needsConfirmation = !entry || form.classification !== entry.classification;
  const duplicates = (report?.duplicates ?? []).filter((d) => d.entry_id !== entry?.id);
  const [confirmOpen, setConfirmOpen] = useState(false);

  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);

  const pick = async (file: File | undefined) => {
    if (!file) return;
    setPhoto(file);
    setPreview(URL.createObjectURL(file));
    setReport(null);
    setSameAnyway(false);
    setChecking(true);
    try {
      const f = new FormData();
      f.set("photo", file);
      setReport(await postForm<QualityReport>("/api/persons/validate-photo", f));
    } catch (err) {
      setReport({ ok: false, checks: [{ name: "Validación", ok: false, detail: (err as Error).message }] });
    } finally {
      setChecking(false);
    }
  };

  const save = useMutation({
    mutationFn: () => {
      const f = new FormData();
      const onlyRestricted = ["reason", "legal_basis", "alert_level"];
      Object.entries(form).forEach(([k, v]) => {
        if (!restricted && onlyRestricted.includes(k)) return;
        f.set(k, k === "expires_at" ? new Date(`${v}T23:59:59`).toISOString() : v);
      });
      f.set("consent", String(!restricted && consent));
      if (!entry) f.set("confirm_duplicate", String(sameAnyway));
      if (photo) f.set("photo", photo);
      return entry ? postForm(`/api/persons/${entry.id}`, f, "PUT") : postForm("/api/persons", f);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["persons"] });
      toast({ kind: "success", title: entry ? "Registro actualizado" : "Registro creado", body: "La plantilla biométrica se guardó cifrada." });
      onClose();
    },
    onError: (err) => {
      setConfirmOpen(false);
      const d = err instanceof ApiError ? (err.detail as { report?: QualityReport; duplicates?: DuplicateMatch[] }) : null;
      if (d?.report) setReport(d.report);
      if (d?.duplicates && report) setReport({ ...report, duplicates: d.duplicates });
    },
  });

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
    setForm({ ...form, [k]: e.target.value });
  const valid = form.full_name.trim() && form.expires_at && (!needsConfirmation || consent)
    && (!restricted || (form.reason.trim() && form.legal_basis.trim()))
    && (entry || (photo && report?.ok)) && (!photo || report?.ok) && (entry || !duplicates.length || sameAnyway);

  return (
    <Modal open onClose={onClose} size="lg" title={entry ? `Editar ${entry.uid}` : "Añadir persona"}
      footer={<>
        <Button variant="ghost" onClick={onClose}>Cancelar</Button>
        <Button variant="primary" disabled={!valid} onClick={() => setConfirmOpen(true)}>{entry ? "Guardar cambios" : "Registrar persona"}</Button>
      </>}>
      <div className="grid gap-5 md:grid-cols-[220px_1fr]">
        <div>
          <label className="group grid aspect-[4/5] cursor-pointer place-items-center overflow-hidden rounded-lg border-2 border-dashed border-ink-600 bg-ink-900 transition hover:border-volt-500/60">
            {preview ? <img src={preview} alt="Vista previa" className="h-full w-full object-cover" /> : (
              <div className="p-4 text-center text-xs text-ink-300">
                <ImageUp className="mx-auto mb-2 h-8 w-8 text-ink-400 group-hover:text-volt-400" />
                {entry ? "Reemplazar fotografía (opcional)" : "Seleccionar fotografía"}<br /><span className="text-ink-400">JPG o PNG · máx. 6 MB</span>
              </div>
            )}
            <input type="file" accept="image/jpeg,image/png" className="hidden" onChange={(e) => pick(e.target.files?.[0])} />
          </label>
          {(checking || report) && (
            <div className="mt-3 space-y-1.5 rounded-lg border border-ink-700 bg-ink-900 p-3">
              <p className="text-xs font-semibold text-ink-200">{checking ? "Validando calidad…" : report?.ok ? "Fotografía apta" : "Fotografía no apta"}</p>
              {report?.checks.map((c) => (
                <p key={c.name} className="flex items-start gap-1.5 text-[11px]">
                  {c.ok ? <CheckCircle2 className="mt-px h-3.5 w-3.5 shrink-0 text-ok-400" /> : <CircleX className="mt-px h-3.5 w-3.5 shrink-0 text-alert-400" />}
                  <span><span className="text-ink-100">{c.name}:</span> <span className="text-ink-300">{c.detail}</span></span>
                </p>
              ))}
            </div>
          )}
          {duplicates.length > 0 && (
            <div className="mt-3 space-y-2 rounded-lg border border-warn-500/30 bg-warn-500/5 p-3 text-xs">
              <p className="flex items-center gap-1.5 font-semibold text-warn-400"><TriangleAlert className="h-3.5 w-3.5" />Posible duplicado</p>
              {duplicates.map((d) => <p key={d.entry_id} className="text-ink-200">{d.full_name} <span className="font-mono text-ink-400">{d.uid} · {fmtScore(d.score)}</span></p>)}
              {!entry && (
                <label className="flex items-start gap-2 text-ink-200">
                  <input type="checkbox" checked={sameAnyway} onChange={(e) => setSameAnyway(e.target.checked)} className="mt-0.5 accent-[#1f8bff]" />
                  Revisé el registro y es otra persona.
                </label>
              )}
            </div>
          )}
        </div>
        <div className="space-y-3">
          <Field label="Nombre completo" required><Input value={form.full_name} onChange={set("full_name")} maxLength={300} /></Field>
          <Field label="Clasificación" required hint="Una persona desconocida nunca se clasifica automáticamente.">
            <Select value={form.classification} onChange={(e) => { setForm({ ...form, classification: e.target.value as Classification }); setConsent(false); }}>
              <option value="no_autorizada">No autorizada (blacklist)</option><option value="autorizada">Autorizada</option>
            </Select>
          </Field>
          <div className="grid gap-3 sm:grid-cols-2">
            {restricted && (
              <Field label="Nivel de alerta" required hint="El buzzer suena desde el nivel configurado (por defecto, medio).">
                <Select value={form.alert_level} onChange={set("alert_level")}>
                  <option value="bajo">Bajo</option><option value="medio">Medio</option><option value="alto">Alto</option>
                </Select>
              </Field>
            )}
            <Field label="Próxima revisión / vencimiento" required hint="Al vencer, el registro se desactiva solo.">
              <Input type="date" value={form.expires_at} onChange={set("expires_at")} min={toDateInput(new Date().toISOString())} />
            </Field>
          </div>
          {restricted && <>
            <Field label="Motivo documentado de inclusión" required><Textarea value={form.reason} onChange={set("reason")} maxLength={300} /></Field>
            <Field label="Base legal / documento de autorización" required hint="Ej.: orden judicial N.º…, resolución de la asamblea de copropietarios del…">
              <Input value={form.legal_basis} onChange={set("legal_basis")} maxLength={300} />
            </Field>
          </>}
          <Field label="Información adicional autorizada"><Textarea value={form.info} onChange={set("info")} maxLength={2000} /></Field>
          <Field label="Observaciones"><Textarea value={form.notes} onChange={set("notes")} maxLength={2000} /></Field>
          {needsConfirmation && (
            <label className="flex items-start gap-2 rounded-lg border border-warn-500/30 bg-warn-500/5 p-3 text-xs text-ink-200">
              <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} className="mt-0.5 accent-[#1f8bff]" />
              {restricted ? "Confirmo que existe una autorización legal válida y documentada para registrar a esta persona, y que la información es exacta."
                : "Confirmo que esta persona dio su consentimiento para registrar su fotografía y sus datos biométricos."}
            </label>
          )}
          <ErrorNote error={save.error} />
        </div>
      </div>
      <ConfirmDialog open={confirmOpen} title={entry ? "Confirmar cambios" : "Confirmar registro"} loading={save.isPending}
        onClose={() => setConfirmOpen(false)} onConfirm={() => save.mutate()}
        message={entry ? `Se guardarán los cambios de ${entry.uid}. La modificación queda en el historial y en la auditoría.`
          : `Se registrará a ${form.full_name} como ${restricted ? `no autorizada, nivel ${form.alert_level}` : "autorizada"}. Sus datos biométricos se guardarán cifrados y la acción quedará auditada.`} />
    </Modal>
  );
}
