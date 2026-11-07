"""Exporta o piloto a partir do índice Git da pasta de envio, sem dados de execução."""
import argparse
from pathlib import Path
import subprocess

FILES = (
    "LICENSE", "LICENSE-DOCS", ".env.example", ".gitignore", "init_preview.py", "preview_config.py",
    "Chronos_stock/README.md", "Chronos_stock/requirements.txt",
    "Chronos_stock/demo_items.py", "Chronos_stock/exportar_piloto.py",
    "Chronos_stock/verificar_piloto.py", "Chronos_stock/stock_api/app/main.py",
    *(f"chronos_auth/{name}.py" for name in (
        "__init__", "assets", "config", "integration", "middleware", "policy", "scope",
        "services", "token", "webhooks")),
    *(f"chronos_storage/{name}.py" for name in (
        "__init__", "atomic", "postgres", "runtime_sync", "stock_runtime",
        "stock_catalog_csv", "stock_shop_exchange")),
)


def export(destination, files=FILES):
    root = Path(__file__).resolve().parents[1]
    destination = destination.resolve()
    if destination.is_relative_to(root):
        raise SystemExit("Escolha uma pasta nova fora deste repositório.")
    def git(*args):
        return subprocess.check_output(["git", "-C", str(root), *args])
    index = {}
    for row in git("ls-files", "--stage", "-z", "--", *files).split(b"\0"):
        if row:
            metadata, path = row.split(b"\t")
            mode, oid, stage = metadata.split()
            if mode != b"100644" or stage != b"0":
                raise SystemExit("O piloto exige arquivos normais e um índice sem conflito.")
            index[path.decode("utf-8")] = oid.decode("ascii")
    if set(index) != set(files):
        raise SystemExit("Há fontes ausentes no índice. Revise git status.")
    blobs = {name: git("cat-file", "blob", index[name]) for name in files}
    destination.mkdir(exist_ok=False)
    for name, content in blobs.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as out:
            out.write(content)
    print(f"Piloto exportado: {len(blobs)} arquivos do índice.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destino", type=Path)
    export(parser.parse_args().destino)
