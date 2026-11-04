import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { FileClock, FileDown, FileSpreadsheet, RotateCcw, Search } from "lucide-react";
import { download, get, qs } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useToast } from "@/lib/toast";
import { dayToIso, fmtDateTime, fmtScore } from "@/lib/format";
import type { FGEvent, Paged } from "@/lib/types";
import { Button, Card, Field, Input, LevelBadge, PageHeader, Pagination, ReviewBadge, Select, SimBadge, Table, Td } from "@/components/ui";
import EventDetailModal from "@/components/EventDetail";

const EMPTY = { q: "", type: "", level: "", status: "", from: "", to: "", simulated: "" };

export default function EventsPage() {
  const { can } = useAuth();
  const toast = useToast();
  const [params, setParams] = useSearchParams();
  const [f, setF] = useState(EMPTY);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [exporting, setExporting] = useState<string | null>(null);
  const openId = params.get("id");

  useEffect(() => {
    const t = setTimeout(() => { setF((x) => ({ ...x, q: search })); setPage(1); }, 300);
    return () => clearTimeout(t);
  }, [search]);

  const filterQs = { q: f.q, type: f.type, level: f.level, status: f.status, simulated: f.simulated,
    date_from: dayToIso(f.from), date_to: dayToIso(f.to, true) };
  const list = useQuery({
    queryKey: ["events", f, page],
    queryFn: () => get<Paged<FGEvent>>(`/api/events${qs({ ...filterQs, page, page_size: 20 })}`),
  });
  const set = (k: keyof typeof EMPTY) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => { setF({ ...f, [k]: e.target.value }); setPage(1); };

  const exportAs = async (format: "csv" | "pdf") => {
    setExporting(format);
    try {
      await download(`/api/events/export${qs({ ...filterQs, format })}`, `faceguard-eventos.${format}`);
      toast({ kind: "success", title: `Exportación ${format.toUpperCase()} lista`, body: "La descarga quedó registrada en la auditoría." });
    } catch (e) {
      toast({ kind: "error", title: "No se pudo exportar", body: (e as Error).message });
    } finally {
      setExporting(null);
    }
  };

  const openEvent = (id: number | null) => {
    const p = new URLSearchParams(params);
    if (id === null) p.delete("id"); else p.set("id", String(id));
    setParams(p, { replace: true });
  };

  return (
    <>
      <PageHeader title="Historial de detecciones y eventos" subtitle="Consulta, filtros y exportación del registro de actividad" icon={FileClock}
        actions={can("events.export") && <>
          <Button icon={FileSpreadsheet} loading={exporting === "csv"} onClick={() => exportAs("csv")}>Exportar CSV</Button>
          <Button icon={FileDown} loading={exporting === "pdf"} onClick={() => exportAs("pdf")}>Exportar PDF</Button>
        </>} />

      <Card bodyClass="p-3">
        <div className="mb-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-[1.4fr_repeat(4,1fr)_140px_140px_auto]">
          <Field label="Buscar"><Input icon={Search} placeholder="ID, persona, responsable…" value={search} onChange={(e) => setSearch(e.target.value)} /></Field>
          <Field label="Tipo">
            <Select value={f.type} onChange={set("type")}>
              <option value="">Todos</option><option value="deteccion">Detección</option><option value="coincidencia">Posible coincidencia</option>
              <option value="captura">Captura autorizada</option><option value="sistema">Sistema</option>
            </Select>
          </Field>
          <Field label="Nivel">
            <Select value={f.level} onChange={set("level")}><option value="">Todos</option><option value="alto">Alto</option><option value="medio">Medio</option><option value="bajo">Bajo</option></Select>
          </Field>
          <Field label="Estado">
            <Select value={f.status} onChange={set("status")}>
              <option value="">Todos</option><option value="pendiente">Pendiente</option><option value="confirmada">Confirmada</option>
              <option value="falso_positivo">Descartada</option><option value="cerrada">Cerrada</option>
            </Select>
          </Field>
          <Field label="Origen">
            <Select value={f.simulated} onChange={set("simulated")}><option value="">Todos</option><option value="0">Real</option><option value="1">Simulado</option></Select>
          </Field>
          <Field label="Desde"><Input type="date" value={f.from} onChange={set("from")} /></Field>
          <Field label="Hasta"><Input type="date" value={f.to} onChange={set("to")} /></Field>
          <div className="flex items-end"><Button variant="ghost" icon={RotateCcw} onClick={() => { setF(EMPTY); setSearch(""); setPage(1); }}>Limpiar</Button></div>
        </div>
        <Table head={["ID del evento", "Fecha y hora", "Cámara", "Tipo", "Posible coincidencia", "Similitud", "Nivel", "Revisión", "Responsable", "Observaciones"]}
          loading={list.isLoading} empty={list.data?.items.length === 0}>
          {list.data?.items.map((e) => (
            <tr key={e.id} className="row-hover" onClick={() => openEvent(e.id)}>
              <Td mono>{e.uid} {e.is_simulated && <SimBadge />}</Td>
              <Td className="text-ink-200">{fmtDateTime(e.occurred_at)}</Td>
              <Td className="text-ink-200">{e.camera}</Td>
              <Td>{e.type_label}{e.type === "deteccion" && <span className="text-ink-400"> ({e.faces_count})</span>}</Td>
              <Td>{e.entry_name ?? <span className="text-ink-400">—</span>}</Td>
              <Td mono>{fmtScore(e.score)}</Td>
              <Td><LevelBadge level={e.level} /></Td>
              <Td><ReviewBadge status={e.review_status} /></Td>
              <Td className="text-ink-200">{e.reviewer_name ?? "—"}</Td>
              <Td className="max-w-[220px] truncate text-ink-300">{e.notes || e.message}</Td>
            </tr>
          ))}
        </Table>
        {list.data && <Pagination page={page} pageSize={list.data.page_size} total={list.data.total} onPage={setPage} />}
      </Card>
      {openId && <EventDetailModal id={Number(openId)} onClose={() => openEvent(null)} />}
    </>
  );
}
