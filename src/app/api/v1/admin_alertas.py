from datetime import UTC, datetime
from typing import Annotated, Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.orm import Session

from app.api.autorizacao import AdminDep, exigir_modulo
from app.api.deps import SessionDep
from app.api.schemas import RESPOSTAS_PROTEGIDAS, Erro
from app.api.schemas_config_alertas import (
    CampoAlerta,
    ConfiguracaoAlertas,
    DestinoAlerta,
    DestinoAlertaEntrada,
    EnvioMensagemAvulsa,
    MensagemAvulsaEntrada,
    MensagemAvulsaSaida,
    ModeloMensagemAlerta,
    ModeloMensagemAvulsaEntrada,
    ModeloMensagemAvulsaSaida,
    ModeloMensagemEntrada,
    PreviaMensagemEntrada,
    PreviaModelo,
    RegraAlertaConfig,
    RegraAlertaEntrada,
    VariavelModelo,
)
from app.core.config import get_settings
from app.core.logging_config import get_logger
from app.database.models import MensagemAvulsa
from app.dominio.modulos import Modulo
from app.notifications.modelos import MODELOS
from app.notifications.variaveis_mensagem import VARIAVEIS as VARIAVEIS_MENSAGEM
from app.rules.catalogo import CATALOGO
from app.services import atividades, mensagens_avulsas
from app.services import config_alertas as service

logger = get_logger(__name__)

router = APIRouter(
    prefix="/admin/alertas",
    tags=["admin"],
    dependencies=[Depends(exigir_modulo(Modulo.ADMINISTRACAO))],
    responses=RESPOSTAS_PROTEGIDAS,
)

Respostas = dict[int | str, dict[str, Any]]
_R404: Respostas = {404: {"model": Erro, "description": "Regra ou destino não encontrado."}}
_R422: Respostas = {422: {"model": Erro, "description": "Configuração inválida."}}

IdDestino = Annotated[int, Path(description="Id do destino.")]


def _configuracao(db: Session) -> ConfiguracaoAlertas:
    return ConfiguracaoAlertas(
        regras=[
            RegraAlertaConfig(
                regra=r.definicao.regra,
                tipo=r.definicao.tipo,
                nome=r.definicao.nome,
                descricao=r.definicao.descricao,
                ativo=r.ativo,
                personalizada=r.personalizada,
                campos_disponiveis=[
                    CampoAlerta(chave=c.chave, rotulo=c.rotulo, padrao=c.padrao)
                    for c in r.definicao.campos
                ],
                campos=r.campos,
                destinos=[d.id for d in r.destinos],
            )
            for r in service.listar_regras(db)
        ],
        destinos=[DestinoAlerta.model_validate(d) for d in service.listar_destinos(db)],
        modelos=[
            ModeloMensagemAlerta(
                chave=m.definicao.chave,
                nome=m.definicao.nome,
                grupo=m.definicao.grupo,
                descricao=m.definicao.descricao,
                variaveis=[
                    VariavelModelo(chave=v.chave, rotulo=v.rotulo, exemplo=v.exemplo)
                    for v in m.definicao.variaveis
                ],
                padrao=m.definicao.padrao,
                texto=m.texto,
                personalizado=m.personalizado,
                atualizado_por=m.usuario_nome,
                atualizado_em=m.atualizado_em,
            )
            for m in service.listar_modelos(db)
        ],
    )


def _nome_regra(regra: str) -> str:
    definicao = CATALOGO.get(regra)
    return f'"{definicao.nome}"' if definicao else regra


def _nome_modelo(chave: str) -> str:
    definicao = MODELOS.get(chave)
    return f'"{definicao.nome}"' if definicao else chave


def _invalida(erro: service.ConfigInvalida) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(erro))


@router.get("", summary="Configuração dos alertas: regras, campos e destinos")
def ler(db: SessionDep, admin: AdminDep) -> ConfiguracaoAlertas:
    return _configuracao(db)


@router.put(
    "/regras/{regra}",
    summary="Liga/desliga a regra e define campos da mensagem e destinos",
    responses={**_R404, **_R422},
)
def salvar_regra(
    regra: Annotated[str, Path(description="Nome da regra.", examples=["transferencia_atrasada"])],
    dados: RegraAlertaEntrada,
    db: SessionDep,
    admin: AdminDep,
) -> ConfiguracaoAlertas:
    try:
        service.salvar_regra(
            db,
            regra,
            ativo=dados.ativo,
            campos=dados.campos,
            destinos_ids=dados.destinos,
        )
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Regra não encontrada.") from None
    except service.ConfigInvalida as erro:
        raise _invalida(erro) from None
    atividades.registrar(
        db,
        "alertas_alterados",
        f"{admin.nome_exibicao} alterou o alerta {_nome_regra(regra)}",
        usuario=admin,
    )
    db.commit()
    logger.info("alertas.config regra=%s ator=%s", regra, admin.id)
    return _configuracao(db)


@router.delete(
    "/regras/{regra}",
    summary="Volta a regra ao padrão (todos os campos padrão, destino Padrão)",
    responses=_R404,
)
def restaurar_regra(
    regra: Annotated[str, Path(description="Nome da regra.")], db: SessionDep, admin: AdminDep
) -> ConfiguracaoAlertas:
    try:
        service.restaurar_padrao(db, regra)
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Regra não encontrada.") from None
    atividades.registrar(
        db,
        "alertas_alterados",
        f"{admin.nome_exibicao} voltou ao padrão o alerta {_nome_regra(regra)}",
        usuario=admin,
    )
    db.commit()
    logger.info("alertas.config regra=%s restaurada ator=%s", regra, admin.id)
    return _configuracao(db)


@router.post(
    "/destinos",
    status_code=status.HTTP_201_CREATED,
    summary="Cadastra um destino: chat do Telegram ou número do WhatsApp",
    responses=_R422,
)
def criar_destino(
    dados: DestinoAlertaEntrada, db: SessionDep, admin: AdminDep
) -> ConfiguracaoAlertas:
    try:
        destino = service.criar_destino(db, **dados.model_dump())
    except service.ConfigInvalida as erro:
        raise _invalida(erro) from None
    atividades.registrar(
        db,
        "alertas_alterados",
        f"{admin.nome_exibicao} criou o destino {destino.nome}",
        usuario=admin,
    )
    db.commit()
    logger.info("alertas.config destino=%s criado ator=%s", destino.id, admin.id)
    return _configuracao(db)


@router.put("/destinos/{id}", summary="Altera um destino", responses={**_R404, **_R422})
def editar_destino(
    id: IdDestino, dados: DestinoAlertaEntrada, db: SessionDep, admin: AdminDep
) -> ConfiguracaoAlertas:
    try:
        service.editar_destino(db, id, **dados.model_dump())
    except service.DestinoNaoEncontrado:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Destino não encontrado.") from None
    except service.ConfigInvalida as erro:
        raise _invalida(erro) from None
    atividades.registrar(
        db,
        "alertas_alterados",
        f"{admin.nome_exibicao} alterou o destino {dados.nome}",
        usuario=admin,
    )
    db.commit()
    logger.info("alertas.config destino=%s editado ator=%s", id, admin.id)
    return _configuracao(db)


@router.delete(
    "/destinos/{id}",
    summary="Exclui um destino sem histórico de envios (com histórico: desligue)",
    responses={
        **_R404,
        409: {
            "model": Erro,
            "description": "Destino já recebeu alertas: desligue em vez de excluir.",
        },
    },
)
def excluir_destino(id: IdDestino, db: SessionDep, admin: AdminDep) -> ConfiguracaoAlertas:
    try:
        service.excluir_destino(db, id)
    except service.DestinoNaoEncontrado:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Destino não encontrado.") from None
    except service.DestinoEmUso:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Este destino já recebeu alertas e fica no histórico: desligue-o em vez de excluir.",
        ) from None
    atividades.registrar(
        db,
        "alertas_alterados",
        f"{admin.nome_exibicao} excluiu um destino de alertas",
        usuario=admin,
    )
    db.commit()
    logger.info("alertas.config destino=%s excluido ator=%s", id, admin.id)
    return _configuracao(db)


ChaveModelo = Annotated[
    str, Path(description="Chave da mensagem.", examples=["transferencia_coi_errado:aviso"])
]
_R404_MODELO: Respostas = {404: {"model": Erro, "description": "Mensagem não encontrada."}}


@router.put(
    "/modelos/{chave}",
    summary="Muda o texto de uma mensagem do Telegram",
    responses={**_R404_MODELO, **_R422},
)
def salvar_modelo(
    chave: ChaveModelo, dados: ModeloMensagemEntrada, db: SessionDep, admin: AdminDep
) -> ConfiguracaoAlertas:
    try:
        service.salvar_modelo(
            db, chave, dados.texto, usuario_id=admin.id, usuario_nome=admin.nome_exibicao
        )
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mensagem não encontrada.") from None
    except service.ConfigInvalida as erro:
        raise _invalida(erro) from None
    atividades.registrar(
        db,
        "alertas_alterados",
        f"{admin.nome_exibicao} mudou o texto da mensagem {_nome_modelo(chave)}",
        usuario=admin,
    )
    db.commit()
    logger.info("alertas.config modelo=%s ator=%s", chave, admin.id)
    return _configuracao(db)


@router.delete(
    "/modelos/{chave}",
    summary="Volta a mensagem ao texto padrão",
    responses=_R404_MODELO,
)
def restaurar_modelo(chave: ChaveModelo, db: SessionDep, admin: AdminDep) -> ConfiguracaoAlertas:
    try:
        service.restaurar_modelo(db, chave)
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mensagem não encontrada.") from None
    atividades.registrar(
        db,
        "alertas_alterados",
        f"{admin.nome_exibicao} voltou ao padrão a mensagem {_nome_modelo(chave)}",
        usuario=admin,
    )
    db.commit()
    logger.info("alertas.config modelo=%s restaurado ator=%s", chave, admin.id)
    return _configuracao(db)


@router.post(
    "/modelos/{chave}/previa",
    summary="Mostra como a mensagem fica, com valores de exemplo (não salva)",
    responses={**_R404_MODELO, **_R422},
)
def previa_modelo(
    chave: ChaveModelo, dados: ModeloMensagemEntrada, admin: AdminDep
) -> PreviaModelo:
    try:
        return PreviaModelo(texto=service.previa_modelo(chave, dados.texto))
    except LookupError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mensagem não encontrada.") from None
    except service.ConfigInvalida as erro:
        raise _invalida(erro) from None


IdMensagem = Annotated[int, Path(description="Id da mensagem avulsa.")]
_R404_MENSAGEM: Respostas = {404: {"model": Erro, "description": "Mensagem não encontrada."}}


def _mensagem_saida(m: MensagemAvulsa) -> MensagemAvulsaSaida:
    return MensagemAvulsaSaida(
        id=m.id,
        texto=m.texto,
        agendada_para=m.agendada_para,
        horario=m.horario,
        dias_semana=list(m.dias_semana),
        criada_por=m.criada_por_nome,
        criada_em=m.created_at,
        cancelada_em=m.cancelada_em,
        envios=[
            EnvioMensagemAvulsa.model_validate(e, from_attributes=True)
            for e in mensagens_avulsas.envios(m)
        ],
    )


@router.get("/mensagens", summary="Mensagens avulsas: agendadas e já enviadas (as 50 últimas)")
def listar_mensagens(db: SessionDep, admin: AdminDep) -> list[MensagemAvulsaSaida]:
    return [_mensagem_saida(m) for m in mensagens_avulsas.listar(db)]


@router.get(
    "/mensagens/variaveis",
    summary="Variáveis da mensagem avulsa: números de vendas e do financeiro na hora do envio",
)
def variaveis_mensagem(admin: AdminDep) -> list[VariavelModelo]:
    return [
        VariavelModelo(chave=v.chave, rotulo=v.rotulo, exemplo=v.exemplo)
        for v in VARIAVEIS_MENSAGEM
    ]


@router.post(
    "/mensagens/previa",
    summary="Mostra a mensagem com os valores de agora (não salva nem envia)",
    responses=_R422,
)
def previa_mensagem(dados: PreviaMensagemEntrada, db: SessionDep, admin: AdminDep) -> PreviaModelo:
    try:
        texto = mensagens_avulsas.previa(
            db, dados.texto, datetime.now(UTC), ZoneInfo(get_settings().tz)
        )
    except mensagens_avulsas.MensagemInvalida as erro:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(erro)) from None
    return PreviaModelo(texto=texto)


@router.post(
    "/mensagens",
    status_code=status.HTTP_201_CREATED,
    summary="Envia uma mensagem livre agora ou agenda para uma data e hora",
    responses=_R422,
)
def criar_mensagem(
    dados: MensagemAvulsaEntrada, db: SessionDep, admin: AdminDep
) -> MensagemAvulsaSaida:
    agora = datetime.now(UTC)
    try:
        mensagem = mensagens_avulsas.criar(
            db,
            texto=dados.texto,
            destinos=dados.destinos,
            agendada_para=dados.agendada_para,
            usuario=admin,
            agora=agora,
            tz=ZoneInfo(get_settings().tz),
            horario=dados.horario,
            dias_semana=dados.dias_semana,
        )
    except mensagens_avulsas.MensagemInvalida as erro:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(erro)) from None
    if mensagem.horario is not None:
        quando = f"todo dia às {mensagem.horario:%H:%M}"
    else:
        quando = "para agora" if mensagem.agendada_para <= agora else "agendada"
    atividades.registrar(
        db,
        "alertas_alterados",
        f"{admin.nome_exibicao} criou uma mensagem avulsa ({quando})",
        usuario=admin,
    )
    db.commit()
    db.refresh(mensagem)
    logger.info("alertas.mensagem=%s criada ator=%s", mensagem.id, admin.id)
    return _mensagem_saida(mensagem)


@router.delete(
    "/mensagens/{id}",
    summary="Cancela os envios de uma mensagem que ainda não saíram",
    responses={
        **_R404_MENSAGEM,
        409: {"model": Erro, "description": "Nada a cancelar: já enviada ou já cancelada."},
    },
)
def cancelar_mensagem(id: IdMensagem, db: SessionDep, admin: AdminDep) -> MensagemAvulsaSaida:
    try:
        mensagem = mensagens_avulsas.cancelar(db, id, datetime.now(UTC))
    except mensagens_avulsas.MensagemNaoEncontrada:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mensagem não encontrada.") from None
    except mensagens_avulsas.NadaParaCancelar:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Nada a cancelar: a mensagem já saiu ou já foi cancelada."
        ) from None
    atividades.registrar(
        db,
        "alertas_alterados",
        f"{admin.nome_exibicao} cancelou uma mensagem avulsa",
        usuario=admin,
    )
    db.commit()
    db.refresh(mensagem)
    logger.info("alertas.mensagem=%s cancelada ator=%s", id, admin.id)
    return _mensagem_saida(mensagem)


IdModeloAvulsa = Annotated[int, Path(description="Id do modelo de mensagem.")]


@router.get("/mensagens/modelos", summary="Modelos de mensagem avulsa salvos, por nome")
def listar_modelos_mensagem(db: SessionDep, admin: AdminDep) -> list[ModeloMensagemAvulsaSaida]:
    return [
        ModeloMensagemAvulsaSaida.model_validate(m) for m in mensagens_avulsas.listar_modelos(db)
    ]


@router.post(
    "/mensagens/modelos",
    summary="Salva o texto como modelo (o mesmo nome substitui o texto)",
    responses=_R422,
)
def salvar_modelo_mensagem(
    dados: ModeloMensagemAvulsaEntrada, db: SessionDep, admin: AdminDep
) -> list[ModeloMensagemAvulsaSaida]:
    try:
        modelo = mensagens_avulsas.salvar_modelo(
            db, nome=dados.nome, texto=dados.texto, usuario=admin
        )
    except mensagens_avulsas.MensagemInvalida as erro:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(erro)) from None
    atividades.registrar(
        db,
        "alertas_alterados",
        f"{admin.nome_exibicao} salvou o modelo de mensagem {modelo.nome}",
        usuario=admin,
    )
    db.commit()
    logger.info("alertas.modelo_avulsa=%s salvo ator=%s", modelo.id, admin.id)
    return listar_modelos_mensagem(db, admin)


@router.delete(
    "/mensagens/modelos/{id}",
    summary="Exclui um modelo (mensagens já programadas não mudam)",
    responses={404: {"model": Erro, "description": "Modelo não encontrado."}},
)
def excluir_modelo_mensagem(
    id: IdModeloAvulsa, db: SessionDep, admin: AdminDep
) -> list[ModeloMensagemAvulsaSaida]:
    try:
        mensagens_avulsas.excluir_modelo(db, id)
    except mensagens_avulsas.ModeloNaoEncontrado:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Modelo não encontrado.") from None
    atividades.registrar(
        db,
        "alertas_alterados",
        f"{admin.nome_exibicao} excluiu um modelo de mensagem",
        usuario=admin,
    )
    db.commit()
    logger.info("alertas.modelo_avulsa=%s excluido ator=%s", id, admin.id)
    return listar_modelos_mensagem(db, admin)
