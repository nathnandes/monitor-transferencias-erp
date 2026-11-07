from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.api.schemas import DataUTC, EmpresaResumo
from app.api.schemas_vendas import CoberturaVendas


class FiltroFinanceiro(BaseModel):
    empresa: EmpresaResumo | None = Field(description="Nulo no consolidado.")
    data_inicial: date | None
    data_final: date | None


class FormaVendida(BaseModel):
    forma: str = Field(description="Descrição da forma no ERP.", examples=["PIX TEF"])
    valor: Decimal = Field(description="Valor das vendas do período nessa forma.")
    valor_pago: Decimal = Field(
        description="Quanto dessas parcelas já foi pago (até a última leitura)."
    )
    valor_pendente: Decimal = Field(description="Quanto dessas parcelas ainda falta pagar.")
    parcelas: int = Field(description="Parcelas (títulos) lançadas nessa forma.")


class VendasPagas(BaseModel):
    valor: Decimal = Field(description="Valor das vendas do período (parcelas lançadas).")
    valor_pago: Decimal
    valor_pendente: Decimal
    parcelas: int
    formas: list[FormaVendida]


class FormaRecebida(BaseModel):
    forma: str = Field(
        description="Descrição da forma no ERP.",
        examples=["BOLETO BANCO EXEMPLO"],
    )
    valor: Decimal = Field(description="Valor pago das parcelas recebidas no período.")
    titulos: int


class Recebidos(BaseModel):
    total: Decimal = Field(
        description=(
            "Valor pago das parcelas com o último recebimento no período, de qualquer venda "
            "(o boleto pago agora de uma venda de outro mês inclusive)."
        )
    )
    de_vendas_anteriores: Decimal = Field(
        description="Parte do total que é de parcelas lançadas fora do período."
    )
    de_boletos: Decimal = Field(
        description=(
            "Parte do total paga em boleto (formas que começam por BOLETO), de qualquer venda."
        )
    )
    das_vendas_do_periodo: Decimal = Field(
        description="Parte do total, fora boleto, de parcelas lançadas no período."
    )
    outros_anteriores: Decimal = Field(
        description=(
            "Parte do total, fora boleto, de parcelas lançadas antes do período "
            "(transferência a receber, receber na entrega...). "
            "de_boletos + das_vendas_do_periodo + outros_anteriores = total."
        )
    )
    juros: Decimal = Field(description="Juros cobrados nessas parcelas (à parte do total).")
    titulos: int
    formas: list[FormaRecebida]


class ResumoFinanceiro(BaseModel):
    gerado_em: DataUTC
    filtro: FiltroFinanceiro
    vendas: VendasPagas = Field(
        description=(
            "Parcelas (série PDV) lançadas no período por forma de pagamento: o valor das "
            "vendas, o já pago e o pendente."
        )
    )
    recebidos: Recebidos = Field(
        description=(
            "O que foi recebido no período (pela data do último recebimento de cada parcela), "
            "por forma. O ERP só guarda o último recebimento: parcela paga em duas vezes "
            "conta inteira no dia da última."
        )
    )
    cobertura: CoberturaVendas


class Parcela(BaseModel):
    empresa: str = Field(description="Código da empresa.", examples=["1"])
    empresa_nome: str
    documento: str = Field(description="IDPLANILHA do ERP (documento do caixa/pedido).")
    titulo: str = Field(description="IDTITULO do ERP.")
    parcela: str = Field(description="DIGITOTITULO do ERP.")
    forma: str = Field(examples=["BOLETO BANCO EXEMPLO (NOVO)"])
    dia_lancamento: date
    vencimento: date | None
    dia_pagamento: date | None = Field(description="Último pagamento; nulo se nada foi pago.")
    valor: Decimal
    valor_pago: Decimal
    valor_pendente: Decimal
    juros: Decimal
    desconto: Decimal
    situacao: Literal["PAGA", "PARCIAL", "PENDENTE"] = Field(
        description="PAGA: nada pendente. PARCIAL: pago em parte. PENDENTE: nada pago."
    )


class PaginaParcelas(BaseModel):
    total: int = Field(description="Parcelas que atendem aos filtros.")
    pagina: int
    tamanho_pagina: int
    total_paginas: int
    valor: Decimal = Field(description="Soma do filtro inteiro (todas as páginas).")
    valor_pago: Decimal
    valor_pendente: Decimal
    itens: list[Parcela]
