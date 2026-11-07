import json
from pathlib import Path
from typing import Any

from app.main import create_app

DESTINO = Path(__file__).resolve().parents[3] / "frontend" / "openapi.json"


def gerar() -> dict[str, Any]:
    return create_app().openapi()


def serializar(contrato: dict[str, Any]) -> str:
    return json.dumps(contrato, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> int:
    DESTINO.write_text(serializar(gerar()), encoding="utf-8", newline="\n")
    print(f"contrato gravado em {DESTINO}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
