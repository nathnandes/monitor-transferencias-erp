from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.api.schemas import DataUTC, EmpresaResumo, _DoOrm

StatusCobertura = Literal["ruptura", "critica", "baixa", "adequada", "excesso", "sem_giro"]

DESCRICAO_STATUS_COBERTURA = (
    "ruptura (sem saldo disponível e com venda), critica (< 7 dias), baixa (< 15), "
    "adequada, excesso (> 90 dias) ou sem_giro (com saldo e sem venda na janela). Vazio "
    "quando não se aplica (sem saldo e sem venda, ou empresa que não vende)."
)


class _Cobertura(BaseModel):
    venda_media_diaria: Decimal | None = Field(
        None, description="Quantidade vendida por dia na janela (consolidado: soma das empresas)."
    )
    cobertura_dias: Decimal | None = Field(
        None, description="Saldo disponível / venda média diária, em dias (1 casa)."
    )
    status_cobertura: StatusCobertura | None = Field(None, description=DESCRICAO_STATUS_COBERTURA)


class JanelaVendas(BaseModel):
    inicio: date = Field(description="Primeiro dia das vendas consideradas.")
    fim: date = Field(description="Último dia (ontem: hoje ainda não fechou).")
    dias: int


class _Saldos(BaseModel):
    saldo_atual: Decimal | None
    saldo_reservado: Decimal | None
    saldo_disponivel: Decimal | None = Field(description="Valor do ERP, não recalculado.")


class ItemEstoque(_Saldos, _Cobertura, _DoOrm):
    id_produto: str = Field(examples=["9798"])
    id_subproduto: str = Field(examples=["9798"])
    empresas_com_estoque: int = Field(description="Empresas com saldo atual > 0.")
    descricao: str | None = Field(None, description="Descrição do cadastro de produtos.")
    preco_varejo_min: Decimal | None = Field(
        None, description="Preço de varejo (consolidado: o menor entre as empresas)."
    )
    preco_varejo_max: Decimal | None = Field(
        None, description="Preço de varejo (consolidado: o maior entre as empresas)."
    )
    custo_gerencial: Decimal | None = Field(
        None, description="Custo gerencial (consolidado: média ponderada pelo saldo)."
    )
    valor_custo: Decimal | None = Field(
        None, description="Saldo atual x custo gerencial (consolidado: soma das empresas)."
    )
    fabricante: str | None = Field(None, description="Marca do cadastro de produtos.")
    fornecedor: str | None = Field(
        None, description="Emitente da última nota de compra do item, em qualquer empresa."
    )
    excecao: bool = Field(
        False,
        description="Exceção de falta da empresa filtrada: fica sem classificação de cobertura.",
    )


class PaginaEstoque(BaseModel):
    total: int = Field(description="Produtos que atendem aos filtros.")
    pagina: int
    tamanho_pagina: int
    total_paginas: int
    atualizado_em: DataUTC | None = Field(
        description="Fim da última sincronização de estoque que gravou dados."
    )
    janela: JanelaVendas = Field(description="Vendas usadas na média diária e na cobertura.")
    tem_vendas: bool = Field(
        description="False quando a empresa filtrada não vendeu na janela (depósito): "
        "sem cobertura."
    )
    itens: list[ItemEstoque]


class ContagemCobertura(BaseModel):
    ruptura: int
    critica: int
    baixa: int
    adequada: int
    excesso: int
    sem_giro: int


class ResumoCobertura(BaseModel):
    janela: JanelaVendas
    tem_vendas: bool = Field(description="False: a empresa filtrada não vendeu na janela.")
    produtos: ContagemCobertura = Field(description="Produtos em cada classificação.")


class LocalSomado(BaseModel):
    id_local: str = Field(examples=["8"])
    descricao: str | None = Field(examples=["DEPOSITO 03"])


class CoberturaLocal(BaseModel):
    id_local: str = Field(examples=["1"])
    descricao: str | None = Field(examples=["LOJA MATRIZ"])
    produtos_com_saldo: int = Field(description="Produtos com saldo atual positivo no local.")
    produtos: ContagemCobertura = Field(
        description="Saldo do local ÷ venda média da empresa inteira, por classificação."
    )
    somados: list[LocalSomado] = Field(
        description="Locais que contam como estoque deste (ESTOQUE_LOCAIS_SOMADOS): o saldo "
        "deles entra aqui e eles não aparecem sozinhos."
    )


class CoberturaEmpresa(BaseModel):
    empresa: EmpresaResumo
    tem_vendas: bool = Field(description="False: a empresa não vendeu na janela (depósito).")
    produtos: ContagemCobertura = Field(description="A empresa inteira (soma dos locais).")
    locais: list[CoberturaLocal]
    excecoes: int = Field(
        0, description="Itens que são exceção de falta da empresa (fora das contagens)."
    )
    desconsiderados: list[LocalSomado] = Field(
        default_factory=list,
        description="Locais que não são de venda (ESTOQUE_LOCAIS_FORA_DA_LOJA: trocas, "
        "avarias...): fora das contagens, inclusive da empresa inteira.",
    )


class CoberturaLojas(BaseModel):
    janela: JanelaVendas
    empresas: list[CoberturaEmpresa]


class ItemPedidoAbastecimento(_DoOrm):
    id_produto: str = Field(examples=["9798"])
    id_subproduto: str = Field(examples=["9798"])
    descricao: str | None
    marca: str | None = Field(description="Marca do cadastro (fabricante).")
    status_cobertura: StatusCobertura
    saldo_loja: Decimal = Field(
        description="Disponível nos locais de venda da loja (sem trocas, avarias...)."
    )
    venda_media_diaria: Decimal = Field(description="Baixa real do estoque por dia.")
    cobertura_dias: Decimal | None
    necessidade: Decimal = Field(description="O que falta para cobrir o alvo de dias.")
    quantidade: Decimal = Field(description="O que pedir a este depósito.")
    disponivel_deposito: Decimal = Field(description="Saldo disponível no depósito.")


class PedidoDeposito(BaseModel):
    deposito: EmpresaResumo
    itens: list[ItemPedidoAbastecimento]


class PedidoAbastecimento(BaseModel):
    loja: EmpresaResumo
    janela: JanelaVendas
    alvo_dias: int
    tem_vendas: bool = Field(description="False: a loja não vendeu na janela.")
    pedidos: list[PedidoDeposito] = Field(
        description="Um pedido por depósito (ESTOQUE_DEPOSITOS_ABASTECIMENTO)."
    )
    sem_estoque: list[ItemPedidoAbastecimento] = Field(
        description="Em falta na loja e sem saldo em nenhum depósito (compra)."
    )


class UltimaSincronizacao(_DoOrm):
    tipo: str = Field(examples=["estoque"])
    status: str = Field(description="em_andamento | sucesso | parcial | erro")
    inicio: DataUTC
    fim: DataUTC | None


class EstoquePorEmpresa(BaseModel):
    empresa: EmpresaResumo
    produtos_com_saldo: int
    linhas: int = Field(description="Linhas empresa/produto/local ativas.")
    valor_custo: Decimal | None = Field(
        None, description="Soma de saldo x custo gerencial dos saldos positivos."
    )


class LocalPerda(BaseModel):
    empresa: EmpresaResumo
    id_local: str
    descricao: str | None = Field(description="Nome do local no ERP.")
    motivo: str = Field(examples=["Avaria"])
    produtos: int = Field(description="Produtos com saldo positivo no local.")
    valor: Decimal | None = Field(description="Saldo positivo × custo gerencial: o perdido.")


class ResumoEstoque(BaseModel):
    produtos: int = Field(description="Produtos/subprodutos no consolidado.")
    produtos_com_saldo: int
    produtos_negativos: int
    produtos_com_reserva: int
    atualizado_em: DataUTC | None
    ultima_sincronizacao: UltimaSincronizacao | None
    por_empresa: list[EstoquePorEmpresa]
    valor_custo: Decimal | None = Field(
        None, description="Valor do estoque a custo gerencial (só saldos positivos)."
    )
    linhas_sem_custo: int = Field(
        0, description="Linhas com saldo positivo sem custo cadastrado (fora do valor)."
    )
    precos_atualizados_em: DataUTC | None = Field(
        None, description="Fim da última sincronização de preços que gravou dados."
    )
    locais_perda: list[LocalPerda] = Field(
        default_factory=list,
        description="Locais tratados como perda: fora de todos os saldos e valores acima.",
    )


class LocalEstoque(_Saldos, _DoOrm):
    id_local_estoque: str
    descricao_local_estoque: str | None
    descricao_lote: str = Field(description="Vazio quando não há lote.")
    inativo_erp: bool | None = Field(description="flaginativo do ERP.")
    data_alteracao_erp: DataUTC | None
    sincronizado_em: DataUTC
    perda: str | None = Field(
        None,
        description="Motivo, se o local é de perda (ESTOQUE_LOCAIS_PERDA): fica fora das "
        "somas da empresa e do total.",
    )


class PrecoEmpresa(_DoOrm):
    preco_varejo: Decimal | None
    preco_promocao_varejo: Decimal | None
    inicio_promocao_varejo: DataUTC | None
    fim_promocao_varejo: DataUTC | None
    preco_atacado: Decimal | None
    preco_promocao_atacado: Decimal | None
    custo_reposicao: Decimal | None
    custo_gerencial: Decimal | None
    custo_nota_fiscal: Decimal | None
    data_alteracao_erp: DataUTC | None
    sincronizado_em: DataUTC


class EmpresaDoProduto(_Saldos, _Cobertura):
    empresa: EmpresaResumo
    preco: PrecoEmpresa | None = None
    valor_custo: Decimal | None = None
    locais: list[LocalEstoque]


class FornecedorEstoque(_DoOrm):
    cnpj: str = Field(description="CNPJ/CPF do emitente, só dígitos: o valor do filtro.")
    nome: str = Field(description="Emitente das notas de compra.")
    itens: int = Field(description="Itens diferentes comprados dele no histórico.")


class FornecedorDoProduto(BaseModel):
    nome: str = Field(description="Emitente das notas de compra.")
    cnpj: str | None = Field(None, description="CNPJ/CPF do emitente, só dígitos.")
    compras: int = Field(description="Notas de compra do item com esse fornecedor.")
    quantidade: Decimal | None = Field(description="Quantidade comprada somada.")
    ultima_compra: date = Field(description="Dia da compra mais recente (fuso do ERP).")
    ultima_empresa: EmpresaResumo = Field(description="Empresa que fez a compra mais recente.")
    custo_ultima: Decimal | None = Field(
        description="Valor do item / quantidade na compra mais recente."
    )


class ProdutoEstoque(_Saldos, _Cobertura):
    id_produto: str
    id_subproduto: str
    descricao: str | None = None
    fabricante: str | None = Field(None, description="Marca do cadastro de produtos.")
    empresas_com_estoque: int
    atualizado_em: DataUTC | None = Field(description="Quando o consolidado foi recalculado.")
    empresas: list[EmpresaDoProduto] = Field(description="Ordenadas por código da empresa.")
    fornecedores: list[FornecedorDoProduto] = Field(
        default_factory=list,
        description="De quem o item foi comprado (notas de compra do livro), da compra "
        "mais recente à mais antiga.",
    )
    janela: JanelaVendas | None = None


TipoMovimento = Literal["entrada_avulsa", "saida_avulsa", "balanco"]


class MovimentoEstoque(BaseModel):
    id: int
    empresa: EmpresaResumo
    dia: date = Field(description="Dia do movimento no fuso do ERP.")
    tipo: TipoMovimento
    coi: int = Field(description="80 entrada avulsa, 8080 saída avulsa, 2000 balanço.")
    id_planilha: str = Field(description="Documento do lançamento no ERP.")
    sequencia: str | None
    id_produto: str = Field(examples=["9798"])
    id_subproduto: str | None
    descricao: str | None = Field(
        description="Descrição do item (só as saídas trazem) ou, sem ela, a do cadastro."
    )
    quantidade: Decimal | None = Field(description="Efeito no estoque: negativa = saiu/faltou.")
    valor: Decimal | None = Field(description="Valor líquido com o mesmo sinal da quantidade.")


class ResumoMovimentosDia(BaseModel):
    empresa: EmpresaResumo
    dia: date
    tipo: TipoMovimento
    itens: int
    quantidade: Decimal | None = Field(description="Soma dos efeitos (sobra - falta no balanço).")
    valor: Decimal | None
    falta_itens: int | None = Field(description="Só no balanço: itens com quantidade negativa.")
    falta_quantidade: Decimal | None = Field(description="Só no balanço; negativa.")
    falta_valor: Decimal | None = Field(description="Só no balanço; negativo.")
    sobra_itens: int | None = Field(description="Só no balanço: itens com quantidade positiva.")
    sobra_quantidade: Decimal | None = Field(description="Só no balanço; positiva.")
    sobra_valor: Decimal | None = Field(description="Só no balanço; positivo.")


class FiltroMovimentos(BaseModel):
    data_inicial: date | None
    data_final: date | None
    empresa: EmpresaResumo | None
    tipo: Literal["entrada_avulsa", "saida_avulsa", "balanco", "avulsas"] | None
    produto: str | None
    subproduto: str | None


class CoberturaMovimentos(BaseModel):
    desde: date | None = Field(description="Dia mais antigo já lido do ERP.")
    ate: date | None = Field(description="Dia mais recente já lido do ERP.")
    atualizado_em: DataUTC | None = Field(
        description="Fim da última sincronização de movimentos que gravou dados."
    )


class PaginaMovimentosEstoque(BaseModel):
    total: int = Field(description="Movimentos que atendem aos filtros.")
    pagina: int
    tamanho_pagina: int
    total_paginas: int
    filtro: FiltroMovimentos
    cobertura: CoberturaMovimentos
    itens: list[MovimentoEstoque]
    resumo: list[ResumoMovimentosDia] = Field(
        description="Por empresa, dia e tipo, com os mesmos filtros e sem paginação."
    )


CategoriaMovimento = Literal[
    "venda",
    "devolucao_venda",
    "compra",
    "devolucao_compra",
    "transferencia_entrada",
    "transferencia_saida",
    "entrada_avulsa",
    "saida_avulsa",
    "balanco",
    "perda",
    "uso_consumo",
    "producao",
    "bonificacao",
    "remessa",
    "outros",
    "nao_classificado",
]

_DESCRICAO_AFETA = (
    "Se o COI mexe no estoque: true entra nos totais e no saldo; false não (ativo, despesa, "
    "nota de cupom já contado); null = a confirmar ou COI novo, fora dos totais."
)


class LinhaLivro(BaseModel):
    empresa: EmpresaResumo
    coi: int
    operacao: str | None = Field(description="Nome do COI no ERP.")
    categoria: CategoriaMovimento
    afeta: bool | None = Field(description=_DESCRICAO_AFETA)
    documentos: int = Field(description="Documentos (IDPLANILHA) distintos.")
    itens: int
    valor: Decimal | None = Field(description="Soma do valor dos itens, com o sinal do efeito.")


class LivroEstoque(BaseModel):
    data_inicial: date
    data_final: date
    linhas: list[LinhaLivro] = Field(description="Por empresa e COI, na ordem das empresas.")
    dias_sem_leitura: int = Field(
        description="Dias × empresas do período ainda não lidos no livro completo."
    )


class NotaLivro(BaseModel):
    empresa: EmpresaResumo
    id_planilha: str = Field(description="Documento (IDPLANILHA).")
    numero: str | None = Field(description="Número da nota, quando há cabeçalho.")
    dia: date
    momento: DataUTC | None = Field(
        description="Data e hora do lançamento (cabeçalho da nota). null: o ERP não tem "
        "cabeçalho (entrada/saída avulsa, balanço) ou ele ainda não foi lido."
    )
    usuario: str | None = Field(
        description="Quem lançou (nomeusuario). Só as notas de saída trazem."
    )
    coi: int
    operacao: str | None = Field(description="Nome do COI no ERP.")
    categoria: CategoriaMovimento
    afeta: bool | None = Field(description=_DESCRICAO_AFETA)
    itens: int
    valor: Decimal | None = Field(description="Soma do valor dos itens, com o sinal do efeito.")
    destinatario: str | None = Field(
        default=None, description="Nome do destinatário (só nas notas de saída)."
    )
    destino_empresa: str | None = Field(
        default=None,
        description="Código da empresa do grupo com o CNPJ do destinatário (outra que não a "
        "da nota). null: o destinatário não é do grupo.",
    )
    empresa_errada: bool = Field(
        default=False,
        description="Nota de saída, fora as transferências, com o CNPJ de outra empresa do "
        "grupo como destinatário: foi emitida na empresa errada e tem que ser cancelada.",
    )


class PaginaNotasLivro(BaseModel):
    total: int
    pagina: int
    tamanho_pagina: int
    total_paginas: int
    data_inicial: date
    data_final: date
    notas: list[NotaLivro] = Field(description="Do mais recente (dia e hora) para o mais antigo.")


class ItemNotaLivro(BaseModel):
    sequencia: str | None
    id_produto: str
    id_subproduto: str
    descricao: str | None
    quantidade: Decimal | None = Field(description="Efeito no estoque: entrada +, saída -.")
    valor: Decimal | None


class MovimentoExtrato(BaseModel):
    dia: date
    coi: int
    operacao: str | None
    categoria: CategoriaMovimento
    afeta: bool | None = Field(description=_DESCRICAO_AFETA)
    id_planilha: str = Field(description="Documento (IDPLANILHA).")
    sequencia: str | None
    quantidade: Decimal | None
    valor: Decimal | None
    saldo_fim_dia: Decimal | None = Field(
        description="Saldo reconstruído no fim do dia: saldo atual menos o efeito dos dias "
        "seguintes (só COIs que mexem no estoque)."
    )


class TotalCategoriaExtrato(BaseModel):
    categoria: CategoriaMovimento
    afeta: bool | None
    itens: int
    quantidade: Decimal


class ExtratoProduto(BaseModel):
    empresa: EmpresaResumo
    id_produto: str
    id_subproduto: str
    descricao: str | None
    data_inicial: date
    data_final: date
    saldo_atual: Decimal | None = Field(description="Saldo atual do ERP nesta empresa.")
    saldo_inicial: Decimal | None = Field(description="Reconstruído, antes do 1º dia.")
    saldo_final: Decimal | None = Field(description="Reconstruído, no fim do último dia.")
    entradas: Decimal
    saidas: Decimal = Field(description="Negativa.")
    por_categoria: list[TotalCategoriaExtrato]
    total_itens: int
    limite: int = Field(description="Máximo de itens devolvidos (os mais recentes).")
    itens: list[MovimentoExtrato] = Field(description="Do mais recente para o mais antigo.")
    dias_sem_leitura: list[date] = Field(
        description="Dias, do início do período até hoje, ainda não lidos: com algum, o saldo "
        "reconstruído pode estar errado."
    )


class TotaisBalanco(BaseModel):
    perda: Decimal = Field(description="Soma dos ajustes negativos dos itens (negativa).")
    ganho: Decimal = Field(description="Soma dos ajustes positivos dos itens.")
    resultado: Decimal = Field(description="Perda + ganho.")
    produtos_com_falta: int
    produtos_com_sobra: int
    itens: int = Field(description="Itens lançados nos balanços.")
    balancos: int = Field(description="Dias × loja com balanço.")


class LojaBalanco(TotaisBalanco):
    empresa: EmpresaResumo


class AjusteProduto(BaseModel):
    empresa: EmpresaResumo
    id_produto: str
    id_subproduto: str
    descricao: str | None
    quantidade: Decimal = Field(description="Ajuste líquido no período.")
    valor: Decimal = Field(description="Quantidade × custo médio dos lançamentos.")


class ParTransferencia(BaseModel):
    id_produto: str
    id_subproduto: str
    descricao: str | None
    loja_falta: EmpresaResumo
    quantidade_falta: Decimal
    loja_sobra: EmpresaResumo
    quantidade_sobra: Decimal
    quantidade: Decimal = Field(description="Casada: o menor dos dois lados.")
    valor: Decimal = Field(description="Quantidade casada × custo unitário da falta.")


class Recontagem(BaseModel):
    empresa: EmpresaResumo
    id_produto: str
    id_subproduto: str
    descricao: str | None
    marca: str | None
    contagens: int = Field(description="Documentos de balanço com o produto na loja.")
    dias: list[date] = Field(description="Dias com contagem, do mais antigo ao mais recente.")
    quantidade: Decimal = Field(description="Ajuste líquido no período.")
    valor: Decimal = Field(description="Soma do valor dos itens, a custo.")


class MarcaRecontagem(BaseModel):
    marca: str
    produtos: int = Field(description="Produtos recontados da marca (antes do filtro de marca).")


class Recontagens(BaseModel):
    data_inicial: date
    data_final: date
    mais_de: int
    desde: date | None
    total: int = Field(description="Produtos no filtro; a lista traz até `limite`.")
    limite: int
    itens: list[Recontagem]
    marcas: list[MarcaRecontagem] = Field(
        description="Marcas dos recontados com os outros filtros, para escolher; da que tem "
        "mais produtos para a que tem menos."
    )


class ResumoBalancos(BaseModel):
    data_inicial: date
    data_final: date
    totais: TotaisBalanco
    por_loja: list[LojaBalanco]
    eventos: list[ResumoMovimentosDia] = Field(description="Um por loja e dia de balanço.")
    maiores_perdas: list[AjusteProduto]
    maiores_ganhos: list[AjusteProduto]
    transferencias_provaveis: list[ParTransferencia] = Field(
        description="Mesmo produto com falta numa loja e sobra em outra no período (indício "
        "de transferência errada), do maior valor para o menor."
    )
    valor_transferencias_provaveis: Decimal = Field(
        description="Soma do valor casado de todos os pares (não só os listados)."
    )
    locais_perda: list[LocalPerda] = Field(
        description="Estoque parado em locais de perda (ex.: avaria), a custo. É o valor "
        "de hoje, não do período, e fica fora dos totais do balanço."
    )


TipoAvulsa = Literal["entrada_avulsa", "saida_avulsa"]


class MotivoAvulsa(BaseModel):
    codigo: str
    rotulo: str
    tipos: list[TipoAvulsa] = Field(description="Em quais avulsas o motivo vale.")
    exige_observacao: bool


class JustificativaAvulsa(BaseModel):
    motivo: str
    motivo_rotulo: str
    observacao: str | None
    usuario_nome: str = Field(description="Quem justificou por último.")
    atualizado_em: DataUTC
    pelo_vinculo: bool = Field(
        description="Gravada ao relacionar com outra avulsa; desfazer o vínculo a apaga."
    )


class VinculoAvulsa(BaseModel):
    id_planilha: str = Field(description="O outro documento do par.")
    dia: date | None
    tipo: TipoAvulsa
    usuario_nome: str = Field(description="Quem relacionou.")
    criado_em: DataUTC


class RegraAlerta(BaseModel):
    codigo: str
    rotulo: str
    janela_dias: int | None = Field(
        description="Até quantos dias antes da entrada; null: sem limite."
    )


class AlertaAvulsa(BaseModel):
    regra: str = Field(description="Código da regra (`regras` da página): balanco, uso_consumo...")
    id_produto: str
    id_subproduto: str
    descricao: str | None
    dia: date = Field(description="Dia do movimento que tirou o produto.")
    id_planilha: str = Field(description="Documento do movimento (balanço, nota de uso e consumo).")
    numero: str | None = Field(description="Número da nota, quando o ERP tem cabeçalho.")
    operacao: str | None = Field(description="Operação do ERP (DESCROPERACAO).")
    quantidade: Decimal = Field(description="O que saiu (negativa).")
    valor: Decimal


class CandidatoVinculo(BaseModel):
    id_planilha: str
    dia: date
    tipo: TipoAvulsa
    itens: int
    quantidade: Decimal
    valor: Decimal
    em_comum: int = Field(description="Produtos em comum com o documento.")
    exato: bool = Field(description="Mesmos produtos e mesmas quantidades (sem o sinal).")
    id_produto: str = Field(description="O primeiro produto em comum.")
    id_subproduto: str
    descricao: str | None
    justificativa: JustificativaAvulsa | None


class NovoVinculoAvulsa(BaseModel):
    id_planilha: str = Field(max_length=50, description="A outra avulsa (do outro tipo).")


class DocumentoAvulso(BaseModel):
    empresa: EmpresaResumo
    id_planilha: str = Field(description="Documento (IDPLANILHA) no ERP.")
    dia: date
    tipo: TipoAvulsa
    itens: int
    quantidade: Decimal = Field(description="Efeito no estoque: entrada +, saída −.")
    valor: Decimal
    id_produto: str = Field(description="O primeiro produto do documento.")
    id_subproduto: str
    descricao: str | None
    exige_justificativa: bool = Field(description="Sem dia de corte, ou do corte em diante.")
    justificativa: JustificativaAvulsa | None
    vinculo: VinculoAvulsa | None = Field(description="A avulsa do outro tipo relacionada.")
    alertas: list[AlertaAvulsa] = Field(
        description="Só nas entradas: produtos que um movimento da loja (o último balanço, "
        "uma saída para uso e consumo...) tirou do estoque antes da entrada."
    )


class PendenciasAvulsas(BaseModel):
    documentos: int
    valor: Decimal = Field(description="Valor movimentado: soma sem sinal de entradas e saídas.")


class CorteAvulsas(BaseModel):
    justificar_desde: date | None = Field(
        description="Dia de corte: dele em diante é obrigatório. null: todas são obrigatórias."
    )
    definido_por: str | None = Field(
        description="Quem mudou na tela; null: vem de JUSTIFICAR_AVULSAS_DESDE (.env)."
    )
    atualizado_em: DataUTC | None


class NovoCorteAvulsas(BaseModel):
    justificar_desde: date | None = Field(description="null: sem corte, todas são cobradas.")


class PaginaDocumentosAvulsos(BaseModel):
    data_inicial: date
    data_final: date
    justificar_desde: date | None = Field(
        description="Dia de corte: dele em diante é obrigatório. null: todas são obrigatórias."
    )
    situacao: Literal["pendente", "justificada", "todas"]
    pagina: int
    tamanho_pagina: int
    total: int
    total_paginas: int
    documentos: list[DocumentoAvulso]
    pendentes: PendenciasAvulsas = Field(description="Sem justificativa, com os filtros.")
    pendentes_desde_o_corte: PendenciasAvulsas = Field(
        description="Sem justificativa do dia de corte (sem corte: de todo o livro) até hoje "
        "(empresa e tipo do filtro)."
    )
    justificadas: int = Field(description="Com justificativa, com os filtros.")
    motivos: list[MotivoAvulsa]
    regras: list[RegraAlerta] = Field(description="Os avisos que as entradas podem ter.")
    corte: CorteAvulsas


class NovaJustificativaAvulsa(BaseModel):
    motivo: str = Field(max_length=30)
    observacao: str | None = Field(None, max_length=2000)


class RefDocumentoAvulso(BaseModel):
    empresa: str = Field(max_length=20, description="Código da empresa.")
    id_planilha: str = Field(max_length=50, description="Documento (IDPLANILHA).")


class JustificativaEmLote(NovaJustificativaAvulsa):
    documentos: list[RefDocumentoAvulso] = Field(min_length=1, max_length=200)


class ResultadoLoteJustificativas(BaseModel):
    justificados: int


class ExcecaoCobertura(BaseModel):
    empresa: EmpresaResumo
    id_produto: str = Field(examples=["9798"])
    id_subproduto: str = Field(examples=["9798"])
    descricao: str | None
    motivo: str | None = Field(examples=["Só fica no depósito"])
    usuario_nome: str = Field(description="Quem incluiu.")
    criado_em: DataUTC


class NovaExcecaoCobertura(BaseModel):
    empresa: str = Field(max_length=20, description="Código da empresa.", examples=["1"])
    codigo: str = Field(
        min_length=1,
        max_length=50,
        description="Código do item, ou da grade (inclui todos os itens dela).",
        examples=["9798"],
    )
    motivo: str | None = Field(None, max_length=200, examples=["Loja sem estrutura"])


class ResultadoExcecaoCobertura(BaseModel):
    incluidos: int = Field(description="Itens incluídos agora (os que já eram exceção ficam).")
