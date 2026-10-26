import { useState, type FormEvent } from "react";
import { Lock, LogIn, ShieldCheck, User } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { Button, ErrorNote, Field, Input } from "@/components/ui";
import Logo from "@/components/Logo";

export default function LoginPage() {
  const { login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await login(username.trim(), password);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="grid-bg relative grid min-h-full place-items-center overflow-hidden px-4 py-10">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-volt-500/60 to-transparent" />
      <div className="w-full max-w-sm animate-fade-in">
        <div className="mb-8 flex flex-col items-center text-center">
          <Logo className="h-16 w-16 drop-shadow-[0_0_24px_rgba(31,139,255,.45)]" />
          <h1 className="mt-4 text-2xl font-bold tracking-tight text-white">FaceGuard <span className="text-volt-400">AI</span></h1>
          <p className="mt-1 text-sm text-ink-300">Sistema de alerta por reconocimiento facial</p>
        </div>
        <form onSubmit={submit} className="panel space-y-4 p-6">
          <Field label="Usuario">
            <Input icon={User} autoFocus autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required />
          </Field>
          <Field label="Contraseña">
            <Input icon={Lock} type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
          </Field>
          <ErrorNote error={error} />
          <Button type="submit" variant="primary" icon={LogIn} loading={loading} className="w-full">Iniciar sesión</Button>
        </form>
        <p className="mt-6 flex items-center justify-center gap-1.5 text-center text-[11px] text-ink-400">
          <ShieldCheck className="h-3.5 w-3.5" /> Acceso restringido a personal autorizado. Toda actividad queda auditada.
        </p>
      </div>
    </div>
  );
}
