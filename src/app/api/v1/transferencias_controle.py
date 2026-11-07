from datetime import UTC, date, datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy import select

from app.api import schemas
from app.api import schemas_controle as sc
from app.api.autenticacao import UsuarioAutenticadoDep
from app.api.autorizacao import AdminDep, exigir_modulo
from app.api.deps import SessionDep, SessionLeituraDep, SettingsDep
from app.api.schemas import RESPOSTAS_PROTEGIDAS
from app.database.models import Empresa
from app.dominio.modulos import Modulo
from app.services import anomalias, atividades, limites_pendencia
from app.services import controle_transferencias as service

router = APIRouter(
    tags=["transferencias"],
    dependencies=[Depends(exigir_modulo(Modulo.TRANSFERENCIAS))],
    responses=RESPOSTAS_PROTEGIDAS,
)


@router.get(
    "/transferencias/controle",
    summary="Painel de controle: trânsito, rotas, divergências, fiscal e emissores",
    description=(
        "Período sobre `data_criacao` (dias no fuso `TZ`, inclusivos). `empresa` = origem OU "
        "destino. O trânsito é a situação de agora, de qualquer data."
    ),
)
def painel(
    db: SessionLeituraDep,
    settings: SettingsDep,
    empresa: Annotated[str | None, Query(description="Código da empresa.", examples=["03"])] = None,
    data_inicial: Annotated[date | None, Query()] = None,
    data_final: Annotated[date | None, Query()] = None,
) -> sc.PainelControle:
    try:
        filtros = service.Filtros(empresa=empresa, data_inicial=data_inicial, data_final=data_final)
    except service.IntervaloDeDatasInvalido as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    resultado = service.painel_controle(
        db, filtros, tz=ZoneInfo(settings.tz), agora=datetime.now(UTC)
    )
    return sc.PainelControle.model_validate(
        {
            **vars(resultado),
            "filtros": sc.FiltroControle(
                empresa=empresa, data_inicial=data_inicial, data_final=data_final
            ),
        }
    )


@router.get(
    "/transferencias/anomalias",
    summary="Transferências que o detector sinalizou como fora do padrão",
    description=(
        "Período sobre `data_criacao` (dias no fuso `TZ`, inclusivos). `empresa` = origem OU "
        "destino. Fora do padrão não significa erro nem fraude."
    ),
)
def painel_anomalias(
    db: SessionLeituraDep,
    settings: SettingsDep,
    empresa: Annotated[str | None, Query(description="Código da empresa.", examples=["03"])] = None,
    data_inicial: Annotated[date | None, Query()] = None,
    data_final: Annotated[date | None, Query()] = None,
) -> sc.PainelAnomalias:
    try:
        filtros = service.Filtros(empresa=empresa, data_inicial=data_inicial, data_final=data_final)
    except service.IntervaloDeDatasInvalido as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    dados = anomalias.painel(db, filtros, ZoneInfo(settings.tz))
    return sc.PainelAnomalias.model_validate(
        {
            "execucao": dados.execucao,
            "analisadas": dados.analisadas,
            "sinalizadas": dados.sinalizadas,
            "lista": [
                {
                    "transferencia": {
                        "id": a.transferencia.id,
                        "numero_nota": a.transferencia.numero_nota,
                        "origem": a.transferencia.empresa_origem,
                        "destino": a.transferencia.empresa_destino,
                        "status": a.transferencia.status,
                        "data_criacao": a.transferencia.data_criacao,
                        "valor_total": a.transferencia.valor_total,
                        "usuario_emissao": a.transferencia.usuario_emissao,
                        "tratativa": dados.tratativas.get(a.transferencia_id),
                    },
                    "score": a.score,
                    "limiar": a.limiar,
                    "motivos": [m["texto"] for m in a.motivos],
                    "avaliada_em": a.avaliada_em,
                }
                for a in dados.lista
            ],
        }
    )


def _prazos(db: SessionLeituraDep | SessionDep) -> sc.PrazosRota:
    codigos = {e.id: e.codigo for e in db.scalars(select(Empresa))}
    return sc.PrazosRota(
        prazo_padrao_horas=service.prazo_padrao_horas(db),
        prazos=[
            sc.PrazoRota(origem=codigos[o], destino=codigos[d], horas=h)
            for (o, d), h in sorted(
                service.prazos_por_rota(db).items(),
                key=lambda x: (codigos[x[0][0]], codigos[x[0][1]]),
            )
        ],
    )


@router.get("/transferencias/prazos", summary="Prazo de entrega de cada rota (horas)")
def listar_prazos(db: SessionLeituraDep) -> sc.PrazosRota:
    return _prazos(db)


@router.put(
    "/transferencias/prazos",
    summary="Define o prazo de rotas (ADMIN). Horas nulas voltam ao padrão.",
    responses={422: {"model": schemas.Erro}},
)
def definir_prazos(dados: list[sc.PrazoRota], db: SessionDep, admin: AdminDep) -> sc.PrazosRota:
    try:
        service.definir_prazos(db, [(p.origem, p.destino, p.horas) for p in dados], admin.username)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    atividades.registrar(
        db,
        "transferencias_alteradas",
        f"{admin.nome_exibicao} mudou o prazo de {len(dados)} rota(s) de transferência",
        usuario=admin,
        detalhe="\n".join(
            f"• {p.origem} → {p.destino}: {f'{p.horas} h' if p.horas else 'padrão'}" for p in dados
        ),
    )
    db.commit()
    return _prazos(db)


def _limites(g: limites_pendencia.LimitesGravados) -> sc.LimitesPendencia:
    return sc.LimitesPendencia(
        horas_atencao=g.limites.horas_atencao,
        horas_critico=g.limites.horas_critico,
        definido_por=g.usuario_nome,
        atualizado_em=g.atualizado_em,
    )


@router.get(
    "/transferencias/limites",
    summary="Horas sem entrada no destino que deixam a transferência em atenção e em crítico",
)
def ler_limites(db: SessionLeituraDep) -> sc.LimitesPendencia:
    return _limites(limites_pendencia.ler(db))


@router.put(
    "/transferencias/limites",
    summary="Muda os limites de atenção e crítico (ADMIN)",
    description=(
        "Valem na hora para o alerta `transferencia_atrasada`, o status por empresa do "
        "dashboard, o resumo diário e o prazo padrão das rotas (o limite de atenção)."
    ),
    responses={422: {"model": schemas.Erro}},
)
def definir_limites(
    dados: sc.NovosLimitesPendencia, db: SessionDep, admin: AdminDep
) -> sc.LimitesPendencia:
    try:
        g = limites_pendencia.definir(
            db,
            dados.horas_atencao,
            dados.horas_critico,
            usuario_id=admin.id,
            usuario_nome=admin.nome_exibicao,
            agora=datetime.now(UTC),
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    atividades.registrar(
        db,
        "transferencias_alteradas",
        f"{admin.nome_exibicao} mudou os limites das transferências para"
        f" {dados.horas_atencao} h (atenção) e {dados.horas_critico} h (crítico)",
        usuario=admin,
    )
    db.commit()
    return _limites(g)


IdTransferencia = Annotated[int, Path(description="Id interno da transferência.")]


@router.get(
    "/transferencias/{id}/tratativas", summary="Histórico de tratativas, mais recente primeiro"
)
def listar_tratativas(id: IdTransferencia, db: SessionLeituraDep) -> list[sc.TratativaRegistrada]:
    return [sc.TratativaRegistrada.model_validate(t) for t in service.listar_tratativas(db, id)]


@router.post(
    "/transferencias/{id}/tratativas",
    status_code=status.HTTP_201_CREATED,
    summary="Registra que a transferência foi verificada (em análise ou resolvida)",
    responses={404: {"model": schemas.Erro}},
)
def registrar_tratativa(
    id: IdTransferencia, dados: sc.NovaTratativa, db: SessionDep, usuario: UsuarioAutenticadoDep
) -> sc.TratativaRegistrada:
    tratativa = service.registrar_tratativa(
        db,
        id,
        usuario_id=usuario.id,
        usuario_nome=usuario.nome_exibicao,
        situacao=dados.situacao,
        observacao=dados.observacao,
    )
    if tratativa is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Transferência {id} não encontrada.")
    atividades.registrar(
        db,
        "transferencias_alteradas",
        f"{usuario.nome_exibicao} registrou tratativa na transferência {id}"
        f" ({dados.situacao.lower().replace('_', ' ')})",
        usuario=usuario,
        detalhe=dados.observacao,
    )
    db.commit()
    return sc.TratativaRegistrada.model_validate(tratativa)
