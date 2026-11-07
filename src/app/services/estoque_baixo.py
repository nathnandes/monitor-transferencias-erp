import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.database.models import (
    Empresa,
    EstoqueBaixoAvisado,
    ParametrosEstoqueBaixo,
    Produto,
    Usuario,
    VendaDia,
)
from app.services import atividades
from app.services import excecoes_cobertura as excecoes
from app.services.estoque import JanelaVendas, _base, _media_vendas, descricao_item

logger = get_logger(__name__)

JANELA_ATRASO = timedelta(hours=3)
DIAS_PADRAO = 7
JANELA_PADRAO = 30
PRODUTOS_NA_MENSAGEM = 40
_HORARIO = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class ParametrosInvalidos(ValueError):
    pass


def parametros(db: Session) -> ParametrosEstoqueBaixo | None:
    return db.get(ParametrosEstoqueBaixo, 1)


def salvar_parametros(
    db: Session,
    *,
    ativo: bool,
    dias_cobertura: int,
    dias_por_empresa: dict[int, int],
    janela_dias: int,
    horarios: list[str],
    usuario: Usuario,
) -> ParametrosEstoqueBaixo:
    if not 1 <= dias_cobertura <= 365:
        raise ParametrosInvalidos("Os dias de venda vão de 1 a 365.")
    if not 7 <= janela_dias <= 180:
        raise ParametrosInvalidos("O giro é medido em 7 a 180 dias.")
    unicos = sorted({h.strip() for h in horarios})
    if not 1 <= len(unicos) <= 6 or any(not _HORARIO.match(h) for h in unicos):
        raise ParametrosInvalidos("Informe de 1 a 6 horários no formato HH:MM, como 08:00.")
    if any(not 1 <= d <= 365 for d in dias_por_empresa.values()):
        raise ParametrosInvalidos("Os dias de venda de cada loja vão de 1 a 365.")
    existentes = set(db.scalars(select(Empresa.id).where(Empresa.id.in_(list(dias_por_empresa)))))
    if set(dias_por_empresa) - existentes:
        raise ParametrosInvalidos("Loja não encontrada.")

    p = parametros(db) or ParametrosEstoqueBaixo(id=1)
    p.ativo = ativo
    p.dias_cobertura = dias_cobertura
    p.dias_por_empresa = {str(k): v for k, v in sorted(dias_por_empresa.items())}
    p.janela_dias = janela_dias
    p.horarios = unicos
    p.usuario_id = usuario.id
    p.usuario_nome = usuario.nome_exibicao
    p.updated_at = func.now()
    db.add(p)
    db.flush()
    db.refresh(p)
    return p


def dias_da_loja(p: ParametrosEstoqueBaixo, empresa_id: int) -> int:
    return int(p.dias_por_empresa.get(str(empresa_id), p.dias_cobertura))


@dataclass(frozen=True)
class ProdutoBaixo:
    id_produto: str
    id_subproduto: str
    descricao: str | None
    disponivel: Decimal
    media: Decimal
    minimo: Decimal


def lojas_que_vendem(db: Session, janela: JanelaVendas) -> list[Empresa]:
    ids = select(VendaDia.empresa_id).where(
        VendaDia.dia.between(janela.inicio, janela.fim), VendaDia.notas > 0
    )
    return list(
        db.scalars(
            select(Empresa)
            .where(Empresa.ativo.is_(True), Empresa.id.in_(ids))
            .order_by(Empresa.codigo)
        )
    )


def produtos_baixos(
    db: Session, empresa: Empresa, dias: int, janela: JanelaVendas
) -> list[ProdutoBaixo]:
    saldos = _base(empresa.id).subquery("saldos")
    media = _media_vendas(janela, empresa.id)
    disponivel = func.greatest(func.coalesce(saldos.c.saldo_disponivel, 0), 0)
    minimo = media.c.media * dias
    linhas = db.execute(
        select(
            saldos.c.id_produto,
            saldos.c.id_subproduto,
            descricao_item(),
            disponivel,
            media.c.media,
            minimo,
        )
        .join(
            media,
            (media.c.id_produto == saldos.c.id_produto)
            & (media.c.id_subproduto == saldos.c.id_subproduto),
        )
        .outerjoin(
            Produto,
            (Produto.id_produto == saldos.c.id_produto)
            & (Produto.id_subproduto == saldos.c.id_subproduto),
        )
        .where(
            media.c.media > 0,
            disponivel < minimo,
            ~excecoes.em_excecao(empresa.id, saldos.c.id_produto, saldos.c.id_subproduto),
        )
        .order_by((disponivel / media.c.media).asc(), media.c.media.desc(), saldos.c.id_subproduto)
    ).all()
    return [
        ProdutoBaixo(prod, sub, desc, Decimal(disp), Decimal(med), Decimal(mini))
        for prod, sub, desc, disp, med, mini in linhas
    ]


@dataclass
class SituacaoLoja:
    empresa: Empresa
    dias: int
    baixos: list[ProdutoBaixo]


def situacao(db: Session, hoje: date) -> list[SituacaoLoja]:
    p = parametros(db) or ParametrosEstoqueBaixo(
        dias_cobertura=DIAS_PADRAO, janela_dias=JANELA_PADRAO, dias_por_empresa={}
    )
    janela = JanelaVendas.ultimos(p.janela_dias, hoje)
    resultado = []
    for loja in lojas_que_vendem(db, janela):
        dias = dias_da_loja(p, loja.id)
        resultado.append(SituacaoLoja(loja, dias, produtos_baixos(db, loja, dias, janela)))
    return resultado


def _quantidade(valor: Decimal) -> str:
    arredondado = valor.quantize(Decimal("0.01"), ROUND_HALF_UP).normalize()
    texto = f"{arredondado:f}"
    return texto.replace(".", ",")


def _linha(b: ProdutoBaixo) -> str:
    descricao = f" {b.descricao}" if b.descricao else ""
    return (
        f"• {b.id_subproduto}{descricao}: tem {_quantidade(b.disponivel)},"
        f" mínimo {_quantidade(b.minimo)} ({_quantidade(b.media)}/dia)"
    )


def _horario_vencido(p: ParametrosEstoqueBaixo, agora: datetime, tz: ZoneInfo) -> datetime | None:
    local = agora.astimezone(tz)
    candidatos = []
    for dia in (local.date() - timedelta(days=1), local.date()):
        for h in p.horarios:
            hora, minuto = (int(x) for x in h.split(":"))
            candidatos.append(datetime.combine(dia, time(hora, minuto), tzinfo=tz))
    vencidos = [c for c in candidatos if c <= agora]
    if not vencidos:
        return None
    ultimo = max(vencidos)
    if agora - ultimo > JANELA_ATRASO:
        return None
    if p.ultima_execucao is not None and p.ultima_execucao >= ultimo:
        return None
    return ultimo


def processar(db: Session, agora: datetime, tz: ZoneInfo) -> int | None:
    p = db.scalars(
        select(ParametrosEstoqueBaixo)
        .where(ParametrosEstoqueBaixo.id == 1)
        .with_for_update(skip_locked=True)
    ).first()
    if p is None or not p.ativo or _horario_vencido(p, agora, tz) is None:
        return None
    p.ultima_execucao = agora

    janela = JanelaVendas.ultimos(p.janela_dias, agora.astimezone(tz).date())
    avisos = 0
    for loja in lojas_que_vendem(db, janela):
        dias = dias_da_loja(p, loja.id)
        baixos = produtos_baixos(db, loja, dias, janela)
        atuais = {(b.id_produto, b.id_subproduto) for b in baixos}
        anteriores = {
            (prod, sub)
            for prod, sub in db.execute(
                select(EstoqueBaixoAvisado.id_produto, EstoqueBaixoAvisado.id_subproduto).where(
                    EstoqueBaixoAvisado.empresa_id == loja.id
                )
            )
        }

        for prod, sub in anteriores - atuais:
            db.execute(
                delete(EstoqueBaixoAvisado).where(
                    EstoqueBaixoAvisado.empresa_id == loja.id,
                    EstoqueBaixoAvisado.id_produto == prod,
                    EstoqueBaixoAvisado.id_subproduto == sub,
                )
            )
        novos = [b for b in baixos if (b.id_produto, b.id_subproduto) not in anteriores]
        for b in novos:
            db.add(
                EstoqueBaixoAvisado(
                    empresa_id=loja.id,
                    id_produto=b.id_produto,
                    id_subproduto=b.id_subproduto,
                    avisado_em=agora,
                )
            )
        if not novos:
            continue
        linhas = [_linha(b) for b in novos[:PRODUTOS_NA_MENSAGEM]]
        if len(novos) > PRODUTOS_NA_MENSAGEM:
            linhas.append(f"… e mais {len(novos) - PRODUTOS_NA_MENSAGEM}")
        plural = "produto" if len(novos) == 1 else "produtos"
        atividades.registrar(
            db,
            "estoque_baixo",
            f"{loja.nome}: {len(novos)} {plural} com estoque baixo",
            usuario_nome="Sistema",
            valores={
                "loja": loja.nome,
                "quantidade": str(len(novos)),
                "total": str(len(baixos)),
                "dias": f"{dias} dias",
                "produtos": "\n".join(linhas),
            },
            empresas=[loja.id],
            agora=agora,
        )
        avisos += 1
    db.flush()
    logger.info("estoque baixo: %d avisos", avisos)
    return avisos
