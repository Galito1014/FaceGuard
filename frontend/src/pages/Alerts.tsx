import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { FlaskConical, Search, Siren } from "lucide-react";
import { get, post, qs } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useToast } from "@/lib/toast";
import { fmtDateTime, fmtRelative, fmtScore } from "@/lib/format";
import type { FGEvent, Paged } from "@/lib/types";
import { Button, Card, Input, LevelBadge, PageHeader, Pagination, ReviewBadge, Select, SimBadge, Table, Td } from "@/components/ui";
import EventDetailModal from "@/components/EventDetail";

type Resp = Paged<FGEvent> & { counts: { status: string; n: number }[] };
const TABS = [
  { key: "pendiente", label: "Pendientes" },
  { key: "confirmada", label: "Confirmadas" },
  { key: "falso_positivo", label: "Falsos positivos" },
  { key: "cerrada", label: "Cerradas" },
  { key: "", label: "Todas" },
];

export default function AlertsPage() {
  const { can } = useAuth();
  const toast = useToast();
  const [params, setParams] = useSearchParams();
  const status = params.get("status") ?? "pendiente";
  const openId = params.get("id");
  const [level, setLevel] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);

  const list = useQuery({
    queryKey: ["alerts", status, level, q, page],
    queryFn: () => get<Resp>(`/api/alerts${qs({ status, level, q, page, page_size: 15 })}`),
    refetchInterval: 15000,
  });
  const count = (k: string) => (k ? list.data?.counts.find((c) => c.status === k)?.n ?? 0 : list.data?.counts.reduce((a, c) => a + c.n, 0) ?? 0);

  const simulate = useMutation({
    mutationFn: () => post<FGEvent>("/api/demo/alert"),
    onSuccess: () => toast({ kind: "info", title: "Alerta de prueba generada", body: "Está marcada como SIMULADO." }),
  });

  const setParam = (k: string, v: string | null) => {
    const p = new URLSearchParams(params);
    if (v === null) p.delete(k); else p.set(k, v);
    setParams(p, { replace: true });
  };

  return (
    <>
      <PageHeader title="Alertas" subtitle="Posibles coincidencias con la lista de alerta — requieren revisión humana" icon={Siren}
        actions={can("demo.control") && <Button icon={FlaskConical} loading={simulate.isPending} onClick={() => simulate.mutate()}>Generar alerta de prueba</Button>} />

      <div className="mb-4 flex flex-wrap gap-1 rounded-xl border border-ink-700 bg-ink-850/70 p-1">
        {TABS.map((t) => (
          <button key={t.key} onClick={() => { setParam("status", t.key); setPage(1); }}
            className={clsx("flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm font-medium transition",
              status === t.key ? "bg-volt-500/15 text-white" : "text-ink-300 hover:text-white")}>
            {t.label}
            <span className={clsx("rounded-md px-1.5 font-mono text-[11px]", t.key === "pendiente" && count(t.key) ? "bg-alert-500 text-white" : "bg-ink-700 text-ink-200")}>{count(t.key)}</span>
          </button>
        ))}
      </div>

      <Card bodyClass="p-3">
        <div className="mb-3 grid gap-2 md:grid-cols-[1fr_180px]">
          <Input icon={Search} placeholder="Buscar por ID, nombre o responsable…" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
          <Select value={level} onChange={(e) => { setLevel(e.target.value); setPage(1); }}>
            <option value="">Todos los niveles</option><option value="alto">Alto</option><option value="medio">Medio</option><option value="bajo">Bajo</option>
          </Select>
        </div>
        <Table head={["", "Fecha y hora", "Alerta", "Posible coincidencia", "Similitud", "Nivel", "Estado", "Responsable"]}
          loading={list.isLoading} empty={list.data?.items.length === 0}>
          {list.data?.items.map((a) => (
            <tr key={a.id} className="row-hover" onClick={() => setParam("id", String(a.id))}>
              <Td><span className={clsx("block h-2.5 w-2.5 rounded-full", a.review_status === "pendiente" ? (a.level === "alto" ? "animate-pulse bg-alert-500" : "bg-warn-400") : "bg-ink-500")} /></Td>
              <Td><span className="text-ink-100">{fmtDateTime(a.occurred_at)}</span><span className="ml-2 text-[11px] text-ink-400">{fmtRelative(a.occurred_at)}</span></Td>
              <Td mono>{a.uid} {a.is_simulated && <SimBadge />}</Td>
              <Td className="font-medium">{a.entry_name ?? "—"}</Td>
              <Td mono>{fmtScore(a.score)}</Td>
              <Td><LevelBadge level={a.level} /></Td>
              <Td><ReviewBadge status={a.review_status} /></Td>
              <Td className="text-ink-200">{a.reviewer_name ?? "—"}</Td>
            </tr>
          ))}
        </Table>
        {list.data && <Pagination page={page} pageSize={list.data.page_size} total={list.data.total} onPage={setPage} />}
      </Card>

      {openId && <EventDetailModal id={Number(openId)} onClose={() => setParam("id", null)} />}
    </>
  );
}
