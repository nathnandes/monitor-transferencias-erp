import io
import re
from collections.abc import Sequence
from zoneinfo import ZoneInfo

from openpyxl import Workbook
from openpyxl.chart import PieChart, Reference
from openpyxl.chart.label import DataLabelList
from openpyxl.chart.layout import Layout, ManualLayout
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from app.services.vendas import (
    ROTULO_CANAL,
    DescontoNota,
    FormaPagamento,
    eh_vendedor_generico,
)

FORMATO_MOEDA = '"R$" #,##0.00'
FORMATO_INTEIRO = "#,##0"
FORMATO_PERCENTUAL = "0.0%"

_CABECALHO = ("Forma de pagamento", "Valor recebido", "Quantidade (parcelas)", "Participação")
_FUNDO_CABECALHO = PatternFill("solid", fgColor="1F2933")
_LINHA_TOTAL = Border(top=Side(style="thin", color="1F2933"))


def planilha_formas_pagamento(
    formas: Sequence[FormaPagamento], descricao_filtro: Sequence[str]
) -> bytes:
    livro = Workbook()
    padrao = livro.active
    if padrao is not None:
        livro.remove(padrao)
    aba: Worksheet = livro.create_sheet("Formas de pagamento")

    aba["A1"] = "Formas de pagamento"
    aba["A1"].font = Font(bold=True, size=14)
    for i, texto in enumerate(descricao_filtro, start=2):
        aba.cell(row=i, column=1, value=texto).font = Font(color="5B6470")

    linha_cabecalho = len(descricao_filtro) + 3
    for coluna, titulo in enumerate(_CABECALHO, start=1):
        cabecalho = aba.cell(row=linha_cabecalho, column=coluna, value=titulo)
        cabecalho.font = Font(bold=True, color="FFFFFF")
        cabecalho.fill = _FUNDO_CABECALHO
        cabecalho.alignment = Alignment(horizontal="left" if coluna == 1 else "right")

    primeira = linha_cabecalho + 1
    ultima = linha_cabecalho + len(formas)
    linha_total = ultima + 1
    for n, forma in enumerate(formas):
        linha = primeira + n
        aba.cell(row=linha, column=1, value=forma.forma.strip().capitalize())
        aba.cell(row=linha, column=2, value=float(forma.valor)).number_format = FORMATO_MOEDA
        aba.cell(row=linha, column=3, value=forma.parcelas).number_format = FORMATO_INTEIRO

        participacao = aba.cell(
            row=linha, column=4, value=f"=IF($B${linha_total}=0,0,B{linha}/$B${linha_total})"
        )
        participacao.number_format = FORMATO_PERCENTUAL

    aba.cell(row=linha_total, column=1, value="Total")
    if formas:
        aba.cell(row=linha_total, column=2, value=f"=SUM(B{primeira}:B{ultima})")
        aba.cell(row=linha_total, column=3, value=f"=SUM(C{primeira}:C{ultima})")
        aba.cell(row=linha_total, column=4, value=f"=IF(B{linha_total}=0,0,1)")
    else:
        for coluna in (2, 3, 4):
            aba.cell(row=linha_total, column=coluna, value=0)
    for coluna, formato in ((2, FORMATO_MOEDA), (3, FORMATO_INTEIRO), (4, FORMATO_PERCENTUAL)):
        aba.cell(row=linha_total, column=coluna).number_format = formato
    for coluna in range(1, 5):
        rodape = aba.cell(row=linha_total, column=coluna)
        rodape.font = Font(bold=True)
        rodape.border = _LINHA_TOTAL

    larguras = (max([len(_CABECALHO[0]), *(len(f.forma) for f in formas)]) + 2, 18, 22, 14)
    for coluna, largura in enumerate(larguras, start=1):
        aba.column_dimensions[get_column_letter(coluna)].width = min(largura, 60)
    aba.freeze_panes = f"A{primeira}"

    if formas:
        grafico = PieChart()
        grafico.title = "Participação no valor recebido"
        grafico.add_data(
            Reference(aba, min_col=2, min_row=linha_cabecalho, max_row=ultima),
            titles_from_data=True,
        )
        grafico.set_categories(Reference(aba, min_col=1, min_row=primeira, max_row=ultima))
        grafico.dataLabels = DataLabelList()
        grafico.dataLabels.showPercent = True
        grafico.dataLabels.showVal = False
        grafico.dataLabels.showCatName = False
        grafico.dataLabels.showSerName = False
        grafico.dataLabels.showLeaderLines = True
        grafico.dataLabels.position = "bestFit"

        assert grafico.legend is not None
        grafico.legend.position = "b"
        grafico.legend.overlay = False

        grafico.layout = Layout(
            manualLayout=ManualLayout(
                layoutTarget="inner", xMode="edge", yMode="edge", x=0.2, y=0.2, w=0.6, h=0.55
            )
        )
        grafico.width = 16
        grafico.height = 12 + 0.55 * len(formas)
        aba.add_chart(grafico, f"F{linha_cabecalho}")

    saida = io.BytesIO()
    livro.save(saida)
    return saida.getvalue()


_FORMATO_DATA = "dd/mm/yyyy"
_FORMATO_HORA = "hh:mm:ss"
_FUNDO_CONFERIR = PatternFill("solid", fgColor="FFF2CC")
_PREFIXO_LOJA = re.compile(r"^4\s*irm[ãa]os\s+materiais\s+de\s+constru[çc][ãa]o\s*", re.IGNORECASE)
_CABECALHO_DESCONTOS = (
    "Data",
    "Hora",
    "Vendedor",
    "Desconto (R$)",
    "Loja",
    "Nota",
    "Canal",
    "Valor da nota (R$)",
    "% de desconto",
)
_CABECALHO_POR_VENDEDOR = (
    "Vendedor",
    "Notas com desconto",
    "Desconto (R$)",
    "Vendido nessas notas (R$)",
    "% de desconto",
)
_OBSERVACOES_DESCONTOS = (
    "Desconto = soma do desconto dos itens da nota, como vem do ERP (valdescontopro), em reais.",
    "Cada linha é uma nota. Notas canceladas e notas sem desconto ficam de fora.",
    "% de desconto = desconto ÷ (valor da nota + desconto).",
    "Hora = a registrada na nota do ERP: se o relógio do caixa estiver errado, ela sai errada.",
    "Linhas em amarelo: desconto igual ou maior que o valor da nota. Vale conferir se foi erro "
    "de digitação de preço. Os valores estão na soma.",
    '"Vendedor" + código: o código não tem nome no cadastro que conseguimos ler. "Sem vendedor": '
    "a nota não tem vendedor ou tem o cadastro genérico do ERP.",
)


def _rotulo_vendedor(nota: DescontoNota) -> str:
    if not nota.id_vendedor or eh_vendedor_generico(nota.nome_vendedor):
        return "Sem vendedor"
    nome = " ".join((nota.nome_vendedor or "").split())
    return nome or f"Vendedor {nota.id_vendedor}"


def _cabecalho(aba: Worksheet, linha: int, titulos: Sequence[str]) -> None:
    for coluna, titulo in enumerate(titulos, start=1):
        celula = aba.cell(row=linha, column=coluna, value=titulo)
        celula.font = Font(bold=True, color="FFFFFF")
        celula.fill = _FUNDO_CABECALHO
        celula.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    aba.row_dimensions[linha].height = 30


def _texto(aba: Worksheet, linha: int, coluna: int, valor: str | None) -> None:
    celula = aba.cell(row=linha, column=coluna)
    celula.value = valor
    if valor is not None:
        celula.data_type = "s"


def _percentual(desconto: str, valor: str) -> str:
    return f"=IF({desconto}+{valor}=0,0,{desconto}/({desconto}+{valor}))"


def _rodape(aba: Worksheet, linha: int, colunas: int) -> None:
    for coluna in range(1, colunas + 1):
        celula = aba.cell(row=linha, column=coluna)
        celula.font = Font(bold=True)
        celula.border = _LINHA_TOTAL


def _aba_notas_com_desconto(
    aba: Worksheet, notas: Sequence[DescontoNota], descricao_filtro: Sequence[str], tz: ZoneInfo
) -> tuple[int, int]:
    aba["A1"] = "Descontos por vendedor"
    aba["A1"].font = Font(bold=True, size=14)
    for i, texto in enumerate(descricao_filtro, start=2):
        aba.cell(row=i, column=1, value=texto).font = Font(color="5B6470")
    linha_cabecalho = len(descricao_filtro) + 3
    _cabecalho(aba, linha_cabecalho, _CABECALHO_DESCONTOS)

    primeira = linha_cabecalho + 1
    centro = Alignment(horizontal="center")
    for n, nota in enumerate(notas):
        linha = primeira + n
        aba.cell(row=linha, column=1, value=nota.dia).number_format = _FORMATO_DATA
        hora = nota.momento.astimezone(tz).time().replace(tzinfo=None) if nota.momento else None
        aba.cell(row=linha, column=2, value=hora).number_format = _FORMATO_HORA
        _texto(aba, linha, 3, _rotulo_vendedor(nota))
        aba.cell(row=linha, column=4, value=float(nota.desconto)).number_format = FORMATO_MOEDA
        _texto(aba, linha, 5, _PREFIXO_LOJA.sub("", nota.loja).strip() or nota.loja)
        _texto(aba, linha, 6, nota.numero_nota)
        _texto(aba, linha, 7, ROTULO_CANAL.get(nota.canal, nota.canal))
        aba.cell(row=linha, column=8, value=float(nota.valor_nota)).number_format = FORMATO_MOEDA
        percentual = aba.cell(row=linha, column=9, value=_percentual(f"D{linha}", f"H{linha}"))
        percentual.number_format = FORMATO_PERCENTUAL
        for coluna in (1, 2, 6):
            aba.cell(row=linha, column=coluna).alignment = centro
        if nota.desconto >= nota.valor_nota:
            for coluna in range(1, 10):
                aba.cell(row=linha, column=coluna).fill = _FUNDO_CONFERIR

    ultima = primeira + len(notas) - 1
    total = ultima + 1
    aba.cell(row=total, column=3, value="Total")
    aba.cell(row=total, column=4, value=f"=SUM(D{primeira}:D{ultima})" if notas else 0)
    aba.cell(row=total, column=8, value=f"=SUM(H{primeira}:H{ultima})" if notas else 0)
    aba.cell(row=total, column=9, value=_percentual(f"D{total}", f"H{total}"))
    _rodape(aba, total, 9)
    aba.cell(row=total, column=4).number_format = FORMATO_MOEDA
    aba.cell(row=total, column=8).number_format = FORMATO_MOEDA
    aba.cell(row=total, column=9).number_format = FORMATO_PERCENTUAL

    aba.freeze_panes = f"A{primeira}"
    aba.auto_filter.ref = f"A{linha_cabecalho}:I{max(ultima, primeira)}"
    for coluna, largura in enumerate((12, 10, 38, 15, 26, 10, 22, 16, 11), start=1):
        aba.column_dimensions[get_column_letter(coluna)].width = largura
    return primeira, ultima


def _aba_por_vendedor(
    aba: Worksheet, notas: Sequence[DescontoNota], primeira: int, ultima: int
) -> None:
    aba["A1"] = "Total de desconto por vendedor"
    aba["A1"].font = Font(bold=True, size=14)
    _cabecalho(aba, 3, _CABECALHO_POR_VENDEDOR)

    soma: dict[str, float] = {}
    for nota in notas:
        rotulo = _rotulo_vendedor(nota)
        soma[rotulo] = soma.get(rotulo, 0.0) + float(nota.desconto)

    def faixa(coluna: str) -> str:
        return f"Descontos!${coluna}${primeira}:${coluna}${ultima}"

    linha = 3
    for rotulo in sorted(soma, key=lambda r: (-soma[r], r)):
        linha += 1
        _texto(aba, linha, 1, rotulo)
        aba.cell(row=linha, column=2, value=f"=COUNTIF({faixa('C')},A{linha})")
        aba.cell(row=linha, column=3, value=f"=SUMIF({faixa('C')},A{linha},{faixa('D')})")
        aba.cell(row=linha, column=4, value=f"=SUMIF({faixa('C')},A{linha},{faixa('H')})")
        aba.cell(row=linha, column=5, value=_percentual(f"C{linha}", f"D{linha}"))
    total = linha + 1
    aba.cell(row=total, column=1, value="Total")
    for coluna, letra in ((2, "B"), (3, "C"), (4, "D")):
        aba.cell(row=total, column=coluna, value=f"=SUM({letra}4:{letra}{linha})" if notas else 0)
    aba.cell(row=total, column=5, value=_percentual(f"C{total}", f"D{total}"))
    _rodape(aba, total, 5)
    for n in range(4, total + 1):
        aba.cell(row=n, column=2).number_format = FORMATO_INTEIRO
        aba.cell(row=n, column=3).number_format = FORMATO_MOEDA
        aba.cell(row=n, column=4).number_format = FORMATO_MOEDA
        aba.cell(row=n, column=5).number_format = FORMATO_PERCENTUAL
    aba.freeze_panes = "A4"
    for coluna, largura in enumerate((38, 12, 16, 18, 11), start=1):
        aba.column_dimensions[get_column_letter(coluna)].width = largura


def planilha_descontos(
    notas: Sequence[DescontoNota], descricao_filtro: Sequence[str], tz: ZoneInfo
) -> bytes:
    livro = Workbook()
    padrao = livro.active
    if padrao is not None:
        livro.remove(padrao)
    primeira, ultima = _aba_notas_com_desconto(
        livro.create_sheet("Descontos"), notas, descricao_filtro, tz
    )
    _aba_por_vendedor(livro.create_sheet("Por vendedor"), notas, primeira, ultima)

    observacoes = livro.create_sheet("Observações")
    observacoes["A1"] = "Observações"
    observacoes["A1"].font = Font(bold=True, size=14)
    for i, texto in enumerate(_OBSERVACOES_DESCONTOS, start=3):
        celula = observacoes.cell(row=i, column=1, value=texto)
        celula.alignment = Alignment(wrap_text=True, vertical="top")
    observacoes.column_dimensions["A"].width = 110

    livro.calculation.fullCalcOnLoad = True
    saida = io.BytesIO()
    livro.save(saida)
    return saida.getvalue()
