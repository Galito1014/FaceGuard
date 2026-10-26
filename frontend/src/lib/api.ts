// Cliente HTTP para la API de FaceGuard AI. La sesión viaja en una cookie httpOnly.

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

type Handler = () => void;
let onUnauthorized: Handler = () => {};
export function setUnauthorizedHandler(fn: Handler) {
  onUnauthorized = fn;
}

function messageFrom(detail: unknown, fallback: string): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    // errores de validación de FastAPI
    return detail.map((d: { msg?: string; loc?: string[] }) => `${d.loc?.slice(-1)[0] ?? ""}: ${d.msg ?? ""}`).join(" · ");
  }
  if (detail && typeof detail === "object" && "message" in detail) return String((detail as { message: string }).message);
  return fallback;
}

export async function api<T = unknown>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const { json, headers, ...rest } = init;
  const res = await fetch(path, {
    credentials: "same-origin",
    ...rest,
    headers: { ...(json !== undefined ? { "Content-Type": "application/json" } : {}), ...headers },
    body: json !== undefined ? JSON.stringify(json) : rest.body,
  });
  if (res.status === 401 && !path.startsWith("/api/auth/login")) onUnauthorized();
  if (!res.ok) {
    let detail: unknown = undefined;
    try {
      detail = (await res.json()).detail;
    } catch {
      /* sin cuerpo JSON */
    }
    throw new ApiError(res.status, messageFrom(detail, `Error ${res.status}`), detail);
  }
  const type = res.headers.get("content-type") ?? "";
  return (type.includes("application/json") ? res.json() : res.text()) as Promise<T>;
}

export const get = <T,>(path: string) => api<T>(path);
export const post = <T,>(path: string, json?: unknown) => api<T>(path, { method: "POST", json: json ?? {} });
export const put = <T,>(path: string, json: unknown) => api<T>(path, { method: "PUT", json });
export const del = <T,>(path: string) => api<T>(path, { method: "DELETE" });
export const postForm = <T,>(path: string, form: FormData, method = "POST") => api<T>(path, { method, body: form });

export function qs(params: Record<string, string | number | undefined | null>): string {
  const p = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  });
  const s = p.toString();
  return s ? `?${s}` : "";
}

/** Descarga un archivo protegido (PDF/CSV) usando la sesión actual. */
export async function download(path: string, fallbackName: string) {
  const res = await fetch(path, { credentials: "same-origin" });
  if (!res.ok) throw new ApiError(res.status, `No se pudo descargar (${res.status})`);
  const blob = await res.blob();
  const cd = res.headers.get("content-disposition") ?? "";
  const name = /filename="([^"]+)"/.exec(cd)?.[1] ?? fallbackName;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}
