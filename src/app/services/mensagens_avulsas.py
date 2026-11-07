from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.database.models import (
    AlertaDestino,
    MensagemAvulsa,
    ModeloMensagemAvulsa,
    Notificacao,
    Usuario,
)
from app.notifications import variaveis_mensagem
from app.notifications.outbox import VALIDADE, enfileirar_mensagem

LIMITE_TEXTO = 4000

TOLERANCIA_PASSADO = timedelta(minutes=5)
MAXIMO_ANTECEDENCIA = timedelta(days=366)
LIMITE_LISTA = 50
TODOS_OS_DIAS = (1, 2, 3, 4, 5, 6, 7)


class MensagemInvalida(ValueError):
    pass


class MensagemNaoEncontrada(LookupError):
    pass


class NadaParaCancelar(Exception):
    pass


@dataclass(frozen=True)
class EnvioDestino:
    destino_id: int | None
    destino_nome: str
    canal: str
    status: str
    enviada_em: datetime | None
    ultimo_erro: str | None


def _destinos(db: Session, ids: Sequence[int]) -> list[AlertaDestino]:
    unicos = list(dict.fromkeys(ids))
    if not unicos:
        raise MensagemInvalida("Escolha pelo menos um destino.")
    encontrados = {
        d.id: d for d in db.scalars(select(AlertaDestino).where(AlertaDestino.id.in_(unicos)))
    }
    faltando = [i for i in unicos if i not in encontrados]
    if faltando:
        raise MensagemInvalida(f"Destino inexistente: {', '.join(map(str, faltando))}.")
    desligados = [encontrados[i].nome for i in unicos if not encontrados[i].ativo]
    if desligados:
        raise MensagemInvalida(f"Destino desligado: {', '.join(desligados)}.")
    return [encontrados[i] for i in unicos]


def _hora_marcada(agendada_para: datetime | None, agora: datetime, tz: ZoneInfo) -> datetime:
    if agendada_para is None:
        return agora
    if agendada_para.tzinfo is None:
        agendada_para = agendada_para.replace(tzinfo=tz)
    if agendada_para < agora - TOLERANCIA_PASSADO:
        raise MensagemInvalida("A data e hora marcadas já passaram.")
    if agendada_para - agora > MAXIMO_ANTECEDENCIA:
        raise MensagemInvalida("Marque no máximo um ano à frente.")
    return max(agendada_para, agora)


def proximo_envio(
    horario: time, dias_semana: Sequence[int], depois_de: datetime, tz: ZoneInfo
) -> datetime:
    dia = depois_de.astimezone(tz).date()
    for _ in range(8):
        candidato = datetime.combine(dia, horario, tzinfo=tz)
        if dia.isoweekday() in dias_semana and candidato > depois_de:
            return candidato
        dia += timedelta(days=1)
    raise MensagemInvalida("Marque pelo menos um dia da semana.")


def _dias(dias_semana: Sequence[int]) -> list[int]:
    dias = sorted(set(dias_semana))
    if not dias:
        raise MensagemInvalida("Marque pelo menos um dia da semana.")
    if any(d not in TODOS_OS_DIAS for d in dias):
        raise MensagemInvalida("Dia da semana inválido (use 1 = segunda ... 7 = domingo).")
    return dias


def criar(
    db: Session,
    *,
    texto: str,
    destinos: Sequence[int],
    agendada_para: datetime | None,
    usuario: Usuario,
    agora: datetime,
    tz: ZoneInfo,
    horario: time | None = None,
    dias_semana: Sequence[int] = TODOS_OS_DIAS,
) -> MensagemAvulsa:
    texto = texto.strip()
    if not texto:
        raise MensagemInvalida("Escreva a mensagem.")
    if len(texto) > LIMITE_TEXTO:
        raise MensagemInvalida(f"A mensagem passa de {LIMITE_TEXTO} caracteres.")
    try:
        variaveis_mensagem.validar(texto)
    except variaveis_mensagem.VariavelDesconhecida as erro:
        raise MensagemInvalida(str(erro)) from None
    lista = _destinos(db, destinos)

    if horario is not None:
        horario = horario.replace(second=0, microsecond=0, tzinfo=None)
        dias = _dias(dias_semana)
        quando = proximo_envio(horario, dias, agora, tz)
    else:
        dias = []
        quando = _hora_marcada(agendada_para, agora, tz)

    mensagem = MensagemAvulsa(
        texto=texto,
        agendada_para=quando,
        horario=horario,
        dias_semana=dias,
        destinos=[d.id for d in lista],
        criada_por_id=usuario.id,
        criada_por_nome=usuario.nome_exibicao[:100],
        created_at=agora,
    )
    db.add(mensagem)
    if horario is None:
        enfileirar_mensagem(db, mensagem, lista, quando)
    db.flush()
    return mensagem


def gerar_repetidas(db: Session, agora: datetime, tz: ZoneInfo) -> int:
    vencidas = db.scalars(
        select(MensagemAvulsa)
        .where(
            MensagemAvulsa.horario.is_not(None),
            MensagemAvulsa.cancelada_em.is_(None),
            MensagemAvulsa.agendada_para <= agora,
        )
        .with_for_update(skip_locked=True)
    ).all()
    enfileiradas = 0
    for mensagem in vencidas:
        assert mensagem.horario is not None
        momento = mensagem.agendada_para
        if agora - momento <= VALIDADE:
            ativos = [
                d
                for d in db.scalars(
                    select(AlertaDestino).where(AlertaDestino.id.in_(mensagem.destinos))
                )
                if d.ativo
            ]
            enfileirar_mensagem(db, mensagem, ativos, momento)
            enfileiradas += len(ativos)
        mensagem.agendada_para = proximo_envio(mensagem.horario, mensagem.dias_semana, agora, tz)
    db.flush()
    return enfileiradas


def previa(db: Session, texto: str, agora: datetime, tz: ZoneInfo) -> str:
    try:
        variaveis_mensagem.validar(texto)
    except variaveis_mensagem.VariavelDesconhecida as erro:
        raise MensagemInvalida(str(erro)) from None
    return variaveis_mensagem.preencher(db, texto, agora, tz)


def listar(db: Session, limite: int = LIMITE_LISTA) -> list[MensagemAvulsa]:
    return list(
        db.scalars(
            select(MensagemAvulsa)
            .options(selectinload(MensagemAvulsa.notificacoes).selectinload(Notificacao.destino))
            .order_by(
                (
                    MensagemAvulsa.horario.is_not(None) & MensagemAvulsa.cancelada_em.is_(None)
                ).desc(),
                MensagemAvulsa.agendada_para.desc(),
                MensagemAvulsa.id.desc(),
            )
            .limit(limite)
        )
    )


def envios(mensagem: MensagemAvulsa) -> list[EnvioDestino]:
    notificacoes = mensagem.notificacoes
    if mensagem.horario is not None and notificacoes:
        ultimo = max(n.created_at for n in notificacoes)
        notificacoes = [n for n in notificacoes if n.created_at == ultimo]
    return [
        EnvioDestino(
            destino_id=n.destino_id,
            destino_nome=n.destino.nome if n.destino is not None else "Padrão",
            canal=n.canal,
            status=n.status,
            enviada_em=n.enviada_em,
            ultimo_erro=n.ultimo_erro,
        )
        for n in notificacoes
    ]


def cancelar(db: Session, mensagem_id: int, agora: datetime) -> MensagemAvulsa:
    mensagem = db.get(MensagemAvulsa, mensagem_id)
    if mensagem is None:
        raise MensagemNaoEncontrada(mensagem_id)
    pendentes = db.scalars(
        select(Notificacao)
        .where(Notificacao.mensagem_id == mensagem_id, Notificacao.status == "PENDENTE")
        .with_for_update(of=Notificacao)
    ).all()
    repetida_ativa = mensagem.horario is not None
    if mensagem.cancelada_em is not None or not (pendentes or repetida_ativa):
        raise NadaParaCancelar(mensagem_id)
    mensagem.cancelada_em = agora
    for n in pendentes:
        n.status = "DESCARTADA"
        n.ultimo_erro = "mensagem cancelada"
    db.flush()
    return mensagem


LIMITE_NOME_MODELO = 80


class ModeloNaoEncontrado(LookupError):
    pass


def listar_modelos(db: Session) -> list[ModeloMensagemAvulsa]:
    return list(db.scalars(select(ModeloMensagemAvulsa).order_by(ModeloMensagemAvulsa.nome)))


def salvar_modelo(db: Session, *, nome: str, texto: str, usuario: Usuario) -> ModeloMensagemAvulsa:
    nome = " ".join(nome.split())
    texto = texto.strip()
    if not nome:
        raise MensagemInvalida("Dê um nome ao modelo.")
    if len(nome) > LIMITE_NOME_MODELO:
        raise MensagemInvalida(f"O nome passa de {LIMITE_NOME_MODELO} caracteres.")
    if not texto:
        raise MensagemInvalida("Escreva a mensagem.")
    if len(texto) > LIMITE_TEXTO:
        raise MensagemInvalida(f"A mensagem passa de {LIMITE_TEXTO} caracteres.")
    try:
        variaveis_mensagem.validar(texto)
    except variaveis_mensagem.VariavelDesconhecida as erro:
        raise MensagemInvalida(str(erro)) from None

    modelo = db.scalar(
        select(ModeloMensagemAvulsa)
        .where(func.lower(ModeloMensagemAvulsa.nome) == nome.lower())
        .with_for_update()
    )
    if modelo is None:
        modelo = ModeloMensagemAvulsa(nome=nome, texto=texto, atualizado_por="")
        db.add(modelo)
    modelo.nome = nome
    modelo.texto = texto
    modelo.atualizado_por = usuario.nome_exibicao[:100]
    db.flush()
    return modelo


def excluir_modelo(db: Session, modelo_id: int) -> None:
    modelo = db.get(ModeloMensagemAvulsa, modelo_id)
    if modelo is None:
        raise ModeloNaoEncontrado(modelo_id)
    db.delete(modelo)
    db.flush()
