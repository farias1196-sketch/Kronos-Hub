"""Seis exemplos inventados para a empresa demo da distribuição local."""
from pathlib import Path


def enable_demo_stock():
    directory = Path(__file__).resolve().parents[1] / ".local" / "stock"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / ".demo-on-first-start").touch()


def demo_items():
    examples = (
        ("sale", "Farol de papel", "FIC-V-001", 12, 3.25),
        ("sale", "Mapa lunar de bolso", "FIC-V-002", 7, 6.80),
        ("sale", "Marcador de constelações", "FIC-V-003", 18, 1.45),
        ("internal", "Gabarito de órbitas", "FIC-I-001", 4, 4.10),
        ("internal", "Suporte para mapas", "FIC-I-002", 9, 2.55),
        ("internal", "Régua de crateras", "FIC-I-003", 5, 3.70),
    )
    return [dict(id=sku.lower(), tenant_id="demo", name=name, kind=kind,
                 sku=sku, quantity=quantity, cost_price=cost)
            for kind, name, sku, quantity, cost in examples]


if __name__ == "__main__":
    enable_demo_stock()
    print("Exemplos habilitados para a primeira inicialização de um estoque vazio.")
