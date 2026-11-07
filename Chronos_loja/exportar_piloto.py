"""Prepara, a partir do índice revisado, o piloto local de Loja e Estoque."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from Chronos_stock.exportar_piloto import FILES as STOCK_FILES, export

FILES = (*STOCK_FILES, "preview_http.py",
         "Chronos_loja/README.md", "Chronos_loja/requirements.txt",
         "Chronos_loja/exportar_piloto.py", "Chronos_loja/verificar_integracao.py",
         *(f"Chronos_loja/loja_api/app/{name}.py" for name in
           ("__init__", "main", "promotions", "easy_sales", "order_pdf", "quote_pdf")),
         *(f"chronos_storage/{name}.py" for name in
           ("loja_runtime", "nexus_runtime", "pdf_header", "product_extras",
            "product_variants", "quote_validity", "order_numbering", "client_display")))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destino", type=Path)
    export(parser.parse_args().destino, FILES)
