import { useState, type FormEvent } from "react";
import { KeyRound, LogOut } from "lucide-react";
import { post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useToast } from "@/lib/toast";
import { Button, Card, ErrorNote, Field, Input, PageHeader } from "@/components/ui";

export default function ChangePasswordPage({ forced }: { forced?: boolean }) {
  const { refresh, logout, me } = useAuth();
  const toast = useToast();
  const [form, setForm] = useState({ current: "", next: "", confirm: "" });
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (form.next !== form.confirm) return setError(new Error("Las contraseñas nuevas no coinciden."));
    setLoading(true);
    try {
      await post("/api/auth/change-password", { current_password: form.current, new_password: form.next });
      toast({ kind: "success", title: "Contraseña actualizada", body: "Las demás sesiones abiertas se cerraron." });
      setForm({ current: "", next: "", confirm: "" });
      await refresh();
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  };

  const content = (
    <form onSubmit={submit} className="space-y-4">
      <Field label="Contraseña actual" required>
        <Input type="password" autoComplete="current-password" value={form.current} onChange={(e) => setForm({ ...form, current: e.target.value })} required />
      </Field>
      <Field label="Nueva contraseña" hint="Mínimo 10 caracteres, con letras y números." required>
        <Input type="password" autoComplete="new-password" value={form.next} onChange={(e) => setForm({ ...form, next: e.target.value })} required />
      </Field>
      <Field label="Confirmar nueva contraseña" required>
        <Input type="password" autoComplete="new-password" value={form.confirm} onChange={(e) => setForm({ ...form, confirm: e.target.value })} required />
      </Field>
      <ErrorNote error={error} />
      <div className="flex gap-2">
        <Button type="submit" variant="primary" icon={KeyRound} loading={loading}>Guardar contraseña</Button>
        {forced && <Button type="button" variant="ghost" icon={LogOut} onClick={logout}>Salir</Button>}
      </div>
    </form>
  );

  if (forced) {
    return (
      <div className="grid-bg grid min-h-full place-items-center px-4 py-10">
        <div className="panel w-full max-w-md animate-fade-in p-6">
          <h1 className="text-lg font-semibold text-white">Cambie su contraseña temporal</h1>
          <p className="mb-5 mt-1 text-sm text-ink-300">
            Hola, {me?.full_name}. Por seguridad debe definir una contraseña personal antes de usar el sistema.
          </p>
          {content}
        </div>
      </div>
    );
  }
  return (
    <>
      <PageHeader title="Mi cuenta" subtitle={`${me?.full_name} · ${me?.role_label}`} icon={KeyRound} />
      <Card title="Cambiar contraseña" className="max-w-lg">{content}</Card>
    </>
  );
}
