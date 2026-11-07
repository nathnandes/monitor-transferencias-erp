import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.models import (
    SEVERIDADES_EVENTO,
    AlertaConfiguracao,
    AlertaDestino,
    Empresa,
    ModeloMensagem,
    Notificacao,
)
from app.notifications.modelos import (
    MODELOS,
    DefinicaoModelo,
    ModeloInvalido,
    validar,
)
from app.notifications.modelos import previa as previa_texto
from app.rules.catalogo import CATALOGO, DefinicaoRegra
from app.rules.config import carregar

_CHAT_ID = re.compile(r"^(-?\d{1,20}|@[A-Za-z][A-Za-z0-9_]{4,31})$")

_NUMERO_DIGITADO = re.compile(r"^\+?[\d\s().-]+$")
CANAIS = ("telegram", "whatsapp")


def normalizar_numero_whatsapp(numero: str) -> str | None:
    numero = numero.strip()
    if not _NUMERO_DIGITADO.match(numero):
        return None
    digitos = re.sub(r"\D", "", numero)
    if not numero.startswith("+") and len(digitos) in (10, 11):
        digitos = "55" + digitos
    if not 11 <= len(digitos) <= 15:
        return None
    return digitos


class ConfigInvalida(ValueError):
    pass


class DestinoNaoEncontrado(LookupError):
    pass


class DestinoEmUso(Exception):
    pass


@dataclass
class RegraConfigurada:
    definicao: DefinicaoRegra
    ativo: bool
    campos: list[str]
    destinos: list[AlertaDestino]
    personalizada: bool


def listar_regras(db: Session) -> list[RegraConfigurada]:
    config = carregar(db)
    salvas = set(db.scalars(select(AlertaConfiguracao.regra)))
    resultado = []
    for nome, definicao in CATALOGO.items():
        c = config.regra(nome)
        resultado.append(RegraConfigurada(definicao, c.ativo, c.campos, c.destinos, nome in salvas))
    return resultado


def listar_destinos(db: Session) -> list[AlertaDestino]:
    return list(db.scalars(select(AlertaDestino).order_by(AlertaDestino.nome)))


def _destinos(db: Session, ids: Sequence[int]) -> list[AlertaDestino]:
    destinos = list(db.scalars(select(AlertaDestino).where(AlertaDestino.id.in_(ids))))
    faltando = set(ids) - {d.id for d in destinos}
    if faltando:
        raise ConfigInvalida(f"Destino não encontrado: {', '.join(map(str, sorted(faltando)))}.")
    return destinos


def salvar_regra(
    db: Session,
    regra: str,
    *,
    ativo: bool,
    campos: Sequence[str],
    destinos_ids: Sequence[int],
) -> None:
    definicao = CATALOGO.get(regra)
    if definicao is None:
        raise LookupError(regra)
    conhecidos = [c.chave for c in definicao.campos]
    desconhecidos = set(campos) - set(conhecidos)
    if desconhecidos:
        lista = ", ".join(sorted(desconhecidos))
        raise ConfigInvalida(f"Campo desconhecido para esta regra: {lista}.")
    linha = db.get(AlertaConfiguracao, regra) or AlertaConfiguracao(regra=regra)
    linha.ativo = ativo
    linha.campos = [c for c in conhecidos if c in set(campos)]
    linha.destinos = _destinos(db, destinos_ids)
    db.add(linha)
    db.flush()


def restaurar_padrao(db: Session, regra: str) -> None:
    if regra not in CATALOGO:
        raise LookupError(regra)
    linha = db.get(AlertaConfiguracao, regra)
    if linha is not None:
        db.delete(linha)
        db.flush()


def _validar_chat(canal: str, chat_id: str | None) -> str | None:
    chat = (chat_id or "").strip() or None
    if canal not in CANAIS:
        raise ConfigInvalida("Canal inválido: use telegram ou whatsapp.")
    if canal == "whatsapp":
        if chat is None:
            raise ConfigInvalida("Informe o número do WhatsApp que recebe os alertas.")
        numero = normalizar_numero_whatsapp(chat)
        if numero is None:
            raise ConfigInvalida(
                "Número do WhatsApp inválido: use DDI, DDD e número (ex.: +55 11 98765-4321)."
            )
        return numero
    if chat is not None and not _CHAT_ID.match(chat):
        raise ConfigInvalida(
            "Chat do Telegram inválido: use o número do chat (ex.: -1001234567890) "
            "ou o @ de um canal público."
        )
    return chat


def _validar_destino(
    db: Session,
    nome: str,
    canal: str,
    chat_id: str | None,
    severidade_minima: str,
    empresas: Sequence[int],
) -> tuple[str, str | None, list[int]]:
    nome = " ".join(nome.split())
    if not nome:
        raise ConfigInvalida("Informe o nome do destino.")
    chat = _validar_chat(canal, chat_id)
    if severidade_minima not in SEVERIDADES_EVENTO:
        raise ConfigInvalida("Severidade mínima inválida.")
    ids = sorted(set(empresas))
    if ids:
        existentes = set(db.scalars(select(Empresa.id).where(Empresa.id.in_(ids))))
        if set(ids) - existentes:
            raise ConfigInvalida("Empresa não encontrada.")
    return nome, chat, ids


def _gravar_destino(db: Session, destino: AlertaDestino) -> AlertaDestino:
    try:
        with db.begin_nested():
            db.add(destino)
            db.flush()
    except IntegrityError:
        raise ConfigInvalida("Já existe um destino com esse nome.") from None
    return destino


def criar_destino(
    db: Session,
    *,
    nome: str,
    chat_id: str | None,
    severidade_minima: str,
    empresas: Sequence[int],
    ativo: bool,
    canal: str = "telegram",
) -> AlertaDestino:
    nome, chat, ids = _validar_destino(db, nome, canal, chat_id, severidade_minima, empresas)
    return _gravar_destino(
        db,
        AlertaDestino(
            nome=nome,
            canal=canal,
            chat_id=chat,
            severidade_minima=severidade_minima,
            empresas=ids,
            ativo=ativo,
        ),
    )


def editar_destino(
    db: Session,
    destino_id: int,
    *,
    nome: str,
    chat_id: str | None,
    severidade_minima: str,
    empresas: Sequence[int],
    ativo: bool,
    canal: str = "telegram",
) -> AlertaDestino:
    destino = db.get(AlertaDestino, destino_id)
    if destino is None:
        raise DestinoNaoEncontrado(destino_id)
    nome, chat, ids = _validar_destino(db, nome, canal, chat_id, severidade_minima, empresas)
    if canal != destino.canal and _usos(db, destino_id):
        raise ConfigInvalida(
            "Este destino já recebeu alertas: para mudar o canal, cadastre outro destino."
        )
    destino.canal = canal
    destino.nome, destino.chat_id, destino.severidade_minima = nome, chat, severidade_minima
    destino.empresas, destino.ativo = ids, ativo
    return _gravar_destino(db, destino)


def _usos(db: Session, destino_id: int) -> int:
    usos = db.scalar(
        select(func.count()).select_from(Notificacao).where(Notificacao.destino_id == destino_id)
    )
    return usos or 0


def excluir_destino(db: Session, destino_id: int) -> None:
    destino = db.get(AlertaDestino, destino_id)
    if destino is None:
        raise DestinoNaoEncontrado(destino_id)
    if _usos(db, destino_id):
        raise DestinoEmUso(destino_id)
    db.delete(destino)
    db.flush()


@dataclass
class ModeloConfigurado:
    definicao: DefinicaoModelo
    texto: str
    personalizado: bool
    usuario_nome: str | None
    atualizado_em: datetime | None


def listar_modelos(db: Session) -> list[ModeloConfigurado]:
    salvos = {m.chave: m for m in db.scalars(select(ModeloMensagem))}
    resultado = []
    for chave, definicao in MODELOS.items():
        salvo = salvos.get(chave)
        resultado.append(
            ModeloConfigurado(
                definicao,
                salvo.texto if salvo else definicao.padrao,
                salvo is not None,
                salvo.usuario_nome if salvo else None,
                salvo.updated_at if salvo else None,
            )
        )
    return resultado


def _definicao_modelo(chave: str) -> DefinicaoModelo:
    definicao = MODELOS.get(chave)
    if definicao is None:
        raise LookupError(chave)
    return definicao


def salvar_modelo(
    db: Session, chave: str, texto: str, *, usuario_id: int | None, usuario_nome: str
) -> None:
    definicao = _definicao_modelo(chave)
    try:
        texto = validar(definicao, texto)
    except ModeloInvalido as erro:
        raise ConfigInvalida(str(erro)) from None
    linha = db.get(ModeloMensagem, chave)
    if texto == definicao.padrao:
        if linha is not None:
            db.delete(linha)
            db.flush()
        return
    if linha is None:
        linha = ModeloMensagem(chave=chave)
        db.add(linha)
    linha.texto = texto
    linha.usuario_id = usuario_id
    linha.usuario_nome = usuario_nome
    linha.updated_at = func.now()
    db.flush()


def restaurar_modelo(db: Session, chave: str) -> None:
    _definicao_modelo(chave)
    linha = db.get(ModeloMensagem, chave)
    if linha is not None:
        db.delete(linha)
        db.flush()


def previa_modelo(chave: str, texto: str) -> str:
    definicao = _definicao_modelo(chave)
    try:
        return previa_texto(definicao, texto)
    except ModeloInvalido as erro:
        raise ConfigInvalida(str(erro)) from None
