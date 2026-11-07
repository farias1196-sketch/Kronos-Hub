"""Verifica Loja e Estoque por HTTP real em um diretório temporário exclusivo."""
import asyncio
from contextlib import contextmanager
from importlib import import_module
import json
import multiprocessing
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
from urllib.error import HTTPError
from urllib.request import build_opener, ProxyHandler, Request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
STOCK_PORT = 18815


def api(url, path, token=None, method="GET", body=None, status=200):
    headers = {"Authorization": "Bearer " + token} if token else {}
    raw = None if body is None else json.dumps(body).encode()
    if raw is not None:
        headers["Content-Type"] = "application/json"
    req = Request(url + path, data=raw, method=method, headers=headers)
    try:
        response = build_opener(ProxyHandler({})).open(req, timeout=9)
    except HTTPError as error:
        response = error
    with response:
        result = json.load(response)
        actual = response.status
    if actual != status:
        raise AssertionError(f"{method} {path}: esperado {status}, recebido {actual}.")
    return result


@contextmanager
def socket_local(port):
    with socket.socket() as sock:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            raise SystemExit(f"Porta {port} indisponível; nenhum serviço existente foi usado.") from None
        yield sock


def child(module, sock, ready, stop, reads):
    import uvicorn
    app = import_module(module).app

    async def observed(scope, receive, send):
        if scope["type"] == "http" and scope["path"] == "/stock/items" and scope["method"] == "GET":
            with reads.get_lock():
                reads.value += 1
        await app(scope, receive, send)

    async def run():
        server = uvicorn.Server(uvicorn.Config(observed, log_level="error", access_log=False))
        task = asyncio.create_task(server.serve(sockets=[sock]))
        while not task.done() and not stop.is_set():
            if server.started:
                ready.set()
            await asyncio.sleep(0.05)
        server.should_exit = True
        await task
    # O teste reusa o socket reservado entre processos. Um seletor evita vinculá-lo
    # de forma permanente à porta de conclusão de E/S do primeiro processo no Windows.
    with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
        runner.run(run())


@contextmanager
def service(module, sock, reads):
    ctx = multiprocessing.get_context("spawn")
    stop, ready = ctx.Event(), ctx.Event()
    proc = ctx.Process(target=child, args=(module, sock, ready, stop, reads))
    proc.start()
    try:
        if not ready.wait(15):
            raise AssertionError(f"{module} não iniciou.")
        url = f"http://127.0.0.1:{sock.getsockname()[1]}"
        assert api(url, "/health")["ok"]
        yield url
    finally:
        stop.set()
        proc.join(10)
        if proc.is_alive():
            proc.terminate()
            proc.join()
            raise AssertionError("O processo de teste não encerrou normalmente.")
        if proc.exitcode:
            raise AssertionError(f"{module} encerrou com código {proc.exitcode}.")


def exercise():
    from init_preview import initialize_env
    initialize_env()
    from chronos_auth.token import create_token
    def session(tenant):
        return create_token(member_id="m", user_id="u", user_name="Teste",
                            tenant_id=tenant, tenant_slug=tenant, role="ADMIN",
                            permissions=["loja.store.manage", "stock.products.manage"])
    a, b = session("demo"), session("vizinha")
    count = multiprocessing.get_context("spawn").Value("i", 0)
    stock_module = "Chronos_stock.stock_api.app.main"
    shop_module = "Chronos_loja.loja_api.app.main"
    save = ROOT / ".local/loja/loja_data.json"
    with socket_local(STOCK_PORT) as stock_socket, socket_local(0) as shop_socket:
        with service(shop_module, shop_socket, count) as shop:
            api(shop, "/shop/config", a)
            prior = save.read_bytes()
            api(shop, "/shop/products/import-from-stock", a, "POST", status=503)
            assert save.read_bytes() == prior
            with service(stock_module, stock_socket, count) as stock:
                for key, name in ((a, "Caderno de marés"), (b, "Flor de papel")):
                    api(stock, "/stock/items", key, "POST", {"name":name, "sku":"FIC-01",
                        "category":"Oficina", "family":name, "quantity":8, "kind":"sale"})
                api(shop, "/shop/products/import-from-stock", method="POST", status=401)
                api(shop, "/shop/products/import-from-stock?tenant_id=vizinha", a, "POST", status=403)
                before = count.value
                first = api(shop, "/shop/products/import-from-stock", a, "POST")
                assert count.value == before + 1
                assert first["imported"] == 1 and len(first["products"]) == 1
                product = first["products"][0]
                pid = product["id"]
                vid = product["variants"][0]["stock_item_id"]
                assert product["family"] == "Caderno de marés"
                assert not api(shop, "/public/demo/catalog")["products"]
                api(shop, "/shop/products/"+pid, a, "PATCH", {
                    "published":True, "public_name":"Catálogo fictício", "visible_stock":False,
                    "variant_prices":{vid:{"sale_price":19.25,"sellable":True}},
                })
                second = api(shop, "/shop/products/import-from-stock", a, "POST")
                assert second["imported"] == 0 and len(second["products"]) == 1
                assert second["products"][0]["variants"][0]["sale_price"] == 19.25
                # Simula o catálogo da distribuição inicial, que ainda não guardava a família de origem.
                legacy = json.loads(save.read_text(encoding="utf-8"))
                del legacy["products"]["demo"][pid]["stock_family"]
                save.write_text(json.dumps(legacy), encoding="utf-8")
                api(stock, "/stock/items", a, "POST", {"name":"Segunda família", "sku":"FIC-02",
                    "category":"Oficina", "family":"CADERNO DE MARÉS", "quantity":3, "kind":"sale"})
                collided = api(shop, "/shop/products/import-from-stock", a, "POST")
                assert collided["imported"] == 1
                siblings = {p["family"]: p for p in collided["products"]}
                assert siblings["Caderno de marés"]["id"] == pid
                sibling = siblings["CADERNO DE MARÉS"]
                assert sibling["id"] != pid and not sibling["published"]
                assert sibling["variants"][0]["sale_price"] == 0
                assert siblings["Caderno de marés"]["variants"][0]["sale_price"] == 19.25
                assert api(shop, "/shop/products/import-from-stock", a, "POST")["imported"] == 0
                prior = save.read_bytes()
                ambiguous = json.loads(prior)
                old = ambiguous["products"]["demo"][pid]
                del old["stock_family"]
                old["variant_prices"][sibling["variants"][0]["stock_item_id"]] = {"sale_price": 8}
                save.write_text(json.dumps(ambiguous), encoding="utf-8")
                unchanged = save.read_bytes()
                api(shop, "/shop/products/import-from-stock", a, "POST", status=409)
                api(shop, "/shop/products/"+pid, a, "PATCH", {"published":False}, status=409)
                assert save.read_bytes() == unchanged
                save.write_bytes(prior)
                other = api(shop, "/shop/products/import-from-stock", b, "POST")
                assert other["products"][0]["family"] == "Flor de papel"
        # Dois novos processos leem os mesmos arquivos locais.
        with service(stock_module, stock_socket, count), service(shop_module, shop_socket, count) as shop:
            by_id = {p["id"]: p for p in api(shop, "/shop/products", a)["products"]}
            assert by_id[sibling["id"]]["family"] == "CADERNO DE MARÉS"
            private = by_id[pid]
            assert private["published"] and private["variants"][0]["quantity"] == 8
            public = api(shop, "/public/demo/catalog")["products"]
            assert len(public) == 1 and public[0]["id"] == pid and public[0]["public_name"] == "Catálogo fictício"
            assert "variant_prices" not in public[0]
            variant = public[0]["variants"][0]
            assert not ({"quantity","available","min_quantity","source_lot_totals"} & variant.keys())
            assert variant["sale_price"] == 19.25
            api(shop, "/shop/products/"+pid, a, "PATCH", {"visible_stock":True})
            assert api(shop, "/public/demo/catalog")["products"][0]["variants"][0]["quantity"] == 8
            api(shop, "/shop/products/"+pid, a, "PATCH", {"variant_prices":{vid:{"sellable":False}}})
            assert not api(shop, "/public/demo/catalog")["products"][0]["variants"]

    # Uma resposta inconsistente do fornecedor não pode atualizar o catálogo já salvo.
    from io import BytesIO
    from unittest.mock import patch
    from fastapi import HTTPException
    from Chronos_loja.loja_api.app import main as loja
    prior = save.read_bytes()
    for bad in (b"not-json", b"{}", b'{"items":[{"tenant_id":"vizinha","kind":"sale"}]}'):
        with patch.object(loja, "urlopen", return_value=BytesIO(bad)):
            try:
                loja.import_from_stock("demo")
            except HTTPException as error:
                assert error.status_code == 502
            else:
                raise AssertionError("Resposta inválida do Estoque foi aceita.")
        assert save.read_bytes() == prior
    print("OK: indisponibilidade, isolamento, importação, reimportação e catálogo após reinício.")


if __name__ == "__main__":
    if sys.argv[1:] == ["--isolado"]:
        if ROOT != Path.cwd() or ROOT.parent != Path(tempfile.gettempdir()).resolve() or not ROOT.name.startswith("loja-stock-"):
            raise SystemExit("Use a pasta temporária criada pelo teste.")
        exercise()
    else:
        from Chronos_loja.exportar_piloto import FILES
        with tempfile.TemporaryDirectory(prefix="loja-stock-") as temp:
            sandbox = Path(temp)
            for name in FILES:
                target = sandbox / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT/name, target)
            subprocess.run([sys.executable, "-IB", str(sandbox / Path(__file__).relative_to(ROOT)),
                            "--isolado"], cwd=sandbox, check=True)
