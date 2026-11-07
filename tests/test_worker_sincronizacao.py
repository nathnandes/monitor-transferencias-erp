from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select, update

from app.core.config import Settings
from app.database.models import Sincronizacao, SolicitacaoSincronizacao
from app.services import sincronizacao as pedidos
from app.sync import ResultadoSincronizacao
from app.sync.comum import finalizar_execucao_isolada, iniciar_execucao
from app.workers.sincronizacao import executar_ciclo
from tests.sync_fakes import fabrica_de

pytestmark = pytest.mark.integration


SETTINGS = Settings(
    _env_file=None,
    sync_estoque_intervalo_segundos=600,
    sync_empresas_intervalo_segundos=86400,
    sync_transferencias_intervalo_segundos=600,
    sync_estoque_completo_horario="",
    sync_precos_intervalo_segundos=0,
    sync_precos_completo_horario="",
    sync_vendas_intervalo_segundos=0,
    sync_movimentos_intervalo_segundos=0,
)
FUSO_LOCAL = ZoneInfo("America/Porto_Velho")
COM_COMPLETA = Settings(
    _env_file=None,
    sync_estoque_intervalo_segundos=600,
    sync_empresas_intervalo_segundos=86400,
    sync_transferencias_intervalo_segundos=0,
    sync_estoque_completo_horario="02:00",
    sync_precos_intervalo_segundos=0,
    sync_precos_completo_horario="",
    sync_vendas_intervalo_segundos=0,
    sync_movimentos_intervalo_segundos=0,
    tz="America/Porto_Velho",
)
SO_PRECOS = Settings(
    _env_file=None,
    sync_estoque_intervalo_segundos=0,
    sync_empresas_intervalo_segundos=0,
    sync_transferencias_intervalo_segundos=0,
    sync_estoque_completo_horario="",
    sync_precos_intervalo_segundos=1800,
    sync_precos_completo_horario="03:30",
    sync_vendas_intervalo_segundos=0,
    sync_movimentos_intervalo_segundos=0,
    tz="America/Porto_Velho",
)
SO_VENDAS = Settings(
    _env_file=None,
    sync_estoque_intervalo_segundos=0,
    sync_empresas_intervalo_segundos=0,
    sync_transferencias_intervalo_segundos=0,
    sync_estoque_completo_horario="",
    sync_precos_intervalo_segundos=0,
    sync_precos_completo_horario="",
    sync_vendas_intervalo_segundos=900,
    sync_movimentos_intervalo_segundos=0,
    tz="America/Porto_Velho",
)

SO_MOVIMENTOS = SO_VENDAS.model_copy(
    update={"sync_vendas_intervalo_segundos": 0, "sync_movimentos_intervalo_segundos": 600}
)


class ExecutorFalso:
    def __init__(self, fabrica):
        self.fabrica = fabrica
        self.tipos: list[str] = []

        self.momento: datetime | None = None

    def __call__(self, tipo):
        self.tipos.append(tipo)
        execucao = iniciar_execucao(self.fabrica, tipo)
        if self.momento is not None:
            with self.fabrica() as db, db.begin():
                db.execute(
                    update(Sincronizacao)
                    .where(Sincronizacao.id == execucao)
                    .values(inicio=self.momento, fim=self.momento)
                )
            return ResultadoSincronizacao(execucao, "sucesso")
        finalizar_execucao_isolada(self.fabrica, execucao, "sucesso")
        return ResultadoSincronizacao(execucao, "sucesso")


@pytest.fixture
def limpo(db_vazio):
    return db_vazio


def test_atende_o_pedido_manual_e_conclui_com_a_execucao(limpo):
    db = limpo
    pedido = pedidos.solicitar(db, "estoque", "admin")
    db.flush()
    fabrica = fabrica_de(db)
    executor = ExecutorFalso(fabrica)

    feitas = executar_ciclo(fabrica, executor, SETTINGS, agendamento=True)

    assert executor.tipos == ["estoque"]
    db.refresh(pedido)
    assert pedido.status == "CONCLUIDA"
    assert pedido.sincronizacao_id == feitas[0].sincronizacao_id
    assert pedido.iniciado_em is not None and pedido.concluido_em is not None


def test_pedido_e_atendido_mesmo_sem_agendamento(limpo):
    db = limpo
    pedidos.solicitar(db, "empresas", None)
    fabrica = fabrica_de(db)
    executor = ExecutorFalso(fabrica)

    executar_ciclo(fabrica, executor, SETTINGS, agendamento=False)
    executar_ciclo(fabrica, executor, SETTINGS, agendamento=False)

    assert executor.tipos == ["empresas"]


def test_agendamento_roda_empresas_transferencias_e_estoque_quando_vencidos(limpo):
    fabrica = fabrica_de(limpo)
    executor = ExecutorFalso(fabrica)

    executar_ciclo(fabrica, executor, SETTINGS, agendamento=True)

    executar_ciclo(fabrica, executor, SETTINGS, agendamento=True)

    assert executor.tipos == ["empresas", "transferencias", "estoque"]


def test_estoque_vence_antes_das_empresas(limpo):
    fabrica = fabrica_de(limpo)
    executor = ExecutorFalso(fabrica)
    executar_ciclo(fabrica, executor, SETTINGS, agendamento=True)

    daqui_11_min = datetime.now(UTC) + timedelta(minutes=11)
    executar_ciclo(fabrica, executor, SETTINGS, agendamento=True, agora=lambda: daqui_11_min)

    assert executor.tipos == [
        "empresas",
        "transferencias",
        "estoque",
        "transferencias",
        "estoque",
    ]


def test_sem_agendamento_nada_roda_sozinho(limpo):
    fabrica = fabrica_de(limpo)
    executor = ExecutorFalso(fabrica)

    assert executar_ciclo(fabrica, executor, SETTINGS, agendamento=False) == []
    assert executor.tipos == []


def test_execucao_e_pedido_orfaos_sao_fechados(limpo):
    db = limpo
    fabrica = fabrica_de(db)
    orfa = iniciar_execucao(fabrica, "estoque")
    pedido = pedidos.solicitar(db, "estoque", None)
    db.execute(
        update(SolicitacaoSincronizacao)
        .where(SolicitacaoSincronizacao.id == pedido.id)
        .values(status="EM_EXECUCAO")
    )

    executar_ciclo(fabrica, ExecutorFalso(fabrica), SETTINGS, agendamento=False)

    db.expire_all()
    execucao = db.get(Sincronizacao, orfa)
    assert (execucao.status, execucao.mensagem_erro) == (
        "erro",
        "interrompida (worker reiniciado)",
    )
    assert (
        db.scalar(
            select(SolicitacaoSincronizacao.status).where(SolicitacaoSincronizacao.id == pedido.id)
        )
        == "CONCLUIDA"
    )


def test_trava_impede_duas_sincronizacoes_ao_mesmo_tempo(engine):
    from sqlalchemy.orm import Session

    from app.sync import trava_sincronizacao

    def fabrica():
        return Session(bind=engine)

    with trava_sincronizacao(fabrica) as primeira:
        with trava_sincronizacao(fabrica) as segunda:
            assert (primeira, segunda) == (True, False)

    with trava_sincronizacao(fabrica) as de_novo:
        assert de_novo is True


def test_trava_nao_deixa_a_conexao_idle_in_transaction(engine):
    from sqlalchemy import text
    from sqlalchemy.orm import Session

    from app.sync import trava_sincronizacao
    from app.sync.comum import _LOCK_SINCRONIZACAO

    def fabrica():
        return Session(bind=engine)

    with trava_sincronizacao(fabrica) as obtida:
        if not obtida:
            pytest.skip("trava ocupada pelo sincronizador desta maquina")
        with engine.connect() as outra:
            estado = outra.execute(
                text(
                    "SELECT a.state FROM pg_locks l JOIN pg_stat_activity a USING (pid)"
                    " WHERE l.locktype = 'advisory' AND l.objid = :chave AND l.granted"
                ),
                {"chave": _LOCK_SINCRONIZACAO},
            ).scalar()

    assert estado == "idle"


def _no_fuso(dia, hora, minuto=0):
    return datetime(2026, 10, dia, hora, minuto, tzinfo=FUSO_LOCAL)


def test_leitura_completa_roda_uma_vez_por_dia_no_horario(limpo):
    fabrica = fabrica_de(limpo)
    executor = ExecutorFalso(fabrica)

    def ciclo(momento):
        executor.tipos.clear()
        executor.momento = momento
        executar_ciclo(fabrica, executor, COM_COMPLETA, agendamento=True, agora=lambda: momento)
        return list(executor.tipos)

    assert ciclo(_no_fuso(7, 14)) == ["empresas", "estoque_completo", "estoque"]

    assert ciclo(_no_fuso(7, 14, 20)) == ["estoque"]
    assert ciclo(_no_fuso(8, 1, 59)) == ["estoque"]

    assert ciclo(_no_fuso(8, 2, 10)) == ["estoque_completo", "estoque"]
    assert ciclo(_no_fuso(8, 2, 15)) == []


def test_pedido_de_leitura_completa_e_atendido(limpo):
    pedidos.solicitar(limpo, "estoque_completo", "admin")
    fabrica = fabrica_de(limpo)
    executor = ExecutorFalso(fabrica)

    executar_ciclo(fabrica, executor, SETTINGS, agendamento=False)

    assert executor.tipos == ["estoque_completo"]


def test_precos_completa_no_horario_e_incremental_no_intervalo(limpo):
    fabrica = fabrica_de(limpo)
    executor = ExecutorFalso(fabrica)

    def ciclo(momento):
        executor.tipos.clear()
        executor.momento = momento
        executar_ciclo(fabrica, executor, SO_PRECOS, agendamento=True, agora=lambda: momento)
        return list(executor.tipos)

    assert ciclo(_no_fuso(7, 14)) == ["precos_completo", "precos"]
    assert ciclo(_no_fuso(7, 14, 20)) == []
    assert ciclo(_no_fuso(7, 14, 31)) == ["precos"]

    assert ciclo(_no_fuso(8, 3, 35)) == ["precos_completo", "precos"]


def test_vendas_rodam_no_intervalo(limpo):
    fabrica = fabrica_de(limpo)
    executor = ExecutorFalso(fabrica)

    def ciclo(momento):
        executor.tipos.clear()
        executor.momento = momento
        executar_ciclo(fabrica, executor, SO_VENDAS, agendamento=True, agora=lambda: momento)
        return list(executor.tipos)

    assert ciclo(_no_fuso(7, 14)) == ["vendas"]
    assert ciclo(_no_fuso(7, 14, 10)) == []
    assert ciclo(_no_fuso(7, 14, 16)) == ["vendas"]


def test_movimentos_de_estoque_rodam_no_intervalo(limpo):
    fabrica = fabrica_de(limpo)
    executor = ExecutorFalso(fabrica)

    def ciclo(momento):
        executor.tipos.clear()
        executor.momento = momento
        executar_ciclo(fabrica, executor, SO_MOVIMENTOS, agendamento=True, agora=lambda: momento)
        return list(executor.tipos)

    assert ciclo(_no_fuso(7, 14)) == ["movimentos_estoque"]
    assert ciclo(_no_fuso(7, 14, 5)) == []
    assert ciclo(_no_fuso(7, 14, 11)) == ["movimentos_estoque"]


def test_pedido_de_precos_e_atendido(limpo):
    pedidos.solicitar(limpo, "precos_completo", "admin")
    fabrica = fabrica_de(limpo)
    executor = ExecutorFalso(fabrica)

    executar_ciclo(fabrica, executor, SETTINGS, agendamento=False)

    assert executor.tipos == ["precos_completo"]


def test_agenda_tem_cada_tipo_uma_vez_na_ordem_de_prioridade():
    from typing import get_args

    from app.sync import TipoSincronizacao
    from app.workers.sincronizacao import AGENDA

    tipos = [a.tipo for a in AGENDA]
    assert sorted(tipos) == sorted(get_args(TipoSincronizacao))

    assert tipos[:4] == ["empresas", "transferencias", "estoque_completo", "estoque"]
    assert {a.tipo for a in AGENDA if a.diario} == {"estoque_completo", "precos_completo"}
