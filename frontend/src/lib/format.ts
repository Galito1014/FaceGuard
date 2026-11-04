import type { Level, ReviewStatus } from "./types";

const dtf = new Intl.DateTimeFormat("es-BO", {
  day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
});
const df = new Intl.DateTimeFormat("es-BO", { day: "2-digit", month: "short", year: "numeric" });
const tf = new Intl.DateTimeFormat("es-BO", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });

export const fmtDateTime = (iso?: string | null) => (iso ? dtf.format(new Date(iso)) : "—");
export const fmtDate = (iso?: string | null) => (iso ? df.format(new Date(iso)) : "—");
export const fmtTime = (iso?: string | null) => (iso ? tf.format(new Date(iso)) : "—");

export function fmtRelative(iso?: string | null): string {
  if (!iso) return "—";
  const s = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 0) return "en el futuro";
  if (s < 10) return "ahora";
  if (s < 60) return `hace ${s} s`;
  if (s < 3600) return `hace ${Math.floor(s / 60)} min`;
  if (s < 86400) return `hace ${Math.floor(s / 3600)} h`;
  return `hace ${Math.floor(s / 86400)} d`;
}

export function fmtUptime(s: number): string {
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60);
  return d ? `${d} d ${h} h` : h ? `${h} h ${m} min` : `${m} min`;
}

/** Similitud coseno de SFace. No es una probabilidad: mostrarla como porcentaje exigiría calibrarla. */
export const fmtScore = (v?: number | null) => (v === null || v === undefined ? "—" : v.toFixed(3));

export const LEVEL_LABEL: Record<Level, string> = { bajo: "Bajo", medio: "Medio", alto: "Alto" };
export const REVIEW_LABEL: Record<ReviewStatus, string> = {
  pendiente: "Pendiente de revisión",
  confirmada: "Confirmada por operador",
  falso_positivo: "Descartada por operador",
  cerrada: "Cerrada",
};

/** Convierte 'YYYY-MM-DD' local en ISO para filtros (inicio o fin del día). */
export function dayToIso(day: string, end = false): string | undefined {
  if (!day) return undefined;
  const d = new Date(`${day}T${end ? "23:59:59" : "00:00:00"}`);
  return d.toISOString();
}

export function toDateInput(iso?: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}
