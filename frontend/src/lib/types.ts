export type Role = "superadmin" | "admin" | "operator" | "auditor";
export type Level = "bajo" | "medio" | "alto";
export type ReviewStatus = "pendiente" | "confirmada" | "falso_positivo" | "cerrada";
export type EventType = "deteccion" | "coincidencia" | "captura" | "sistema";

export interface Me {
  id: number;
  username: string;
  full_name: string;
  role: Role;
  role_label: string;
  must_change_password: boolean;
  permissions: string[];
}

export interface Paged<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface FGEvent {
  id: number;
  uid: string;
  occurred_at: string;
  camera: string;
  type: EventType;
  type_label: string;
  entry_id: number | null;
  entry_name: string | null;
  score: number | null;
  level: Level | null;
  faces_count: number;
  review_status: ReviewStatus | null;
  review_label: string | null;
  reviewer_name: string | null;
  reviewed_at: string | null;
  notes: string;
  message: string;
  has_snapshot: boolean;
  is_simulated: boolean;
}

export interface EventDetail extends FGEvent {
  can_view_images: boolean;
  can_review: boolean;
  entry?: { uid: string; full_name: string; alert_level: Level; reason: string; status: string; has_photo: boolean };
}

export type Classification = "autorizada" | "no_autorizada";

export interface DuplicateMatch {
  entry_id: number;
  uid: string;
  full_name: string;
  classification: Classification;
  status: string;
  score: number;
}

export interface FaceSample {
  id: number;
  is_primary: boolean;
  model_version: string | null;
  quality: Record<string, number | boolean> | null;
  created_at: string;
}

export interface AnalysisMatch {
  entry_id: number | null;
  uid: string | null;
  name: string | null;
  level: Level | null;
  classification: Classification;
  score: number;
}

export interface AnalysisFace {
  box: [number, number, number, number];
  detection_score: number;
  result: "posible_no_autorizada" | "autorizada" | "desconocida" | "calidad_insuficiente";
  quality_issues: string[];
  match: AnalysisMatch | null;
  score: number | null;
  ambiguous: boolean;
  alternatives: AnalysisMatch[];
  alert?: { id: number; uid: string };
}

export interface AnalysisResult {
  image: { width: number; height: number };
  threshold: number;
  faces: AnalysisFace[];
}

export interface BlacklistEntry {
  id: number;
  classification: Classification;
  sample_count: number;
  template_count: number;
  uid: string;
  full_name: string;
  info: string;
  reason: string;
  legal_basis: string;
  alert_level: Level;
  registered_at: string;
  expires_at: string;
  status: "activo" | "inactivo" | "vencido";
  notes: string;
  has_photo: boolean;
  has_template: boolean;
  photo_quality: Record<string, number | boolean> | null;
  updated_at: string;
  is_simulated: boolean;
  can_view_photo: boolean;
}

export interface BlacklistDetail extends BlacklistEntry {
  samples: FaceSample[];
  history: { username: string; action: string; changes: string; at: string }[];
  alerts: { uid: string; occurred_at: string; score: number; review_status: ReviewStatus }[];
}

export interface QualityReport {
  ok: boolean;
  checks: { name: string; ok: boolean; detail: string }[];
  duplicates?: DuplicateMatch[];
  metrics?: Record<string, number>;
}

export interface SystemSnapshot {
  cpu_percent: number;
  cpu_count: number;
  ram_percent: number;
  ram_used_mb: number;
  ram_total_mb: number;
  disk_percent: number;
  disk_free_gb: number;
  temperature_c: number | null;
  temperature_status: "normal" | "alta" | "critica" | null;
  uptime_s: number;
  load_avg: number[];
}

export interface CameraStatus {
  running: boolean;
  connected: boolean;
  synthetic: boolean;
  index: number;
  device?: string;          // "/dev/video0" en Raspberry Pi, "Cámara 0" en Windows
  backend?: string | null;  // backend de OpenCV usado: v4l2, dshow, msmf…
  resolution: string;
  capture_fps: number;
  error: string | null;
  reconnects: number;
}

export interface EngineStatus {
  state: "activo" | "detenido" | "error" | "demo" | "esperando";
  label: string;
  running: boolean;
  engine_ready: boolean;
  models: string;
  gallery_size: number;
  templates: number;
  embeds_computed: number;
  embeds_skipped: number;
  processing_fps: number;
  latency_ms: number;
  faces_now: number;
  frames_processed: number;
  alerts_generated: number;
  ws_clients: number;
}

export interface GpioStatus {
  available: boolean;
  simulated: boolean;
  error: string | null;
  alarm_active: boolean;
  last_action: string | null;
}

export interface LiveStatus {
  system: SystemSnapshot;
  camera: CameraStatus;
  engine: EngineStatus;
  gpio: GpioStatus;
  pending_alerts: number;
  demo_mode: boolean;
  alert_sound: boolean;
}

export interface Summary extends LiveStatus {
  blacklist_active: number;
  blacklist_total: number;
  persons_total: number;
  authorized_active: number;
  database: { ok: boolean; size_kb: number };
  events_today: number;
  faces_today: number;
  alerts_today: number;
  false_positives: number;
  confirmed: number;
  recent: FGEvent[];
}

export interface Activity {
  range: "day" | "week";
  series: { label: string; detecciones: number; rostros: number; alertas: number }[];
  by_level: { level: string; n: number }[];
  by_review: { status: string; n: number }[];
}

export interface Settings {
  match_threshold: number;
  detection_confidence: number;
  min_face_size: number;
  confirm_frames: number;
  process_interval_ms: number;
  process_width: number;
  dedup_seconds: number;
  detection_log_seconds: number;
  camera_index: number;
  camera_width: number;
  camera_height: number;
  monitoring_enabled: boolean;
  alerts_enabled: boolean;
  alert_sound: boolean;
  gpio_enabled: boolean;
  led_pin: number;
  buzzer_pin: number;
  led_enabled: boolean;
  buzzer_enabled: boolean;
  buzzer_min_level: Level;
  gpio_alarm_seconds: number;
  retention_days_events: number;
  retention_days_snapshots: number;
  retention_days_audit: number;
  retention_days_expired_authorized: number;
  demo_mode: boolean;
}

export interface UserRow {
  id: number;
  username: string;
  full_name: string;
  role: Role;
  role_label: string;
  active: number;
  must_change_password: number;
  created_at: string;
  last_login: string | null;
}

export interface AuditRow {
  id: number;
  at: string;
  username: string | null;
  action: string;
  target: string;
  details: string;
  ip: string | null;
}
