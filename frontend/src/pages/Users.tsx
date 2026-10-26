import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, Pencil, Plus, Trash2, UserCog } from "lucide-react";
import { del, get, post, put } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useToast } from "@/lib/toast";
import { fmtDateTime } from "@/lib/format";
import type { Role, UserRow } from "@/lib/types";
import { Badge, Button, Card, ConfirmDialog, ErrorNote, Field, Input, Modal, PageHeader, Select, Table, Td, Toggle } from "@/components/ui";

const ROLES: { value: Role; label: string; desc: string }[] = [
  { value: "superadmin", label: "Superadministrador", desc: "Configuración, usuarios y auditoría" },
  { value: "admin", label: "Administrador", desc: "Lista de alerta, alertas y registros" },
  { value: "operator", label: "Operador", desc: "Monitoreo y revisión de alertas" },
  { value: "auditor", label: "Auditor", desc: "Consulta sin permisos de modificación" },
];

export default function UsersPage() {
  const { me } = useAuth();
  const qc = useQueryClient();
  const toast = useToast();
  const users = useQuery({ queryKey: ["users"], queryFn: () => get<UserRow[]>("/api/users") });
  const [editing, setEditing] = useState<UserRow | "new" | null>(null);
  const [deleting, setDeleting] = useState<UserRow | null>(null);

  const remove = useMutation({
    mutationFn: (id: number) => del(`/api/users/${id}`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["users"] }); setDeleting(null); toast({ kind: "success", title: "Usuario eliminado" }); },
    onError: (e) => { setDeleting(null); toast({ kind: "error", title: "No se pudo eliminar", body: (e as Error).message }); },
  });

  return (
    <>
      <PageHeader title="Usuarios y roles" subtitle="Control de acceso basado en roles" icon={UserCog}
        actions={<Button variant="primary" icon={Plus} onClick={() => setEditing("new")}>Nuevo usuario</Button>} />
      <div className="mb-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {ROLES.map((r) => (
          <div key={r.value} className="panel p-3">
            <p className="text-sm font-semibold text-white">{r.label}</p>
            <p className="text-xs text-ink-300">{r.desc}</p>
            <p className="mt-2 font-mono text-lg text-volt-300">{users.data?.filter((u) => u.role === r.value).length ?? 0}</p>
          </div>
        ))}
      </div>
      <Card bodyClass="p-3">
        <Table head={["Usuario", "Nombre", "Rol", "Estado", "Último acceso", "Creado", ""]} loading={users.isLoading} empty={users.data?.length === 0}>
          {users.data?.map((u) => (
            <tr key={u.id}>
              <Td mono>{u.username} {u.id === me?.id && <Badge tone="volt">usted</Badge>}</Td>
              <Td>{u.full_name}</Td>
              <Td><Badge tone={u.role === "superadmin" ? "red" : u.role === "admin" ? "amber" : u.role === "operator" ? "volt" : "slate"}>{u.role_label}</Badge></Td>
              <Td>{u.active ? <Badge tone="green" dot>Activo</Badge> : <Badge dot>Desactivado</Badge>}
                {!!u.must_change_password && <Badge tone="amber" className="ml-1.5">Contraseña temporal</Badge>}</Td>
              <Td className="text-ink-200">{fmtDateTime(u.last_login)}</Td>
              <Td className="text-ink-200">{fmtDateTime(u.created_at)}</Td>
              <Td>
                <div className="flex justify-end gap-1">
                  <Button size="sm" variant="ghost" icon={Pencil} onClick={() => setEditing(u)}>Editar</Button>
                  {u.id !== me?.id && <Button size="sm" variant="ghost" icon={Trash2} onClick={() => setDeleting(u)} className="hover:text-alert-400">Eliminar</Button>}
                </div>
              </Td>
            </tr>
          ))}
        </Table>
      </Card>
      {editing && <UserForm user={editing === "new" ? null : editing} self={editing !== "new" && editing.id === me?.id} onClose={() => setEditing(null)} />}
      <ConfirmDialog open={!!deleting} danger title="Eliminar usuario" confirmLabel="Eliminar" loading={remove.isPending}
        onClose={() => setDeleting(null)} onConfirm={() => deleting && remove.mutate(deleting.id)}
        message={<>Se eliminará la cuenta <b>{deleting?.username}</b>. Sus revisiones anteriores conservan el nombre del responsable. Considere desactivarla en lugar de eliminarla.</>} />
    </>
  );
}

function UserForm({ user, self, onClose }: { user: UserRow | null; self: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [form, setForm] = useState({ username: user?.username ?? "", full_name: user?.full_name ?? "", role: user?.role ?? "operator" as Role,
    active: user ? !!user.active : true, password: "" });
  const save = useMutation({
    mutationFn: () => user
      ? put(`/api/users/${user.id}`, { full_name: form.full_name, role: form.role, active: form.active, password: form.password || undefined })
      : post("/api/users", { username: form.username, full_name: form.full_name, role: form.role, password: form.password }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["users"] });
      toast({ kind: "success", title: user ? "Usuario actualizado" : "Usuario creado", body: form.password ? "Deberá cambiar la contraseña temporal al ingresar." : undefined });
      onClose();
    },
  });
  return (
    <Modal open onClose={onClose} title={user ? `Editar ${user.username}` : "Nuevo usuario"}
      footer={<><Button variant="ghost" onClick={onClose}>Cancelar</Button><Button variant="primary" loading={save.isPending} onClick={() => save.mutate()}>Guardar</Button></>}>
      <div className="space-y-3">
        {!user && <Field label="Nombre de usuario" required hint="Letras, números, punto, guion o guion bajo."><Input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} /></Field>}
        <Field label="Nombre completo" required><Input value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} /></Field>
        <Field label="Rol" required>
          <Select value={form.role} disabled={self} onChange={(e) => setForm({ ...form, role: e.target.value as Role })}>
            {ROLES.map((r) => <option key={r.value} value={r.value}>{r.label} — {r.desc}</option>)}
          </Select>
        </Field>
        <Field label={user ? "Restablecer contraseña (opcional)" : "Contraseña temporal"} required={!user} hint="Mínimo 10 caracteres con letras y números. El usuario deberá cambiarla al ingresar.">
          <Input type="password" autoComplete="new-password" icon={KeyRound} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
        </Field>
        {user && !self && <Toggle checked={form.active} onChange={(v) => setForm({ ...form, active: v })} label="Cuenta activa" description="Una cuenta desactivada no puede iniciar sesión." />}
        <ErrorNote error={save.error} />
      </div>
    </Modal>
  );
}
