from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.logging_config import get_logger
from app.core.mascaramento import mascarar_texto
from app.database.models import ResumoDiario, Transferencia
from app.dominio.intervalo import Intervalo
from app.dominio.transferencias import STATUS_PENDENTE
from app.notifications.enviador import Enviador, ErroEnvio
from app.notifications.modelos import modelo, renderizar
from app.services import limites_pendencia
from app.services.alertas import contar_abertos
from app.services.comum import condicao_entre_empresas
from app.services.frescor import frescor
from app.services.pipeline import condicao_situacao_coi
from app.services.vendas import totais_do_periodo

logger = get_logger(__name__)

JANELA = timedelta(hours=6)
MAX_TENTATIVAS = 5
ESPERA = timedelta(minutes=5)

_SEVERIDADES = {
    "CRITICAL": ("crítico", "críticos"),
    "ERROR": ("erro", "erros"),
    "WARNING": ("aviso", "avisos"),
}

_ROTULO_SYNC = {
    "transferencias": "transferências",
    "estoque": "estoque",
    "precos": "preços",
    "vendas": "vendas",
    "movimentos_estoque": "movimentos de estoque",
}


def _moeda(valor: Decimal) -> str:
    return "R$ " + f"{valor:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _horario(texto: str) -> time | None:
    if not texto:
        return None
    hora, minuto = texto.split(":")
    return time(int(hora), int(minuto))


def variaveis_resumo(db: Session, agora: datetime, settings: Settings) -> dict[str, str]:
    tz = ZoneInfo(settings.tz)
    hoje = agora.astimezone(tz).date()
    ontem = hoje - timedelta(days=1)

    abertos = contar_abertos(db)
    total_abertos = sum(abertos.values())
    if total_abertos:
        partes = [
            f"{abertos[s]} {singular if abertos[s] == 1 else plural}"
            for s, (singular, plural) in _SEVERIDADES.items()
            if abertos[s]
        ]
        bloco_alertas = f"• {total_abertos}" + (": " + ", ".join(partes) if partes else "")
    else:
        bloco_alertas = "• nenhum ✅"

    entre = condicao_entre_empresas()
    emitidas = db.scalar(
        select(func.count())
        .select_from(Transferencia)
        .where(entre, Intervalo(ontem, ontem).condicao(Transferencia.data_criacao, tz))
    )
    limites = limites_pendencia.limites(db)
    pendentes = db.execute(
        select(
            func.count(),
            func.count().filter(Transferencia.data_criacao < agora - limites.atencao),
            func.count().filter(Transferencia.data_criacao < agora - limites.critico),
        ).where(entre, Transferencia.status == STATUS_PENDENTE)
    ).one()
    coi_errado = db.scalar(
        select(func.count()).select_from(Transferencia).where(condicao_situacao_coi("ERRADO"))
    )
    total, em_atencao, em_critico = pendentes
    sem_entrada = f"• sem entrada no destino: {total}"
    if em_atencao:
        sem_entrada += (
            f" ({em_atencao} há mais de {limites.horas_atencao} h,"
            f" {em_critico} há mais de {limites.horas_critico} h)"
        )
    bloco_transferencias = "\n".join(
        [
            f"• emitidas ontem: {emitidas}",
            sem_entrada,
            f"• com COI errado: {coi_errado}" + (" 🚨" if coi_errado else ""),
        ]
    )

    vendas = totais_do_periodo(db, Intervalo(ontem, ontem))
    linhas_vendas = []
    if vendas.notas:
        linhas_vendas.append(f"• faturamento: {_moeda(vendas.faturamento)} em {vendas.notas} notas")
        if vendas.ticket_medio is not None:
            linhas_vendas.append(f"• ticket médio: {_moeda(vendas.ticket_medio)}")
        if vendas.devolucoes:
            linhas_vendas.append(f"• devoluções: {_moeda(vendas.devolucoes)}")
    else:
        linhas_vendas.append("• nenhuma venda sincronizada")

    linhas_sync = []
    atrasadas = [f for f in frescor(db, settings, agora) if f.situacao in ("ATRASADA", "PARADA")]
    if atrasadas:
        linhas_sync.append("⚠️ Sincronização com o ERP")
        for f in atrasadas:
            quando = (
                f.ultima_conclusao.astimezone(tz).strftime("%d/%m %H:%M")
                if f.ultima_conclusao
                else "—"
            )
            situacao = "parada" if f.situacao == "PARADA" else "atrasada"
            linhas_sync.append(
                f"• {_ROTULO_SYNC.get(f.tipo, f.tipo)} {situacao} (última: {quando})"
            )

    return {
        "data": f"{hoje:%d/%m/%Y}",
        "ontem": f"{ontem:%d/%m}",
        "bloco_alertas": bloco_alertas,
        "alertas_abertos": str(total_abertos),
        "bloco_transferencias": bloco_transferencias,
        "transferencias_emitidas": str(emitidas),
        "sem_entrada": str(total),
        "coi_errado": str(coi_errado),
        "bloco_vendas": "\n".join(linhas_vendas),
        "faturamento": _moeda(vendas.faturamento) if vendas.notas else "",
        "notas": str(vendas.notas),
        "ticket_medio": _moeda(vendas.ticket_medio) if vendas.ticket_medio is not None else "",
        "devolucoes": _moeda(vendas.devolucoes) if vendas.devolucoes else "",
        "bloco_sincronizacao": "\n".join(linhas_sync),
    }


def montar_resumo(db: Session, agora: datetime, settings: Settings) -> str:
    return renderizar(modelo(db, "resumo_diario"), variaveis_resumo(db, agora, settings))


def processar_resumo_diario(
    db: Session, enviador: Enviador, agora: datetime, settings: Settings
) -> str | None:
    horario = _horario(settings.resumo_diario_horario)
    if horario is None:
        return None
    tz = ZoneInfo(settings.tz)
    local = agora.astimezone(tz)
    inicio = datetime.combine(local.date(), horario, tzinfo=tz)
    if agora < inicio:
        return None

    if agora <= inicio + JANELA:
        db.execute(
            insert(ResumoDiario)
            .values(
                dia=local.date(),
                texto=montar_resumo(db, agora, settings),
                status="PENDENTE",
                proxima_tentativa_em=agora,
            )
            .on_conflict_do_nothing(index_elements=["dia"])
        )

    resumo = db.scalars(
        select(ResumoDiario)
        .where(
            ResumoDiario.dia == local.date(),
            ResumoDiario.status == "PENDENTE",
            ResumoDiario.proxima_tentativa_em <= agora,
        )
        .with_for_update(skip_locked=True)
    ).first()
    if resumo is None:
        return None
    if agora > inicio + JANELA:
        resumo.status = "FALHA"
        resumo.ultimo_erro = "fora da janela do resumo: descartado"
        db.flush()
        return resumo.status

    resumo.tentativas += 1
    try:
        enviador.enviar(resumo.texto)
    except ErroEnvio as erro:
        resumo.ultimo_erro = mascarar_texto(str(erro))[:500]
        if erro.transitorio and resumo.tentativas < MAX_TENTATIVAS:
            resumo.proxima_tentativa_em = agora + ESPERA * resumo.tentativas
        else:
            resumo.status = "FALHA"
            logger.error("resumo diario de %s falhou de vez: %s", resumo.dia, resumo.ultimo_erro)
    else:
        resumo.status = "ENVIADO"
        resumo.enviado_em = agora
        resumo.ultimo_erro = None
        logger.info("resumo diario de %s enviado", resumo.dia)
    db.flush()
    return resumo.status
