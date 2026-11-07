"""Verificações locais sobre os arquivos preparados no índice Git."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args])


def main():
    names = [item.decode("utf-8") for item in git("ls-files", "-z").split(b"\0") if item]
    licenses = {"LICENSE", "LICENSE-DOCS"}
    missing = licenses.difference(names)
    if missing:
        raise SystemExit("Licenças ausentes do índice: " + ", ".join(sorted(missing)))
    if ".env.example" not in names or not names:
        raise SystemExit("Adicione os fontes revisados e .env.example ao índice.")
    expected = {"PREVIEW_SSO_SECRET=", "PREVIEW_ADM_SECRET=", "PREVIEW_DEMO_PASSWORD=",
                "PREVIEW_INITIAL_ADMIN_PASSWORD="}
    example = git("show", ":.env.example").decode().splitlines()
    if {line for line in example if line and not line.startswith("#")} != expected:
        raise SystemExit("Revise .env.example: somente os quatro campos vazios são permitidos.")
    values = []
    if (ROOT / ".env").is_file():
        for line in (ROOT / ".env").read_bytes().splitlines():
            name, sep, value = line.partition(b"=")
            if name.decode("utf-8", errors="replace") + "=" in expected and sep and value:
                values.append(value)
    patterns = (
        rb"-----BEGIN (?:RSA |EC |OPENSSH |ENCRYPTED )?PRIVATE KEY-----",
        rb"gh[pousr]_[A-Za-z0-9]{30,}|AKIA[0-9A-Z]{16}",
        rb"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b|\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b",
    )
    allowed_types = {".md", ".py", ".sql"}
    exceptions = licenses | {".env.example", ".gitignore", "requirements.txt", "Chronos_stock/requirements.txt", "Chronos_loja/requirements.txt"}
    excluded = {".local", "data", "backups", "imports", "secrets", "sessions", "exports"}
    ui_files = {
        "Chronos_UI/index.html", "Chronos_UI/package.json", "Chronos_UI/package-lock.json",
        "Chronos_UI/vite.config.js", "Chronos Prisma/schema.prisma",
        "Chronos_zap/message_queue/prisma/schema.prisma",
    }
    forbidden_parts = {".git", "node_modules", "dist", "uploads", "storage", "artifacts", "runtime-logs"}
    findings = []
    for record in git("ls-files", "--stage", "-z").split(b"\0"):
        if record and not record.startswith(b"100644 "):
            raise SystemExit("O índice contém links, submódulos ou modos inesperados.")
    for name in names:
        path = Path(name)
        blob = git("show", ":" + name)
        ui_source = name.startswith("Chronos_UI/src/") and path.suffix in {".jsx", ".js", ".css"}
        if (name not in exceptions and name not in ui_files and not ui_source and path.suffix.lower() not in allowed_types
                or forbidden_parts.intersection(p.lower() for p in path.parts)
                or excluded.intersection(p.lower() for p in path.parts)
                or b"\0" in blob or any(v in blob for v in values)
                or any(re.search(pattern, blob) for pattern in patterns)):
            findings.append(name)
    if findings:
        raise SystemExit("Arquivos para revisão (valores omitidos): " + ", ".join(findings))
    for sample in [".env", ".env.backup", ".local/core.sqlite3"]:
        subprocess.run(["git", "-C", str(ROOT), "check-ignore", "-q", "--", sample], check=True)
    print(f"{len(names)} arquivos no índice. O .env e o armazenamento local estão excluídos.")


if __name__ == "__main__":
    main()
