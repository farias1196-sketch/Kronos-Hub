"""Atualiza uma instalação fictícia da primeira revisão pública para o checkout atual."""
from io import BytesIO
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parent
BASE = "970a8ac42a9886beb5f2bb0b49cae7b8b80c3066"


def checkout(ref, dest):
    archive = subprocess.check_output(["git", "-C", str(ROOT), "archive", "--format=zip", ref])
    with ZipFile(BytesIO(archive)) as bundle:
        bundle.extractall(dest)


def exercise(mode):
    from init_preview import initialize_env
    initialize_env()
    from fastapi.testclient import TestClient
    from chronos_auth.token import create_token
    from Chronos_stock.stock_api.app.main import app as stock
    from Chronos_loja.loja_api.app import main as loja
    from unittest.mock import patch

    token = create_token(member_id="m", user_id="u", user_name="Pessoa de teste",
                         tenant_id="demo", tenant_slug="demo", role="ADMIN",
                         permissions=["loja.store.manage", "stock.products.manage"])
    headers = {"Authorization": "Bearer " + token}
    with TestClient(stock, headers=headers) as inventory, TestClient(loja.app, headers=headers) as shop:
        if mode == "antes":
            assert shop.get("/shop/config").status_code == 200
            response = inventory.post("/stock/items", json={"name":"Mapa fictício", "sku":"FIC-ATUAL",
                "kind":"sale", "category":"Oficina", "family":"Cartografia", "quantity":9})
            assert response.status_code == 200
        items = inventory.get("/stock/items").json()["items"]
        assert len(items) == 1 and items[0]["quantity"] == 9 and items[0]["sku"] == "FIC-ATUAL"
        with patch.object(loja, "stock_items", return_value=items):
            imported = shop.post("/shop/products/import-from-stock")
            assert imported.status_code == 200
            result = imported.json()
            assert result["imported"] == (1 if mode == "antes" else 0)
            product = result["products"][0]
            assert product["id"] == "demo:oficina:cartografia"
            if mode == "antes":
                update = shop.patch("/shop/products/" + product["id"], json={"published":True,
                    "variant_prices":{items[0]["id"]:{"sale_price":14.75, "sellable":True}}})
                assert update.status_code == 200
            else:
                assert product["published"] and product["variants"][0]["sale_price"] == 14.75
                response = shop.get("/public/demo/catalog")
                assert response.status_code == 200, response.status_code
                catalog = response.json()["products"]
                assert catalog[0]["id"] == product["id"]


def main():
    with tempfile.TemporaryDirectory(prefix="chronos-upgrade-") as temp:
        before, after = [Path(temp) / n for n in ("antes", "depois")]
        checkout(BASE, before)
        checkout("HEAD", after)
        for mode, root in [("antes", before), ("depois", after)]:
            if mode == "depois":
                shutil.copy2(before / ".env", after / ".env")
                shutil.copytree(before / ".local", after / ".local")
            # Exercita somente os módulos da revisão em uso.
            subprocess.run([sys.executable, "-IB", str(Path(__file__).resolve()), mode], cwd=root, check=True)
        assert (before / ".env").read_bytes() == (after / ".env").read_bytes()
    print("Atualização preservou configuração, saldo, ID do produto, publicação e preço editado.")


if __name__ == "__main__":
    if len(sys.argv) == 1:
        main()
    else:
        cwd = Path.cwd().resolve()
        if (sys.argv[1:] != [cwd.name] or cwd.name not in {"antes", "depois"} or
            cwd.parent.parent != Path(tempfile.gettempdir()).resolve() or not cwd.parent.name.startswith("chronos-upgrade-")):
            raise SystemExit("Use o diretório temporário do verificador.")
        sys.path.insert(0, str(cwd))
        exercise(cwd.name)
