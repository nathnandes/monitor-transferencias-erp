from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.database.models import Empresa, Sincronizacao, Transferencia
from app.dominio.transferencias import STATUS_ERRO, STATUS_PENDENTE
from app.rules.catalogo import CATALOGO, montar_corpo
from app.services import anomalias, limites_pendencia, notas_empresa_errada
from app.services.comum import condicao_entre_empresas
from app.services.frescor import frescor
from app.services.pipeline import condicao_situacao_coi

NIVEL_SEVERIDADE = {"INFO": 0, "WARNING": 1, "ERROR": 2, "CRITICAL": 3}

DIAS_ALERTA_ANOMALIA = 30


@dataclass(frozen=True)
class Ocorrencia:
    regra: str
    chave: str
    severidade: str
    titulo: str
    mensagem: str
    empresa_id: int | None = None
    transferencia_id: int | None = None
    detalhes: dict[str, Any] = field(default_factory=dict)


Regra = Callable[[Session, datetime], list[Ocorrencia]]


def _ocorrencia(
    regra: str,
    chave: str,
    severidade: str,
    titulo: str,
    valores: dict[str, str],
    *,
    empresas_ids: list[int | None],
    empresa_id: int | None = None,
    transferencia_id: int | None = None,
    extras: dict[str, Any] | None = None,
) -> Ocorrencia:
    padrao = CATALOGO[regra].campos_padrao
    return Ocorrencia(
        regra=regra,
        chave=chave,
        severidade=severidade,
        titulo=titulo,
        mensagem=montar_corpo(regra, valores, padrao),
        empresa_id=empresa_id,
        transferencia_id=transferencia_id,
        detalhes={
            **(extras or {}),
            "campos": {k: v for k, v in valores.items() if v},
            "empresas_ids": sorted({e for e in empresas_ids if e is not None}),
        },
    )


def _hora_local(momento: datetime) -> str:
    return momento.astimezone(ZoneInfo(get_settings().tz)).strftime("%d/%m %H:%M")


def _rotulo_empresa(empresa: Empresa) -> str:
    return f"{empresa.codigo} - {empresa.nome}"


def _numero(t: Transferencia) -> str:
    return f"NF {t.numero_nota}" if t.numero_nota else t.id_erp


def _valor(valor: Decimal | None) -> str:
    if valor is None:
        return ""
    texto = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


def _campos_transferencia(t: Transferencia) -> dict[str, str]:
    destino = _rotulo_empresa(t.empresa_destino) if t.empresa_destino else "não é uma das empresas"
    return {
        "nota": _numero(t),
        "origem": _rotulo_empresa(t.empresa_origem),
        "destino": destino,
        "emitida_em": _hora_local(t.data_criacao) if t.data_criacao else "",
        "emitida_por": t.usuario_emissao or "",
        "valor": _valor(t.valor_total),
        "itens": str(t.quantidade_itens) if t.quantidade_itens is not None else "",
    }


def _empresas(t: Transferencia) -> list[int | None]:
    return [t.empresa_origem_id, t.empresa_destino_id]


def _transferencias_com_status(db: Session, status: str) -> list[Transferencia]:
    return list(
        db.scalars(
            select(Transferencia)
            .options(
                joinedload(Transferencia.empresa_origem),
                joinedload(Transferencia.empresa_destino),
            )
            .where(Transferencia.status == status, condicao_entre_empresas())
            .order_by(Transferencia.id)
        )
    )


def transferencia_erro(db: Session, agora: datetime) -> list[Ocorrencia]:
    return [
        _ocorrencia(
            "transferencia_erro",
            f"transferencia_erro:{t.id}",
            "ERROR",
            f"Transferência {t.id_erp} com erro",
            {**_campos_transferencia(t), "status": t.status or ""},
            empresas_ids=_empresas(t),
            empresa_id=t.empresa_origem_id,
            transferencia_id=t.id,
            extras={"id_erp": t.id_erp, "status": t.status},
        )
        for t in _transferencias_com_status(db, STATUS_ERRO)
    ]


def _horas(delta: timedelta) -> str:
    horas = int(delta.total_seconds() // 3600)
    return f"{horas}h" if horas < 48 else f"{horas // 24} dias"


def transferencia_atrasada(db: Session, agora: datetime) -> list[Ocorrencia]:
    limites = limites_pendencia.limites(db)
    ocorrencias = []
    for t in _transferencias_com_status(db, STATUS_PENDENTE):
        if t.data_criacao is None:
            continue
        idade = agora - t.data_criacao
        if idade <= limites.atencao:
            continue
        ocorrencias.append(
            _ocorrencia(
                "transferencia_atrasada",
                f"transferencia_atrasada:{t.id}",
                "CRITICAL" if idade > limites.critico else "WARNING",
                f"Transferência {_numero(t)} sem entrada no destino há {_horas(idade)}",
                {**_campos_transferencia(t), "sem_entrada_ha": _horas(idade)},
                empresas_ids=_empresas(t),
                empresa_id=t.empresa_origem_id,
                transferencia_id=t.id,
                extras={"id_erp": t.id_erp, "pendente_desde": t.data_criacao.isoformat()},
            )
        )
    return ocorrencias


def sincronizacao_erro(db: Session, agora: datetime) -> list[Ocorrencia]:

    ordem = (
        func.row_number()
        .over(
            partition_by=(Sincronizacao.empresa_id, Sincronizacao.tipo),
            order_by=(Sincronizacao.inicio.desc(), Sincronizacao.id.desc()),
        )
        .label("ordem")
    )
    recentes = (
        select(Sincronizacao.id, ordem).where(Sincronizacao.empresa_id.is_not(None)).subquery()
    )
    ultimas = db.scalars(
        select(Sincronizacao)
        .join(recentes, recentes.c.id == Sincronizacao.id)
        .join(Empresa, Empresa.id == Sincronizacao.empresa_id)
        .options(joinedload(Sincronizacao.empresa))
        .where(recentes.c.ordem == 1, Empresa.ativo.is_(True), Sincronizacao.status == "erro")
        .order_by(Empresa.codigo, Sincronizacao.tipo)
    )
    ocorrencias = []
    for s in ultimas:
        assert s.empresa is not None
        ocorrencias.append(
            _ocorrencia(
                "sincronizacao_erro",
                f"sincronizacao_erro:{s.empresa_id}:{s.tipo}",
                "ERROR",
                f"Sincronização de {s.tipo} da empresa {s.empresa.codigo} falhou",
                {
                    "empresa": _rotulo_empresa(s.empresa),
                    "tipo": s.tipo,
                    "inicio": _hora_local(s.inicio),
                    "erro": (s.mensagem_erro or "")[:500],
                },
                empresas_ids=[s.empresa_id],
                empresa_id=s.empresa_id,
                extras={"sincronizacao_id": s.id, "tipo": s.tipo},
            )
        )
    return ocorrencias


def _duracao(delta: timedelta) -> str:
    minutos = int(delta.total_seconds() // 60)
    return f"{minutos} min" if minutos < 60 else _horas(delta)


def sincronizacao_parada(db: Session, agora: datetime) -> list[Ocorrencia]:
    ocorrencias = []
    for f in frescor(db, get_settings(), agora):
        if f.situacao not in ("ATRASADA", "PARADA") or f.ultima_conclusao is None:
            continue
        ocorrencias.append(
            _ocorrencia(
                "sincronizacao_parada",
                f"sincronizacao_parada:{f.tipo}",
                "CRITICAL" if f.situacao == "PARADA" else "WARNING",
                f"Sincronização de {f.tipo} parada há {_duracao(agora - f.ultima_conclusao)}",
                {
                    "ultima_conclusao": _hora_local(f.ultima_conclusao),
                    "intervalo": f"{f.intervalo_segundos // 60 or 1} min",
                    "orientacao": (
                        "Os dados do ERP no painel estão ficando velhos. Confira se o worker "
                        "de sincronização está rodando e o log dele."
                    ),
                },
                empresas_ids=[],
                extras={"tipo": f.tipo, "ultima_conclusao": f.ultima_conclusao.isoformat()},
            )
        )
    return ocorrencias


def transferencia_coi_errado(db: Session, agora: datetime) -> list[Ocorrencia]:
    transferencias = db.scalars(
        select(Transferencia)
        .options(
            joinedload(Transferencia.empresa_origem),
            joinedload(Transferencia.empresa_destino),
        )
        .where(condicao_situacao_coi("ERRADO"))
        .order_by(Transferencia.id)
    )
    ocorrencias = []
    for t in transferencias:
        ocorrencias.append(
            _ocorrencia(
                "transferencia_coi_errado",
                f"transferencia_coi_errado:{t.id}",
                "CRITICAL",
                f"Transferência {_numero(t)} com COI ERRADO",
                {
                    **_campos_transferencia(t),
                    "coi_saida": t.coi or "—",
                    "coi_entrada": t.coi_entrada or "",
                    "problemas": "\n".join(f"• {p}" for p in t.problemas_coi),
                    "orientacao": "Confira a operação no ERP e corrija a nota.",
                },
                empresas_ids=[*_empresas(t), t.empresa_entrada_id],
                empresa_id=t.empresa_origem_id,
                transferencia_id=t.id,
                extras={
                    "id_erp": t.id_erp,
                    "coi": t.coi,
                    "coi_entrada": t.coi_entrada,
                    "problemas": list(t.problemas_coi),
                },
            )
        )
    return ocorrencias


def nota_empresa_errada(db: Session, agora: datetime) -> list[Ocorrencia]:
    ocorrencias = []
    for x in notas_empresa_errada.listar(db):
        nota = f"NF {x.numero}" if x.numero else f"documento {x.id_planilha}"
        ocorrencias.append(
            _ocorrencia(
                "nota_empresa_errada",
                f"nota_empresa_errada:{x.empresa.id}:{x.id_planilha}",
                "CRITICAL",
                f"{nota} emitida na empresa {x.empresa.codigo} para a empresa {x.destino.codigo}",
                {
                    "nota": nota,
                    "origem": _rotulo_empresa(x.empresa),
                    "destino": _rotulo_empresa(x.destino),
                    "coi": f"{x.coi} - {x.operacao}" if x.operacao else str(x.coi),
                    "orientacao": (
                        f"Quem fica com a mercadoria é a empresa {x.destino.codigo}: cancele "
                        f"a nota e emita de novo na empresa {x.destino.codigo}."
                    ),
                    "emitida_em": _hora_local(x.momento) if x.momento else x.dia.strftime("%d/%m"),
                    "emitida_por": x.usuario or "",
                    "valor": _valor(-x.valor if x.valor is not None else None),
                    "itens": str(x.itens),
                },
                empresas_ids=[x.empresa.id, x.destino.id],
                empresa_id=x.empresa.id,
                extras={"id_planilha": x.id_planilha, "coi": x.coi, "dia": x.dia.isoformat()},
            )
        )
    return ocorrencias


def transferencia_anomala(db: Session, agora: datetime) -> list[Ocorrencia]:
    ocorrencias = []
    for a in anomalias.para_alerta(db, agora - timedelta(days=DIAS_ALERTA_ANOMALIA)):
        t = a.transferencia
        ocorrencias.append(
            _ocorrencia(
                "transferencia_anomala",
                f"transferencia_anomala:{t.id}",
                "WARNING",
                f"Transferência {_numero(t)} fora do padrão",
                {
                    **{k: v for k, v in _campos_transferencia(t).items() if k != "emitida_por"},
                    "motivos": "\n".join(f"• {m['texto']}" for m in a.motivos),
                    "orientacao": (
                        "Fora do padrão não significa erro nem fraude. Confira a nota e registre "
                        "uma tratativa."
                    ),
                },
                empresas_ids=_empresas(t),
                empresa_id=t.empresa_origem_id,
                transferencia_id=t.id,
                extras={"id_erp": t.id_erp, "score": a.score, "limiar": a.limiar},
            )
        )
    return ocorrencias


REGRAS: dict[str, Regra] = {
    "transferencia_erro": transferencia_erro,
    "transferencia_atrasada": transferencia_atrasada,
    "sincronizacao_erro": sincronizacao_erro,
    "transferencia_coi_errado": transferencia_coi_errado,
    "sincronizacao_parada": sincronizacao_parada,
    "nota_empresa_errada": nota_empresa_errada,
    "transferencia_anomala": transferencia_anomala,
}
