"""Teste HTTP do Estoque com duas empresas e dois processos sucessivos, em uma cópia temporária."""
from contextlib import contextmanager
from hashlib import sha256
import json
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import build_opener, ProxyHandler, Request

ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def server():
    # A API escolhe uma porta de loopback livre, sem disputar portas dos serviços do usuário.
    instance = uuid4().hex
    proc = subprocess.Popen([sys.executable, "-IB", __file__, "--serve", instance])
    address = Path(f"test-port-{instance}")
    shutdown = Path(f"test-stop-{instance}")
    try:
        for _ in range(120):
            if proc.poll() is not None:
                raise RuntimeError("O processo de teste encerrou antes da inicialização.")
            if address.exists() and address.read_text().isdigit():
                url = "http://127.0.0.1:" + address.read_text()
                try:
                    if request(url, "/health").get("ok"):
                        break
                except URLError:
                    pass
            time.sleep(0.1)
        else:
            raise RuntimeError("A API isolada não iniciou no prazo.")
        yield url
    finally:
        shutdown.touch()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.terminate()
            proc.wait(timeout=5)
            raise AssertionError("A API de teste não encerrou normalmente.")
        if proc.returncode:
            raise AssertionError(f"A API de teste encerrou com código {proc.returncode}.")


def request(url, route, token=None, *, method="GET", data=None, expected=200):
    headers = {"Authorization": "Bearer " + token} if token else {}
    body = None
    if data is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(data).encode()
    req = Request(url + route, data=body, headers=headers, method=method)
    try:
        with build_opener(ProxyHandler({})).open(req, timeout=4) as res:
            result, code = json.load(res), res.status
    except HTTPError as error:
        with error:
            error.read()
            result, code = None, error.code
    if code != expected:
        raise AssertionError(f"{method} {route}: esperado {expected}, recebido {code}")
    return result


def test_token(slug):
    from chronos_auth.token import create_token
    return create_token(member_id="m-test", user_id="u-test", user_name="Fictício",
                        tenant_id=slug, tenant_slug=slug, role="OPERATOR",
                        permissions=["stock.products.manage"])


def exercise():
    from init_preview import initialize_env
    initialize_env()
    from Chronos_stock.demo_items import enable_demo_stock
    with server() as api:
        assert request(api, "/stock/items", test_token("demo"))["items"] == []
    # Estoque existente não é resemeado. Para o cenário da demonstração usar outro sandbox.
    enable_demo_stock()
    with server() as api:
        assert not request(api, "/stock/items", test_token("demo"))["items"]


def exercise_demo():
    from init_preview import initialize_env
    initialize_env()
    from Chronos_stock.demo_items import enable_demo_stock
    enable_demo_stock()
    left, right = "Demo", "demo"
    a, b = test_token(left), test_token(right)
    stock = ROOT / ".local/stock"
    with server() as api:
        request(api, "/stock/items", expected=401)
        seeds = request(api, "/stock/items", b)["items"]
        assert len(seeds) == 6 and len({i["sku"] for i in seeds}) == 6
        assert sum(i["kind"] == "sale" for i in seeds) == 3
        assert not request(api, "/stock/items", a)["items"]
        initial = (stock / "stock_data.json").read_bytes()
        for invalid in ("..", ".", "../demo", "foo/bar", "foo\\bar", "C:temp", "demo "):
            request(api, "/stock/ai/snapshot", test_token(invalid), expected=400)
            request(api, "/stock/items", test_token(invalid), method="POST", data={"name":"Inválido","kind":"sale"}, expected=400)
        assert (stock / "stock_data.json").read_bytes() == initial
        assert not (stock / "ai_snapshots").exists()
        assert not (stock / "stock_snapshot.json").exists()
        # Um redirecionamento presente no disco não pode levar uma escrita para fora.
        import os
        redirected = stock / "ai_snapshots" / sha256(b"redirected").hexdigest()
        redirected.parent.mkdir(parents=True)
        outside = ROOT / "outside-snapshots"
        outside.mkdir()
        if os.name == "nt":
            env = dict(os.environ, STOCK_TEST_LINK=str(redirected), STOCK_TEST_TARGET=str(outside))
            subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                            "$ErrorActionPreference='Stop'; New-Item -ItemType Junction "
                            "-Path $env:STOCK_TEST_LINK -Target $env:STOCK_TEST_TARGET | Out-Null"],
                           env=env, check=True)
        else:
            redirected.symlink_to(outside, target_is_directory=True)
        request(api, "/stock/ai/snapshot", test_token("redirected"), expected=400)
        assert not list(outside.iterdir())
        assert (stock / "stock_data.json").read_bytes() == initial
        item = {"name":"Item de isolamento","kind":"sale","sku":"TESTE-COMPARTILHADO"}
        result = request(api, "/stock/items", a, method="POST", data=item)["item"]
        request(api, "/stock/items?tenant_id=Demo", b, expected=403)
        request(api, "/stock/items/" + result["id"], b, method="DELETE", expected=404)
        request(api, "/stock/items", b, method="POST", data=item)
        request(api, "/stock/items/" + seeds[0]["id"], b, method="DELETE")
        for slug in (left,right):
            snap = request(api, "/stock/ai/snapshot", test_token(slug))["snapshot"]
            path = stock / "ai_snapshots" / sha256(slug.encode()).hexdigest() / "stock_snapshot.json"
            assert json.loads(path.read_text(encoding="utf-8"))["tenant_id"] == slug
            assert all(row["tenant_id"] == slug for row in snap["stock"]["sale"])
    with server() as api:
        one = request(api, "/stock/items", a)["items"]
        two = request(api, "/stock/items", b)["items"]
        assert len(one) == 1 and one[0]["id"] == result["id"]
        assert len(two) == 6 and seeds[0]["id"] not in {i["id"] for i in two}
        assert all(i["tenant_id"] == right for i in two)
        assert all(i["tenant_id"] == left for i in one)


def exercise_concurrent_movements():
    from init_preview import initialize_env
    initialize_env()
    auth = test_token("demo")
    with server() as first:
        item = request(first, "/stock/items", auth, method="POST",
                       data={"kind":"sale","name":"Peça de teste","quantity":10})["item"]
        endpoint = "/stock/items/" + item["id"] + "/withdraw"
        with server() as second:
            def simultaneous(amount):
                barrier = Barrier(2)
                def withdraw(url):
                    barrier.wait(timeout=5)
                    req = Request(url + endpoint, method="POST",
                                  headers={"Authorization":"Bearer " + auth,"Content-Type":"application/json"},
                                  data=json.dumps({"quantity":amount}).encode())
                    try:
                        response = build_opener(ProxyHandler({})).open(req, timeout=8)
                    except HTTPError as error:
                        response = error
                    with response:
                        response.read()
                        return response.status
                with ThreadPoolExecutor(max_workers=2) as pool:
                    return sorted(pool.map(withdraw, [first, second]))
            statuses = simultaneous(7)
            assert statuses == [200, 409], f"Duas baixas de 7 com saldo 10: {statuses}"
            assert simultaneous(1) == [200, 200]
            for url in (first, second):
                assert request(url, "/stock/items", auth)["items"][0]["quantity"] == 1
    with server() as restarted:
        assert request(restarted, "/stock/items", auth)["items"][0]["quantity"] == 1
        moves = request(restarted, "/stock/internal/movements?item_id=" + item["id"], auth)["movements"]
        assert sorted(row["quantity"] for row in moves) == [1, 1, 7]
        assert len({row["id"] for row in moves}) == 3


def serve(instance):
    import uvicorn
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        Path(f"test-port-{instance}").write_text(str(port))
        config = uvicorn.Config("Chronos_stock.stock_api.app.main:app", log_config=None, access_log=False)
        import asyncio
        async def run():
            server = uvicorn.Server(config)
            task = asyncio.create_task(server.serve(sockets=[sock]))
            while not task.done() and not Path(f"test-stop-{instance}").exists():
                await asyncio.sleep(0.05)
            server.should_exit = True
            await task
        asyncio.run(run())


if __name__ == "__main__":
    is_server = (len(sys.argv) == 3 and sys.argv[1] == "--serve" and len(sys.argv[2]) == 32
                 and all(c in "0123456789abcdef" for c in sys.argv[2]))
    if sys.argv[1:] in (["--empty"], ["--demo"], ["--parallel"]) or is_server:
        if ROOT != Path.cwd().resolve() or ROOT.parent != Path(tempfile.gettempdir()).resolve() or not ROOT.name.startswith("chronos-stock-test-"):
            raise SystemExit("Esta operação só é permitida na pasta temporária do teste.")
        sys.path.insert(0, str(ROOT))
        if is_server: serve(sys.argv[2])
        elif sys.argv[1] == "--empty": exercise()
        elif sys.argv[1] == "--parallel": exercise_concurrent_movements()
        else: exercise_demo()
    else:
        sys.path.insert(0, str(ROOT / "Chronos_stock"))
        from exportar_piloto import FILES
        for flag in ("--empty", "--demo", "--parallel"):
            with tempfile.TemporaryDirectory(prefix="chronos-stock-test-") as temp:
                sandbox = Path(temp)
                for name in FILES:
                    target = sandbox / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(ROOT / name, target)
                child = sandbox / Path(__file__).relative_to(ROOT)
                subprocess.run([sys.executable,"-IB",str(child),flag],cwd=sandbox,check=True)
        print("OK: início vazio, seis exemplos, isolamento, snapshots, baixas simultâneas e reinício.")
