import csv
import io
from collections.abc import Iterable, Sequence
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi.responses import Response

LIMITE_EXPORTACAO = 50_000

Celula = str | int | Decimal | datetime | date | None


def formatar_celula(valor: Celula, tz: ZoneInfo) -> str:
    if valor is None:
        return ""
    if isinstance(valor, datetime):
        return valor.astimezone(tz).strftime("%d/%m/%Y %H:%M")
    if isinstance(valor, date):
        return valor.strftime("%d/%m/%Y")
    if isinstance(valor, Decimal):
        return format(valor.normalize(), "f").replace(".", ",")
    return str(valor)


def resposta_csv(
    nome: str,
    cabecalho: Sequence[str],
    linhas: Iterable[Sequence[Celula]],
    *,
    tz: ZoneInfo,
    total: int,
) -> Response:
    buffer = io.StringIO()
    escritor = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    escritor.writerow(cabecalho)
    for linha in linhas:
        escritor.writerow([formatar_celula(v, tz) for v in linha])
    arquivo = f"{nome}_{datetime.now(tz):%Y%m%d_%H%M}.csv"
    return Response(
        content="﻿" + buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{arquivo}"',
            "X-Total-Registros": str(total),
            "Access-Control-Expose-Headers": "Content-Disposition, X-Total-Registros",
        },
    )


TIPO_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def resposta_xlsx(nome: str, conteudo: bytes, *, tz: ZoneInfo) -> Response:
    arquivo = f"{nome}_{datetime.now(tz):%Y%m%d_%H%M}.xlsx"
    return Response(
        content=conteudo,
        media_type=TIPO_XLSX,
        headers={
            "Content-Disposition": f'attachment; filename="{arquivo}"',
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )
