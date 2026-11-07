"""Inicia as APIs desta pasta em loopback até Ctrl+C."""
from pathlib import Path
import socket
import subprocess
import sys
import time

from preview_config import require_secret

ROOT = Path(__file__).resolve().parent
SERVICES = {
    "Chronos_Core.core_api.app.main": 18802,
    "Chronos_nexus.nexus_api.app.main": 18803,
    "Chronos_ADM.adm_api.main": 18805,
    "Chronos_loja.loja_api.app.main": 18806,
    "Chronos_agenda.Agenda_api.app.main": 18807,
    "Chronos Media.media_api.app.main": 18809,
    "Chronos_stock.stock_api.app.main": 18815,
}


def main():
    require_secret("PREVIEW_SSO_SECRET")
    for port in SERVICES.values():
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError as exc:
                raise SystemExit(f"Porta {port} ocupada. Verifique-a antes de iniciar.") from exc
    processes = {}
    try:
        for module, port in SERVICES.items():
            processes[module] = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", module + ":app",
                 "--host", "127.0.0.1", "--port", str(port)], cwd=ROOT
            )
        while True:
            for module, process in processes.items():
                if process.poll() is not None:
                    raise SystemExit(f"{module} encerrou com código {process.returncode}.")
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        for process in processes.values():
            if process.poll() is None:
                process.terminate()
        for process in processes.values():
            process.wait()


if __name__ == "__main__":
    main()
