import argparse
import json
import sys
from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.anomalias.registros import RegistroTransferencia
from app.anomalias.sintetico import EMPRESAS, gerar
from app.core.config import Settings, get_settings
from app.database.models import AnomaliaExecucao, Empresa, Transferencia, TransferenciaItem
from app.database.simulacao import (
    AVISO,
    PREFIXO_SIMULADO,
    AmbienteNaoPermitido,
    aplicar_seed,
    limpar_simulados,
    verificar_ambiente,
)
from app.dominio import coi as catalogo_coi
from app.dominio.transferencias import STATUS_PENDENTE, STATUS_PROCESSADA

PREFIXO_DEMO = f"{PREFIXO_SIMULADO}IA-"
_RAW = {"simulado": True, "aviso": AVISO}


def _transferencia(
    r: RegistroTransferencia, numero: int, codigos: dict[str, str], ids: dict[str, int]
) -> Transferencia:
    origem, destino = codigos[r.origem], codigos[r.destino]
    com_entrada = r.recebida_em is not None
    transferencia = Transferencia(
        id_erp=f"{PREFIXO_DEMO}{numero:06d}",
        empresa_origem_id=ids[origem],
        empresa_destino_id=ids[destino],
        empresa_entrada_id=ids[destino] if com_entrada else None,
        status=STATUS_PROCESSADA if com_entrada else STATUS_PENDENTE,
        data_criacao=r.emitida_em,
        data_processamento=r.recebida_em,
        quantidade_itens=r.quantidade_itens,
        coi=str(min(catalogo_coi.COIS_SAIDA[int(origem)])),
        coi_entrada=str(catalogo_coi.coi_entrada_esperado(int(origem), int(destino)))
        if com_entrada
        else None,
        numero_nota=f"9{numero:05d}",
        valor_total=Decimal(str(r.valor)),
        problemas_coi=[],
        entre_empresas=True,
        raw_data=_RAW,
    )

    transferencia.itens = [
        TransferenciaItem(
            id_produto_erp=f"{PREFIXO_DEMO}PRODUTO",
            descricao_produto="Produto Demonstração",
            quantidade_solicitada=Decimal(str(r.quantidade_enviada)),
            quantidade_processada=Decimal(str(r.quantidade_recebida))
            if r.quantidade_recebida is not None
            else None,
            valor_total=Decimal(str(r.valor)),
            raw_data=_RAW,
        )
    ]
    return transferencia


def _apagar_demo(db: Session) -> int:
    apagadas = db.scalars(
        delete(Transferencia)
        .where(Transferencia.id_erp.startswith(PREFIXO_DEMO))
        .returning(Transferencia.id)
    ).all()
    db.execute(delete(AnomaliaExecucao))
    return len(apagadas)


def aplicar(db: Session, settings: Settings, agora: datetime, semente: int = 42) -> int:
    aplicar_seed(db, agora)
    _apagar_demo(db)
    tz = ZoneInfo(settings.tz)
    ontem = agora.astimezone(tz).date() - timedelta(days=1)
    conjunto = gerar(semente, fim=datetime.combine(ontem, time(23, 59), tz))

    codigos = {nome: f"{i:02d}" for i, nome in enumerate(EMPRESAS, start=1)}
    ids = {
        codigo: id_
        for id_, codigo in db.execute(
            select(Empresa.id, Empresa.codigo).where(Empresa.id_erp.startswith(PREFIXO_SIMULADO))
        )
    }
    db.add_all(
        _transferencia(r, n, codigos, ids) for n, r in enumerate(conjunto.registros, start=1)
    )
    db.flush()
    return len(conjunto.registros)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dados sinteticos do detector de anomalias")
    parser.add_argument("comando", choices=["seed", "limpar"])
    parser.add_argument("--semente", type=int, default=42)
    args = parser.parse_args(argv)

    settings = get_settings()
    try:
        verificar_ambiente(settings)
    except AmbienteNaoPermitido as exc:
        print(f"RECUSADO: {exc}", file=sys.stderr)
        return 2

    from app.database.session import SessionLocal

    with SessionLocal() as db, db.begin():
        if args.comando == "seed":
            agora = datetime.now(ZoneInfo(settings.tz))
            saida = {"transferencias": aplicar(db, settings, agora, args.semente)}
        else:
            saida = {"transferencias": _apagar_demo(db)}
            limpar_simulados(db)
    print(json.dumps(saida))
    return 0


if __name__ == "__main__":
    sys.exit(main())
