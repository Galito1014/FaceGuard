"""Alarma física de FaceGuard AI: LED rojo y buzzer conectados a la Raspberry Pi.

Responsabilidades:
  * Inicializar las salidas GPIO **apagadas** (nunca se encienden al arrancar).
  * Encender el LED (fijo) y el buzzer (intermitente o continuo) con duraciones
    independientes, en un hilo propio: el procesamiento de video nunca espera.
  * Soportar buzzer **activo** (basta con 3,3 V continuos) y **pasivo** (necesita
    una onda PWM; la frecuencia se configura).
  * Evitar activaciones duplicadas: una alarma nueva reemplaza a la que está en
    curso en lugar de sumarse. El cooldown por persona lo aplica pipeline.py.
  * Silenciar manualmente una alarma activa.
  * Apagar y liberar los pines al cerrar FaceGuard (también con atexit).
  * Registrar cada activación en la tabla `alarm_activations`.
  * Si el LED o el buzzer fallan, registrar el error y seguir: el reconocimiento
    facial no depende de este módulo.

Modos:
  hardware  → Raspberry Pi con gpiozero funcionando.
  simulado  → equipo sin GPIO (Windows, Linux de escritorio). Se imitan las
              salidas en memoria para que la versión Desktop funcione igual.
  error     → es una Raspberry Pi pero los pines no se pudieron abrir (pin
              ocupado por otro proceso, permisos, falta lgpio). Se informa la
              causa en el panel en lugar de fingir que todo funciona.
"""
from __future__ import annotations

import atexit
import logging
import threading
import time
from typing import Any, Callable

from app.core import compat

log = logging.getLogger("faceguard.alarm")

LEVELS = {"bajo": 1, "medio": 2, "alto": 3}

# Pines GPIO (BCM) que se pueden usar sin chocar con I2C (2, 3), UART (14, 15),
# SPI0 (7-11) ni con la EEPROM de los HAT (0, 1). El ventilador del case va a
# 5 V y GND, así que no ocupa ningún GPIO.
SAFE_PINS = frozenset({4, 5, 6, 12, 13, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27})

# Número BCM → número de pin físico en el conector de 40 pines.
_BCM_TO_PHYSICAL = {
    2: 3, 3: 5, 4: 7, 14: 8, 15: 10, 17: 11, 18: 12, 27: 13, 22: 15, 23: 16, 24: 18, 10: 19, 9: 21,
    25: 22, 11: 23, 8: 24, 7: 26, 0: 27, 1: 28, 5: 29, 6: 31, 12: 32, 13: 33, 19: 35, 16: 36, 26: 37,
    20: 38, 21: 40,
}

BEEP_ON_S = 0.25   # patrón intermitente del buzzer
BEEP_OFF_S = 0.15
PASSIVE_DUTY = 0.5  # onda cuadrada para el buzzer pasivo


def physical_pin(bcm: int) -> int | None:
    return _BCM_TO_PHYSICAL.get(bcm)


def _has_gpio_hardware() -> tuple[bool, str]:
    """¿Tiene sentido intentar abrir los pines? Devuelve (sí/no, motivo)."""
    if not compat.gpio_supported():
        return False, f"{compat.os_name()} no tiene pines GPIO"
    from app.services.system_monitor import is_raspberry_pi

    if not is_raspberry_pi():
        return False, "este equipo no es una Raspberry Pi"
    return True, ""


def _now_iso() -> str:
    from app.core.database import utcnow

    return utcnow()


class _SimOutput:
    """Salida imitada en memoria (versión Desktop o pruebas sin hardware)."""

    def __init__(self) -> None:
        self.value = 0

    def close(self) -> None:
        self.value = 0


def explain_gpio_error(exc: BaseException, led_pin: int, buzzer_pin: int) -> str:
    """Convierte la excepción de gpiozero/lgpio en un mensaje que diga qué hacer."""
    name = exc.__class__.__name__
    text = str(exc)
    low = f"{name} {text}".lower()
    if "inuse" in low.replace(" ", "") or "busy" in low or "in use" in low:
        return (f"El GPIO{led_pin} o el GPIO{buzzer_pin} ya está en uso por otro proceso. ¿Hay otra instancia de "
                "FaceGuard o un script de prueba abierto? Deténgalo (sudo systemctl stop faceguard) o elija otros pines.")
    if isinstance(exc, PermissionError) or "permission" in low or "eacces" in low:
        return ("Sin permiso para abrir /dev/gpiochip*. Agregue el usuario al grupo gpio "
                "(sudo usermod -aG gpio faceguard) y reinicie el servicio.")
    if "badpinfactory" in low or "lgpio" in low or "no module" in low:
        return ("gpiozero no encontró un backend de pines. Instale lgpio (sudo apt install python3-lgpio) y use un "
                "entorno virtual creado con --system-site-packages (deploy/install.sh ya lo hace).")
    if "pwm" in low:
        return f"El pin GPIO{buzzer_pin} no admite PWM con este backend ({name}: {text}). Pruebe el buzzer como activo."
    return f"No se pudieron abrir los pines GPIO ({name}: {text})"


class AlarmController:
    def __init__(self) -> None:
        self._lock = threading.RLock()     # configuración y ciclo de vida de una alarma
        self._io_lock = threading.Lock()   # escrituras en los pines
        self._led: Any = None
        self._buzzer: Any = None
        self.mode = "simulado"
        self.error: str | None = None
        self.led_pin: int | None = None
        self.buzzer_pin: int | None = None
        self.buzzer_type = "activo"
        self.buzzer_frequency = 2500
        self.led_on = False
        self.buzzer_on = False
        self.last_action: str | None = None
        self.trigger_count = 0
        self.on_change: Callable[[dict[str, Any]], None] | None = None
        self._gen = 0
        self._stop: threading.Event | None = None
        self._thread: threading.Thread | None = None
        self._active_until = 0.0
        self._atexit = False

    # --------------------------------------------------------------- ciclo de vida
    def setup(self, led_pin: int, buzzer_pin: int, buzzer_type: str = "activo", buzzer_frequency: int = 2500) -> None:
        """(Re)abre los pines. Las salidas quedan apagadas."""
        with self._lock:
            self._cancel_running("cerrada")
            self._close_devices()
            self.led_pin, self.buzzer_pin = led_pin, buzzer_pin
            self.buzzer_type, self.buzzer_frequency = buzzer_type, buzzer_frequency
            if not self._atexit:
                atexit.register(self.close)  # corte por señal o fallo: deja los pines apagados
                self._atexit = True
            ok, reason = _has_gpio_hardware()
            if not ok:
                self._led, self._buzzer = _SimOutput(), _SimOutput()
                self.mode = "simulado"
                self.error = f"GPIO no disponible: {reason}. LED y buzzer en modo simulado."
                log.info(self.error)
                self._notify()
                return
            led = buzzer = None
            try:
                from gpiozero import DigitalOutputDevice, PWMOutputDevice  # type: ignore

                led = DigitalOutputDevice(led_pin, active_high=True, initial_value=False)
                if buzzer_type == "pasivo":
                    buzzer = PWMOutputDevice(buzzer_pin, active_high=True, initial_value=0, frequency=buzzer_frequency)
                else:
                    buzzer = DigitalOutputDevice(buzzer_pin, active_high=True, initial_value=False)
                self._led, self._buzzer = led, buzzer
                self.mode, self.error = "hardware", None
                log.info("GPIO listo: LED=GPIO%s (pin %s), buzzer %s=GPIO%s (pin %s)", led_pin, physical_pin(led_pin),
                         buzzer_type, buzzer_pin, physical_pin(buzzer_pin))
            except Exception as exc:
                for dev in (led, buzzer):
                    try:
                        if dev is not None:
                            dev.close()
                    except Exception:
                        pass
                self._led = self._buzzer = None
                self.mode = "error"
                self.error = explain_gpio_error(exc, led_pin, buzzer_pin)
                log.error("Alarma física sin hardware: %s", self.error)
            self._notify()

    def close(self) -> None:
        """Apaga las salidas y libera los pines (al cerrar FaceGuard)."""
        with self._lock:
            self._cancel_running("cerrada")
            self._close_devices()

    def _close_devices(self) -> None:
        for name in ("led", "buzzer"):
            dev = getattr(self, f"_{name}")
            self._write(dev, name, False)
            try:
                if dev is not None:
                    dev.close()
            except Exception:
                pass
        self._led = self._buzzer = None

    @staticmethod
    def recover_interrupted() -> int:
        """Marca como interrumpidas las activaciones que quedaron abiertas por un corte o reinicio.

        Al arrancar, los pines ya se abrieron apagados; esto solo deja el historial
        coherente para que el panel no muestre una alarma "activa" fantasma.
        """
        from app.core.database import get_db

        try:
            with get_db() as db:
                return db.execute("UPDATE alarm_activations SET state='error', ended_at=?, "
                                  "error='Interrumpida por un reinicio del servicio' WHERE state='activa'",
                                  (_now_iso(),)).rowcount
        except Exception:
            log.exception("No se pudo revisar el historial de la alarma")
            return 0

    # ------------------------------------------------------------------ disparo
    def trigger(self, level: str, cfg: dict[str, Any], *, source: str, event_id: int | None = None,
                entry_name: str | None = None) -> dict[str, Any]:
        """Activa la alarma por una coincidencia confirmada. Nunca bloquea ni lanza excepciones."""
        result: dict[str, Any] = {"led": False, "buzzer": False, "state": "desactivada", "mode": self.mode,
                                  "activation_id": None}
        try:
            if not cfg["gpio_enabled"]:
                return result
            use_led = bool(cfg["led_enabled"])
            use_buzzer = bool(cfg["buzzer_enabled"]) and LEVELS.get(level, 3) >= LEVELS[cfg["buzzer_min_level"]]
            if not (use_led or use_buzzer):
                return result
            result.update(led=use_led, buzzer=use_buzzer)
            result["activation_id"] = self._start(
                use_led, use_buzzer, int(cfg["led_seconds"]), int(cfg["buzzer_seconds"]), cfg["buzzer_pattern"],
                source=source, level=level, event_id=event_id, entry_name=entry_name)
            result["state"] = {"hardware": "activada", "simulado": "simulada"}.get(self.mode, "error")
            result["mode"] = self.mode
        except Exception:
            log.exception("Error al activar la alarma física")
            result["state"] = "error"
        return result

    def test(self, which: str, seconds: float, pattern: str = "intermitente") -> dict[str, Any]:
        """Prueba manual: 'led', 'buzzer' o 'completa'. Ignora los interruptores del panel."""
        use_led = which in ("led", "completa")
        use_buzzer = which in ("buzzer", "completa")
        act = self._start(use_led, use_buzzer, int(seconds), int(seconds), pattern, source="prueba",
                          level=None, event_id=None, entry_name=f"Prueba manual: {which}")
        return {"activation_id": act, "led": use_led, "buzzer": use_buzzer, "mode": self.mode,
                "simulated": self.mode != "hardware", "error": self.error}

    def silence(self, by: str | None = None) -> bool:
        """Apaga de inmediato la alarma en curso. Devuelve False si no había ninguna."""
        with self._lock:
            active = self._thread is not None and self._thread.is_alive()
            self._cancel_running("silenciada", by)
            # Por si quedó algo encendido fuera de un ciclo (p. ej. tras un error).
            self._write(self._led, "led", False)
            self._write(self._buzzer, "buzzer", False)
        if active:
            self.last_action = f"Alarma silenciada{f' por {by}' if by else ''}"
            log.info(self.last_action)
        self._notify()
        return active

    # ------------------------------------------------------------- funcionamiento
    def _start(self, use_led: bool, use_buzzer: bool, led_s: int, buzzer_s: int, pattern: str, *, source: str,
               level: str | None, event_id: int | None, entry_name: str | None) -> int | None:
        with self._lock:
            self._cancel_running("completada")  # una alarma nueva reemplaza a la anterior
            mode = self.mode
            act_id = self._record_start(source, event_id, entry_name, level, use_led, use_buzzer, led_s, buzzer_s, mode)
            self.trigger_count += 1
            self.last_action = (f"Alarma ({source}{f', nivel {level}' if level else ''}): "
                                f"LED {led_s if use_led else 0} s, buzzer {buzzer_s if use_buzzer else 0} s"
                                + ("" if mode == "hardware" else f" [{mode}]"))
            log.info(self.last_action)
            if mode == "error":
                self._record_end(act_id, "error", error=self.error)
                return act_id
            self._gen += 1
            stop = threading.Event()
            self._stop = stop
            longest = max(led_s if use_led else 0, buzzer_s if use_buzzer else 0)
            self._active_until = time.monotonic() + longest
            self._thread = threading.Thread(target=self._run, name="alarm-run", daemon=True,
                                            args=(self._gen, stop, act_id, use_led, use_buzzer, led_s, buzzer_s, pattern))
            self._thread.start()
        self._notify()
        return act_id

    def _cancel_running(self, reason: str, by: str | None = None) -> None:
        stop, thread = self._stop, self._thread
        if stop is not None and thread is not None and thread.is_alive():
            stop.reason = reason  # type: ignore[attr-defined]
            stop.by = by  # type: ignore[attr-defined]
            stop.set()
            thread.join(timeout=2)
        self._stop = self._thread = None
        self._active_until = 0.0

    def _run(self, gen: int, stop: threading.Event, act_id: int | None, use_led: bool, use_buzzer: bool,
             led_s: float, buzzer_s: float, pattern: str) -> None:
        t0 = time.monotonic()
        led_end = t0 + led_s if use_led else None
        buz_end = t0 + buzzer_s if use_buzzer else None
        buz_on, next_toggle = False, t0
        errors: list[str] = []
        try:
            if use_led and not self._write(self._led, "led", True):
                errors.append(self.error or "LED")
            while not stop.is_set():
                now = time.monotonic()
                deadlines: list[float] = []
                if led_end is not None:
                    if now >= led_end:
                        self._write(self._led, "led", False)
                        led_end = None
                    else:
                        deadlines.append(led_end)
                if buz_end is not None:
                    if now >= buz_end:
                        self._write(self._buzzer, "buzzer", False)
                        buz_end = None
                    else:
                        if now >= next_toggle:
                            if pattern == "continuo":
                                buz_on, next_toggle = True, buz_end
                            else:
                                buz_on = not buz_on
                                next_toggle = now + (BEEP_ON_S if buz_on else BEEP_OFF_S)
                            if not self._write(self._buzzer, "buzzer", buz_on) and self.error not in errors:
                                errors.append(self.error or "buzzer")
                        deadlines += [buz_end, next_toggle]
                if not deadlines:
                    break
                stop.wait(max(0.005, min(deadlines) - time.monotonic()))
        except Exception as exc:  # nunca dejar el hilo con una salida encendida
            log.exception("Fallo durante la alarma")
            errors.append(f"{exc.__class__.__name__}: {exc}")
        finally:
            self._write(self._led, "led", False)
            self._write(self._buzzer, "buzzer", False)
            reason = getattr(stop, "reason", None) if stop.is_set() else None
            state = "error" if errors else ("silenciada" if reason == "silenciada" else "completada")
            self._record_end(act_id, state, by=getattr(stop, "by", None), error="; ".join(errors) or None)
            if gen == self._gen:
                self._active_until = 0.0
                self._notify()

    def _write(self, dev: Any, name: str, on: bool) -> bool:
        """Escribe en un pin. Si falla, registra el error y devuelve False (sin propagar)."""
        if dev is None:
            setattr(self, f"{name}_on", False)
            return not on
        try:
            with self._io_lock:
                if not on:
                    dev.value = 0
                elif name == "buzzer" and self.buzzer_type == "pasivo":
                    dev.value = PASSIVE_DUTY
                else:
                    dev.value = 1
            setattr(self, f"{name}_on", on)
            return True
        except Exception as exc:
            setattr(self, f"{name}_on", False)
            pin = self.led_pin if name == "led" else self.buzzer_pin
            self.error = f"Error al escribir en el {name} (GPIO{pin}): {exc.__class__.__name__}: {exc}"
            log.error(self.error)
            return False

    # -------------------------------------------------------------- historial
    @staticmethod
    def _record_start(source: str, event_id: int | None, entry_name: str | None, level: str | None, led: bool,
                      buzzer: bool, led_s: int, buzzer_s: int, mode: str) -> int | None:
        from app.core.database import execute

        try:
            return execute(
                "INSERT INTO alarm_activations (at, source, event_id, entry_name, level, led, buzzer, led_seconds, "
                "buzzer_seconds, mode, state) VALUES (?,?,?,?,?,?,?,?,?,?, 'activa')",
                (_now_iso(), source, event_id, entry_name, level, int(led), int(buzzer),
                 led_s if led else None, buzzer_s if buzzer else None, mode))
        except Exception:
            log.exception("No se pudo registrar la activación de la alarma")
            return None

    @staticmethod
    def _record_end(act_id: int | None, state: str, by: str | None = None, error: str | None = None) -> None:
        if act_id is None:
            return
        from app.core.database import execute

        try:
            execute("UPDATE alarm_activations SET state=?, ended_at=?, silenced_by=?, error=? WHERE id=?",
                    (state, _now_iso(), by, error, act_id))
        except Exception:
            log.exception("No se pudo cerrar el registro de la activación %s", act_id)

    # ------------------------------------------------------------------ estado
    @property
    def alarm_active(self) -> bool:
        return time.monotonic() < self._active_until

    def status(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "available": self.mode == "hardware",
            "simulated": self.mode == "simulado",
            "error": self.error,
            "alarm_active": self.alarm_active,
            "led_on": self.led_on,
            "buzzer_on": self.buzzer_on,
            "led_pin": self.led_pin,
            "buzzer_pin": self.buzzer_pin,
            "led_physical": physical_pin(self.led_pin) if self.led_pin is not None else None,
            "buzzer_physical": physical_pin(self.buzzer_pin) if self.buzzer_pin is not None else None,
            "buzzer_type": self.buzzer_type,
            "last_action": self.last_action,
            "activations": self.trigger_count,
        }

    def _notify(self) -> None:
        if self.on_change is None:
            return
        try:
            self.on_change(self.status())
        except Exception:
            log.debug("No se pudo publicar el estado de la alarma", exc_info=True)


alarm = AlarmController()
