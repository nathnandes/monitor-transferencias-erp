from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.api.schemas import DataUTC, EmpresaResumo

Canal = Literal["balcao", "televendas", "faturamento"]


class TotaisVendas(BaseModel):
    faturamento: Decimal = Field(examples=["125430.90"])
    notas: int = Field(description="Notas de venda não canceladas.")
    ticket_medio: Decimal | None = Field(description="Faturamento ÷ notas; nulo sem notas.")
    quantidade: Decimal = Field(description="Soma das quantidades vendidas (unidades, kg, m...).")
    desconto: Decimal = Field(
        description=(
            "Soma do desconto dos itens, como vem do ERP. Pode conter erro de digitação "
            "(preço errado e descontado): não usar como indicador sem conferir."
        )
    )
    devolucoes: Decimal | None = Field(
        description=(
            "Devoluções de venda (notas de entrada, COI 30 e 31) no período. Nulo com "
            "filtro de canal: a devolução não tem canal."
        )
    )
    faturamento_liquido: Decimal = Field(description="Faturamento − devoluções.")


class FiltroVendas(BaseModel):
    empresa: EmpresaResumo | None
    data_inicial: date | None
    data_final: date | None
    comparar_inicial: date | None
    comparar_final: date | None
    canal: Canal | None
    dias: list[date] | None = Field(
        default=None, description="Dias avulsos do filtro `dias`; nulo sem ele."
    )


class PontoVendas(BaseModel):
    chave: str = Field(description="AAAA-MM-DD (dia) ou AAAA-MM (mês).", examples=["2026-10"])
    faturamento: Decimal
    notas: int
    quantidade: Decimal
    devolucoes: Decimal | None = Field(description="Nulo com filtro de canal.")


class VendasPorCanal(BaseModel):
    canal: Canal
    rotulo: str = Field(examples=["Balcão (NFC-e)"])
    faturamento: Decimal
    notas: int
    quantidade: Decimal


class VendasPorCategoria(BaseModel):
    categoria: str = Field(
        description="Divisão do cadastro de produtos; SEM CATEGORIA ou OUTRAS (o resto).",
        examples=["TINTAS"],
    )
    faturamento: Decimal
    notas: int = Field(description="Notas com item da categoria (0 em OUTRAS).")
    quantidade: Decimal


class VendasPorEmpresa(BaseModel):
    empresa: EmpresaResumo
    faturamento: Decimal
    notas: int
    ticket_medio: Decimal | None


class ProdutoVendido(BaseModel):
    id_produto: str = Field(examples=["12636"])
    id_subproduto: str | None
    descricao: str | None
    quantidade: Decimal
    faturamento: Decimal


class FormaPagamento(BaseModel):
    forma: str = Field(
        description="Descrição da forma no ERP; OUTRAS agrupa as menores.", examples=["PIX TEF"]
    )
    valor: Decimal
    parcelas: int = Field(description="Parcelas (títulos) recebidas nessa forma.")


class VendasPorVendedor(BaseModel):
    id_vendedor: str = Field(description="IDVENDEDOR das notas no ERP.", examples=["633"])
    nome: str | None = Field(
        description="Nome do vendedor no ERP; nulo enquanto não foi achado.",
        examples=["MARIA SOUZA"],
    )
    empresas: list[EmpresaResumo] = Field(description="Lojas onde o vendedor vendeu no filtro.")
    faturamento: Decimal
    notas: int
    ticket_medio: Decimal | None
    faturamento_comparacao: Decimal | None = Field(
        description="Faturamento no intervalo de comparação (0 sem venda); nulo sem ele."
    )
    abaixo_da_media: bool = Field(description="Faturamento menor que a média por vendedor.")


class RankingVendedores(BaseModel):
    media_faturamento: Decimal | None = Field(
        description="Faturamento dos vendedores ÷ vendedores com venda; nulo sem venda."
    )
    vendedores: list[VendasPorVendedor] = Field(
        description="Do maior para o menor faturamento bruto (a devolução não tem vendedor)."
    )
    sem_vendedor_faturamento: Decimal = Field(
        description="Notas sem vendedor: fora do ranking e da média."
    )
    sem_vendedor_notas: int


class CoberturaVendas(BaseModel):
    desde: date | None = Field(
        description="Primeiro dia com todas as empresas lidas (o histórico chega aos poucos)."
    )
    ate: date | None = Field(description="Último dia lido.")
    atualizado_em: DataUTC | None = Field(description="Última leitura de um dia de vendas.")


class ResumoVendas(BaseModel):
    gerado_em: DataUTC
    filtro: FiltroVendas
    totais: TotaisVendas
    comparacao: TotaisVendas | None = Field(
        description="Mesmos totais no intervalo de comparação; nulo sem ele."
    )
    granularidade: Literal["dia", "mes"] = Field(
        description="dia até 62 dias de período; acima (ou sem período), mês."
    )
    serie: list[PontoVendas]
    por_canal: list[VendasPorCanal]
    por_categoria: list[VendasPorCategoria]
    por_empresa: list[VendasPorEmpresa]
    produtos: list[ProdutoVendido] = Field(description="Os 10 de maior faturamento.")
    cobertura: CoberturaVendas
    vendedores: RankingVendedores
    formas_pagamento: list[FormaPagamento] | None = Field(
        description=(
            "Recebimentos do caixa (série PDV) por forma de pagamento no período. Não há "
            "chave entre recebimento e nota: é o total por forma, que bate com o faturamento. "
            "Nulo com filtro de canal."
        )
    )
