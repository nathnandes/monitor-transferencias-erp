import argparse
import getpass
import sys
from collections.abc import Callable

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.seguranca import SenhaFracaError, validar_senha
from app.database.models import Usuario
from app.services.admin_usuarios import criar_usuario_administrado
from app.services.auditoria import OrigemAuditoria
from app.services.autorizacao import PAPEL_ADMIN
from app.services.usuarios import (
    UsernameEmUsoError,
    UsuarioInvalidoError,
    buscar_por_username,
    normalizar_nome_exibicao,
    normalizar_username,
)

SAIDA_OK = 0
SAIDA_INVALIDO = 1
SAIDA_RECUSADO = 2
SAIDA_CANCELADO = 130


_CHAVE_LOCK = 7_310_001


def existe_admin_ativo(session: Session) -> bool:
    return (
        session.scalar(
            select(Usuario.id).where(Usuario.role == PAPEL_ADMIN, Usuario.ativo.is_(True)).limit(1)
        )
        is not None
    )


def executar(
    session: Session,
    *,
    ler: Callable[[str], str] = input,
    ler_senha: Callable[[str], str] = getpass.getpass,
    escrever: Callable[[str], None] = print,
) -> int:

    session.execute(text("SELECT pg_advisory_xact_lock(:chave)"), {"chave": _CHAVE_LOCK})
    if existe_admin_ativo(session):
        escrever(
            "Recusado: ja existe um ADMIN ativo. Crie outros usuarios pela API "
            "(/api/v1/admin/users) com esse ADMIN."
        )
        return SAIDA_RECUSADO

    try:
        username = normalizar_username(ler("Username: "))
        nome = normalizar_nome_exibicao(ler("Nome de exibicao: "))
    except UsuarioInvalidoError as erro:
        escrever(f"Invalido: {erro}")
        return SAIDA_INVALIDO
    if buscar_por_username(session, username) is not None:
        escrever(f"Recusado: username ja cadastrado: {username}")
        return SAIDA_INVALIDO

    senha = ler_senha("Senha: ")
    try:
        validar_senha(senha)
    except SenhaFracaError as erro:
        escrever("Senha fora da politica: " + "; ".join(erro.problemas))
        return SAIDA_INVALIDO
    if ler_senha("Confirme a senha: ") != senha:
        escrever("As senhas nao conferem.")
        return SAIDA_INVALIDO

    try:
        usuario = criar_usuario_administrado(
            session,
            ator=None,
            username=username,
            nome_exibicao=nome,
            senha=senha,
            role=PAPEL_ADMIN,
            must_change_password=False,
            origem=OrigemAuditoria.CLI,
        )
    except UsernameEmUsoError:
        escrever(f"Recusado: username ja cadastrado: {username}")
        return SAIDA_INVALIDO
    session.commit()
    escrever(f"ADMIN criado: {usuario.username} (id {usuario.id}).")
    return SAIDA_OK


def main(argv: list[str] | None = None) -> int:

    argparse.ArgumentParser(
        prog="python -m app.scripts.create_admin",
        description=(
            "Cria o primeiro ADMIN local. Username, nome e senha sao pedidos no "
            "terminal; a senha nunca e aceita por argumento."
        ),
    ).parse_args(argv)

    if not sys.stdin.isatty():
        print("Recusado: execute em um terminal interativo (a senha e digitada sem eco).")
        return SAIDA_RECUSADO

    from app.database.session import SessionLocal

    try:
        with SessionLocal() as session:
            return executar(session)
    except (KeyboardInterrupt, EOFError):
        print("\nCancelado. Nada foi gravado.")
        return SAIDA_CANCELADO


if __name__ == "__main__":
    sys.exit(main())
