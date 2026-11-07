"""Cria segredos locais e, opcionalmente, contas inteiramente fictícias."""
import argparse
import os
import secrets
import tempfile
from pathlib import Path

from preview_config import ENV_PATH, FIELDS, require_secret


def initialize_env():
    if not ENV_PATH.exists():
        # Publique o arquivo completo sem substituir segredos de outra execução.
        with tempfile.NamedTemporaryFile(dir=ENV_PATH.parent, prefix=".env.",
                                         delete=False, mode="w", encoding="utf-8") as f:
            candidate = Path(f.name)
            for key in FIELDS:
                f.write(f"{key}={secrets.token_urlsafe(36)}\n")
        try:
            try:
                os.link(candidate, ENV_PATH)
            except FileExistsError:
                pass
        finally:
            candidate.unlink()
    for field in FIELDS:
        require_secret(field)


def create_demo():
    from Chronos_Core.core_api.app import core_store as core
    from Chronos_ADM.adm_api.database import SessionLocal, SuperAdmin
    from Chronos_ADM.adm_api.main import hash_password
    from sqlalchemy import text

    core.init_db()
    with core.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute(
            "INSERT OR IGNORE INTO tenants(id, name, slug, status, created_at, updated_at) "
            "VALUES ('demo-local', 'Empresa de demonstração', 'demo', 'ACTIVE', "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
        exists = db.execute("SELECT 1 FROM users WHERE email=?", ("demo@example.invalid",)).fetchone()
    if not exists:
        core.create_or_update_member("demo", {"name": "Pessoa Demo", "email": "demo@example.invalid",
                                             "role": "ADMIN", "temporary_password": require_secret("PREVIEW_DEMO_PASSWORD")})
    with SessionLocal.begin() as db:
        db.execute(text("BEGIN IMMEDIATE"))
        if not db.query(SuperAdmin).first():
            db.add(SuperAdmin(username="admin-local", display_name="Admin local",
                              hashed_password=hash_password(require_secret("PREVIEW_INITIAL_ADMIN_PASSWORD"))))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true", help="criar empresa e acessos fictícios")
    args = parser.parse_args()
    initialize_env()
    if args.demo:
        from Chronos_stock.demo_items import enable_demo_stock
        create_demo()
        enable_demo_stock()
    print("Configuração local pronta.")
