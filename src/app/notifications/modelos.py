import re
from collections.abc import Mapping
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import ModeloMensagem
from app.rules.catalogo import CATALOGO

LIMITE_CARACTERES = 4096

LIMITE_MODELO = 3000

_VARIAVEL = re.compile(r"\{(\w+)\}")


@dataclass(frozen=True)
class Variavel:
    chave: str
    rotulo: str
    exemplo: str


@dataclass(frozen=True)
class DefinicaoModelo:
    chave: str
    nome: str
    grupo: str
    descricao: str
    variaveis: tuple[Variavel, ...]
    padrao: str

    @property
    def exemplos(self) -> dict[str, str]:
        return {v.chave: v.exemplo for v in self.variaveis}


_EXEMPLOS_CAMPOS = {
    "nota": "NF 123456",
    "origem": "1 - Matriz",
    "destino": "5 - Depósito 02",
    "emitida_em": "30/10 08:34",
    "emitida_por": "MARIA",
    "valor": "R$ 1.234,50",
    "itens": "12",
    "sem_entrada_ha": "26h",
    "coi": "8038 - SAIDA MERC. EPI UNIFORME FARDAMENTO",
    "coi_saida": "5152",
    "coi_entrada": "1152",
    "problemas": "• COI de entrada 1100 não é o da empresa que recebe",
    "orientacao": "Confira a operação no ERP e corrija a nota.",
    "status": "ERRO",
    "empresa": "1 - Matriz",
    "tipo": "estoque",
    "inicio": "31/10 07:00",
    "erro": "timeout ao consultar o ERP",
    "ultima_conclusao": "31/10 06:10",
    "intervalo": "5 min",
    "usuario": "MARIA",
    "quando": "31/10 08:02",
    "detalhe": "Campos alterados: nome, módulos",
    "ip": "127.0.0.1",
    "alvo": "Loja Matriz",
    "periodo": "novembro/2026",
    "meta": "R$ 500.000,00",
    "realizado": "R$ 512.340,00",
    "percentual": "102%",
    "falta": "R$ 0,00",
    "loja": "MATRIZ",
    "quantidade": "2",
    "total": "15",
    "produtos": "• 12345 LONA AZUL 3X3M: tem 2, mínimo 8 (0,57/dia)\n"
    "• 67890 CIMENTO CP II 50KG: tem 10, mínimo 42 (3/dia)",
}

_AVISO_GERAIS = (
    Variavel("emoji", "Emoji da severidade", "🚨"),
    Variavel("severidade", "Severidade (CRITICAL, ERROR...)", "CRITICAL"),
    Variavel("nivel", "Severidade em português", "crítico"),
    Variavel("agravou", 'Texto "AGRAVOU PARA " quando o alerta piora', ""),
    Variavel("titulo", "Título do alerta", "Transferência NF 123456 com COI ERRADO"),
    Variavel("campos", "Informações marcadas na regra", "Nota: NF 123456\nOrigem: 1 - Matriz"),
    Variavel("desde", "Aberto em", "30/10 08:34"),
    Variavel("id", "Número do alerta", "1234"),
)
_RESOLUCAO_GERAIS = (
    Variavel("titulo", "Título do alerta", "Transferência NF 123456 com COI ERRADO"),
    Variavel("desde", "Aberto em", "30/10 08:34"),
    Variavel("resolvido_em", "Resolvido em", "30/10 11:02"),
    Variavel("id", "Número do alerta", "1234"),
)

PADRAO_AVISO = "{emoji} {agravou}{severidade}: {titulo}\n\n{campos}\n\nDesde {desde} · alerta #{id}"
PADRAO_ATIVIDADE = "{emoji} {titulo}\n\n{campos}"
PADRAO_RESOLUCAO = "✅ RESOLVIDO: {titulo}\n\nAberto em {desde}, resolvido em {resolvido_em}."
PADRAO_RESUMO = (
    "☀️ Resumo de {data}\n\n"
    "Alertas abertos\n{bloco_alertas}\n\n"
    "Transferências\n{bloco_transferencias}\n\n"
    "Vendas de ontem ({ontem})\n{bloco_vendas}\n\n"
    "{bloco_sincronizacao}"
)

_RESUMO_VARIAVEIS = (
    Variavel("data", "Data de hoje", "31/10/2026"),
    Variavel("ontem", "Data de ontem", "30/10"),
    Variavel("bloco_alertas", "Alertas abertos (linhas prontas)", "• 3: 2 críticos, 1 aviso"),
    Variavel("alertas_abertos", "Total de alertas abertos", "3"),
    Variavel(
        "bloco_transferencias",
        "Transferências (linhas prontas)",
        "• emitidas ontem: 14\n• sem entrada no destino: 4\n• com COI errado: 1 🚨",
    ),
    Variavel("transferencias_emitidas", "Transferências emitidas ontem", "14"),
    Variavel("sem_entrada", "Transferências sem entrada no destino", "4"),
    Variavel("coi_errado", "Transferências com COI errado", "1"),
    Variavel(
        "bloco_vendas",
        "Vendas de ontem (linhas prontas)",
        "• faturamento: R$ 48.210,90 em 312 notas\n• ticket médio: R$ 154,52",
    ),
    Variavel("faturamento", "Faturamento de ontem", "R$ 48.210,90"),
    Variavel("notas", "Notas de venda de ontem", "312"),
    Variavel("ticket_medio", "Ticket médio de ontem", "R$ 154,52"),
    Variavel("devolucoes", "Devoluções de ontem", "R$ 320,00"),
    Variavel(
        "bloco_sincronizacao",
        "Sincronizações atrasadas (vazio quando está tudo em dia)",
        "⚠️ Sincronização com o ERP\n• estoque atrasada (última: 31/10 06:10)",
    ),
)


_ATIVIDADE_GERAIS = (
    Variavel("emoji", "Emoji da atividade", "👤"),
    Variavel("titulo", "O que aconteceu", "MARIA entrou no sistema"),
    Variavel("campos", "Informações marcadas", "Usuário: MARIA\nQuando: 31/10 08:02"),
)


def _modelos_das_regras() -> list[DefinicaoModelo]:
    modelos = []
    for regra in CATALOGO.values():
        campos = tuple(
            Variavel(c.chave, c.rotulo, _EXEMPLOS_CAMPOS.get(c.chave, c.rotulo))
            for c in regra.campos
        )
        if regra.tipo != "alerta":
            modelos.append(
                DefinicaoModelo(
                    f"{regra.regra}:aviso",
                    f"{regra.nome}: mensagem",
                    regra.nome,
                    regra.descricao,
                    _ATIVIDADE_GERAIS + campos,
                    PADRAO_ATIVIDADE,
                )
            )
            continue
        modelos += [
            DefinicaoModelo(
                f"{regra.regra}:aviso",
                f"{regra.nome}: aviso",
                regra.nome,
                "Quando o alerta abre ou agrava.",
                _AVISO_GERAIS + campos,
                PADRAO_AVISO,
            ),
            DefinicaoModelo(
                f"{regra.regra}:resolucao",
                f"{regra.nome}: resolvido",
                regra.nome,
                "Quando a situação acaba (vai só para quem recebeu o aviso).",
                _RESOLUCAO_GERAIS + campos,
                PADRAO_RESOLUCAO,
            ),
        ]
    return modelos


MODELOS: dict[str, DefinicaoModelo] = {
    m.chave: m
    for m in (
        *_modelos_das_regras(),
        DefinicaoModelo(
            "resumo_diario",
            "Resumo do dia",
            "Resumo do dia",
            "Uma vez por dia, no horário de RESUMO_DIARIO_HORARIO.",
            _RESUMO_VARIAVEIS,
            PADRAO_RESUMO,
        ),
    )
}


class ModeloInvalido(ValueError):
    pass


def renderizar(texto: str, valores: Mapping[str, str]) -> str:
    preenchido = _VARIAVEL.sub(lambda m: valores.get(m.group(1), m.group(0)), texto)
    linhas = [linha.rstrip() for linha in preenchido.splitlines()]
    juntas = re.sub(r"\n{3,}", "\n\n", "\n".join(linhas)).strip()
    return juntas[:LIMITE_CARACTERES]


def validar(definicao: DefinicaoModelo, texto: str) -> str:
    texto = texto.strip()
    if not texto:
        raise ModeloInvalido("O modelo não pode ficar vazio.")
    if len(texto) > LIMITE_MODELO:
        raise ModeloInvalido(f"O modelo passa de {LIMITE_MODELO} caracteres.")
    conhecidas = {v.chave for v in definicao.variaveis}
    desconhecidas = sorted({m for m in _VARIAVEL.findall(texto)} - conhecidas)
    if desconhecidas:
        lista = ", ".join(f"{{{v}}}" for v in desconhecidas)
        raise ModeloInvalido(f"Variável que esta mensagem não tem: {lista}.")
    return texto


def previa(definicao: DefinicaoModelo, texto: str) -> str:
    return renderizar(validar(definicao, texto), definicao.exemplos)


def carregar(db: Session) -> dict[str, str]:
    salvos = {m.chave: m.texto for m in db.scalars(select(ModeloMensagem))}
    return {chave: salvos.get(chave, d.padrao) for chave, d in MODELOS.items()}


def modelo(db: Session, chave: str) -> str:
    salvo = db.get(ModeloMensagem, chave)
    return salvo.texto if salvo is not None else MODELOS[chave].padrao
