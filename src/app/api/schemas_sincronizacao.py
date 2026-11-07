from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.api.schemas import DataUTC, EmpresaResumo, _DoOrm


class Solicitacao(_DoOrm):
    id: int
    tipo: Literal[
        "empresas",
        "estoque",
        "estoque_completo",
        "transferencias",
        "precos",
        "precos_completo",
        "vendas",
        "movimentos_estoque",
    ]
    status: Literal["PENDENTE", "EM_EXECUCAO", "CONCLUIDA"]
    solicitado_por: str | None
    solicitado_em: DataUTC
    iniciado_em: DataUTC | None
    sincronizacao_id: int | None = Field(description="Execução que atendeu o pedido.")


class _Contadores(_DoOrm):
    id: int
    status: str = Field(description="em_andamento | sucesso | parcial | erro")
    inicio: DataUTC
    fim: DataUTC | None
    paginas_processadas: int
    registros_recebidos: int = Field(validation_alias="registros_consultados")
    registros_gravados: int = Field(description="Criados + atualizados.")
    registros_criados: int
    registros_atualizados: int
    registros_ignorados: int
    mensagem_erro: str | None


class ExecucaoEmpresa(_Contadores):
    empresa: EmpresaResumo | None


class Execucao(_Contadores):
    tipo: str
    empresas_processadas: int


class ErroIntegracao(_DoOrm):
    id: int
    sincronizacao_id: int | None
    id_erp_empresa: str | None
    endpoint: str | None
    status_http: int | None
    tipo_erro: str = Field(
        description="Classe do erro na integração (acesso negado, timeout, resposta inválida...)."
    )
    mensagem: str
    tentativa: int
    ocorrido_em: DataUTC


class ResumoSincronizacaoEstoque(BaseModel):
    linhas_ativas: int = Field(description="Linhas empresa/produto/local/lote ativas.")
    linhas_inativas: int = Field(description="Deixaram de vir do ERP; fora do consolidado.")
    produtos_consolidados: int
    consolidado_atualizado_em: datetime | None


class StatusSincronizacao(BaseModel):
    pendentes: list[Solicitacao]
    em_execucao: list[Solicitacao]
    empresas: Execucao | None = Field(description="Última sincronização de empresas.")
    estoque: Execucao | None = Field(description="Última leitura incremental de estoque.")
    estoque_completo: Execucao | None = Field(
        description="Última leitura completa de estoque (a que desativa linhas que sumiram)."
    )
    precos: Execucao | None = Field(
        default=None, description="Última leitura incremental de produtos e preços/custos."
    )
    precos_completo: Execucao | None = Field(
        default=None, description="Última leitura completa de produtos e preços/custos."
    )
    estoque_por_empresa: list[ExecucaoEmpresa] = Field(
        description="Uma linha por empresa da sincronização de estoque mais recente."
    )
    erros_recentes: list[ErroIntegracao]
    resumo_estoque: ResumoSincronizacaoEstoque
