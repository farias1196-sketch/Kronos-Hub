import json
from fastapi import HTTPException
from chronos_storage.runtime_sync import postgres_mode, run
from chronos_storage.postgres import get_connection
from . import nexus_store

async def pg_profile(slug, fields=None):
    async with get_connection() as connection:
        if fields is None:
            data = await connection.fetchval("SELECT settings->'nexus_registration_profile' FROM tenants WHERE slug=$1", slug)
            return data or []
        result = await connection.execute("UPDATE tenants SET settings=jsonb_set(COALESCE(settings,'{}'::jsonb),'{nexus_registration_profile}',$2::jsonb) WHERE slug=$1", slug, fields)
        if result == "UPDATE 0": raise HTTPException(404, "Empresa não encontrada.")
        return fields

def profile(slug, fields=None):
    if postgres_mode("nexus") == "primary": return run(pg_profile(slug, fields))
    nexus_store.init_db()
    with nexus_store.connect() as db:
        db.execute("CREATE TABLE IF NOT EXISTS registration_profiles (empresa_id TEXT PRIMARY KEY, fields TEXT NOT NULL)")
        if fields is not None:
            db.execute("INSERT INTO registration_profiles VALUES (?,?) ON CONFLICT(empresa_id) DO UPDATE SET fields=excluded.fields", (slug,json.dumps(fields,ensure_ascii=False)))
            return fields
        row=db.execute("SELECT fields FROM registration_profiles WHERE empresa_id=?",(slug,)).fetchone()
        return json.loads(row[0]) if row else []

def validate_answers(slug, answers, required=False):
    fields=profile(slug)
    known={field["id"]:field for field in fields}
    if len(answers)>50 or any(key not in known or len(value)>2000 for key,value in answers.items()):
        raise HTTPException(422,"Confira os campos do perfil de cadastro.")
    if required:
        for field in fields:
            if field.get("required") and not answers.get(field["id"],"").strip():
                raise HTTPException(422,"Preencha o campo: "+field["label"])
    return {key:value.strip() for key,value in answers.items()}
