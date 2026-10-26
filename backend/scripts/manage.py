"""Herramientas de administración por consola.

Uso (desde la carpeta backend/):
  python -m scripts.manage create-user <usuario> "<Nombre completo>" <rol>
  python -m scripts.manage reset-password <usuario>
  python -m scripts.manage list-users
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


def ask_password() -> str:
    while True:
        pw = getpass.getpass("Contraseña temporal: ")
        if pw != getpass.getpass("Repita la contraseña: "):
            print("No coinciden."); continue
        problem = validate_password_strength(pw)
        if problem:
            print(problem); continue
        return pw


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
    elif cmd == "list-users":
        for u in query("SELECT username, full_name, role, active, last_login FROM users ORDER BY role"):
            print(f"{u['username']:<16} {u['role']:<11} {'activo' if u['active'] else 'inactivo':<9} {u['full_name']}")
    else:
        print(__doc__); return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
