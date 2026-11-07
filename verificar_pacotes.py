"""Exercita os serviços instalados em um ambiente virtual fora do checkout."""
from importlib.metadata import version
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent


def verify(name, script, flags):
    for flag in flags:
        with tempfile.TemporaryDirectory(prefix=name) as temp:
            runtime = Path(temp)
            test = runtime / script
            test.parent.mkdir()
            shutil.copyfile(ROOT / script, test)
            subprocess.run([sys.executable, "-IB", str(test), flag], cwd=runtime, check=True)


if __name__ == "__main__":
    for package in ("chronos-hub-shared", "chronos-hub-stock", "chronos-hub-loja"):
        assert version(package) == "0.1.0", package
    verify("chronos-stock-test-", "Chronos_stock/verificar_piloto.py", ["--empty", "--demo", "--parallel"])
    verify("loja-stock-", "Chronos_loja/verificar_integracao.py", ["--isolado"])
    print("Estoque, Loja e pacote compartilhado verificados fora do checkout.")
