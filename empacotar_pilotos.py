"""Constrói três wheels locais com os mesmos fontes selecionados pelos exportadores."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

from Chronos_loja.exportar_piloto import FILES, export

VERSION = "0.1.0"


def build(source, workspace, name, entries, deps, modules):
    project = workspace / name
    project.mkdir()
    for entry in [*entries, "LICENSE", "LICENSE-DOCS"]:
        dest = project / entry
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / entry, dest)
    packages = sorted({str(Path(e).parent).replace("\\", ".").replace("/", ".") for e in entries if "/" in e})
    manifest = f'''[build-system]
requires = ["setuptools>=77,<83", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "{name}"
version = "{VERSION}"
requires-python = ">=3.11"
license = "MIT"
license-files = ["LICENSE", "LICENSE-DOCS"]
dependencies = {json.dumps(deps)}

[tool.setuptools]
packages = {json.dumps(packages)}
py-modules = {json.dumps(modules)}
'''
    (project / "pyproject.toml").write_text(manifest, encoding="utf-8")
    subprocess.run([sys.executable, "-m", "pip", "wheel", "--no-deps", "--wheel-dir",
                    str(workspace / "wheels"), str(project)], check=True)


def main(destination):
    destination = destination.resolve()
    if destination.exists():
        raise SystemExit("Escolha um diretório novo para os três wheels.")
    with TemporaryDirectory(prefix="chronos-build-") as temp:
        workspace = Path(temp)
        source = workspace / "source"
        export(source, FILES)
        common = [e for e in FILES if e.startswith(("chronos_auth/", "chronos_storage/"))]
        modules = ["init_preview", "preview_config", "preview_http"]
        requirements = (source / "Chronos_stock/requirements.txt").read_text().splitlines()
        build(source, workspace, "chronos-hub-shared", common + [m+".py" for m in modules],
              requirements, modules)
        shared = f"chronos-hub-shared=={VERSION}"
        for name, prefix, deps in [("chronos-hub-stock", "Chronos_stock/", [shared]),
                                   ("chronos-hub-loja", "Chronos_loja/", [shared, "reportlab>=4,<5"])]:
            files = [e for e in FILES if e.startswith(prefix) and e.endswith(".py")
                     and not Path(e).name.startswith(("exportar_", "verificar_"))]
            build(source, workspace, name, files, deps, [])
        shutil.copytree(workspace / "wheels", destination)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destino", type=Path)
    main(parser.parse_args().destino)
