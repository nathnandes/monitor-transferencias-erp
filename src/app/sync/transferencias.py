import hashlib
import json
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from functools import partial
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, selectinload

from app.core.logging_config import get_logger
from app.database.models import Empresa, Transferencia, TransferenciaItem
from app.dominio import coi as catalogo
from app.dominio.transferencias import STATUS_CANCELADA, STATUS_PENDENTE, STATUS_PROCESSADA
from app.erp.errors import ErpApiError
from app.erp.schemas import RespostaPaginada
from app.erp.servicos import (
    ROTA_ITENS_ENTRADA,
    ROTA_ITENS_SAIDA,
    ROTA_NOTAS_ENTRADA,
    ROTA_NOTAS_SAIDA,
    ItemNota,
    Nota,
    RegistroInvalidoError,
    ServicosErp,
    mapear_item_nota,
    mapear_nota,
)
from app.sync.comum import (
    FabricaSessao,
    FalhaGeralError,
    Leitura,
    PoliticaRetry,
    RegistroErros,
    agora_utc,
    com_retry,
    eh_falha_geral,
    finalizar_execucao_isolada,
    iniciar_execucao,
    percorrer_paginas,
    resumir,
)
from app.sync.empresas import ResultadoSincronizacao

logger = get_logger(__name__)

TIPO = "transferencias"


MAX_BUSCAS_POR_CHAVE = 5
IDADE_BUSCA_POR_CHAVE = timedelta(hours=24)
DIAS_BUSCA_POR_CHAVE = 30

_MAX_ERROS_DE_REGISTRO = 5

Relogio = Callable[[], datetime]

COIS_SAIDA = tuple(sorted(c for cois in catalogo.COIS_SAIDA.values() for c in cois))
COIS_ENTRADA = tuple(
    sorted(set(catalogo.COI_ENTRADA.values()) | set(catalogo.COI_ENTRADA_EXCECOES.values()))
)


@dataclass
class Resultado:
    rotulo: str
    status: str = "sucesso"
    paginas: int = 0
    recebidos: int = 0
    criados: int = 0
    atualizados: int = 0
    ignorados: int = 0
    mensagem: str | None = None


@dataclass(frozen=True)
class _Empresas:
    por_id_erp: dict[str, int]
    id_erp_por_id: dict[int, str]
    id_erp_por_cnpj: dict[str, str]


def _carregar_empresas(fabrica: FabricaSessao, ambiente: str) -> _Empresas:
    with fabrica() as db:
        linhas = db.execute(
            select(Empresa.id, Empresa.id_erp, Empresa.cnpj).where(
                Empresa.ambiente == ambiente, Empresa.id_erp.is_not(None)
            )
        ).all()
    validas = [(id_, id_erp, cnpj) for id_, id_erp, cnpj in linhas if id_erp]
    return _Empresas(
        por_id_erp={id_erp: id_ for id_, id_erp, _ in validas},
        id_erp_por_id={id_: id_erp for id_, id_erp, _ in validas},
        id_erp_por_cnpj={cnpj: id_erp for _, id_erp, cnpj in validas if cnpj},
    )


def dias_da_janela(agora: datetime, janela: timedelta, fuso: ZoneInfo) -> list[date]:
    hoje = agora.astimezone(fuso).date()
    inicio = (agora - janela).astimezone(fuso).date()
    return [hoje - timedelta(days=n) for n in range((hoje - inicio).days + 1)]


class _Leitor:
    def __init__(
        self,
        servicos: ServicosErp,
        politica: PoliticaRetry,
        erros: RegistroErros,
        resultado: Resultado,
        id_empresa: str | None,
    ) -> None:
        self.servicos = servicos
        self.politica = politica
        self.erros = erros
        self.resultado = resultado
        self.id_empresa = id_empresa
        self.detalhados = 0

    def ler(self, buscar: Callable[[int], RespostaPaginada], pedido: str) -> list[dict[str, Any]]:
        leitura = percorrer_paginas(
            buscar,
            max_paginas=self.servicos.max_paginas,
            politica=self.politica,
            ao_falhar=lambda exc, tentativa, pagina: self.erros.erpapi(
                exc,
                tentativa=tentativa,
                id_empresa=self.id_empresa,
                pedido=f"page={pagina}, {pedido}",
            ),
            leitura=Leitura(),
        )
        self.resultado.paginas += leitura.paginas
        self.resultado.recebidos += len(leitura.registros)
        return leitura.registros

    def recusar(self, tipo: str, mensagem: str, endpoint: str) -> None:
        self.resultado.ignorados += 1
        if self.detalhados < _MAX_ERROS_DE_REGISTRO:
            self.detalhados += 1
            self.erros.outro(tipo, mensagem, id_empresa=self.id_empresa, endpoint=endpoint)

    def itens(self, brutos: list[dict[str, Any]], *, pedido: str, endpoint: str) -> list[ItemNota]:
        vistos: dict[tuple[str, str, str, str | None] | int, ItemNota] = {}
        validos = 0
        for n, bruto in enumerate(brutos):
            try:
                item = mapear_item_nota(bruto, self.servicos.fuso)
            except RegistroInvalidoError as exc:
                self.recusar("RegistroInvalido", str(exc), endpoint)
                continue
            validos += 1
            if item.sequencia is None:
                vistos[n] = item
            else:
                chave = (item.id_planilha, item.sequencia, item.id_produto, item.id_subproduto)
                vistos[chave] = item
        if len(vistos) < validos:
            self.recusar(
                "PaginacaoInstavel",
                f"{pedido}: {len(brutos)} linhas, so {len(vistos)} distintas; "
                "pode ter faltado item (consulta grande demais)",
                endpoint,
            )
        return list(vistos.values())

    def cabecalho(
        self, brutos: list[dict[str, Any]], *, id_planilha: str, endpoint: str
    ) -> Nota | None:
        for bruto in brutos:
            try:
                nota = mapear_nota(bruto, self.servicos.fuso)
            except RegistroInvalidoError as exc:
                self.recusar("RegistroInvalido", str(exc), endpoint)
                continue
            if nota.id_planilha == id_planilha:
                return nota
        self.recusar(
            "NotaSemCabecalho", f"cabecalho da nota {id_planilha} nao encontrado", endpoint
        )
        return None


def sincronizar_transferencias(
    fabrica: FabricaSessao,
    servicos: ServicosErp,
    *,
    ambiente: str,
    empresas: tuple[str, ...],
    politica: PoliticaRetry,
    janela: timedelta,
    agora: Relogio = agora_utc,
) -> ResultadoSincronizacao:
    pai_id = iniciar_execucao(fabrica, TIPO)
    erros = RegistroErros(fabrica, pai_id)
    cadastro = _carregar_empresas(fabrica, ambiente)
    nao_cadastradas = [e for e in empresas if e not in cadastro.por_id_erp]
    for id_erp in nao_cadastradas:
        erros.outro(
            "EmpresaNaoCadastrada",
            f"empresa {id_erp} nao esta na tabela empresas ({ambiente}); "
            "rode a sincronizacao de empresas antes",
            id_empresa=id_erp,
        )
    sem_cnpj = sorted(i for i in cadastro.por_id_erp if i not in cadastro.id_erp_por_cnpj.values())
    if sem_cnpj:
        erros.outro(
            "EmpresaSemCnpj",
            f"empresas sem CNPJ: {', '.join(sem_cnpj)}; rode a sincronizacao de empresas",
        )

    momento = agora()
    dias = dias_da_janela(momento, janela, servicos.fuso)
    resultados: list[Resultado] = []
    interrupcao: str | None = None
    try:
        com_retry(servicos.autenticar, politica, lambda exc, t: erros.erpapi(exc, tentativa=t))
        for id_erp in empresas:
            if id_erp in cadastro.por_id_erp:
                resultados.append(
                    sincronizar_saidas_empresa(
                        fabrica,
                        servicos,
                        cadastro,
                        id_erp=id_erp,
                        dias=dias,
                        agora=momento,
                        pai_id=pai_id,
                        politica=politica,
                    )
                )
        resultados.append(
            sincronizar_entradas(
                fabrica,
                servicos,
                cadastro,
                empresas=[e for e in empresas if e in cadastro.por_id_erp],
                dias=dias,
                agora=momento,
                pai_id=pai_id,
                politica=politica,
            )
        )
    except FalhaGeralError as exc:
        interrupcao = f"interrompida: {exc}"
    except ErpApiError as exc:
        interrupcao = f"interrompida: {resumir(exc)}"
    except Exception as exc:
        logger.exception("sync.transferencias.falha_interna execucao=%s", pai_id)
        finalizar_execucao_isolada(fabrica, pai_id, "erro", mensagem=resumir(exc))
        raise

    ok = [r for r in resultados if r.status != "erro"]
    mensagens: list[str] = []
    if interrupcao:
        mensagens.append(interrupcao)
    if nao_cadastradas:
        mensagens.append(f"empresas nao cadastradas: {', '.join(nao_cadastradas)}")
    mensagens += [f"{r.rotulo}: {r.mensagem}" for r in resultados if r.mensagem]

    esperados = len(empresas) + 1
    if interrupcao or not ok:
        status = "erro"
    elif len(ok) == esperados and all(r.status == "sucesso" for r in ok):
        status = "sucesso"
    else:
        status = "parcial"
    mensagem = "; ".join(mensagens) or None
    finalizar_execucao_isolada(
        fabrica,
        pai_id,
        status,
        mensagem=mensagem,
        empresas_processadas=len([r for r in ok if r.rotulo.startswith("empresa")]),
        paginas_processadas=sum(r.paginas for r in resultados),
        registros_consultados=sum(r.recebidos for r in resultados),
        registros_criados=sum(r.criados for r in resultados),
        registros_atualizados=sum(r.atualizados for r in resultados),
        registros_ignorados=sum(r.ignorados for r in resultados),
    )
    logger.info("sync.transferencias.fim execucao=%s status=%s", pai_id, status)
    return ResultadoSincronizacao(pai_id, status, mensagem)


def _falhou(
    fabrica: FabricaSessao, execucao_id: int, resultado: Resultado, exc: ErpApiError
) -> Resultado:
    resultado.status = "erro"
    resultado.mensagem = resumir(exc)
    finalizar_execucao_isolada(
        fabrica,
        execucao_id,
        "erro",
        mensagem=resultado.mensagem,
        paginas_processadas=resultado.paginas,
        registros_consultados=resultado.recebidos,
    )
    if eh_falha_geral(exc):
        raise FalhaGeralError(exc) from None
    return resultado


def _fechar(fabrica: FabricaSessao, execucao_id: int, resultado: Resultado) -> Resultado:
    if resultado.status == "sucesso" and resultado.ignorados:
        resultado.status = "parcial"
        resultado.mensagem = f"{resultado.ignorados} registro(s)/nota(s) ignorado(s)"
    finalizar_execucao_isolada(
        fabrica,
        execucao_id,
        resultado.status,
        mensagem=resultado.mensagem,
        empresas_processadas=1 if resultado.rotulo.startswith("empresa") else 0,
        paginas_processadas=resultado.paginas,
        registros_consultados=resultado.recebidos,
        registros_criados=resultado.criados,
        registros_atualizados=resultado.atualizados,
        registros_ignorados=resultado.ignorados,
    )
    return resultado


def sincronizar_saidas_empresa(
    fabrica: FabricaSessao,
    servicos: ServicosErp,
    cadastro: _Empresas,
    *,
    id_erp: str,
    dias: list[date],
    agora: datetime,
    pai_id: int | None,
    politica: PoliticaRetry,
) -> Resultado:
    origem_id = cadastro.por_id_erp[id_erp]
    execucao_id = iniciar_execucao(fabrica, TIPO, empresa_id=origem_id, pai_id=pai_id)
    resultado = Resultado(f"empresa {id_erp}")
    leitor = _Leitor(servicos, politica, RegistroErros(fabrica, execucao_id), resultado, id_erp)

    try:
        notas = _varrer(leitor, servicos, saida=True, id_erp=id_erp, cois=COIS_SAIDA, dias=dias)
        canceladas = _saidas_sumidas(
            leitor,
            fabrica,
            servicos,
            origem_id=origem_id,
            id_erp=id_erp,
            lidas={nota.id_planilha for nota, _ in notas},
            desde=agora - timedelta(days=DIAS_BUSCA_POR_CHAVE),
        )
    except ErpApiError as exc:
        return _falhou(fabrica, execucao_id, resultado, exc)

    try:
        with fabrica() as db, db.begin():
            existentes = _transferencias_da_janela(db, origem_id, notas)
            for nota, itens in notas:
                if _gravar_saida(db, cadastro, nota, itens, existentes):
                    resultado.criados += 1
                else:
                    resultado.atualizados += 1
            for nota in canceladas:
                if _cancelar_saida(db, origem_id, nota):
                    resultado.atualizados += 1
    except Exception as exc:
        logger.exception("sync.transferencias.gravacao_falhou empresa=%s", id_erp)
        resultado.status = "erro"
        resultado.mensagem = f"falha ao gravar: {resumir(exc)}"
        resultado.criados = resultado.atualizados = 0
        finalizar_execucao_isolada(fabrica, execucao_id, "erro", mensagem=resultado.mensagem)
        return resultado

    logger.info(
        "sync.transferencias.saidas empresa=%s notas=%s criadas=%s",
        id_erp,
        len(notas),
        resultado.criados,
    )
    return _fechar(fabrica, execucao_id, resultado)


def _varrer(
    leitor: _Leitor,
    servicos: ServicosErp,
    *,
    saida: bool,
    id_erp: str,
    cois: tuple[int, ...],
    dias: list[date],
) -> list[tuple[Nota, list[ItemNota]]]:
    lado = "saida" if saida else "entrada"
    rota = ROTA_ITENS_SAIDA if saida else ROTA_ITENS_ENTRADA
    itens_por_nota: dict[str, list[ItemNota]] = defaultdict(list)
    for coi in cois:
        for dia in dias:
            pedido = f"{lado} idempresa={id_erp} idoperacao={coi} dtmovimento={dia}"
            brutos = leitor.ler(
                partial(servicos.pagina_itens_nota, saida, id_erp, coi, dia), pedido
            )
            for item in leitor.itens(brutos, pedido=pedido, endpoint=rota):
                if item.id_empresa != id_erp or item.id_operacao != coi:
                    leitor.recusar(
                        "RegistroForaDoFiltro",
                        f"pedido {pedido}, veio idempresa={item.id_empresa} "
                        f"idoperacao={item.id_operacao}",
                        rota,
                    )
                    continue
                itens_por_nota[item.id_planilha].append(item)

    notas: list[tuple[Nota, list[ItemNota]]] = []
    for id_planilha, itens in sorted(itens_por_nota.items()):
        brutos = leitor.ler(
            partial(servicos.pagina_nota, saida, id_erp, id_planilha),
            f"{lado} idempresa={id_erp} idplanilha={id_planilha}",
        )
        nota = leitor.cabecalho(brutos, id_planilha=id_planilha, endpoint=rota)
        if nota is not None:
            notas.append((nota, itens))
    return notas


def _saidas_sumidas(
    leitor: _Leitor,
    fabrica: FabricaSessao,
    servicos: ServicosErp,
    *,
    origem_id: int,
    id_erp: str,
    lidas: set[str],
    desde: datetime,
) -> list[Nota]:
    with fabrica() as db:
        sumidas = [
            id_planilha
            for id_planilha in db.scalars(
                select(Transferencia.id_erp)
                .where(
                    Transferencia.empresa_origem_id == origem_id,
                    Transferencia.status == STATUS_PENDENTE,
                    Transferencia.data_criacao >= desde,
                )
                .order_by(Transferencia.id)
            )
            if id_planilha not in lidas
        ]
    canceladas: list[Nota] = []
    for id_planilha in sumidas:
        brutos = leitor.ler(
            partial(servicos.pagina_nota, True, id_erp, id_planilha),
            f"saida idempresa={id_erp} idplanilha={id_planilha}",
        )
        nota = leitor.cabecalho(brutos, id_planilha=id_planilha, endpoint=ROTA_NOTAS_SAIDA)
        if nota is not None and nota.cancelada:
            canceladas.append(nota)
    return canceladas


def _buscar_por_chave(
    leitor: _Leitor, servicos: ServicosErp, chave: str
) -> tuple[Nota, list[ItemNota]] | None:
    brutos = leitor.ler(
        partial(servicos.pagina_entrada_por_chave, chave), f"entrada chavenfe={chave}"
    )
    for bruto in brutos:
        try:
            nota = mapear_nota(bruto, servicos.fuso)
        except RegistroInvalidoError as exc:
            leitor.recusar("RegistroInvalido", str(exc), ROTA_NOTAS_ENTRADA)
            continue
        if nota.chave_nfe != chave or nota.cancelada:
            continue
        pedido = f"entrada idempresa={nota.id_empresa} idplanilha={nota.id_planilha}"
        brutos_itens = leitor.ler(
            partial(servicos.pagina_itens_planilha, False, nota.id_empresa, nota.id_planilha),
            pedido,
        )
        return nota, leitor.itens(brutos_itens, pedido=pedido, endpoint=ROTA_ITENS_ENTRADA)
    return None


def sincronizar_entradas(
    fabrica: FabricaSessao,
    servicos: ServicosErp,
    cadastro: _Empresas,
    *,
    empresas: list[str],
    dias: list[date],
    agora: datetime,
    pai_id: int | None,
    politica: PoliticaRetry,
) -> Resultado:
    execucao_id = iniciar_execucao(fabrica, TIPO, pai_id=pai_id)
    resultado = Resultado("entradas")
    leitor = _Leitor(servicos, politica, RegistroErros(fabrica, execucao_id), resultado, None)

    entradas: list[tuple[Nota, list[ItemNota]]] = []
    try:
        for id_erp in empresas:
            leitor.id_empresa = id_erp
            entradas += _varrer(
                leitor, servicos, saida=False, id_erp=id_erp, cois=COIS_ENTRADA, dias=dias
            )
        leitor.id_empresa = None

        with fabrica() as db:
            achadas = {n.chave_nfe for n, _ in entradas if n.chave_nfe}
            repescagem = [
                (id_, chave)
                for id_, chave in db.execute(
                    select(Transferencia.id, Transferencia.chave_nfe)
                    .where(
                        Transferencia.chave_nfe.is_not(None),
                        Transferencia.coi_entrada.is_(None),
                        Transferencia.status == STATUS_PENDENTE,
                        Transferencia.data_criacao < agora - IDADE_BUSCA_POR_CHAVE,
                        Transferencia.data_criacao >= agora - timedelta(days=DIAS_BUSCA_POR_CHAVE),
                    )
                    .order_by(Transferencia.updated_at, Transferencia.id)
                )
                if chave and chave not in achadas
            ][:MAX_BUSCAS_POR_CHAVE]
        procuradas: list[int] = []
        for transferencia_id, chave in repescagem:
            procuradas.append(transferencia_id)
            achada = _buscar_por_chave(leitor, servicos, chave)
            if achada is not None:
                entradas.append(achada)
    except ErpApiError as exc:
        return _falhou(fabrica, execucao_id, resultado, exc)

    sem_saida = 0
    try:
        with fabrica() as db, db.begin():
            for nota, itens in entradas:
                if not nota.chave_nfe:
                    continue
                t = db.scalar(
                    select(Transferencia)
                    .options(selectinload(Transferencia.itens))
                    .where(Transferencia.chave_nfe == nota.chave_nfe)
                )
                if nota.cancelada:
                    if t is not None and t.id_erp_entrada == nota.id_planilha:
                        _desfazer_entrada(t, cadastro, nota)
                        resultado.atualizados += 1
                    continue
                if t is None:
                    sem_saida += 1
                    continue
                if nota.id_empresa not in cadastro.por_id_erp:
                    leitor.recusar(
                        "EntradaEmEmpresaNaoCadastrada",
                        f"entrada {nota.id_planilha} na empresa {nota.id_empresa}",
                        ROTA_NOTAS_ENTRADA,
                    )
                    continue
                _gravar_entrada(t, cadastro, nota, itens)
                resultado.atualizados += 1

            if procuradas:
                db.execute(
                    update(Transferencia)
                    .where(Transferencia.id.in_(procuradas), Transferencia.coi_entrada.is_(None))
                    .values(updated_at=func.now())
                )
    except Exception as exc:
        logger.exception("sync.transferencias.gravacao_entradas_falhou")
        resultado.status = "erro"
        resultado.mensagem = f"falha ao gravar: {resumir(exc)}"
        resultado.atualizados = 0
        finalizar_execucao_isolada(fabrica, execucao_id, "erro", mensagem=resultado.mensagem)
        return resultado

    logger.info(
        "sync.transferencias.entradas notas=%s gravadas=%s sem_saida=%s repescagem=%s",
        len(entradas),
        resultado.atualizados,
        sem_saida,
        len(procuradas),
    )
    return _fechar(fabrica, execucao_id, resultado)


def _hash(bruto: dict[str, Any]) -> str:
    texto = json.dumps(bruto, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(texto.encode()).hexdigest()


def _cois(itens: list[ItemNota]) -> list[int]:
    return sorted({i.id_operacao for i in itens if i.id_operacao is not None})


def _json(valor: Any) -> Any:
    if isinstance(valor, datetime):
        return valor.isoformat()
    if isinstance(valor, Decimal):
        return str(valor)
    return valor


def _nota_json(nota: Nota) -> dict[str, Any]:
    return {k: _json(v) for k, v in vars(nota).items()}


def _conferir(t: Transferencia, cadastro: _Empresas) -> None:
    def codigo(empresa_id: int | None) -> str | None:
        return cadastro.id_erp_por_id.get(empresa_id) if empresa_id else None

    raw = t.raw_data or {}
    entrada = raw.get("entrada") or {}
    conferencia = catalogo.conferir_transferencia(
        origem=codigo(t.empresa_origem_id),
        coi_saida=t.coi,
        destino=codigo(t.empresa_destino_id),
        coi_entrada=t.coi_entrada,
        empresa_entrada=codigo(t.empresa_entrada_id),
        origem_da_entrada=cadastro.id_erp_por_cnpj.get(entrada.get("cnpj_cpf") or ""),
        entrada_registrada=t.id_erp_entrada is not None,
    )
    fora_do_padrao = list(conferencia.fora_do_padrao)
    for lado, chave in (("saida", "cois_saida"), ("entrada", "cois_entrada")):
        cois = list(raw.get(chave) or [])
        if len(cois) > 1:
            fora_do_padrao.append(f"itens da nota de {lado} com COIs diferentes: {cois}")
    t.problemas_coi = list(conferencia.problemas)
    t.entre_empresas = bool(conferencia.problemas) or not fora_do_padrao


def _transferencias_da_janela(
    db: Session, origem_id: int, notas: list[tuple[Nota, list[ItemNota]]]
) -> dict[str, Transferencia]:
    ids = sorted({nota.id_planilha for nota, _ in notas})
    if not ids:
        return {}
    return {
        t.id_erp: t
        for t in db.scalars(
            select(Transferencia)
            .options(selectinload(Transferencia.itens))
            .where(Transferencia.empresa_origem_id == origem_id, Transferencia.id_erp.in_(ids))
        )
    }


def _item_json(item: ItemNota) -> dict[str, Any]:
    return {k: _json(v) for k, v in vars(item).items()}


def _gravar_saida(
    db: Session,
    cadastro: _Empresas,
    nota: Nota,
    itens: list[ItemNota],
    existentes: dict[str, Transferencia] | None = None,
) -> bool:
    origem_id = cadastro.por_id_erp[nota.id_empresa]
    if existentes is not None:
        t = existentes.get(nota.id_planilha)
    else:
        t = db.scalar(
            select(Transferencia)
            .options(selectinload(Transferencia.itens))
            .where(
                Transferencia.empresa_origem_id == origem_id,
                Transferencia.id_erp == nota.id_planilha,
            )
        )
    assinatura = _hash({"nota": _nota_json(nota), "itens": [_item_json(i) for i in itens]})
    if t is not None and (t.raw_data or {}).get("assinatura_saida") == assinatura:
        _conferir(t, cadastro)
        return False
    criada = t is None
    if t is None:
        t = Transferencia(empresa_origem_id=origem_id, id_erp=nota.id_planilha)
        db.add(t)
        recebidas: dict[ChaveProduto, Decimal] = {}
        cfops_entrada: dict[ChaveProduto, str | None] = {}
    else:
        recebidas = {}
        for i in t.itens:
            if i.quantidade_processada is not None:
                k = _chave_linha(i)
                recebidas[k] = recebidas.get(k, Decimal(0)) + i.quantidade_processada
        cfops_entrada = {_chave_linha(i): i.cfop_entrada for i in t.itens}

    destino = cadastro.id_erp_por_cnpj.get(nota.cnpj_cpf or "")
    cois = _cois(itens)
    t.empresa_destino_id = cadastro.por_id_erp.get(destino) if destino else None
    t.coi = str(cois[0]) if cois else None
    t.chave_nfe = nota.chave_nfe
    t.numero_nota = nota.numero
    t.valor_total = nota.valor_contabil
    t.usuario_emissao = nota.usuario
    t.data_criacao = nota.data_movimento or nota.data_emissao
    t.quantidade_itens = len(itens)
    if nota.cancelada:
        t.status = STATUS_CANCELADA
    elif t.coi_entrada:
        t.status = STATUS_PROCESSADA
    else:
        t.status = STATUS_PENDENTE
    t.raw_data = {
        **(t.raw_data or {}),
        "saida": _nota_json(nota),
        "cois_saida": cois,
        "assinatura_saida": assinatura,
    }
    t.hash_payload = _hash(t.raw_data)
    t.itens = [
        TransferenciaItem(
            id_produto_erp=i.id_produto,
            codigo_produto=i.id_subproduto,
            descricao_produto=i.descricao_produto,
            quantidade_solicitada=i.quantidade,
            quantidade_processada=None,
            valor_total=i.valor_liquido,
            cfop_saida=i.cfop,
            cfop_entrada=cfops_entrada.get(_chave_item(i)),
            raw_data={"sequencia": i.sequencia, "idoperacao": i.id_operacao},
        )
        for i in itens
    ]
    distribuir_recebido(t.itens, recebidas)
    db.flush()
    _conferir(t, cadastro)
    return criada


def _cancelar_saida(db: Session, origem_id: int, nota: Nota) -> bool:
    t = db.scalar(
        select(Transferencia).where(
            Transferencia.empresa_origem_id == origem_id,
            Transferencia.id_erp == nota.id_planilha,
        )
    )
    if t is None or t.status == STATUS_CANCELADA:
        return False
    t.status = STATUS_CANCELADA
    t.raw_data = {**(t.raw_data or {}), "saida": _nota_json(nota)}
    t.hash_payload = _hash(t.raw_data)
    return True


ChaveProduto = tuple[str, str]


def _chave(id_produto: str, id_subproduto: str | None) -> ChaveProduto:
    return (id_produto, id_subproduto or id_produto)


def _chave_item(item: ItemNota) -> ChaveProduto:
    return _chave(item.id_produto, item.id_subproduto)


def _chave_linha(linha: TransferenciaItem) -> ChaveProduto:
    return _chave(linha.id_produto_erp, linha.codigo_produto)


def distribuir_recebido(
    linhas: list[TransferenciaItem], recebidas: dict[ChaveProduto, Decimal]
) -> None:
    por_produto: dict[ChaveProduto, list[TransferenciaItem]] = defaultdict(list)
    for linha in linhas:
        por_produto[_chave_linha(linha)].append(linha)
    for produto, grupo in por_produto.items():
        grupo.sort(key=lambda linha: linha.id or 0)
        total = recebidas.get(produto)
        if total is None:
            for linha in grupo:
                linha.quantidade_processada = None
            continue
        resto = total
        for linha in grupo[:-1]:
            parte = max(min(linha.quantidade_solicitada or Decimal(0), resto), Decimal(0))
            linha.quantidade_processada = parte
            resto -= parte
        grupo[-1].quantidade_processada = resto


def _descricao(itens: list[ItemNota], chave: ChaveProduto) -> str | None:
    return next((i.descricao_produto for i in itens if _chave_item(i) == chave), None)


def _desfazer_entrada(t: Transferencia, cadastro: _Empresas, nota: Nota) -> None:
    t.id_erp_entrada = None
    t.coi_entrada = None
    t.empresa_entrada_id = None
    t.data_processamento = None
    if t.status != STATUS_CANCELADA:
        t.status = STATUS_PENDENTE
    for item in t.itens:
        item.quantidade_processada = None
        item.cfop_entrada = None
    raw = {k: v for k, v in (t.raw_data or {}).items() if k not in ("entrada", "cois_entrada")}
    t.raw_data = {**raw, "itens_sem_saida": [], "entrada_cancelada": _nota_json(nota)}
    t.hash_payload = _hash(t.raw_data)
    _conferir(t, cadastro)


def _gravar_entrada(
    t: Transferencia, cadastro: _Empresas, nota: Nota, itens: list[ItemNota]
) -> None:
    cois = _cois(itens)
    t.id_erp_entrada = nota.id_planilha
    t.coi_entrada = str(cois[0]) if cois else None
    t.empresa_entrada_id = cadastro.por_id_erp[nota.id_empresa]
    t.data_processamento = nota.data_movimento or nota.data_emissao
    if t.status != STATUS_CANCELADA:
        t.status = STATUS_PROCESSADA

    recebidas: dict[ChaveProduto, Decimal] = {}
    for i in itens:
        if i.quantidade is not None:
            k = _chave_item(i)
            recebidas[k] = recebidas.get(k, Decimal(0)) + i.quantidade
    distribuir_recebido(t.itens, recebidas)
    for item in t.itens:
        item.cfop_entrada = next(
            (i.cfop for i in itens if _chave_item(i) == _chave_linha(item) and i.cfop), None
        )

    enviados = {_chave_linha(i) for i in t.itens}
    sem_saida: dict[ChaveProduto, Decimal] = {}
    for i in itens:
        k = _chave_item(i)
        if k not in enviados and i.quantidade is not None:
            sem_saida[k] = sem_saida.get(k, Decimal(0)) + i.quantidade
    t.raw_data = {
        **(t.raw_data or {}),
        "entrada": _nota_json(nota),
        "cois_entrada": cois,
        "itens_sem_saida": [
            {
                "id_produto": k[0],
                "id_subproduto": k[1],
                "descricao": _descricao(itens, k),
                "quantidade": str(q),
            }
            for k, q in sorted(sem_saida.items())
        ],
    }
    t.hash_payload = _hash(t.raw_data)
    _conferir(t, cadastro)
