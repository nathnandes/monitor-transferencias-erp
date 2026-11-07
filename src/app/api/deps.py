from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.database.session import get_session, get_session_leitura


def get_settings_da_app(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


SettingsDep = Annotated[Settings, Depends(get_settings_da_app)]
SessionDep = Annotated[Session, Depends(get_session)]

SessionLeituraDep = Annotated[Session, Depends(get_session_leitura)]
