import clsx from "clsx";
import { forwardRef, useEffect, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode,
  type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";
import { ChevronLeft, ChevronRight, FlaskConical, Inbox, Loader2, X } from "lucide-react";
import type { Level, ReviewStatus } from "@/lib/types";
import { LEVEL_LABEL, REVIEW_LABEL } from "@/lib/format";

/* ------------------------------------------------------------------ layout */
export function Card({ className, children, title, icon: Icon, actions, bodyClass }: {
  className?: string; children: ReactNode; title?: ReactNode; icon?: React.ElementType; actions?: ReactNode; bodyClass?: string;
}) {
  return (
    <section className={clsx("panel animate-fade-in", className)}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-3 border-b border-ink-700/70 px-4 py-3">
          <h2 className="flex items-center gap-2 text-[13px] font-semibold uppercase tracking-wider text-ink-200">
            {Icon && <Icon className="h-4 w-4 text-volt-400" />}
            {title}
          </h2>
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={clsx("p-4", bodyClass)}>{children}</div>
    </section>
  );
}

export function PageHeader({ title, subtitle, icon: Icon, actions }: {
  title: string; subtitle?: string; icon?: React.ElementType; actions?: ReactNode;
}) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div className="flex items-center gap-3">
        {Icon && (
          <div className="grid h-10 w-10 place-items-center rounded-xl border border-volt-500/30 bg-volt-500/10">
            <Icon className="h-5 w-5 text-volt-400" />
          </div>
        )}
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-white">{title}</h1>
          {subtitle && <p className="text-sm text-ink-300">{subtitle}</p>}
        </div>
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function StatCard({ label, value, icon: Icon, tone = "volt", hint, pulse }: {
  label: string; value: ReactNode; icon: React.ElementType; tone?: "volt" | "red" | "green" | "amber" | "slate";
  hint?: ReactNode; pulse?: boolean;
}) {
  const tones = {
    volt: "text-volt-400 bg-volt-500/10 border-volt-500/25",
    red: "text-alert-400 bg-alert-500/10 border-alert-500/30",
    green: "text-ok-400 bg-ok-500/10 border-ok-500/25",
    amber: "text-warn-400 bg-warn-500/10 border-warn-500/25",
    slate: "text-ink-200 bg-ink-600/30 border-ink-500/40",
  };
  return (
    <div className="panel animate-fade-in p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-medium uppercase leading-tight tracking-wider text-ink-300">{label}</p>
          <p className="mt-1.5 font-mono text-2xl font-semibold tabular-nums text-white">{value}</p>
        </div>
        <div className={clsx("grid h-9 w-9 shrink-0 place-items-center rounded-lg border", tones[tone], pulse && "animate-pulse-ring")}>
          <Icon className="h-[18px] w-[18px]" />
        </div>
      </div>
      {hint && <div className="mt-2 text-xs text-ink-300">{hint}</div>}
    </div>
  );
}

/* ------------------------------------------------------------------ botones */
type BtnVariant = "primary" | "secondary" | "danger" | "ghost" | "success";
export const Button = forwardRef<HTMLButtonElement, ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: BtnVariant; icon?: React.ElementType; loading?: boolean; size?: "sm" | "md";
}>(({ variant = "secondary", icon: Icon, loading, size = "md", className, children, disabled, ...props }, ref) => (
  <button
    ref={ref}
    disabled={disabled || loading}
    className={clsx(
      "inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-volt-500/60 disabled:cursor-not-allowed disabled:opacity-50",
      size === "sm" ? "h-8 px-3 text-xs" : "h-9 px-3.5 text-sm",
      variant === "primary" && "bg-volt-500 text-white shadow-[0_0_20px_-6px_rgba(31,139,255,.8)] hover:bg-volt-400",
      variant === "secondary" && "border border-ink-600 bg-ink-750 text-ink-100 hover:border-ink-500 hover:bg-ink-700",
      variant === "danger" && "border border-alert-500/40 bg-alert-500/15 text-alert-400 hover:bg-alert-500/25",
      variant === "success" && "border border-ok-500/40 bg-ok-500/15 text-ok-400 hover:bg-ok-500/25",
      variant === "ghost" && "text-ink-200 hover:bg-ink-750 hover:text-white",
      className,
    )}
    {...props}
  >
    {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : Icon ? <Icon className="h-4 w-4" /> : null}
    {children}
  </button>
));
Button.displayName = "Button";

/* ------------------------------------------------------------------ badges */
export function Badge({ children, tone = "slate", className, dot }: {
  children: ReactNode; tone?: "slate" | "volt" | "red" | "green" | "amber" | "violet"; className?: string; dot?: boolean;
}) {
  const tones = {
    slate: "border-ink-500/50 bg-ink-600/30 text-ink-200",
    volt: "border-volt-500/40 bg-volt-500/10 text-volt-300",
    red: "border-alert-500/40 bg-alert-500/10 text-alert-400",
    green: "border-ok-500/40 bg-ok-500/10 text-ok-400",
    amber: "border-warn-500/40 bg-warn-500/10 text-warn-400",
    violet: "border-fuchsia-500/40 bg-fuchsia-500/10 text-fuchsia-300",
  };
  return (
    <span className={clsx("inline-flex items-center gap-1.5 whitespace-nowrap rounded-md border px-2 py-0.5 text-[11px] font-semibold", tones[tone], className)}>
      {dot && <span className="h-1.5 w-1.5 rounded-full bg-current" />}
      {children}
    </span>
  );
}

export const LevelBadge = ({ level }: { level: Level | null }) =>
  level ? <Badge tone={level === "alto" ? "red" : level === "medio" ? "amber" : "volt"} dot>{LEVEL_LABEL[level]}</Badge> : <span className="text-ink-400">—</span>;

export const ReviewBadge = ({ status }: { status: ReviewStatus | null }) => {
  if (!status) return <span className="text-ink-400">—</span>;
  const tone = { pendiente: "amber", confirmada: "red", falso_positivo: "green", cerrada: "slate" } as const;
  return <Badge tone={tone[status]}>{REVIEW_LABEL[status]}</Badge>;
};

export const SimBadge = ({ show = true }: { show?: boolean }) =>
  show ? (
    <Badge tone="violet" className="uppercase tracking-wide">
      <FlaskConical className="h-3 w-3" /> Simulado
    </Badge>
  ) : null;

export function StatusDot({ ok, warn, label }: { ok: boolean; warn?: boolean; label: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-2 text-sm">
      <span className={clsx("relative flex h-2.5 w-2.5")}>
        {ok && <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-ok-400 opacity-50" />}
        <span className={clsx("relative inline-flex h-2.5 w-2.5 rounded-full", ok ? "bg-ok-400" : warn ? "bg-warn-400" : "bg-alert-500")} />
      </span>
      {label}
    </span>
  );
}

/* ---------------------------------------------------------------- formularios */
export function Field({ label, hint, error, children, required }: {
  label: string; hint?: ReactNode; error?: string; children: ReactNode; required?: boolean;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-xs font-medium text-ink-200">
        {label} {required && <span className="text-alert-400">*</span>}
      </span>
      {children}
      {hint && !error && <span className="mt-1 block text-[11px] text-ink-400">{hint}</span>}
      {error && <span className="mt-1 block text-[11px] text-alert-400">{error}</span>}
    </label>
  );
}

const inputCls = "w-full rounded-lg border border-ink-600 bg-ink-900 px-3 text-sm text-ink-100 placeholder:text-ink-400 transition focus:border-volt-500 focus:outline-none focus:ring-2 focus:ring-volt-500/25 disabled:opacity-60";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement> & { icon?: React.ElementType }>(
  ({ className, icon: Icon, ...props }, ref) =>
    Icon ? (
      <div className="relative">
        <Icon className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-400" />
        <input ref={ref} className={clsx(inputCls, "h-9 pl-9", className)} {...props} />
      </div>
    ) : (
      <input ref={ref} className={clsx(inputCls, "h-9", className)} {...props} />
    ),
);
Input.displayName = "Input";

export const Select = ({ className, children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) => (
  <select className={clsx(inputCls, "h-9 pr-8", className)} {...props}>{children}</select>
);

export const Textarea = ({ className, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) => (
  <textarea className={clsx(inputCls, "min-h-[76px] py-2", className)} {...props} />
);

export function Toggle({ checked, onChange, disabled, label, description }: {
  checked: boolean; onChange: (v: boolean) => void; disabled?: boolean; label?: ReactNode; description?: ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-4">
      {(label || description) && (
        <div>
          {label && <p className="text-sm font-medium text-ink-100">{label}</p>}
          {description && <p className="text-xs text-ink-300">{description}</p>}
        </div>
      )}
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={clsx("relative h-6 w-11 shrink-0 rounded-full border transition disabled:opacity-50",
          checked ? "border-volt-500 bg-volt-500/80" : "border-ink-500 bg-ink-700")}
      >
        <span className={clsx("absolute top-0.5 h-[18px] w-[18px] rounded-full bg-white shadow transition-all", checked ? "left-[22px]" : "left-0.5")} />
      </button>
    </div>
  );
}

/* -------------------------------------------------------------------- modal */
export function Modal({ open, onClose, title, children, footer, size = "md", danger }: {
  open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; footer?: ReactNode;
  size?: "sm" | "md" | "lg" | "xl"; danger?: boolean;
}) {
  useEffect(() => {
    if (!open) return;
    const fn = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", fn);
    return () => window.removeEventListener("keydown", fn);
  }, [open, onClose]);
  if (!open) return null;
  const w = { sm: "max-w-md", md: "max-w-xl", lg: "max-w-3xl", xl: "max-w-5xl" }[size];
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/70 p-4 backdrop-blur-sm sm:items-center" onMouseDown={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        onMouseDown={(e) => e.stopPropagation()}
        className={clsx("panel my-8 w-full animate-fade-in", w, danger && "border-alert-500/40")}
      >
        <div className="flex items-center justify-between border-b border-ink-700 px-5 py-3.5">
          <h3 className="text-base font-semibold text-white">{title}</h3>
          <button onClick={onClose} className="rounded-md p-1 text-ink-300 hover:bg-ink-700 hover:text-white" aria-label="Cerrar">
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="max-h-[75vh] overflow-y-auto p-5">{children}</div>
        {footer && <div className="flex flex-wrap justify-end gap-2 border-t border-ink-700 px-5 py-3">{footer}</div>}
      </div>
    </div>
  );
}

export function ConfirmDialog({ open, title, message, confirmLabel = "Confirmar", danger, loading, onConfirm, onClose, children }: {
  open: boolean; title: string; message: ReactNode; confirmLabel?: string; danger?: boolean; loading?: boolean;
  onConfirm: () => void; onClose: () => void; children?: ReactNode;
}) {
  return (
    <Modal open={open} onClose={onClose} title={title} size="sm" danger={danger}
      footer={<>
        <Button variant="ghost" onClick={onClose}>Cancelar</Button>
        <Button variant={danger ? "danger" : "primary"} loading={loading} onClick={onConfirm}>{confirmLabel}</Button>
      </>}>
      <div className="text-sm leading-relaxed text-ink-200">{message}</div>
      {children}
    </Modal>
  );
}

/* -------------------------------------------------------------------- tablas */
export function Table({ head, children, empty, loading }: {
  head: ReactNode[]; children: ReactNode; empty?: boolean; loading?: boolean;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[720px] text-left text-sm">
        <thead>
          <tr className="border-b border-ink-700 text-[11px] uppercase tracking-wider text-ink-300">
            {head.map((h, i) => <th key={i} className="whitespace-nowrap px-3 py-2.5 font-semibold">{h}</th>)}
          </tr>
        </thead>
        <tbody className="divide-y divide-ink-700/60">{children}</tbody>
      </table>
      {loading && <div className="py-10"><Spinner /></div>}
      {!loading && empty && <EmptyState />}
    </div>
  );
}

export const Td = ({ children, className, mono }: { children?: ReactNode; className?: string; mono?: boolean }) => (
  <td className={clsx("whitespace-nowrap px-3 py-2.5 text-ink-100", mono && "font-mono text-xs text-ink-200", className)}>{children}</td>
);

export function Pagination({ page, pageSize, total, onPage }: { page: number; pageSize: number; total: number; onPage: (p: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  return (
    <div className="flex items-center justify-between gap-3 border-t border-ink-700 px-3 pt-3 text-xs text-ink-300">
      <span>{total} registro{total === 1 ? "" : "s"} · página {page} de {pages}</span>
      <div className="flex gap-1">
        <Button size="sm" variant="ghost" icon={ChevronLeft} disabled={page <= 1} onClick={() => onPage(page - 1)}>Anterior</Button>
        <Button size="sm" variant="ghost" disabled={page >= pages} onClick={() => onPage(page + 1)}>
          Siguiente <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}

export function EmptyState({ title = "Sin resultados", text = "No hay registros que coincidan con los filtros.", icon: Icon = Inbox }: {
  title?: string; text?: string; icon?: React.ElementType;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-12 text-center">
      <div className="grid h-12 w-12 place-items-center rounded-full border border-ink-600 bg-ink-800">
        <Icon className="h-5 w-5 text-ink-300" />
      </div>
      <p className="text-sm font-medium text-ink-100">{title}</p>
      <p className="max-w-sm text-xs text-ink-300">{text}</p>
    </div>
  );
}

export const Spinner = ({ className }: { className?: string }) => (
  <div className={clsx("flex justify-center", className)}><Loader2 className="h-6 w-6 animate-spin text-volt-400" /></div>
);

export function Meter({ value, max = 100, tone }: { value: number; max?: number; tone?: "auto" | "volt" }) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100));
  const color = tone === "volt" ? "bg-volt-500" : pct > 85 ? "bg-alert-500" : pct > 65 ? "bg-warn-500" : "bg-ok-500";
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-ink-700">
      <div className={clsx("h-full rounded-full transition-all duration-700", color)} style={{ width: `${pct}%` }} />
    </div>
  );
}

export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null;
  return (
    <div className="rounded-lg border border-alert-500/40 bg-alert-500/10 px-3 py-2 text-sm text-alert-400">
      {error instanceof Error ? error.message : String(error)}
    </div>
  );
}
