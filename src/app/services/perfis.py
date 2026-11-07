from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.models import PerfilAcesso, Usuario
from app.dominio.abas import MODULOS_DE_PERFIL, PAI, TELAS_INICIAIS, VISOES, Aba, modulo_da_aba
from app.dominio.modulos import Modulo

NOME_MAX = 60
DESCRICAO_MAX = 200


class PerfilInvalidoError(ValueError):
    pass


class PerfilEmUsoError(ValueError):
    pass


@dataclass(frozen=True)
class DadosPerfil:
    nome: str
    descricao: str | None
    modulos: list[Modulo]
    abas: list[Aba]
    tela_inicial: str | None


def validar(
    nome: str,
    descricao: str | None,
    modulos: Iterable[str],
    abas: Iterable[str],
    tela_inicial: str | None,
) -> DadosPerfil:
    nome = " ".join(nome.split())
    if not nome:
        raise PerfilInvalidoError("Informe o nome do perfil.")
    if len(nome) > NOME_MAX:
        raise PerfilInvalidoError(f"Nome com no máximo {NOME_MAX} caracteres.")
    descricao = " ".join((descricao or "").split()) or None
    if descricao and len(descricao) > DESCRICAO_MAX:
        raise PerfilInvalidoError(f"Descrição com no máximo {DESCRICAO_MAX} caracteres.")

    try:
        do_perfil = {Modulo(m) for m in modulos}
        marcadas = {Aba(a) for a in abas}
    except ValueError:
        raise PerfilInvalidoError("Módulo ou aba desconhecido.") from None
    if Modulo.ADMINISTRACAO in do_perfil:
        raise PerfilInvalidoError("Administração acompanha o papel ADMIN: não entra no perfil.")
    for aba in marcadas:
        if modulo_da_aba(aba) not in do_perfil:
            raise PerfilInvalidoError(f"A aba {aba} precisa do módulo {modulo_da_aba(aba)}.")
        pai = PAI.get(aba)
        if pai is not None and pai not in marcadas:
            raise PerfilInvalidoError(f"A aba {aba} fica dentro de {pai}: marque as duas.")
    for modulo, visoes in VISOES.items():
        if modulo in do_perfil and not marcadas.intersection(visoes):
            raise PerfilInvalidoError(f"O módulo {modulo} precisa de ao menos uma aba.")

    if tela_inicial is not None:
        if tela_inicial not in TELAS_INICIAIS:
            raise PerfilInvalidoError("Tela inicial desconhecida.")
        if tela_inicial not in {*do_perfil, *marcadas}:
            raise PerfilInvalidoError("A tela inicial precisa estar liberada no perfil.")

    return DadosPerfil(
        nome=nome,
        descricao=descricao,
        modulos=[m for m in Modulo if m in do_perfil],
        abas=[a for a in Aba if a in marcadas],
        tela_inicial=tela_inicial,
    )


def listar(session: Session) -> list[tuple[PerfilAcesso, int]]:
    usuarios = (
        select(Usuario.perfil_id, func.count().label("n"))
        .where(Usuario.perfil_id.is_not(None))
        .group_by(Usuario.perfil_id)
        .subquery()
    )
    linhas = session.execute(
        select(PerfilAcesso, func.coalesce(usuarios.c.n, 0))
        .outerjoin(usuarios, usuarios.c.perfil_id == PerfilAcesso.id)
        .order_by(func.lower(PerfilAcesso.nome))
    )
    return [(p, n) for p, n in linhas]


def usuarios_do_perfil(session: Session, perfil: PerfilAcesso) -> int:
    return session.scalar(select(func.count()).where(Usuario.perfil_id == perfil.id)) or 0


def _nome_livre(session: Session, nome: str, *, exceto: int | None = None) -> None:
    consulta = select(PerfilAcesso.id).where(func.lower(PerfilAcesso.nome) == nome.lower())
    if exceto is not None:
        consulta = consulta.where(PerfilAcesso.id != exceto)
    if session.scalar(consulta) is not None:
        raise PerfilEmUsoError("Já existe um perfil com esse nome.")


def _aplicar(perfil: PerfilAcesso, dados: DadosPerfil) -> None:
    perfil.nome = dados.nome
    perfil.descricao = dados.descricao
    perfil.modulos = [str(m) for m in dados.modulos]
    perfil.abas = [str(a) for a in dados.abas]
    perfil.tela_inicial = dados.tela_inicial


def criar(session: Session, dados: DadosPerfil) -> PerfilAcesso:
    _nome_livre(session, dados.nome)
    perfil = PerfilAcesso()
    _aplicar(perfil, dados)
    session.add(perfil)
    session.flush()
    return perfil


def atualizar(session: Session, perfil: PerfilAcesso, dados: DadosPerfil) -> None:
    _nome_livre(session, dados.nome, exceto=perfil.id)
    _aplicar(perfil, dados)
    session.flush()


def excluir(session: Session, perfil: PerfilAcesso) -> None:
    n = usuarios_do_perfil(session, perfil)
    if n:
        raise PerfilEmUsoError(
            f"O perfil tem {n} usuário(s). Troque o perfil deles antes de excluir."
        )
    session.delete(perfil)
    session.flush()


@dataclass(frozen=True)
class Acesso:
    modulos: frozenset[Modulo]
    abas: list[Aba] | None
    tela_inicial: str | None


def abas_do_perfil(perfil: PerfilAcesso) -> list[Aba]:

    validos = {a.value for a in Aba}
    return [Aba(a) for a in perfil.abas if a in validos]


def modulos_do_perfil(perfil: PerfilAcesso) -> frozenset[Modulo]:
    return frozenset(Modulo(m) for m in perfil.modulos if m in MODULOS_DE_PERFIL)
