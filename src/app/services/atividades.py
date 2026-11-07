from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.core.requisicao import ip_cliente_atual
from app.database.models import Atividade, Notificacao, Usuario
from app.notifications.outbox import canal_do_destino
from app.rules.catalogo import CATALOGO

logger = get_logger(__name__)

TAMANHO_PAGINA_MAXIMO = 200


def registrar(
    db: Session,
    tipo: str,
    resumo: str,
    *,
    usuario: Usuario | None = None,
    usuario_nome: str | None = None,
    detalhe: str | None = None,
    valores: Mapping[str, str] | None = None,
    empresas: Sequence[int] = (),
    agora: datetime | None = None,
) -> Atividade:
    definicao = CATALOGO.get(tipo)
    if definicao is None or definicao.tipo == "alerta":
        raise ValueError(f"atividade desconhecida: {tipo}")

    from app.rules.config import carregar

    momento = agora or datetime.now(UTC)
    atividade = Atividade(
        tipo=tipo,
        usuario_id=usuario.id if usuario is not None else None,
        usuario_nome=(usuario.nome_exibicao if usuario else usuario_nome or "—")[:100],
        ip=ip_cliente_atual(),
        resumo=resumo[:300],
        detalhe=detalhe,
        valores=dict(valores or {}),
        empresas=sorted(set(empresas)),
        ocorrida_em=momento,
    )
    db.add(atividade)

    config = carregar(db)
    if config.regra(tipo).ativo:
        for destino in config.destinos_para(tipo, None, atividade.empresas):
            db.add(
                Notificacao(
                    atividade=atividade,
                    destino=destino,
                    canal=canal_do_destino(destino),
                    tipo="ATIVIDADE",
                    status="PENDENTE",
                    proxima_tentativa_em=momento,
                    created_at=momento,
                )
            )
    db.flush()
    logger.info("atividade %s: %s", tipo, atividade.resumo)
    return atividade


@dataclass
class PaginaAtividades:
    itens: list[Atividade]
    total: int


def listar(
    db: Session,
    *,
    tipo: str | None = None,
    usuario: str | None = None,
    pagina: int = 1,
    tamanho: int = 50,
) -> PaginaAtividades:
    filtros = []
    if tipo:
        filtros.append(Atividade.tipo == tipo)
    if usuario:
        filtros.append(Atividade.usuario_nome.ilike(f"%{usuario.strip()}%"))
    total = db.scalar(select(func.count()).select_from(Atividade).where(*filtros)) or 0
    itens = db.scalars(
        select(Atividade)
        .where(*filtros)
        .order_by(Atividade.ocorrida_em.desc(), Atividade.id.desc())
        .offset((pagina - 1) * tamanho)
        .limit(min(tamanho, TAMANHO_PAGINA_MAXIMO))
    ).all()
    return PaginaAtividades(list(itens), total)
