"""Hardware & Alarm Settings: estado del LED/buzzer, pruebas, silenciar e historial."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.common import paginate
from app.core.audit import audit
from app.core.database import query, query_one
from app.core.security import client_ip, require
from app.services import hardware_diagnostics
from app.services.alarm_controller import SAFE_PINS, alarm, physical_pin
from app.services.settings_store import settings

router = APIRouter(prefix="/api/hardware", tags=["hardware"])


@router.get("")
def hardware_status(user: dict = Depends(require("settings.view"))):
    return {
        "status": alarm.status(),
        "safe_pins": [{"bcm": p, "physical": physical_pin(p)} for p in sorted(SAFE_PINS)],
        "tests": [{"key": k, "title": t} for k, t in hardware_diagnostics.TESTS.items()],
    }


@router.post("/test/{name}")
def hardware_test(name: str, request: Request, user: dict = Depends(require("settings.edit"))):
    if name not in hardware_diagnostics.TESTS:
        raise HTTPException(404, "Prueba desconocida.")
    result = hardware_diagnostics.run(name, settings.all())
    audit(user, "prueba de hardware", target=hardware_diagnostics.TESTS[name],
          details={"ok": result["ok"], "modo": result["mode"]}, ip=client_ip(request))
    return result


@router.post("/silence")
def hardware_silence(request: Request, user: dict = Depends(require("alerts.review"))):
    was_active = alarm.silence(by=user["username"])
    if was_active:
        audit(user, "silenciar alarma física", ip=client_ip(request))
    return {"silenced": was_active, "status": alarm.status()}


@router.get("/activations")
def hardware_activations(page: int = 1, page_size: int = 20, user: dict = Depends(require("settings.view"))):
    limit, offset = paginate(page, page_size)
    total = query_one("SELECT COUNT(*) AS n FROM alarm_activations")["n"]
    rows = query("""SELECT a.*, e.uid AS event_uid FROM alarm_activations a LEFT JOIN events e ON e.id = a.event_id
                    ORDER BY a.at DESC, a.id DESC LIMIT ? OFFSET ?""", (limit, offset))
    return {"items": rows, "total": total, "page": page, "page_size": limit}
