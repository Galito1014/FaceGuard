import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import { AlertTriangle, CheckCircle2, Info, Siren, X } from "lucide-react";
import clsx from "clsx";

type Kind = "success" | "error" | "info" | "alert";
interface Toast {
  id: number;
  kind: Kind;
  title: string;
  body?: string;
  action?: { label: string; onClick: () => void };
}

const Ctx = createContext<{ push: (t: Omit<Toast, "id">) => void } | null>(null);
let seq = 0;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);
  const dismiss = (id: number) => setItems((xs) => xs.filter((t) => t.id !== id));
  const push = useCallback((t: Omit<Toast, "id">) => {
    const id = ++seq;
    setItems((xs) => [...xs.slice(-4), { ...t, id }]);
    setTimeout(() => dismiss(id), t.kind === "alert" ? 12000 : 5000);
  }, []);

  const icon = { success: CheckCircle2, error: AlertTriangle, info: Info, alert: Siren };
  return (
    <Ctx.Provider value={{ push }}>
      {children}
      <div className="pointer-events-none fixed right-4 top-4 z-[100] flex w-[360px] max-w-[calc(100vw-2rem)] flex-col gap-2">
        {items.map((t) => {
          const Icon = icon[t.kind];
          return (
            <div
              key={t.id}
              role="status"
              className={clsx(
                "pointer-events-auto animate-slide-in rounded-xl border bg-ink-850/95 p-3.5 backdrop-blur",
                t.kind === "alert" && "border-alert-500/60 shadow-glow-red",
                t.kind === "error" && "border-alert-500/40",
                t.kind === "success" && "border-ok-500/40",
                t.kind === "info" && "border-volt-500/40",
              )}
            >
              <div className="flex gap-3">
                <Icon
                  className={clsx(
                    "mt-0.5 h-5 w-5 shrink-0",
                    t.kind === "alert" || t.kind === "error" ? "text-alert-400" : t.kind === "success" ? "text-ok-400" : "text-volt-400",
                  )}
                />
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold text-ink-100">{t.title}</p>
                  {t.body && <p className="mt-0.5 text-[13px] leading-snug text-ink-300">{t.body}</p>}
                  {t.action && (
                    <button
                      onClick={() => {
                        t.action!.onClick();
                        dismiss(t.id);
                      }}
                      className="mt-2 text-xs font-semibold text-volt-400 hover:text-volt-300"
                    >
                      {t.action.label} →
                    </button>
                  )}
                </div>
                <button onClick={() => dismiss(t.id)} className="text-ink-400 hover:text-ink-100" aria-label="Cerrar">
                  <X className="h-4 w-4" />
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </Ctx.Provider>
  );
}

export function useToast() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useToast fuera de ToastProvider");
  return ctx.push;
}
