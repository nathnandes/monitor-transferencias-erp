import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import CursorResult, Delete, Select, delete, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.database.models import (
    Empresa,
    Evento,
    Sincronizacao,
    Transferencia,
    TransferenciaItem,
    Venda,
    VendaDia,
    VendaItem,
)
from app.dominio import coi as catalogo_coi
from app.dominio.canais_venda import CANAIS

AMBIENTE_SIMULADO = "development"
PREFIXO_SIMULADO = "DEMO-"
ORIGEM_EVENTO = "seed_desenvolvimento"
AVISO = "DADOS FICTICIOS - gerados pelo seed local, NAO vieram do ERP"


AMBIENTES_PERMITIDOS = ("development", "test")


class AmbienteNaoPermitido(RuntimeError):
    pass


def verificar_ambiente(settings: Settings) -> None:
    informados = {
        nome: valor.strip().lower()
        for nome, valor in (("APP_ENV", settings.app_env), ("ENVIRONMENT", settings.environment))
        if valor and valor.strip()
    }
    permitidos = ", ".join(AMBIENTES_PERMITIDOS)
    if not informados:
        raise AmbienteNaoPermitido(
            f"APP_ENV/ENVIRONMENT nao informados: defina um deles como {permitidos}."
        )
    recusados = {n: v for n, v in informados.items() if v not in AMBIENTES_PERMITIDOS}
    if recusados:
        detalhe = ", ".join(f"{n}={v!r}" for n, v in recusados.items())
        raise AmbienteNaoPermitido(
            f"{detalhe}: dados simulados so podem ser gravados em ambiente "
            f"{permitidos}. Nunca rode o seed contra producao ou homologacao."
        )


EMPRESAS = ["01", "02", "03", "04", "05", "06"]


PRODUTOS = {
    1: ("Caixa de papelao media", "UN"),
    2: ("Fita adesiva transparente", "UN"),
    3: ("Arroz tipo 1 a granel", "KG"),
    4: ("Detergente neutro 500 ml", "UN"),
    5: ("Cafe torrado a granel", "KG"),
    6: ("Copo descartavel 200 ml", "UN"),
    7: ("Papel toalha interfolhado", "UN"),
    8: ("Acucar cristal a granel", "KG"),
    9: ("Sabonete liquido 1 l", "UN"),
    10: ("Etiqueta adesiva 100x50", "UN"),
}

H = timedelta(hours=1)
M = timedelta(minutes=1)

TOTAL_TRANSFERENCIAS = 36

PENDENTES = {1, 2, 3, 15, 27}
ERROS = {6, 8, 12, 20, 33}

DIVERGENTES = {5, 11, 18, 26}


COI_FORA_DO_PADRAO = {4}

ENTRADA_SEM_COI = {22}
MENSAGENS_ERRO = [
    "Falha simulada: saldo insuficiente na origem",
    "Falha simulada: destino bloqueado para recebimento",
    "Falha simulada: produto inativo no destino",
    "Falha simulada: tempo limite na integracao",
    "Falha simulada: divergencia de cadastro fiscal",
]


@dataclass(frozen=True)
class ItemSim:
    produto: int
    solicitada: Decimal
    processada: Decimal | None


@dataclass(frozen=True)
class TransferenciaSim:
    numero: int
    origem: str
    destino: str
    status: str
    criada_ha: timedelta
    processada_ha: timedelta | None
    itens: tuple[ItemSim, ...]
    cenario: str
    coi: str | None = None
    coi_entrada: str | None = None
    problemas_coi: tuple[str, ...] = ()
    entre_empresas: bool = True
    extra: dict[str, Any] = field(default_factory=dict)


def _cenario_pendente(idade: timedelta) -> str:
    if idade < 24 * H:
        return "pendente recente"
    if idade < 48 * H:
        return "pendente atrasada (> 24h)"
    return "pendente muito atrasada (> 48h)"


def _montar_transferencia(n: int) -> TransferenciaSim:

    i_origem = (n - 1) % 6
    i_destino = (i_origem + 1 + ((n - 1) // 6) % 5) % 6

    criada_ha = (1 + (n - 1) * 20) * H

    status = "PENDENTE" if n in PENDENTES else "ERRO" if n in ERROS else "PROCESSADA"

    itens = []
    for k in range(1 + (n * 3) % 5):
        produto = 1 + (n * 7 + k * 3) % 10
        base = Decimal((n + k * 5) % 9 + 1)
        solicitada = base * Decimal("2.5") if PRODUTOS[produto][1] == "KG" else base * 6
        if status != "PROCESSADA":
            processada = None
        elif n in DIVERGENTES and k == 0:
            processada = solicitada - 1
        else:
            processada = solicitada
        itens.append(ItemSim(produto, solicitada, processada))

    n_origem, n_destino = i_origem + 1, i_destino + 1
    saida_de = n_destino if n in COI_FORA_DO_PADRAO else n_origem
    coi: str | None = str(min(catalogo_coi.COIS_SAIDA[saida_de]))
    coi_entrada: str | None = None

    extra: dict[str, Any] = {}
    if status == "PROCESSADA":
        processada_ha = criada_ha - (1 + n % 3) * H
        if n in ENTRADA_SEM_COI:
            cenario = "entrada sem COI"
        else:
            coi_entrada = str(catalogo_coi.coi_entrada_esperado(n_origem, n_destino))
            if n in COI_FORA_DO_PADRAO:
                cenario = "saida com COI de outra empresa (outro tipo)"
            elif n in DIVERGENTES:
                cenario = "divergente: processada menor que a solicitada"
            else:
                cenario = "normal"
    elif status == "PENDENTE":
        processada_ha = None
        cenario = _cenario_pendente(criada_ha)
    else:
        processada_ha = None
        cenario = "erro simulado"
        extra["erro"] = MENSAGENS_ERRO[sorted(ERROS).index(n) % len(MENSAGENS_ERRO)]

    conferencia = catalogo_coi.conferir_transferencia(
        origem=str(n_origem),
        coi_saida=coi,
        destino=str(n_destino),
        coi_entrada=coi_entrada,
        empresa_entrada=str(n_destino) if status == "PROCESSADA" else None,
        entrada_registrada=status == "PROCESSADA",
    )
    return TransferenciaSim(
        numero=n,
        origem=EMPRESAS[i_origem],
        destino=EMPRESAS[i_destino],
        status=status,
        criada_ha=criada_ha,
        processada_ha=processada_ha,
        itens=tuple(itens),
        cenario=cenario,
        coi=coi,
        coi_entrada=coi_entrada,
        problemas_coi=tuple(conferencia.problemas),
        entre_empresas=conferencia.entre_empresas,
        extra=extra,
    )


TRANSFERENCIAS = [_montar_transferencia(n) for n in range(1, TOTAL_TRANSFERENCIAS + 1)]


SINCRONIZACOES = [
    ("01", 15 * M, "sucesso", 6, 0, 1, 5, None),
    ("02", 14 * M, "sucesso", 6, 0, 0, 6, None),
    ("03", 13 * M, "parcial", 6, 0, 1, 4, "Aviso simulado: 1 registro com payload invalido"),
    ("04", 12 * M, "sucesso", 6, 1, 0, 5, None),
    ("05", 11 * M, "sucesso", 6, 0, 2, 4, None),
    ("06", 10 * M, "erro", 0, 0, 0, 0, "Falha simulada: tempo limite excedido"),
    ("01", 26 * H, "sucesso", 5, 1, 0, 4, None),
    ("02", 26 * H, "parcial", 5, 0, 1, 3, "Aviso simulado: resposta incompleta"),
    ("03", 26 * H, "sucesso", 5, 0, 0, 5, None),
    ("04", 26 * H, "erro", 0, 0, 0, 0, "Falha simulada: servico indisponivel"),
    ("05", 26 * H, "sucesso", 5, 1, 1, 3, None),
    ("06", 26 * H, "sucesso", 5, 0, 0, 5, None),
]


@dataclass(frozen=True)
class EventoSim:
    tipo: str
    severidade: str
    ocorreu_ha: timedelta
    transferencia: int | None = None
    empresa: str | None = None


def _montar_eventos() -> list[EventoSim]:
    eventos = []
    for t in TRANSFERENCIAS:
        if t.status == "ERRO":
            eventos.append(EventoSim("transferencia_erro", "ERROR", t.criada_ha - 5 * M, t.numero))
        elif t.status == "PENDENTE":
            if t.criada_ha < 4 * H:
                tipo, severidade = "transferencia_pendente", "INFO"
            elif t.criada_ha < 24 * H:
                tipo, severidade = "transferencia_pendente_atrasada", "WARNING"
            else:
                tipo, severidade = "transferencia_pendente_atrasada", "CRITICAL"
            eventos.append(EventoSim(tipo, severidade, 5 * M, t.numero))
        elif t.processada_ha is None:
            continue
        elif t.numero in DIVERGENTES:
            eventos.append(
                EventoSim("transferencia_divergente", "WARNING", t.processada_ha, t.numero)
            )
        elif t.criada_ha < 7 * 24 * H:
            eventos.append(EventoSim("transferencia_processada", "INFO", t.processada_ha, t.numero))
    for codigo, ha, status, *_ in SINCRONIZACOES:
        if status == "erro":
            eventos.append(EventoSim("sincronizacao_falhou", "ERROR", ha, empresa=codigo))
        elif status == "parcial":
            eventos.append(EventoSim("sincronizacao_parcial", "WARNING", ha, empresa=codigo))
    return eventos


EVENTOS = _montar_eventos()


def id_erp_empresa(codigo: str) -> str:
    return f"{PREFIXO_SIMULADO}EMP-{codigo}"


def id_erp_transferencia(numero: int) -> str:
    return f"{PREFIXO_SIMULADO}TRF-{numero:04d}"


def _hash(dados: Any) -> str:
    normalizado = json.dumps(dados, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(normalizado.encode()).hexdigest()


def _decimal_ou_none(valor: Decimal | None) -> str | None:
    return None if valor is None else str(valor)


@dataclass
class ResultadoSeed:
    empresas_criadas: int = 0
    empresas_atualizadas: int = 0
    transferencias_criadas: int = 0
    transferencias_atualizadas: int = 0
    itens: int = 0
    sincronizacoes: int = 0
    eventos: int = 0
    vendas: int = 0


DIAS_VENDAS = 90
EMPRESAS_COM_VENDAS = ["01", "02", "03", "06"]


def _vendas_simuladas(codigo: str, dia: int) -> list[tuple[str, int, list[tuple[int, Decimal]]]]:
    notas = []
    for k, coi in enumerate(sorted(CANAIS)):
        for j in range(1 + (dia + k + int(codigo)) % 3):
            itens = [
                (1 + (dia * 7 + j * 3 + k + n) % len(PRODUTOS), Decimal(1 + (dia + j + n) % 5))
                for n in range(1 + (dia + j) % 3)
            ]
            notas.append((f"{PREFIXO_SIMULADO}VND-{codigo}-{dia:03d}-{coi}-{j}", coi, itens))
    return notas


def _preco_simulado(produto: int, coi: int) -> Decimal:
    return Decimal(8 + produto * 6) * (5 if coi == 3001 else 1)


def _upsert_empresas(db: Session, resultado: ResultadoSeed) -> dict[str, Empresa]:
    empresas = {}
    for codigo in EMPRESAS:
        id_erp = id_erp_empresa(codigo)
        empresa = db.scalar(
            select(Empresa).where(Empresa.id_erp == id_erp, Empresa.ambiente == AMBIENTE_SIMULADO)
        )
        if empresa is None:
            empresa = Empresa(id_erp=id_erp, ambiente=AMBIENTE_SIMULADO)
            db.add(empresa)
            resultado.empresas_criadas += 1
        else:
            resultado.empresas_atualizadas += 1
        empresa.codigo = codigo
        empresa.nome = f"Empresa Demonstração {codigo}"
        empresa.ativo = True
        empresas[codigo] = empresa
    db.flush()
    return empresas


def _itens(spec: TransferenciaSim) -> list[TransferenciaItem]:
    itens = []
    for item in spec.itens:
        nome, unidade = PRODUTOS[item.produto]
        codigo = f"DEMO{item.produto:03d}"
        raw = {
            "simulado": True,
            "aviso": AVISO,
            "produto": codigo,
            "unidade": unidade,
            "quantidade_solicitada": _decimal_ou_none(item.solicitada),
            "quantidade_processada": _decimal_ou_none(item.processada),
            "divergencia_simulada": (
                item.processada is not None and item.processada != item.solicitada
            ),
        }
        itens.append(
            TransferenciaItem(
                id_produto_erp=f"{PREFIXO_SIMULADO}PROD-{item.produto:03d}",
                codigo_produto=codigo,
                descricao_produto=f"Produto Demonstração {item.produto:03d} - {nome}",
                quantidade_solicitada=item.solicitada,
                quantidade_processada=item.processada,
                raw_data=raw,
            )
        )
    return itens


def _upsert_transferencias(
    db: Session, empresas: dict[str, Empresa], agora: datetime, resultado: ResultadoSeed
) -> dict[int, Transferencia]:
    transferencias = {}
    for spec in TRANSFERENCIAS:
        origem = empresas[spec.origem]
        id_erp = id_erp_transferencia(spec.numero)
        transferencia = db.scalar(
            select(Transferencia).where(
                Transferencia.empresa_origem_id == origem.id,
                Transferencia.id_erp == id_erp,
            )
        )
        if transferencia is None:
            transferencia = Transferencia(id_erp=id_erp, empresa_origem=origem)
            db.add(transferencia)
            resultado.transferencias_criadas += 1
        else:
            resultado.transferencias_atualizadas += 1

        itens = _itens(spec)
        raw = {
            "simulado": True,
            "aviso": AVISO,
            "origem_dados": ORIGEM_EVENTO,
            "cenario": spec.cenario,
            "origem": spec.origem,
            "destino": spec.destino,
            "status": spec.status,
            "coi": spec.coi,
            "coi_entrada": spec.coi_entrada,
            "itens": [i.raw_data for i in itens],
            **spec.extra,
        }
        transferencia.empresa_destino = empresas[spec.destino]
        transferencia.status = spec.status
        transferencia.coi = spec.coi
        transferencia.coi_entrada = spec.coi_entrada
        transferencia.empresa_entrada = empresas[spec.destino] if spec.coi_entrada else None
        transferencia.problemas_coi = list(spec.problemas_coi)
        transferencia.entre_empresas = spec.entre_empresas
        transferencia.data_criacao = agora - spec.criada_ha
        transferencia.data_processamento = (
            agora - spec.processada_ha if spec.processada_ha is not None else None
        )
        transferencia.quantidade_itens = len(itens)
        transferencia.raw_data = raw

        transferencia.hash_payload = _hash(raw)

        transferencia.itens = itens
        resultado.itens += len(itens)
        transferencias[spec.numero] = transferencia
    db.flush()
    return transferencias


def _ids_empresas_simuladas(db: Session) -> list[int]:
    return list(
        db.scalars(
            select(Empresa.id).where(
                Empresa.ambiente == AMBIENTE_SIMULADO,
                Empresa.id_erp.startswith(PREFIXO_SIMULADO),
            )
        )
    )


def _linhas_apagadas(db: Session, stmt: Delete) -> int:
    resultado = db.execute(stmt)
    assert isinstance(resultado, CursorResult)
    return resultado.rowcount


def _apagar_vendas_simuladas(db: Session, ids_empresas: list[int]) -> int:

    vendas = _linhas_apagadas(
        db,
        delete(Venda).where(
            Venda.empresa_id.in_(ids_empresas), Venda.id_erp.startswith(PREFIXO_SIMULADO)
        ),
    )
    db.execute(delete(VendaDia).where(VendaDia.empresa_id.in_(ids_empresas)))
    return vendas


def _gravar_vendas(db: Session, empresas: dict[str, Empresa], agora: datetime) -> int:
    hoje = agora.date()
    total = 0
    for codigo in EMPRESAS_COM_VENDAS:
        empresa = empresas[codigo]
        for dia in range(DIAS_VENDAS):
            notas = _vendas_simuladas(codigo, dia)
            for id_erp, coi, itens in notas:
                valores = [_preco_simulado(produto, coi) * qtd for produto, qtd in itens]
                db.add(
                    Venda(
                        empresa=empresa,
                        id_erp=id_erp,
                        serie="1",
                        modelo="65" if coi == 8300 else "55",
                        coi=coi,
                        canal=CANAIS[coi],
                        data_venda=hoje - timedelta(days=dia),
                        momento=agora - timedelta(days=dia),
                        cancelada=False,
                        valor_total=sum(valores, Decimal(0)),
                        valor_desconto=Decimal(0),
                        quantidade_itens=len(itens),
                        sincronizado_em=agora,
                        itens=[
                            VendaItem(
                                sequencia=str(n),
                                id_produto=f"{PREFIXO_SIMULADO}PROD-{produto:03d}",
                                id_subproduto=f"{PREFIXO_SIMULADO}PROD-{produto:03d}",
                                descricao_produto=(
                                    f"Produto Demonstração {produto:03d} - {PRODUTOS[produto][0]}"
                                ),
                                quantidade=qtd,
                                valor_liquido=valor,
                                valor_desconto=Decimal(0),
                            )
                            for n, ((produto, qtd), valor) in enumerate(
                                zip(itens, valores, strict=True), start=1
                            )
                        ],
                    )
                )
            db.add(
                VendaDia(
                    empresa_id=empresa.id,
                    dia=hoje - timedelta(days=dia),
                    notas=len(notas),
                    sincronizado_em=agora,
                )
            )
            total += len(notas)
    db.flush()
    return total


def _apagar_historico_simulado(db: Session, ids_empresas: list[int]) -> tuple[int, int]:
    eventos = _linhas_apagadas(
        db,
        delete(Evento).where(Evento.origem == ORIGEM_EVENTO, Evento.empresa_id.in_(ids_empresas)),
    )
    sincronizacoes = _linhas_apagadas(
        db, delete(Sincronizacao).where(Sincronizacao.empresa_id.in_(ids_empresas))
    )
    return eventos, sincronizacoes


def aplicar_seed(db: Session, agora: datetime | None = None) -> ResultadoSeed:
    agora = agora or datetime.now(UTC)
    resultado = ResultadoSeed()

    empresas = _upsert_empresas(db, resultado)
    transferencias = _upsert_transferencias(db, empresas, agora, resultado)

    _apagar_historico_simulado(db, [e.id for e in empresas.values()])
    _apagar_vendas_simuladas(db, [e.id for e in empresas.values()])
    resultado.vendas = _gravar_vendas(db, empresas, agora)

    for codigo, ha, status, consultados, criados, atualizados, ignorados, erro in SINCRONIZACOES:
        db.add(
            Sincronizacao(
                empresa=empresas[codigo],
                tipo="transferencias",
                inicio=agora - ha,
                fim=agora - ha + timedelta(seconds=40),
                status=status,
                registros_consultados=consultados,
                registros_criados=criados,
                registros_atualizados=atualizados,
                registros_ignorados=ignorados,
                mensagem_erro=erro,
            )
        )
        resultado.sincronizacoes += 1

    for spec in EVENTOS:
        transferencia = transferencias.get(spec.transferencia) if spec.transferencia else None
        if transferencia is not None:
            empresa = transferencia.empresa_origem
            referencia = transferencia.id_erp
        else:
            assert spec.empresa is not None
            empresa = empresas[spec.empresa]
            referencia = None
        db.add(
            Evento(
                tipo=spec.tipo,
                origem=ORIGEM_EVENTO,
                severidade=spec.severidade,
                referencia_externa=referencia,
                payload={
                    "simulado": True,
                    "aviso": AVISO,
                    "mensagem": f"Evento simulado: {spec.tipo}",
                },
                data_evento=agora - spec.ocorreu_ha,
                empresa=empresa,
                transferencia=transferencia,
            )
        )
        resultado.eventos += 1

    db.flush()
    return resultado


@dataclass
class ResultadoLimpeza:
    empresas: int = 0
    transferencias: int = 0
    itens: int = 0
    sincronizacoes: int = 0
    eventos: int = 0
    vendas: int = 0


def limpar_simulados(db: Session) -> ResultadoLimpeza:
    ids_empresas = _ids_empresas_simuladas(db)
    resultado = ResultadoLimpeza()
    if not ids_empresas:
        return resultado

    resultado.eventos, resultado.sincronizacoes = _apagar_historico_simulado(db, ids_empresas)
    resultado.vendas = _apagar_vendas_simuladas(db, ids_empresas)

    filtro_transferencias = (
        Transferencia.id_erp.startswith(PREFIXO_SIMULADO),
        or_(
            Transferencia.empresa_origem_id.in_(ids_empresas),
            Transferencia.empresa_destino_id.in_(ids_empresas),
        ),
    )
    resultado.itens = (
        db.scalar(
            select(func.count())
            .select_from(TransferenciaItem)
            .join(Transferencia)
            .where(*filtro_transferencias)
        )
        or 0
    )

    resultado.transferencias = _linhas_apagadas(
        db, delete(Transferencia).where(*filtro_transferencias)
    )
    resultado.empresas = _linhas_apagadas(db, delete(Empresa).where(Empresa.id.in_(ids_empresas)))

    db.expire_all()
    return resultado


def resumo_simulados(db: Session) -> dict[str, Any]:
    ids_empresas = _ids_empresas_simuladas(db)
    transferencias = (
        select(Transferencia)
        .where(Transferencia.id_erp.startswith(PREFIXO_SIMULADO))
        .where(Transferencia.empresa_origem_id.in_(ids_empresas))
        .subquery()
    )
    sincronizacoes = select(Sincronizacao).where(Sincronizacao.empresa_id.in_(ids_empresas))
    eventos = select(Evento).where(
        Evento.origem == ORIGEM_EVENTO, Evento.empresa_id.in_(ids_empresas)
    )

    def contar(stmt: Select[*tuple[Any, ...]]) -> int:
        return db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    def agrupar(coluna: Any) -> dict[str, int]:
        return dict(
            db.execute(select(coluna, func.count()).group_by(coluna).order_by(coluna)).all()
        )

    sinc = sincronizacoes.subquery()
    evt = eventos.subquery()
    return {
        "empresas": len(ids_empresas),
        "transferencias": contar(select(transferencias.c.id)),
        "transferencias_por_status": agrupar(transferencias.c.status),
        "itens": contar(
            select(TransferenciaItem.id).where(
                TransferenciaItem.transferencia_id.in_(select(transferencias.c.id))
            )
        ),
        "sincronizacoes": contar(sincronizacoes),
        "sincronizacoes_por_status": agrupar(sinc.c.status),
        "eventos": contar(eventos),
        "eventos_por_severidade": agrupar(evt.c.severidade),
        "vendas": contar(
            select(Venda.id).where(
                Venda.empresa_id.in_(ids_empresas), Venda.id_erp.startswith(PREFIXO_SIMULADO)
            )
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.database.simulacao",
        description="Dados ficticios para desenvolvimento local (nunca usa ERP/ERPAPI).",
    )
    parser.add_argument("comando", choices=["seed", "limpar", "resumo"])
    args = parser.parse_args(argv)

    settings = get_settings()
    try:
        verificar_ambiente(settings)
    except AmbienteNaoPermitido as erro:
        print(f"RECUSADO: {erro}", file=sys.stderr)
        return 2

    from app.database.session import SessionLocal

    with SessionLocal() as db, db.begin():
        if args.comando == "seed":
            saida = vars(aplicar_seed(db))
        elif args.comando == "limpar":
            saida = vars(limpar_simulados(db))
        else:
            saida = resumo_simulados(db)

    print(json.dumps(saida, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
