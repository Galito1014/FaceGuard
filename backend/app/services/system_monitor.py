"""Estado del hardware: CPU, RAM, disco, temperatura y modelo de la Raspberry Pi."""
from __future__ import annotations

import platform
import subprocess
import time
from pathlib import Path
from typing import Any

import psutil

_BOOT = psutil.boot_time()
psutil.cpu_percent(None)  # primera lectura de referencia


def read_temperature() -> float | None:
    thermal = Path("/sys/class/thermal/thermal_zone0/temp")
    try:
        return round(int(thermal.read_text().strip()) / 1000, 1)
    except (OSError, ValueError):
        pass
    try:
        temps = psutil.sensors_temperatures()
        for entries in temps.values():
            if entries:
                return round(entries[0].current, 1)
    except (AttributeError, OSError):
        pass
    return None


def device_model() -> str:
    for path in ("/proc/device-tree/model", "/sys/firmware/devicetree/base/model"):
        try:
            return Path(path).read_text().strip("\x00 \n")
        except OSError:
            continue
    return f"{platform.system()} {platform.machine()} (no es Raspberry Pi)"


def is_raspberry_pi() -> bool:
    return "raspberry pi" in device_model().lower()


def throttled_flags() -> str | None:
    """`vcgencmd get_throttled` indica subtensión o reducción por temperatura."""
    try:
        out = subprocess.run(["vcgencmd", "get_throttled"], capture_output=True, text=True, timeout=2)
        return out.stdout.strip().split("=")[-1] if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def snapshot() -> dict[str, Any]:
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    temp = read_temperature()
    return {
        "cpu_percent": psutil.cpu_percent(None),
        "cpu_count": psutil.cpu_count(),
        "ram_percent": mem.percent,
        "ram_used_mb": round(mem.used / 2**20),
        "ram_total_mb": round(mem.total / 2**20),
        "disk_percent": disk.percent,
        "disk_free_gb": round(disk.free / 2**30, 1),
        "temperature_c": temp,
        "temperature_status": None if temp is None else ("critica" if temp >= 80 else "alta" if temp >= 70 else "normal"),
        "uptime_s": int(time.time() - _BOOT),
        "load_avg": [round(x, 2) for x in psutil.getloadavg()],
    }


def info() -> dict[str, Any]:
    return {
        "model": device_model(),
        "is_raspberry_pi": is_raspberry_pi(),
        "os": platform.platform(),
        "python": platform.python_version(),
        "arch": platform.machine(),
        "hostname": platform.node(),
        "throttled": throttled_flags(),
    }
