"""Herramientas de administración por consola.

Uso (desde la carpeta backend/):
  python -m scripts.manage create-user <usuario> "<Nombre completo>" <rol>
  python -m scripts.manage reset-password <usuario>
  python -m scripts.manage list-users
  python -m scripts.manage backup [carpeta] [--with-key]
  python -m scripts.manage restore <respaldo.zip>
  python -m scripts.manage hardware-test [led|buzzer|completa|blacklist|desconocido|todas]
Roles: superadmin, admin, operator, auditor
"""
from __future__ import annotations

import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import config  # noqa: E402
from app.core.audit import audit  # noqa: E402
from app.core.database import execute, query, query_one, run_migrations, utcnow  # noqa: E402
from app.core.security import ROLES, hash_password, validate_password_strength  # noqa: E402
from app.services.backup import BackupError, create_backup, restore_backup  # noqa: E402


def ask_password() -> str:
    while True:
        pw = getpass.getpass("Contraseña temporal: ")
        if pw != getpass.getpass("Repita la contraseña: "):
            print("No coinciden."); continue
        problem = validate_password_strength(pw)
        if problem:
            print(problem); continue
        return pw


def hardware_test(which: str) -> int:
    """Diagnóstico del LED y el buzzer sin abrir el panel (con el servicio detenido)."""
    import time

    from app.services import hardware_diagnostics as diag
    from app.services.alarm_controller import alarm
    from app.services.settings_store import settings

    names = list(diag.TESTS) if which == "todas" else [which]
    if any(n not in diag.TESTS for n in names):
        print(f"Prueba desconocida. Opciones: {', '.join(diag.TESTS)}, todas"); return 1
    settings.load()
    cfg = settings.all()
    alarm.setup(cfg["led_pin"], cfg["buzzer_pin"], cfg["buzzer_type"], cfg["buzzer_frequency"])
    st = alarm.status()
    print(f"Modo: {st['mode']} · LED GPIO{st['led_pin']} (pin {st['led_physical']}) · "
          f"buzzer {st['buzzer_type']} GPIO{st['buzzer_pin']} (pin {st['buzzer_physical']})")
    if st["error"]:
        print(f"  {st['error']}")
    failed = 0
    try:
        for n in names:
            print(f"\n{diag.TESTS[n]} …")
            r = diag.run(n, cfg, wait=True)
            while alarm.alarm_active:  # la prueba 4 dispara la alarma real: esperar a que termine
                time.sleep(0.1)
            print(f"  {'OK   ' if r['ok'] else 'FALLO'} {r['message']}")
            if r["hint"] and (not r["ok"] or n in ("led", "buzzer")):
                print(f"  → {r['hint']}")
            failed += not r["ok"]
            time.sleep(0.5)
    finally:
        alarm.close()
    print(f"\n{len(names) - failed}/{len(names)} pruebas correctas.")
    return 1 if failed else 0


def main(argv: list[str]) -> int:
    config.ensure_dirs()
    run_migrations()
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__); return 0
    cmd = argv[0]
    if cmd == "create-user" and len(argv) == 4:
        username, name, role = argv[1:]
        if role not in ROLES:
            print(f"Rol inválido. Opciones: {', '.join(ROLES)}"); return 1
        if query_one("SELECT id FROM users WHERE username = ?", (username,)):
            print("El usuario ya existe."); return 1
        execute("INSERT INTO users (username, full_name, password_hash, role, active, must_change_password, created_at) "
                "VALUES (?,?,?,?,1,1,?)", (username, name, hash_password(ask_password()), role, utcnow()))
        audit(None, "crear usuario (consola)", target=username, details={"rol": role})
        print(f"Usuario {username} creado. Deberá cambiar la contraseña al ingresar.")
    elif cmd == "reset-password" and len(argv) == 2:
        if not query_one("SELECT id FROM users WHERE username = ?", (argv[1],)):
            print("Usuario no encontrado."); return 1
        execute("UPDATE users SET password_hash = ?, must_change_password = 1, active = 1 WHERE username = ?",
                (hash_password(ask_password()), argv[1]))
        execute("DELETE FROM sessions WHERE user_id = (SELECT id FROM users WHERE username = ?)", (argv[1],))
        audit(None, "restablecer contraseña (consola)", target=argv[1])
        print("Contraseña restablecida.")
    elif cmd == "backup" and len(argv) >= 1:
        rest = [a for a in argv[1:] if a != "--with-key"]
        target = create_backup(Path(rest[0]) if rest else config.data_dir / "backups", include_key="--with-key" in argv)
        print(f"Respaldo creado: {target}")
        if "--with-key" in argv:
            print("ATENCIÓN: incluye la clave de cifrado. Guárdelo en un lugar seguro.")
        else:
            print("La clave de cifrado no va incluida. Guarde una copia aparte de secret/fernet.key.")
    elif cmd == "restore" and len(argv) == 2:
        print("Asegúrese de que FaceGuard esté detenido antes de continuar.")
        if input("Escriba RESTAURAR para reemplazar los datos actuales: ") != "RESTAURAR":
            print("Cancelado."); return 1
        try:
            previous = restore_backup(Path(argv[1]))
        except BackupError as exc:
            print(f"No se restauró nada: {exc}"); return 1
        print(f"Restauración completa. Datos anteriores guardados en {previous}")
    elif cmd == "hardware-test" and len(argv) <= 2:
        return hardware_test(argv[1] if len(argv) == 2 else "todas")
    elif cmd == "list-users":
        for u in query("SELECT username, full_name, role, active, last_login FROM users ORDER BY role"):
            print(f"{u['username']:<16} {u['role']:<11} {'activo' if u['active'] else 'inactivo':<9} {u['full_name']}")
    else:
        print(__doc__); return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
