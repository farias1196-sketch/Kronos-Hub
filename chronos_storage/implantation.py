from fastapi import HTTPException
from .postgres import transaction

async def set_stage(slug, stage):
    async with transaction() as db:
        row = await db.fetchrow("SELECT id, settings FROM tenants WHERE slug=$1 FOR UPDATE", slug)
        if not row: raise HTTPException(404, "Empresa não encontrada.")
        settings = dict(row['settings'] or {})
        previous = settings.get('implementation_stage', 1 if settings.get('chronos_facil') is True else 4)
        settings.update(implementation_stage=stage, chronos_facil=stage < 4)
        await db.execute("UPDATE tenants SET settings=$2::jsonb,updated_at=CURRENT_TIMESTAMP WHERE id=$1", row['id'], settings)
        await db.execute("INSERT INTO audit_logs(id,tenant_id,action,entity_type,entity_id,metadata) VALUES($1,$2,'core.company.implantation','Tenant',$2,$3::jsonb)",
                         __import__('uuid').uuid4().hex, row['id'], {'previous_stage': previous, 'stage': stage, 'actor': 'ADM geral'})
