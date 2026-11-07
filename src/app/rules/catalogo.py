from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Campo:
    chave: str
    rotulo: str
    padrao: bool = True
    bloco: bool = False
    rotulo_no_bloco: bool = True


@dataclass(frozen=True)
class DefinicaoRegra:
    regra: str
    nome: str
    descricao: str
    campos: tuple[Campo, ...]
    tipo: Literal["alerta", "atividade", "meta", "estoque"] = "alerta"
    ativo_padrao: bool = True

    def campo(self, chave: str) -> Campo | None:
        return next((c for c in self.campos if c.chave == chave), None)

    @property
    def campos_padrao(self) -> list[str]:
        return [c.chave for c in self.campos if c.padrao]


_NOTA = Campo("nota", "Nota")
_ORIGEM = Campo("origem", "Origem")
_DESTINO = Campo("destino", "Destino")
_EMITIDA_EM = Campo("emitida_em", "Emitida em", padrao=False)
_EMITIDA_POR = Campo("emitida_por", "Emitida por", padrao=False)
_VALOR = Campo("valor", "Valor", padrao=False)
_ITENS = Campo("itens", "Itens", padrao=False)
_TRANSFERENCIA_EXTRAS = (_EMITIDA_EM, _EMITIDA_POR, _VALOR, _ITENS)


_CAMPOS_ATIVIDADE = (
    Campo("usuario", "Usuário"),
    Campo("quando", "Quando"),
    Campo("detalhe", "Detalhe", bloco=True, rotulo_no_bloco=False),
    Campo("ip", "IP", padrao=False),
)


ATIVIDADES: tuple[tuple[str, str, str], ...] = (
    ("login", "Entrada no sistema", "Alguém fez login."),
    (
        "login_recusado",
        "Login recusado",
        "Senha errada, usuário inativo ou bloqueio por excesso de tentativas.",
    ),
    ("logout", "Saída do sistema", "Alguém clicou em Sair."),
    ("senha_trocada", "Troca da própria senha", "Alguém trocou a própria senha."),
    (
        "usuarios_alterados",
        "Usuários alterados",
        "Usuário criado, editado, ativado, desativado, com senha redefinida ou permissões mudadas.",
    ),
    ("perfis_alterados", "Perfis de acesso alterados", "Perfil criado, editado ou excluído."),
    (
        "alertas_alterados",
        "Configuração dos alertas alterada",
        "Destinos, tipos de alerta ou texto das mensagens mudados nesta tela.",
    ),
    (
        "transferencias_alteradas",
        "Controle de transferências alterado",
        "Limites de atenção e crítico, prazos das rotas ou tratativa registrada.",
    ),
    (
        "avulsas_alteradas",
        "Avulsas alteradas",
        "Justificativa, relação entrada ↔ saída ou dia de corte das avulsas.",
    ),
    (
        "excecoes_alteradas",
        "Exceções de falta alteradas",
        "Produto incluído ou tirado das exceções de falta de uma empresa (Estoque › Loja).",
    ),
    (
        "metas_alteradas",
        "Metas de vendas alteradas",
        "Meta criada, mudada ou excluída, ou marcos de aviso mudados.",
    ),
    (
        "sincronizacao_pedida",
        "Sincronização pedida na mão",
        "Alguém pediu uma sincronização com o ERP fora do horário.",
    ),
)

CATALOGO: dict[str, DefinicaoRegra] = {
    d.regra: d
    for d in (
        DefinicaoRegra(
            "transferencia_atrasada",
            "Transferência sem entrada no destino",
            "Nota de saída emitida e a entrada ainda não registrada na empresa de destino.",
            (
                _NOTA,
                _ORIGEM,
                _DESTINO,
                Campo("sem_entrada_ha", "Sem entrada há"),
                *_TRANSFERENCIA_EXTRAS,
            ),
        ),
        DefinicaoRegra(
            "transferencia_coi_errado",
            "Transferência com COI errado",
            "Nota de saída ou de entrada sem o COI de transferência entre as empresas.",
            (
                _NOTA,
                _ORIGEM,
                _DESTINO,
                Campo("coi_saida", "COI de saída"),
                Campo("coi_entrada", "COI de entrada"),
                Campo("problemas", "Problemas", bloco=True, rotulo_no_bloco=False),
                Campo("orientacao", "O que fazer", bloco=True, rotulo_no_bloco=False),
                *_TRANSFERENCIA_EXTRAS,
            ),
        ),
        DefinicaoRegra(
            "nota_empresa_errada",
            "Nota emitida pela empresa errada",
            "Nota de saída (fora as transferências) com o CNPJ de outra empresa do grupo "
            "como destinatário: quem fica com a mercadoria é quem tem que emitir a nota.",
            (
                _NOTA,
                Campo("origem", "Emitida na"),
                Campo("destino", "Destinatário"),
                Campo("coi", "COI"),
                Campo("orientacao", "O que fazer", bloco=True, rotulo_no_bloco=False),
                *_TRANSFERENCIA_EXTRAS,
            ),
        ),
        DefinicaoRegra(
            "transferencia_anomala",
            "Transferência fora do padrão (IA)",
            "O detector de anomalias sinalizou a nota como diferente do histórico da rota. "
            "Não significa erro nem fraude: é um pedido de conferência.",
            (
                _NOTA,
                _ORIGEM,
                _DESTINO,
                Campo("motivos", "Por que chamou atenção", bloco=True),
                Campo("orientacao", "O que fazer", bloco=True, rotulo_no_bloco=False),
                _EMITIDA_EM,
                _VALOR,
                _ITENS,
            ),
            ativo_padrao=False,
        ),
        DefinicaoRegra(
            "transferencia_erro",
            "Transferência com erro",
            "Transferência com status ERRO.",
            (_NOTA, _ORIGEM, _DESTINO, Campo("status", "Status"), *_TRANSFERENCIA_EXTRAS),
        ),
        DefinicaoRegra(
            "sincronizacao_erro",
            "Sincronização com erro",
            "A última sincronização de uma empresa ativa com o ERP terminou em erro.",
            (
                Campo("empresa", "Empresa"),
                Campo("tipo", "Tipo"),
                Campo("inicio", "Início"),
                Campo("erro", "Erro", padrao=False),
            ),
        ),
        DefinicaoRegra(
            "sincronizacao_parada",
            "Sincronização parada",
            "Uma sincronização agendada com o ERP está há muito tempo sem concluir "
            "(worker travado ou desligado).",
            (
                Campo("ultima_conclusao", "Última conclusão"),
                Campo("intervalo", "Agendada a cada"),
                Campo("orientacao", "O que fazer", bloco=True, rotulo_no_bloco=False),
            ),
        ),
        *(
            DefinicaoRegra(
                chave,
                nome,
                descricao,
                _CAMPOS_ATIVIDADE,
                tipo="atividade",
                ativo_padrao=False,
            )
            for chave, nome, descricao in ATIVIDADES
        ),
        DefinicaoRegra(
            "meta_atingida",
            "Meta de vendas",
            "Uma loja, um vendedor ou o grupo chegou a um marco da meta (os marcos ficam na "
            "tela de metas; o padrão é só 100%).",
            (
                Campo("alvo", "Quem"),
                Campo("periodo", "Período"),
                Campo("meta", "Meta"),
                Campo("realizado", "Vendido"),
                Campo("percentual", "Da meta"),
                Campo("falta", "Falta", padrao=False),
            ),
            tipo="meta",
        ),
        DefinicaoRegra(
            "estoque_baixo",
            "Estoque baixo",
            "Resumo por loja, nos horários escolhidos, dos produtos que ficaram abaixo do "
            "mínimo pelo giro desde o último resumo.",
            (
                Campo("loja", "Loja"),
                Campo("quantidade", "Produtos novos"),
                Campo("total", "Baixos agora", padrao=False),
                Campo("dias", "Mínimo para", padrao=False),
                Campo("produtos", "Produtos", bloco=True, rotulo_no_bloco=False),
            ),
            tipo="estoque",
        ),
    )
}


def montar_corpo(regra: str, valores: Mapping[str, str], selecionados: Sequence[str]) -> str:
    definicao = CATALOGO.get(regra)
    if definicao is None:
        return "\n".join(f"{k}: {v}" for k, v in valores.items() if v)
    marcados = set(selecionados)
    linhas: list[str] = []
    blocos: list[str] = []
    for campo in definicao.campos:
        valor = valores.get(campo.chave)
        if campo.chave not in marcados or not valor:
            continue
        if campo.bloco:
            blocos.append(f"{campo.rotulo}:\n{valor}" if campo.rotulo_no_bloco else valor)
        else:
            linhas.append(f"{campo.rotulo}: {valor}")
    return "\n\n".join(p for p in ("\n".join(linhas), *blocos) if p)
