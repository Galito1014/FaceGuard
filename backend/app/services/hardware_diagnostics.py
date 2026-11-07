"""Pruebas de diagnóstico de la alarma física.

  1. led          → LED rojo encendido 3 s.
  2. buzzer       → buzzer 2 s.
  3. completa     → LED y buzzer a la vez.
  4. blacklist    → una detección de prueba de una persona de la lista de alerta,
                    confirmada en N análisis, pasa por el mismo código que el video
                    en vivo (pipeline._handle_face) y debe encender las salidas.
                    Genera una alerta marcada [SIMULADO].
  5. desconocido  → un rostro desconocido, una coincidencia dudosa (bajo el umbral)
                    y una persona autorizada NO deben activar la alarma.

Se ejecutan desde el panel (Hardware & Alarm Settings) o por consola:
    python -m scripts.manage hardware-test todas
"""
from __future__ import annotations

import time
from typing import Any

import numpy as np

from app.services.alarm_controller import alarm

TESTS = {
    "led": "Prueba 1 — LED rojo (3 s)",
    "buzzer": "Prueba 2 — Buzzer (2 s)",
    "completa": "Prueba 3 — Alarma completa (LED + buzzer)",
    "blacklist": "Prueba 4 — Detección de la lista de alerta",
    "desconocido": "Prueba 5 — Persona desconocida (no debe sonar)",
}
DURATIONS = {"led": 3, "buzzer": 2, "completa": 3}

HINTS = {
    "led": ("Si el LED no encendió: (1) la pata larga (ánodo) va hacia la resistencia y la corta (cátodo) a GND; "
            "(2) la resistencia de 220-330 Ω está en serie entre el GPIO{led} (pin físico {led_phys}) y el ánodo; "
            "(3) el cátodo llega a un GND (pin 9); (4) las patas están en filas distintas de la protoboard."),
    "buzzer": ("Si el buzzer no sonó o solo hizo un clic: probablemente es PASIVO; cambie 'Tipo de buzzer' a pasivo y "
               "repita. Revise también que una pata vaya al GPIO{buz} (pin físico {buz_phys}) y la otra a GND (pin 14); "
               "si el buzzer tiene marca '+', esa pata va al GPIO."),
}


def _result(name: str, ok: bool, message: str, hint: str | None = None, **details: Any) -> dict[str, Any]:
    st = alarm.status()
    return {"test": name, "title": TESTS[name], "ok": ok, "mode": st["mode"], "simulated": st["mode"] != "hardware",
            "message": message, "hint": hint, "details": details}


def _hint(key: str) -> str:
    st = alarm.status()
    return HINTS[key].format(led=st["led_pin"], led_phys=st["led_physical"], buz=st["buzzer_pin"],
                             buz_phys=st["buzzer_physical"])


def _wait_for(predicate, timeout: float) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


def _output_test(name: str, cfg: dict[str, Any], wait: bool) -> dict[str, Any]:
    if alarm.mode == "error":
        return _result(name, False, "Los pines GPIO no están disponibles.", alarm.error)
    seconds = DURATIONS[name]
    alarm.test(name, seconds, cfg.get("buzzer_pattern", "intermitente"))
    want_led, want_buz = name in ("led", "completa"), name in ("buzzer", "completa")
    # El hilo de la alarma enciende las salidas casi de inmediato; se comprueba que lo hizo.
    started = _wait_for(lambda: (alarm.led_on or not want_led) and (alarm.buzzer_on or not want_buz), 0.5)
    if not started:
        return _result(name, False, "La salida no se pudo activar.", alarm.error)
    if wait:  # consola: esperar a que termine y comprobar que se apagó
        _wait_for(lambda: not alarm.alarm_active, seconds + 2)
        if alarm.led_on or alarm.buzzer_on:
            return _result(name, False, "La salida no se apagó al terminar el tiempo.", alarm.error)
    parts = (["LED"] if want_led else []) + (["buzzer"] if want_buz else [])
    if alarm.mode == "simulado":
        return _result(name, True, f"{' y '.join(parts)} activado(s) en modo simulado: este equipo no tiene GPIO, "
                                   "la lógica funcionó pero no hay salida física.")
    hint = " ".join(_hint(k) for k in ("led", "buzzer") if (k == "led" and want_led) or (k == "buzzer" and want_buz))
    return _result(name, True, f"Señal enviada: {' y '.join(parts)} durante {seconds} s. Confirme visualmente/de oído.",
                   hint, seconds=seconds)


def _frame() -> np.ndarray:
    from app.services.camera import camera

    frame, _, _ = camera.latest()
    return frame if frame is not None else np.full((480, 640, 3), 30, np.uint8)


def _feed(tracker, meta: dict[str, Any] | None, sim: float, cfg: dict[str, Any], frames: int, t0: float):
    """Alimenta al tracker como si el mismo rostro apareciera en `frames` análisis seguidos."""
    box = (260, 160, 120, 150)
    track = None
    for i in range(frames):
        now = t0 + i * cfg["process_interval_ms"] / 1000
        (track,) = tracker.update([box], now)
        tracker.record_result(track, meta, sim, cfg["match_threshold"], cfg["confirm_frames"], now)
    return track


def _face():
    from app.services.face_engine import Face

    return Face(box=(260, 160, 120, 150), score=0.99, raw=np.zeros(15, np.float32))


def _blacklist_test(cfg: dict[str, Any]) -> dict[str, Any]:
    from app.services.pipeline import pipeline
    from app.services.tracker import FaceTracker

    if not cfg["alerts_enabled"]:
        return _result("blacklist", False, "Las alertas están desactivadas: una coincidencia no activaría la alarma.",
                       "Active 'Alertas activas' en Configuración → Alertas.")
    if not cfg["gpio_enabled"] or not (cfg["led_enabled"] or cfg["buzzer_enabled"]):
        return _result("blacklist", False, "La alarma física está desactivada en la configuración.",
                       "Active 'Usar GPIO' y al menos el LED o el buzzer en Hardware & Alarm Settings.")
    meta = {"entry_id": None, "uid": "DIAG-0001", "name": "Prueba de diagnóstico (lista de alerta)",
            "level": "alto", "classification": "no_autorizada"}
    sim = min(0.99, cfg["match_threshold"] + 0.2)
    n = cfg["confirm_frames"]
    tracker, t0 = FaceTracker(), time.time()
    if n > 1:
        early = _feed(tracker, meta, sim, cfg, n - 1, t0)
        if early.confirmed:
            return _result("blacklist", False, f"La coincidencia se confirmó antes de {n} análisis.")
        tracker = FaceTracker()
    track = _feed(tracker, meta, sim, cfg, n, t0)
    if not track.confirmed:
        return _result("blacklist", False, f"La coincidencia no se confirmó tras {n} análisis seguidos.")
    before = alarm.trigger_count
    item = pipeline._handle_face(_frame(), _face(), track, cfg, simulated=True, force=True)
    row = item.get("alert")
    if not row:
        return _result("blacklist", False, "La coincidencia confirmada no generó la alerta.")
    state = row.get("alarm_state")
    fired = alarm.trigger_count > before and state in ("activada", "simulada")
    if not fired:
        return _result("blacklist", False, f"Se registró la alerta {row['uid']} pero la alarma quedó en estado "
                                           f"'{state}'.", alarm.error)
    gpio = row["gpio"]
    outs = " y ".join(p for p, on in (("LED", gpio["led"]), ("buzzer", gpio["buzzer"])) if on)
    return _result("blacklist", True,
                   f"Confirmada en {n} análisis → alerta {row['uid']} registrada [SIMULADO] y alarma {state} ({outs}).",
                   None, event_uid=row["uid"], alarm_state=state)


def _unknown_test(cfg: dict[str, Any]) -> dict[str, Any]:
    from app.services.pipeline import pipeline
    from app.services.tracker import FaceTracker

    n, thr = cfg["confirm_frames"], cfg["match_threshold"]
    cases = {
        "rostro desconocido": (None, max(0.0, thr - 0.25)),
        "coincidencia dudosa (bajo el umbral)": ({"entry_id": None, "uid": "DIAG-0002", "name": "Dudosa",
                                                  "level": "alto", "classification": "no_autorizada"}, thr - 0.02),
        "persona autorizada": ({"entry_id": None, "uid": "DIAG-0003", "name": "Autorizada", "level": "bajo",
                                "classification": "autorizada"}, min(0.99, thr + 0.2)),
    }
    before = alarm.trigger_count
    fired = []
    for label, (meta, sim) in cases.items():
        track = _feed(FaceTracker(), meta, sim, cfg, n + 2, time.time())
        item = pipeline._handle_face(_frame(), _face(), track, cfg, simulated=True, force=True)
        if item.get("alert") or item["match"]:
            fired.append(label)
    if fired or alarm.trigger_count != before:
        return _result("desconocido", False, f"Se activó la alarma con: {', '.join(fired) or 'un caso sin coincidencia'}.",
                       "Revise el umbral de coincidencia y la clasificación de las personas registradas.")
    return _result("desconocido", True, f"Ninguno de los {len(cases)} casos ({', '.join(cases)}) activó la alarma "
                                        f"tras {n + 2} análisis.")


def run(name: str, cfg: dict[str, Any], *, wait: bool = False) -> dict[str, Any]:
    if name not in TESTS:
        raise ValueError(f"Prueba desconocida: {name}. Opciones: {', '.join(TESTS)}")
    try:
        if name in DURATIONS:
            return _output_test(name, cfg, wait)
        return _blacklist_test(cfg) if name == "blacklist" else _unknown_test(cfg)
    except Exception as exc:  # una prueba nunca debe tumbar el servicio
        return _result(name, False, f"Error inesperado: {exc.__class__.__name__}: {exc}",
                       "Revise el registro del sistema (Configuración → Sistema).")
