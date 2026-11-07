import argparse
import sys
from functools import partial

from sqlalchemy import select

from app.database.models import Empresa
from app.database.session import SessionLocal
from app.erp.errors import ErpApiError
from app.erp.servicos import (
    Nota,
    RegistroInvalidoError,
    ServicosErp,
    criar_servicos,
    mapear_nota,
)
from app.sync.comum import PoliticaRetry, agora_utc, com_retry
from app.sync.movimentos import _gravar_cabecalhos


def _reler_par(servicos: ServicosErp, origem: Empresa, destino: Empresa) -> tuple[int, int]:
    assert origem.id_erp is not None and destino.cnpj is not None
    politica = PoliticaRetry()
    gravadas, total, pagina = 0, 0, 1

    def avisar(exc: ErpApiError, tentativa: int) -> None:
        print(f"  pagina {pagina}, tentativa {tentativa}: {exc}")

    while True:
        resposta = com_retry(
            partial(servicos.pagina_notas_para_cnpj, origem.id_erp, destino.cnpj, pagina),
            politica,
            avisar,
        )
        total = resposta.total or total
        cabecalhos: list[tuple[str, bool, Nota | None]] = []
        for bruto in resposta.registros:
            try:
                nota = mapear_nota(bruto, servicos.fuso)
            except RegistroInvalidoError as exc:
                print(f"  cabecalho invalido: {exc}")
                continue
            if nota.id_empresa == origem.id_erp:
                cabecalhos.append((nota.id_planilha, True, nota))
        with SessionLocal() as db, db.begin():
            _gravar_cabecalhos(db, origem.id, cabecalhos, momento=agora_utc())
        gravadas += len(cabecalhos)
        if not resposta.registros or pagina >= servicos.max_paginas or gravadas >= total:
            return gravadas, total
        pagina += 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--empresa", help="Só as notas desta empresa (código do ERP).")
    args = parser.parse_args(argv)

    with SessionLocal() as db:
        empresas = list(
            db.scalars(
                select(Empresa)
                .where(Empresa.ativo.is_(True), Empresa.cnpj.is_not(None))
                .order_by(Empresa.codigo)
            )
        )
    servicos = criar_servicos()
    incompletos = 0
    try:
        for origem in empresas:
            if args.empresa and origem.id_erp != args.empresa:
                continue
            for destino in empresas:
                if destino.id == origem.id:
                    continue
                try:
                    gravadas, total = _reler_par(servicos, origem, destino)
                except ErpApiError as exc:
                    print(f"{origem.codigo} -> {destino.codigo}: FALHOU ({exc})")
                    incompletos += 1
                    continue
                aviso = "" if gravadas >= total else "  INCOMPLETO"
                incompletos += bool(aviso)
                print(f"{origem.codigo} -> {destino.codigo}: {gravadas} de {total}{aviso}")
    finally:
        servicos.close()
    return 1 if incompletos else 0


if __name__ == "__main__":
    sys.exit(main())
