import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ScrollText, Search } from "lucide-react";
import { get, qs } from "@/lib/api";
import { dayToIso, fmtDateTime } from "@/lib/format";
import type { AuditRow, Paged } from "@/lib/types";
import { Card, Field, Input, PageHeader, Pagination, Table, Td } from "@/components/ui";

export default function AuditPage() {
  const [search, setSearch] = useState("");
  const [q, setQ] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [page, setPage] = useState(1);
  useEffect(() => {
    const t = setTimeout(() => { setQ(search); setPage(1); }, 300);
    return () => clearTimeout(t);
  }, [search]);
  const list = useQuery({
    queryKey: ["audit", q, from, to, page],
    queryFn: () => get<Paged<AuditRow>>(`/api/audit${qs({ q, date_from: dayToIso(from), date_to: dayToIso(to, true), page, page_size: 30 })}`),
  });
  return (
    <>
      <PageHeader title="Auditoría" subtitle="Registro inalterable desde la interfaz de toda acción administrativa" icon={ScrollText} />
      <Card bodyClass="p-3">
        <div className="mb-3 grid gap-2 md:grid-cols-[1fr_160px_160px]">
          <Field label="Buscar"><Input icon={Search} placeholder="Usuario, acción u objetivo…" value={search} onChange={(e) => setSearch(e.target.value)} /></Field>
          <Field label="Desde"><Input type="date" value={from} onChange={(e) => { setFrom(e.target.value); setPage(1); }} /></Field>
          <Field label="Hasta"><Input type="date" value={to} onChange={(e) => { setTo(e.target.value); setPage(1); }} /></Field>
        </div>
        <Table head={["Fecha y hora", "Usuario", "Acción", "Objetivo", "Detalles", "IP"]} loading={list.isLoading} empty={list.data?.items.length === 0}>
          {list.data?.items.map((r) => (
            <tr key={r.id}>
              <Td className="text-ink-200">{fmtDateTime(r.at)}</Td>
              <Td mono>{r.username ?? "—"}</Td>
              <Td className={r.action.includes("fallido") || r.action.includes("elimina") ? "font-medium text-alert-400" : "font-medium"}>{r.action}</Td>
              <Td mono>{r.target || "—"}</Td>
              <Td className="max-w-[360px] truncate font-mono text-[11px] text-ink-300" >{r.details || "—"}</Td>
              <Td mono>{r.ip ?? "—"}</Td>
            </tr>
          ))}
        </Table>
        {list.data && <Pagination page={page} pageSize={list.data.page_size} total={list.data.total} onPage={setPage} />}
      </Card>
    </>
  );
}
