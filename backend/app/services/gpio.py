"""Control del LED rojo y del buzzer conectados a la Raspberry Pi.

Usa gpiozero cuando está disponible. En otro equipo (o si la biblioteca no está
instalada) funciona en modo simulado y solo registra las acciones, para que el
resto del sistema se pueda probar sin hardware.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

log = logging.getLogger("faceguard.gpio")

LEVELS = {"bajo": 1, "medio": 2, "alto": 3}


class GPIOService:
    def __init__(self) -> None:
        self._led = None
        self._buzzer = None
        self._lock = threading.Lock()
        self.available = False
        self.error: str | None = None
        self.last_action: str | None = None
        self._alarm_until = 0.0

    def setup(self, led_pin: int, buzzer_pin: int) -> None:
        with self._lock:
            self.close()
            try:
                from gpiozero import LED, Buzzer  # type: ignore

                self._led = LED(led_pin)
                self._buzzer = Buzzer(buzzer_pin)
                self.available = True
                self.error = None
                log.info("GPIO listo: LED=GPIO%s, buzzer=GPIO%s", led_pin, buzzer_pin)
            except Exception as exc:  # sin hardware: modo simulado
                self.available = False
                self.error = f"GPIO no disponible ({exc.__class__.__name__}); modo simulado"
                log.warning(self.error)

    def close(self) -> None:
        for dev in (self._led, self._buzzer):
            try:
                if dev is not None:
                    dev.off()
                    dev.close()
            except Exception:
                pass
        self._led = self._buzzer = None

    def alarm(self, level: str, cfg: dict[str, Any]) -> dict[str, bool]:
        """Activa LED y/o buzzer según la configuración y el nivel de la alerta."""
        if not cfg["gpio_enabled"]:
            return {"led": False, "buzzer": False}
        use_led = bool(cfg["led_enabled"])
        use_buzzer = bool(cfg["buzzer_enabled"]) and LEVELS.get(level, 0) >= LEVELS[cfg["buzzer_min_level"]]
        seconds = int(cfg["gpio_alarm_seconds"])
        threading.Thread(target=self._run_alarm, args=(use_led, use_buzzer, seconds, level),
                         daemon=True, name="gpio-alarm").start()
        return {"led": use_led, "buzzer": use_buzzer}

    def _run_alarm(self, use_led: bool, use_buzzer: bool, seconds: int, level: str) -> None:
        self._alarm_until = time.time() + seconds
        self.last_action = f"Alarma nivel {level}: LED={'sí' if use_led else 'no'}, buzzer={'sí' if use_buzzer else 'no'}"
        log.info(self.last_action + (" [simulado]" if not self.available else ""))
        if not self.available:
            return
        with self._lock:
            # Alto: parpadeo rápido; medio/bajo: parpadeo lento.
            on_t = 0.15 if level == "alto" else 0.4
            if use_led and self._led:
                self._led.blink(on_time=on_t, off_time=on_t, n=max(1, int(seconds / (2 * on_t))), background=True)
            if use_buzzer and self._buzzer:
                self._buzzer.beep(on_time=0.2, off_time=0.3, n=max(1, int(seconds / 0.5)), background=True)

    def test(self, cfg: dict[str, Any]) -> dict[str, Any]:
        result = self.alarm("alto", {**cfg, "gpio_enabled": True, "gpio_alarm_seconds": 2})
        return {"simulated": not self.available, **result}

    def status(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "simulated": not self.available,
            "error": self.error,
            "alarm_active": time.time() < self._alarm_until,
            "last_action": self.last_action,
        }


gpio = GPIOService()
