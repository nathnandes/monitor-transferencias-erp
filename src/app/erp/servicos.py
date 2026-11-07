from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

from app.erp.config import ErpApiSettings, get_erpapi_settings
from app.erp.contratos import ClienteErpApi
from app.erp.schemas import Clausula, Operador, RequisicaoPaginada, RespostaPaginada

ROTA_CAD_LOJAS = "/erpcore-service/cad_lojas"
ROTA_SALDO_ESTOQUE_EMPRESA = "/erpcore-service/produtos_saldo_estoque_empresa"

ROTA_NOTAS_SAIDA = "/erpcore-service/documentos_fiscais_saida_completo"
ROTA_ITENS_SAIDA = "/erpcore-service/itens_documentos_fiscais_saida_completo"
ROTA_NOTAS_ENTRADA = "/erpcore-service/documentos_fiscais_entrada_completo"
ROTA_ITENS_ENTRADA = "/erpcore-service/itens_documentos_fiscais_entrada_completo"

ROTA_PRECOS_CUSTOS = "/erpcore-service/precos_custos_produtos_empresa"
ROTA_CAD_PRODUTOS = "/erpcore-service/cad_produtos"
ROTA_RECEBIMENTOS_SAIDA = "/erpcore-service/recebimentos_documentos_fiscais_saida"


CAMPO_FILTRO_EMPRESA = "idempresa"


FUSO_PADRAO = ZoneInfo("America/Porto_Velho")
FORMATO_DATA_FILTRO = "%Y-%m-%d %H:%M:%S"


class RegistroInvalidoError(ValueError):
    pass


@dataclass(frozen=True)
class Loja:
    id_erp: str
    nome: str
    bairro: str | None
    cnpj: str | None = None


@dataclass(frozen=True)
class SaldoEstoque:
    id_empresa: str
    id_produto: str
    id_subproduto: str
    id_local_estoque: str
    descricao_local_estoque: str | None
    utiliza_lote: bool | None

    descricao_lote: str
    permite_estoque_negativo: bool | None
    saldo_atual: Decimal | None
    saldo_reservado: Decimal | None
    saldo_disponivel: Decimal | None
    data_alteracao: datetime | None

    inativo_erp: bool | None = None

    @property
    def chave(self) -> tuple[str, str, str, str]:
        return (self.id_produto, self.id_subproduto, self.id_local_estoque, self.descricao_lote)


@dataclass(frozen=True)
class ItemNota:
    id_empresa: str
    id_planilha: str
    id_operacao: int | None
    id_produto: str
    id_subproduto: str | None
    sequencia: str | None
    quantidade: Decimal | None
    descricao_produto: str | None
    data_movimento: datetime | None

    valor_liquido: Decimal | None = None
    valor_desconto: Decimal | None = None
    cfop: str | None = None
    id_vendedor: str | None = None

    descricao_operacao: str | None = None


@dataclass(frozen=True)
class Nota:
    id_empresa: str
    id_planilha: str
    numero: str | None
    serie: str | None
    chave_nfe: str | None
    cnpj_cpf: str | None
    data_emissao: datetime | None
    data_movimento: datetime | None
    cancelada: bool
    data_alteracao: datetime | None

    modelo: str | None = None
    valor_contabil: Decimal | None = None

    usuario: str | None = None

    nome: str | None = None


@dataclass(frozen=True)
class Recebimento:
    id_empresa: str
    id_planilha: str
    id_titulo: str | None
    parcela: str | None
    serie: str | None
    id_forma: int | None
    forma: str | None
    valor: Decimal | None
    data_movimento: datetime | None
    valor_pago: Decimal | None = None
    valor_pendente: Decimal | None = None
    juros: Decimal | None = None
    desconto: Decimal | None = None

    dia_lancamento: date | None = None
    vencimento: date | None = None
    dia_pagamento: date | None = None


@dataclass(frozen=True)
class PrecoProduto:
    id_empresa: str
    id_produto: str
    id_subproduto: str
    preco_varejo: Decimal | None
    preco_promocao_varejo: Decimal | None
    inicio_promocao_varejo: datetime | None
    fim_promocao_varejo: datetime | None
    preco_atacado: Decimal | None
    preco_promocao_atacado: Decimal | None
    inicio_promocao_atacado: datetime | None
    fim_promocao_atacado: datetime | None
    custo_reposicao: Decimal | None
    custo_gerencial: Decimal | None
    custo_nota_fiscal: Decimal | None
    data_alteracao: datetime | None
    inativo_erp: bool | None

    @property
    def chave(self) -> tuple[str, str]:
        return (self.id_produto, self.id_subproduto)


@dataclass(frozen=True)
class Produto:
    id_produto: str
    id_subproduto: str
    descricao: str | None
    descricao_resumida: str | None
    referencia: str | None
    codigo_barras: str | None
    embalagem_saida: str | None
    marca: str | None
    divisao: str | None
    secao: str | None
    grupo: str | None
    subgrupo: str | None
    bloqueado_venda: bool | None
    inativo_erp: bool | None
    data_alteracao: datetime | None

    @property
    def chave(self) -> tuple[str, str]:
        return (self.id_produto, self.id_subproduto)


class _Registro:
    def __init__(self, bruto: Mapping[str, Any]) -> None:
        self._campos = {str(k).lower(): v for k, v in bruto.items()}

    def tem(self, campo: str) -> bool:
        return campo in self._campos

    def get(self, campo: str) -> Any:
        return self._campos.get(campo)

    def exigir(self, *campos: str) -> None:
        faltando = [c for c in campos if c not in self._campos]
        if faltando:
            raise RegistroInvalidoError(
                f"campos ausentes: {', '.join(faltando)}; "
                f"campos recebidos: {', '.join(sorted(self._campos)[:30])}"
            )


def _texto(valor: Any, limite: int | None = None) -> str | None:
    if valor is None or isinstance(valor, bool):
        return None
    if isinstance(valor, float) and valor.is_integer():
        valor = int(valor)
    texto = str(valor).strip()
    if not texto:
        return None
    return texto[:limite] if limite else texto


def _id(registro: _Registro, campo: str) -> str:
    valor = _texto(registro.get(campo), 50)
    if valor is None:
        raise RegistroInvalidoError(f"campo '{campo}' vazio")
    return valor


def _decimal(valor: Any, campo: str) -> Decimal | None:
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return None
    if isinstance(valor, bool):
        raise RegistroInvalidoError(f"campo '{campo}' nao e numerico")
    texto = str(valor).strip()
    if "," in texto and "." not in texto:
        texto = texto.replace(",", ".")
    try:
        numero = Decimal(texto)
    except InvalidOperation:
        raise RegistroInvalidoError(f"campo '{campo}' nao e numerico") from None
    if not numero.is_finite():
        raise RegistroInvalidoError(f"campo '{campo}' nao e numerico")
    return numero


_VERDADEIROS = {"S", "SIM", "T", "TRUE", "Y", "1"}
_FALSOS = {"N", "NAO", "NÃO", "F", "FALSE", "0"}


def _flag(valor: Any) -> bool | None:
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, int) and valor in (0, 1):
        return bool(valor)
    if isinstance(valor, str):
        texto = valor.strip().upper()
        if texto in _VERDADEIROS:
            return True
        if texto in _FALSOS:
            return False
    return None


_FORMATOS_DATA = ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y")


def _data(valor: Any, fuso: ZoneInfo = FUSO_PADRAO) -> datetime | None:
    if valor is None or isinstance(valor, bool):
        return None
    data: datetime | None = None
    if isinstance(valor, int | float):
        segundos = valor / 1000 if abs(valor) > 10**11 else valor
        try:
            return datetime.fromtimestamp(segundos, UTC)
        except (OverflowError, OSError, ValueError):
            return None
    texto = str(valor).strip()
    try:
        data = datetime.fromisoformat(texto)
    except ValueError:
        for formato in _FORMATOS_DATA:
            try:
                data = datetime.strptime(texto, formato)
                break
            except ValueError:
                continue
    if data is None:
        return None
    if data.tzinfo is None:
        data = data.replace(tzinfo=fuso)
    return data.astimezone(UTC)


def _dia_local(valor: Any, fuso: ZoneInfo = FUSO_PADRAO) -> date | None:
    data = _data(valor, fuso)
    return data.astimezone(fuso).date() if data is not None else None


_CAMPOS_NOME_LOJA = ("nomefantasia", "fantasia", "nome", "razaosocial")


def mapear_loja(bruto: Mapping[str, Any]) -> Loja:
    registro = _Registro(bruto)
    registro.exigir("idempresa")
    id_erp = _id(registro, "idempresa")
    nome = next(
        (n for c in _CAMPOS_NOME_LOJA if (n := _texto(registro.get(c), 200)) is not None),
        f"Empresa {id_erp}",
    )
    return Loja(
        id_erp=id_erp,
        nome=nome,
        bairro=_texto(registro.get("bairro"), 100),
        cnpj=somente_digitos(registro.get("cnpj")),
    )


def somente_digitos(valor: Any) -> str | None:
    if valor is None or isinstance(valor, bool):
        return None
    if isinstance(valor, int | float):
        return str(int(valor)).zfill(14)
    digitos = "".join(c for c in str(valor) if c.isdigit())
    return digitos or None


def _inteiro(valor: Any, campo: str) -> int | None:
    texto = _texto(valor)
    if texto is None:
        return None
    try:
        return int(Decimal(texto))
    except InvalidOperation:
        raise RegistroInvalidoError(f"campo '{campo}' nao e inteiro") from None


def mapear_item_nota(bruto: Mapping[str, Any], fuso: ZoneInfo = FUSO_PADRAO) -> ItemNota:
    registro = _Registro(bruto)
    registro.exigir("idempresa", "idplanilha", "idoperacao", "idproduto")
    return ItemNota(
        id_empresa=_id(registro, "idempresa"),
        id_planilha=_id(registro, "idplanilha"),
        id_operacao=_inteiro(registro.get("idoperacao"), "idoperacao"),
        id_produto=_id(registro, "idproduto"),
        id_subproduto=_texto(registro.get("idsubproduto"), 50),
        sequencia=_texto(registro.get("numsequencia"), 20),
        quantidade=_decimal(registro.get("qtdproduto"), "qtdproduto"),
        descricao_produto=_texto(registro.get("descrproduto"), 300),
        data_movimento=_data(registro.get("dtmovimento"), fuso),
        valor_liquido=_decimal(registro.get("valtotliquido"), "valtotliquido"),
        valor_desconto=_decimal(registro.get("valdescontopro"), "valdescontopro"),
        cfop=_texto(registro.get("cfop"), 10),
        id_vendedor=_texto(registro.get("idvendedor"), 50),
        descricao_operacao=_texto(registro.get("descroperacao"), 100),
    )


def mapear_nota(bruto: Mapping[str, Any], fuso: ZoneInfo = FUSO_PADRAO) -> Nota:
    registro = _Registro(bruto)
    registro.exigir("idempresa", "idplanilha")
    return Nota(
        id_empresa=_id(registro, "idempresa"),
        id_planilha=_id(registro, "idplanilha"),
        numero=_texto(registro.get("numnota"), 20),
        serie=_texto(registro.get("serienota"), 10),
        chave_nfe=somente_digitos(registro.get("chavenfe") or registro.get("chave")),
        cnpj_cpf=somente_digitos(registro.get("cnpjcpf")),
        data_emissao=_data(registro.get("dtemissao"), fuso),
        data_movimento=_data(registro.get("dtmovimento"), fuso),
        cancelada=(
            _flag(registro.get("flagnotacancel")) is True
            or _flag(registro.get("notacancelada")) is True
        ),
        data_alteracao=_data(registro.get("dtalteracao"), fuso),
        modelo=_texto(registro.get("modelo"), 10),
        valor_contabil=_decimal(registro.get("valcontabil"), "valcontabil"),
        usuario=_texto(registro.get("nomeusuario"), 100),
        nome=_texto(registro.get("nome"), 200),
    )


def mapear_recebimento(bruto: Mapping[str, Any], fuso: ZoneInfo = FUSO_PADRAO) -> Recebimento:
    registro = _Registro(bruto)
    registro.exigir("idempresa", "idplanilha", "valtitulo")
    return Recebimento(
        id_empresa=_id(registro, "idempresa"),
        id_planilha=_id(registro, "idplanilha"),
        id_titulo=_texto(registro.get("idtitulo"), 20),
        parcela=_texto(registro.get("digitotitulo"), 10),
        serie=_texto(registro.get("serienota"), 10),
        id_forma=_inteiro(registro.get("idrecebimento"), "idrecebimento"),
        forma=_texto(registro.get("descrrecebimento"), 60),
        valor=_decimal(registro.get("valtitulo"), "valtitulo"),
        data_movimento=_data(registro.get("dtmovimento"), fuso),
        valor_pago=_decimal(registro.get("valtitulopago"), "valtitulopago"),
        valor_pendente=_decimal(registro.get("valtitulopendente"), "valtitulopendente"),
        juros=_decimal(registro.get("valjuroscobrado"), "valjuroscobrado"),
        desconto=_decimal(registro.get("valdescconcedidotitulo"), "valdescconcedidotitulo"),
        dia_lancamento=_dia_local(registro.get("dtmovimento"), fuso),
        vencimento=_dia_local(registro.get("dtvencimento"), fuso),
        dia_pagamento=_dia_local(registro.get("dtultimopagamento"), fuso),
    )


def nome_da_pessoa(brutos: Iterable[Mapping[str, Any]]) -> str | None:
    nomes = Counter(nome for bruto in brutos if (nome := _texto(_Registro(bruto).get("nome"), 200)))
    return nomes.most_common(1)[0][0] if nomes else None


def mapear_saldo(bruto: Mapping[str, Any], fuso: ZoneInfo = FUSO_PADRAO) -> SaldoEstoque:
    registro = _Registro(bruto)

    registro.exigir(
        "idempresa",
        "idproduto",
        "idsubproduto",
        "idlocalestoque",
        "qtdsaldoatual",
        "qtdsaldodisponivel",
    )
    return SaldoEstoque(
        id_empresa=_id(registro, "idempresa"),
        id_produto=_id(registro, "idproduto"),
        id_subproduto=_id(registro, "idsubproduto"),
        id_local_estoque=_id(registro, "idlocalestoque"),
        descricao_local_estoque=_texto(registro.get("descrlocalestoque"), 200),
        utiliza_lote=_flag(registro.get("flaglote")),
        descricao_lote=_texto(registro.get("descrlote"), 200) or "",
        permite_estoque_negativo=_flag(registro.get("flagestnegativo")),
        saldo_atual=_decimal(registro.get("qtdsaldoatual"), "qtdsaldoatual"),
        saldo_reservado=_decimal(registro.get("qtdsaldoreserva"), "qtdsaldoreserva"),
        saldo_disponivel=_decimal(registro.get("qtdsaldodisponivel"), "qtdsaldodisponivel"),
        data_alteracao=_data(registro.get("dtalteracao"), fuso),
        inativo_erp=_flag(registro.get("flaginativo")),
    )


def mapear_preco(bruto: Mapping[str, Any], fuso: ZoneInfo = FUSO_PADRAO) -> PrecoProduto:
    registro = _Registro(bruto)
    registro.exigir("idempresa", "idproduto", "idsubproduto")

    def valor(campo: str) -> Decimal | None:
        return _decimal(registro.get(campo), campo)

    def data(campo: str) -> datetime | None:
        return _data(registro.get(campo), fuso)

    return PrecoProduto(
        id_empresa=_id(registro, "idempresa"),
        id_produto=_id(registro, "idproduto"),
        id_subproduto=_id(registro, "idsubproduto"),
        preco_varejo=valor("valprecovarejo"),
        preco_promocao_varejo=valor("valpromvarejo"),
        inicio_promocao_varejo=data("dtinipromocaovar"),
        fim_promocao_varejo=data("dtfimpromocaovar"),
        preco_atacado=valor("valprecoatacado"),
        preco_promocao_atacado=valor("valpromatacado"),
        inicio_promocao_atacado=data("dtinipromocaoatac"),
        fim_promocao_atacado=data("dtfimpromocaoatac"),
        custo_reposicao=valor("valcustorepos"),
        custo_gerencial=valor("custogerencial"),
        custo_nota_fiscal=valor("custonotafiscal"),
        data_alteracao=data("dtalteracao"),
        inativo_erp=_flag(registro.get("flaginativo")),
    )


def mapear_produto(bruto: Mapping[str, Any], fuso: ZoneInfo = FUSO_PADRAO) -> Produto:
    registro = _Registro(bruto)
    registro.exigir("idproduto", "idsubproduto")
    return Produto(
        id_produto=_id(registro, "idproduto"),
        id_subproduto=_id(registro, "idsubproduto"),
        descricao=_texto(registro.get("descrcomproduto"), 200),
        descricao_resumida=_texto(registro.get("descrresproduto"), 100),
        referencia=_texto(registro.get("referencia"), 50),
        codigo_barras=_texto(registro.get("nrcodbarprod"), 20),
        embalagem_saida=_texto(registro.get("embalagemsaida"), 10),
        marca=_texto(registro.get("descricao"), 100),
        divisao=_texto(registro.get("descrdivisao"), 100),
        secao=_texto(registro.get("descrsecao"), 100),
        grupo=_texto(registro.get("descrgrupo"), 100),
        subgrupo=_texto(registro.get("descrsubgrupo"), 100),
        bloqueado_venda=_flag(registro.get("flagbloqueiavenda")),
        inativo_erp=_flag(registro.get("flaginativo")),
        data_alteracao=_data(registro.get("dtalteracao"), fuso),
    )


Filtros = tuple[Clausula, ...]


def descrever(filtros: Filtros) -> str:
    return ", ".join(f"{c.campo} {c.operador.value} {c.valor}" for c in filtros)


class ServicosErp:
    def __init__(
        self,
        cliente: ClienteErpApi,
        *,
        campo_registros: str,
        max_paginas: int,
        fuso: ZoneInfo = FUSO_PADRAO,
    ) -> None:
        self._cliente = cliente
        self._campo_registros = campo_registros
        self.max_paginas = max_paginas
        self.fuso = fuso

    def autenticar(self) -> None:
        self._cliente.autenticar()

    def pagina_lojas(self, pagina: int) -> RespostaPaginada:
        return self._cliente.consultar_pagina(
            ROTA_CAD_LOJAS,
            RequisicaoPaginada(pagina=pagina),
            campo_registros=self._campo_registros,
        )

    def pagina_saldo_estoque(
        self, id_empresa: str, pagina: int, filtros: Filtros = ()
    ) -> RespostaPaginada:
        empresa = Clausula(campo=CAMPO_FILTRO_EMPRESA, operador=Operador.IGUAL, valor=id_empresa)
        return self._cliente.consultar_pagina(
            ROTA_SALDO_ESTOQUE_EMPRESA,
            RequisicaoPaginada(pagina=pagina, clausulas=(empresa, *filtros)),
            campo_registros=self._campo_registros,
        )

    def filtro_alterado_desde(self, desde: datetime) -> Filtros:
        valor = desde.astimezone(self.fuso).strftime(FORMATO_DATA_FILTRO)
        return (Clausula(campo="dtalteracao", operador=Operador.MAIOR_IGUAL, valor=valor),)

    @staticmethod
    def filtro_com_reserva() -> Filtros:
        return (Clausula(campo="qtdsaldoreserva", operador=Operador.MAIOR, valor="0"),)

    @staticmethod
    def filtro_produto(id_produto: str, id_subproduto: str) -> Filtros:
        return (
            Clausula(campo="idproduto", operador=Operador.IGUAL, valor=id_produto),
            Clausula(campo="idsubproduto", operador=Operador.IGUAL, valor=id_subproduto),
        )

    def _pagina(self, rota: str, pagina: int, clausulas: Filtros) -> RespostaPaginada:
        return self._cliente.consultar_pagina(
            rota,
            RequisicaoPaginada(pagina=pagina, clausulas=clausulas),
            campo_registros=self._campo_registros,
        )

    def pagina_itens_nota(
        self, saida: bool, id_empresa: str, coi: int, dia: date, pagina: int
    ) -> RespostaPaginada:
        return self._pagina(
            ROTA_ITENS_SAIDA if saida else ROTA_ITENS_ENTRADA,
            pagina,
            (
                Clausula(campo=CAMPO_FILTRO_EMPRESA, operador=Operador.IGUAL, valor=id_empresa),
                Clausula(campo="idoperacao", operador=Operador.IGUAL, valor=str(coi)),
                Clausula(campo="dtmovimento", operador=Operador.IGUAL, valor=dia.isoformat()),
            ),
        )

    def pagina_itens_dia(
        self, saida: bool, id_empresa: str, dia: date, coi_acima_de: int, pagina: int
    ) -> RespostaPaginada:
        return self._pagina(
            ROTA_ITENS_SAIDA if saida else ROTA_ITENS_ENTRADA,
            pagina,
            (
                Clausula(campo=CAMPO_FILTRO_EMPRESA, operador=Operador.IGUAL, valor=id_empresa),
                Clausula(campo="dtmovimento", operador=Operador.IGUAL, valor=dia.isoformat()),
                Clausula(campo="idoperacao", operador=Operador.MAIOR, valor=str(coi_acima_de)),
            ),
        )

    def pagina_itens_planilha(
        self, saida: bool, id_empresa: str, id_planilha: str, pagina: int
    ) -> RespostaPaginada:
        return self._pagina(
            ROTA_ITENS_SAIDA if saida else ROTA_ITENS_ENTRADA,
            pagina,
            (
                Clausula(campo=CAMPO_FILTRO_EMPRESA, operador=Operador.IGUAL, valor=id_empresa),
                Clausula(campo="idplanilha", operador=Operador.IGUAL, valor=id_planilha),
            ),
        )

    def pagina_nota(
        self, saida: bool, id_empresa: str, id_planilha: str, pagina: int
    ) -> RespostaPaginada:
        return self._pagina(
            ROTA_NOTAS_SAIDA if saida else ROTA_NOTAS_ENTRADA,
            pagina,
            (
                Clausula(campo=CAMPO_FILTRO_EMPRESA, operador=Operador.IGUAL, valor=id_empresa),
                Clausula(campo="idplanilha", operador=Operador.IGUAL, valor=id_planilha),
            ),
        )

    def pagina_notas_emitidas(
        self, saida: bool, id_empresa: str, dia: date, pagina: int
    ) -> RespostaPaginada:
        return self._pagina(
            ROTA_NOTAS_SAIDA if saida else ROTA_NOTAS_ENTRADA,
            pagina,
            (
                Clausula(campo=CAMPO_FILTRO_EMPRESA, operador=Operador.IGUAL, valor=id_empresa),
                Clausula(campo="dtemissao", operador=Operador.IGUAL, valor=dia.isoformat()),
            ),
        )

    def pagina_notas_para_cnpj(self, id_empresa: str, cnpj: str, pagina: int) -> RespostaPaginada:
        return self._pagina(
            ROTA_NOTAS_SAIDA,
            pagina,
            (
                Clausula(campo=CAMPO_FILTRO_EMPRESA, operador=Operador.IGUAL, valor=id_empresa),
                Clausula(campo="cnpjcpf", operador=Operador.IGUAL, valor=cnpj),
            ),
        )

    def pagina_notas_da_pessoa(self, saida: bool, id_clifor: str, pagina: int) -> RespostaPaginada:
        return self._pagina(
            ROTA_NOTAS_SAIDA if saida else ROTA_NOTAS_ENTRADA,
            pagina,
            (Clausula(campo="idclifor", operador=Operador.IGUAL, valor=id_clifor),),
        )

    def pagina_recebimentos_saida(
        self, id_empresa: str, dia: date, pagina: int, *, pagos: bool = False
    ) -> RespostaPaginada:
        campo = "dtultimopagamento" if pagos else "dtmovimento"
        return self._pagina(
            ROTA_RECEBIMENTOS_SAIDA,
            pagina,
            (
                Clausula(campo=CAMPO_FILTRO_EMPRESA, operador=Operador.IGUAL, valor=id_empresa),
                Clausula(campo=campo, operador=Operador.IGUAL, valor=dia.isoformat()),
            ),
        )

    def pagina_entrada_por_chave(self, chave_nfe: str, pagina: int) -> RespostaPaginada:
        return self._pagina(
            ROTA_NOTAS_ENTRADA,
            pagina,
            (Clausula(campo="chavenfe", operador=Operador.IGUAL, valor=chave_nfe),),
        )

    def pagina_precos(
        self, id_empresa: str, pagina: int, filtros: Filtros = ()
    ) -> RespostaPaginada:
        empresa = Clausula(campo=CAMPO_FILTRO_EMPRESA, operador=Operador.IGUAL, valor=id_empresa)
        return self._pagina(ROTA_PRECOS_CUSTOS, pagina, (empresa, *filtros))

    def pagina_produtos(self, pagina: int, filtros: Filtros = ()) -> RespostaPaginada:
        return self._pagina(ROTA_CAD_PRODUTOS, pagina, filtros)

    def close(self) -> None:
        self._cliente.close()


def criar_servicos(settings: ErpApiSettings | None = None) -> ServicosErp:
    from app.erp.client import ErpApiClient

    settings = settings or get_erpapi_settings()
    return ServicosErp(
        ErpApiClient(settings),
        campo_registros=settings.campo_registros,
        max_paginas=settings.max_pages,
        fuso=ZoneInfo(settings.fuso),
    )
