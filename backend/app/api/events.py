from __future__ import annotations

import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from app.api.common import norm_dt, paginate
from app.core.audit import audit
from app.core.crypto import read_encrypted_file
from app.core.database import execute, query, query_one, utcnow
from app.core.security import client_ip, has_perm, require
from app.services.events import REVIEW_LABELS, TYPE_LABELS, serialize_event
from app.services.realtime import hub

router = APIRouter(tags=["events"])

TYPES = set(TYPE_LABELS)
REVIEWS = set(REVIEW_LABELS)
LEVELS = {"bajo", "medio", "alto"}


def _filters(q: str, type_: str, level: str, status: str, date_from: str | None, date_to: str | None,
             simulated: str) -> tuple[str, list]:
    where, params = ["1=1"], []
    if q:
        where.append("(uid LIKE ? OR entry_name LIKE ? OR message LIKE ? OR reviewer_name LIKE ?)")
        params += [f"%{q}%"] * 4
    if type_ in TYPES:
        where.append("type = ?"); params.append(type_)
    if level in LEVELS:
        where.append("level = ?"); params.append(level)
    if status in REVIEWS:
        where.append("review_status = ?"); params.append(status)
    if date_from:
        where.append("occurred_at >= ?"); params.append(norm_dt(date_from))
    if date_to:
        where.append("occurred_at <= ?"); params.append(norm_dt(date_to))
    if simulated in ("0", "1"):
        where.append("is_simulated = ?"); params.append(int(simulated))
    return " AND ".join(where), params


@router.get("/api/events")
def list_events(q: str = "", type: str = "", level: str = "", status: str = "", date_from: str | None = None,
                date_to: str | None = None, simulated: str = "", page: int = 1, page_size: int = 25,
                user: dict = Depends(require("events.view"))):
    w, params = _filters(q, type, level, status, date_from, date_to, simulated)
    limit, offset = paginate(page, page_size)
    total = query_one(f"SELECT COUNT(*) AS n FROM events WHERE {w}", tuple(params))["n"]
    rows = query(f"SELECT * FROM events WHERE {w} ORDER BY occurred_at DESC, id DESC LIMIT ? OFFSET ?",
                 (*params, limit, offset))
    return {"items": [serialize_event(r) for r in rows], "total": total, "page": page, "page_size": limit}


@router.get("/api/events/export")
def export_events(request: Request, format: str = Query("csv", pattern="^(csv|pdf)$"), q: str = "", type: str = "",
                  level: str = "", status: str = "", date_from: str | None = None, date_to: str | None = None,
                  simulated: str = "", user: dict = Depends(require("events.export"))):
    w, params = _filters(q, type, level, status, date_from, date_to, simulated)
    rows = query(f"SELECT * FROM events WHERE {w} ORDER BY occurred_at DESC LIMIT 5000", tuple(params))
    audit(user, f"exportar eventos ({format.upper()})", details={"registros": len(rows)}, ip=client_ip(request))
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    headers = ["ID", "Fecha y hora (UTC)", "Cámara", "Tipo", "Posible coincidencia", "Similitud", "Nivel",
               "Estado de revisión", "Responsable", "Observaciones", "Origen"]

    def values(r: dict) -> list:
        return [r["uid"], r["occurred_at"], r["camera"], TYPE_LABELS.get(r["type"], r["type"]), r["entry_name"] or "",
                "" if r["score"] is None else f"{r['score']:.3f}", r["level"] or "",
                REVIEW_LABELS.get(r["review_status"] or "", ""), r["reviewer_name"] or "",
                (r["notes"] or "").replace("\n", " "), "SIMULADO" if r["is_simulated"] else "Real"]

    if format == "csv":
        buf = io.StringIO()
        buf.write("﻿")  # BOM para que Excel reconozca UTF-8
        writer = csv.writer(buf)
        writer.writerow(headers)
        for r in rows:
            writer.writerow(values(r))
        return Response(buf.getvalue(), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="faceguard-eventos-{stamp}.csv"'})

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    pdf = io.BytesIO()
    doc = SimpleDocTemplate(pdf, pagesize=landscape(A4), leftMargin=24, rightMargin=24, topMargin=24, bottomMargin=24,
                            title="FaceGuard AI — Historial de eventos")
    styles = getSampleStyleSheet()
    small = styles["BodyText"].clone("small", fontSize=7, leading=8.5)
    story = [
        Paragraph("FaceGuard AI — Historial de eventos", styles["Title"]),
        Paragraph(f"Generado: {datetime.now():%d/%m/%Y %H:%M} · Usuario: {user['username']} · Registros: {len(rows)} "
                  "· Documento confidencial: contiene datos personales.", styles["Normal"]),
        Spacer(1, 8),
    ]
    data = [[Paragraph(f"<b>{h}</b>", small) for h in headers]]
    data += [[Paragraph(str(v).replace("&", "&amp;").replace("<", "&lt;"), small) for v in values(r)] for r in rows]
    table = Table(data, repeatRows=1, colWidths=[78, 92, 70, 66, 90, 42, 36, 80, 60, 115, 45])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#94a3b8")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(table)
    doc.build(story)
    return Response(pdf.getvalue(), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="faceguard-eventos-{stamp}.pdf"'})


@router.get("/api/events/{event_id}")
def get_event(event_id: int, user: dict = Depends(require("events.view"))):
    row = query_one("SELECT * FROM events WHERE id = ?", (event_id,))
    if not row:
        raise HTTPException(404, "Evento no encontrado.")
    out = serialize_event(row)
    out["can_view_images"] = has_perm(user, "alerts.images")
    out["can_review"] = has_perm(user, "alerts.review")
    if row["entry_id"]:
        entry = query_one("SELECT uid, full_name, alert_level, reason, status, photo_file, is_simulated FROM blacklist WHERE id = ?",
                          (row["entry_id"],))
        if entry:
            out["entry"] = {"uid": entry["uid"], "full_name": entry["full_name"], "alert_level": entry["alert_level"],
                            "reason": entry["reason"], "status": entry["status"], "has_photo": bool(entry["photo_file"])}
    return out


@router.get("/api/events/{event_id}/snapshot")
def event_snapshot(event_id: int, request: Request, user: dict = Depends(require("alerts.images"))):
    row = query_one("SELECT uid, snapshot_file FROM events WHERE id = ?", (event_id,))
    if not row or not row["snapshot_file"]:
        raise HTTPException(404, "Este evento no tiene imagen (o ya venció su periodo de conservación).")
    data = read_encrypted_file(row["snapshot_file"])
    if data is None:
        raise HTTPException(404, "Archivo no disponible.")
    audit(user, "ver imagen detectada", target=row["uid"], ip=client_ip(request))
    return Response(data, media_type="image/jpeg", headers={"Cache-Control": "no-store, private"})


# ------------------------------------------------------------------- alertas
@router.get("/api/alerts")
def list_alerts(status: str = "", level: str = "", q: str = "", simulated: str = "", page: int = 1, page_size: int = 25,
                user: dict = Depends(require("alerts.view"))):
    w, params = _filters(q, "coincidencia", level, status, None, None, simulated)
    limit, offset = paginate(page, page_size)
    total = query_one(f"SELECT COUNT(*) AS n FROM events WHERE {w}", tuple(params))["n"]
    rows = query(f"""SELECT * FROM events WHERE {w}
                     ORDER BY CASE review_status WHEN 'pendiente' THEN 0 ELSE 1 END,
                              CASE level WHEN 'alto' THEN 0 WHEN 'medio' THEN 1 ELSE 2 END, occurred_at DESC
                     LIMIT ? OFFSET ?""", (*params, limit, offset))
    counts = query("SELECT review_status AS status, COUNT(*) AS n FROM events WHERE type='coincidencia' GROUP BY review_status")
    return {"items": [serialize_event(r) for r in rows], "total": total, "page": page, "page_size": limit, "counts": counts}


class ReviewIn(BaseModel):
    status: str = Field(pattern="^(confirmada|falso_positivo|cerrada|pendiente)$")
    notes: str = Field(default="", max_length=1000)


@router.post("/api/alerts/{event_id}/review")
def review_alert(event_id: int, body: ReviewIn, request: Request, user: dict = Depends(require("alerts.review"))):
    row = query_one("SELECT * FROM events WHERE id = ? AND type = 'coincidencia'", (event_id,))
    if not row:
        raise HTTPException(404, "Alerta no encontrada.")
    if body.status in ("confirmada", "falso_positivo") and len(body.notes.strip()) < 5:
        raise HTTPException(422, "Describa brevemente la verificación realizada (mínimo 5 caracteres).")
    notes = body.notes.strip()
    if row["notes"]:
        notes = f"{row['notes']}\n[{utcnow()} {user['username']}] {notes}" if notes else row["notes"]
    elif notes:
        notes = f"[{utcnow()} {user['username']}] {notes}"
    execute("UPDATE events SET review_status = ?, reviewed_by = ?, reviewer_name = ?, reviewed_at = ?, notes = ? WHERE id = ?",
            (body.status, user["id"], user["full_name"], utcnow(), notes, event_id))
    audit(user, "revisión de alerta", target=row["uid"], details={"de": row["review_status"], "a": body.status},
          ip=client_ip(request))
    updated = serialize_event(query_one("SELECT * FROM events WHERE id = ?", (event_id,)))
    hub.publish("alert_updated", updated, perm="alerts.view")
    return updated
