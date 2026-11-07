from datetime import UTC, datetime

from fastapi import APIRouter

from app.api import schemas
from app.api.autenticacao import UsuarioAutenticadoDep
from app.api.deps import SessionLeituraDep, SettingsDep
from app.api.schemas import RESPOSTAS_PROTEGIDAS
from app.services import frescor as service

router = APIRouter(tags=["sincronizacao"], responses=RESPOSTAS_PROTEGIDAS)


@router.get("/frescor", summary="Última conclusão de cada sincronização agendada")
def frescor(
    db: SessionLeituraDep, settings: SettingsDep, _usuario: UsuarioAutenticadoDep
) -> schemas.Frescor:
    agora = datetime.now(UTC)
    return schemas.Frescor(
        gerado_em=agora,
        tipos=[
            schemas.FrescorTipo(
                tipo=f.tipo,
                intervalo_segundos=f.intervalo_segundos,
                ultima_conclusao=f.ultima_conclusao,
                limite_segundos=int(f.limite.total_seconds()),
                situacao=f.situacao,
            )
            for f in service.frescor(db, settings, agora)
        ],
    )
