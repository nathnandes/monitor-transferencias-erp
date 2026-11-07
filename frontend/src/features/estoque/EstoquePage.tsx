import { Boxes, CircleMinus, Coins, Lock, PackageCheck, PackageSearch, Search } from "lucide-react";
import { useCallback, useEffect, useId, useState, type FormEvent } from "react";

import { AppShell } from "../../components/layout/AppShell";
import { Header } from "../../components/layout/Header";
import { IndicadorAtualizacao } from "../../components/layout/IndicadorAtualizacao";
import { BotaoExportar } from "../../components/ui/BotaoExportar";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { LoadingState } from "../../components/ui/LoadingState";
import { MetricCard } from "../../components/ui/MetricCard";
import { Pagination } from "../../components/ui/Pagination";
import { Panel } from "../../components/ui/Panel";
import { useAsync } from "../../hooks/useAsync";
import { useValorEstavel } from "../../hooks/useValorEstavel";
import { formatarCnpj, formatarDataHora, formatarMoeda, formatarNumero, tempoRelativo } from "../../lib/format";
import {
  getCoberturaEstoque,
  getEstoque,
  getFornecedoresEstoque,
  getResumoEstoque,
} from "../../services/estoqueService";
import type { FornecedorEstoque, OrdenacaoEstoque, ParamsEstoque, SituacaoEstoque, StatusCobertura } from "../../types/api";
import type { Aba as CodigoAba } from "../../types/auth";
import { useSessaoOpcional } from "../auth/AuthContext";
import {
  FaixasCobertura,
  JANELA_PADRAO,
  JANELAS_VENDAS,
  ROTULO_COBERTURA,
  STATUS_COBERTURA,
} from "./components/CoberturaEstoque";
import { BalancoEstoque } from "./components/BalancoEstoque";
import { CoberturaLojasEstoque } from "./components/CoberturaLojasEstoque";
import { EstoqueTabela } from "./components/EstoqueTabela";
import { LivroEstoque } from "./components/LivroEstoque";
import { MovimentosEstoque } from "./components/MovimentosEstoque";
import { ProdutoEstoqueDetalhe, type ProdutoSelecionado } from "./components/ProdutoEstoqueDetalhe";

export const TITULO_ESTOQUE = "Estoque";
const SUBTITULO =
  "Saldos, preços e custos do ERP por produto, somando as empresas ou de uma empresa · somente consulta";

type Aba = "saldos" | "loja" | "livro" | "balanco" | "movimentos";

const ABAS: { valor: Aba; rotulo: string; param: string; codigo: CodigoAba }[] = [
  { valor: "saldos", rotulo: "Saldos", param: "saldos", codigo: "ESTOQUE.SALDOS" },
  { valor: "loja", rotulo: "Loja", param: "loja", codigo: "ESTOQUE.LOJA" },
  { valor: "livro", rotulo: "Entradas e saídas", param: "livro", codigo: "ESTOQUE.LIVRO" },
  { valor: "balanco", rotulo: "Balanço", param: "balanco", codigo: "ESTOQUE.BALANCO" },
  { valor: "movimentos", rotulo: "Avulsas", param: "avulsas", codigo: "ESTOQUE.AVULSAS" },
];


function abaInicial(visiveis: typeof ABAS): Aba {
  const pedida = new URLSearchParams(window.location.search).get("aba");
  return (visiveis.find((a) => a.param === pedida) ?? visiveis[0] ?? ABAS[0]!).valor;
}


const INTERVALO_ATUALIZACAO_MS = 120_000;
const TAMANHO_PAGINA = 50;

const ROTULO_SITUACAO: Record<SituacaoEstoque, string> = {
  com_saldo: "Com saldo",
  sem_saldo: "Sem saldo",
  negativo: "Negativo",
  com_reserva: "Com reserva",
};
const ROTULO_ORDENACAO: Record<OrdenacaoEstoque, string> = {
  produto: "Código do produto",
  maior_saldo: "Maior saldo",
  menor_saldo: "Menor saldo",
  menor_cobertura: "Menor cobertura",
  maior_cobertura: "Maior cobertura",
};


const rotuloFornecedor = (f: FornecedorEstoque) => `${f.nome} · ${formatarCnpj(f.cnpj)}`;


function diaMes(iso: string): string {
  const [, mes, dia] = iso.split("-");
  return `${dia}/${mes}`;
}


export function EstoquePage() {
  const sessao = useSessaoOpcional();

  const visiveis = ABAS.filter((a) => !sessao || sessao.temAba(a.codigo));
  const [aba, setAba] = useState<Aba>(() => abaInicial(visiveis));
  const [produtoDigitado, setProdutoDigitado] = useState("");
  const [produto, setProduto] = useState("");
  const [empresa, setEmpresa] = useState("");
  const [fornecedorDigitado, setFornecedorDigitado] = useState("");
  const [fornecedor, setFornecedor] = useState("");
  const [situacao, setSituacao] = useState<SituacaoEstoque | "">("");
  const [ordenacao, setOrdenacao] = useState<OrdenacaoEstoque>("produto");
  const [cobertura, setCobertura] = useState<StatusCobertura | "">("");
  const [janelaDias, setJanelaDias] = useState<number>(JANELA_PADRAO);
  const [pagina, setPagina] = useState(1);
  const [rodada, setRodada] = useState(0);
  const [aberto, setAberto] = useState<ProdutoSelecionado | null>(null);
  const ids = {
    produto: useId(),
    empresa: useId(),
    fornecedor: useId(),
    fornecedores: useId(),
    situacao: useId(),
    ordenacao: useId(),
    cobertura: useId(),
    janela: useId(),
  };

  const atualizar = useCallback(() => setRodada((r) => r + 1), []);


  useEffect(() => {
    const id = window.setInterval(() => {
      if (document.visibilityState === "visible") atualizar();
    }, INTERVALO_ATUALIZACAO_MS);
    return () => window.clearInterval(id);
  }, [atualizar]);

  const montados: ParamsEstoque = { ordenacao };
  if (produto) montados.produto = produto;
  if (empresa) montados.empresa = empresa;
  if (fornecedor) montados.fornecedor = fornecedor;
  if (situacao) montados.situacao = situacao;
  if (cobertura) montados.cobertura = cobertura;
  if (janelaDias !== JANELA_PADRAO) montados.janela_dias = janelaDias;
  const filtros = useValorEstavel(montados);

  const resumo = useAsync((s) => getResumoEstoque(s), [], rodada);
  const fornecedores = useAsync((s) => getFornecedoresEstoque(s), [], rodada);
  const contagem = useAsync(
    (s) => getCoberturaEstoque({ empresa: empresa || undefined, janela_dias: filtros.janela_dias }, s),
    [empresa, filtros.janela_dias],
    rodada,
  );
  const lista = useAsync(
    (s) => getEstoque(filtros, pagina, TAMANHO_PAGINA, s),
    [filtros, pagina],
    rodada,
  );


  const filtrar = <T,>(definir: (valor: T) => void) => (valor: T) => {
    definir(valor);
    setPagina(1);
  };
  const buscarProduto = (evento: FormEvent) => {
    evento.preventDefault();
    filtrar(setProduto)(produtoDigitado.trim());
  };

  const digitarFornecedor = (texto: string) => {
    setFornecedorDigitado(texto);
    const escolhido = fornecedores.data?.find((f) => rotuloFornecedor(f) === texto);
    filtrar(setFornecedor)(escolhido?.cnpj ?? "");
  };
  const limpar = () => {
    setProdutoDigitado("");
    setProduto("");
    setEmpresa("");
    setFornecedorDigitado("");
    setFornecedor("");
    setSituacao("");
    setCobertura("");
    setJanelaDias(JANELA_PADRAO);
    setOrdenacao("produto");
    setPagina(1);
  };

  const filtrarCobertura = (status: StatusCobertura | "") => {
    setCobertura(status);
    if (status && ordenacao === "produto") setOrdenacao("menor_cobertura");
    setPagina(1);
  };
  const temFiltro = Boolean(produto || empresa || fornecedor || situacao || cobertura);

  const dadosDe = resumo.data?.atualizado_em ?? lista.data?.atualizado_em ?? null;
  const header = (
    <Header
      titulo={TITULO_ESTOQUE}
      subtitulo={SUBTITULO}
      info={
        <IndicadorAtualizacao
          atualizadoEm={lista.atualizadoEm}
          atualizando={lista.loading}
          fontes={aba === "saldos" || aba === "loja" ? ["estoque", "precos"] : ["movimentos_estoque"]}
        />
      }
      aoAtualizar={atualizar}
      atualizando={lista.loading || resumo.loading}
      acoes={aba === "saldos" ? <BotaoExportar caminho="/api/v1/estoque/exportar" params={{ ...filtros }} /> : undefined}
    />
  );

  const r = resumo.data;
  const carregandoResumo = resumo.loading && !r;
  const daEmpresa = r?.por_empresa.find((e) => e.empresa.codigo === empresa);
  const nomeEmpresa = daEmpresa?.empresa.nome;
  const valorEstoque = empresa ? daEmpresa?.valor_custo : r?.valor_custo;

  return (
    <AppShell header={header}>
      <div role="tablist" aria-label="Visões do estoque" className="flex gap-1 border-b border-borda">
        {visiveis.map((a) => (
          <button
            key={a.valor}
            type="button"
            role="tab"
            aria-selected={aba === a.valor}
            onClick={() => setAba(a.valor)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium ${
              aba === a.valor ? "border-acento text-texto" : "border-transparent text-texto-mudo hover:text-texto"
            }`}
          >
            {a.rotulo}
          </button>
        ))}
      </div>

      {aba === "loja" ? (
        <CoberturaLojasEstoque rodada={rodada} aoAbrirProduto={setAberto} />
      ) : aba === "livro" ? (
        <LivroEstoque rodada={rodada} empresas={r?.por_empresa.map((e) => e.empresa) ?? []} />
      ) : aba === "balanco" ? (
        <BalancoEstoque
          rodada={rodada}
          empresas={r?.por_empresa.map((e) => e.empresa) ?? []}
          aoAbrirProduto={setAberto}
        />
      ) : aba === "movimentos" ? (
        <MovimentosEstoque
          rodada={rodada}
          empresas={r?.por_empresa.map((e) => e.empresa) ?? []}
          aoAbrirProduto={setAberto}
        />
      ) : (
        <>
          <section aria-label="Resumo do estoque" className="grid grid-cols-2 gap-3 lg:grid-cols-3 xl:grid-cols-6">
            <MetricCard
              rotulo="Produtos"
              valor={r ? formatarNumero(r.produtos) : undefined}
              icone={Boxes}
              destaque
              dica="Produtos/subprodutos com estoque registrado, somando as empresas."
              carregando={carregandoResumo}
            />
            <MetricCard
              rotulo="Com saldo"
              valor={r ? formatarNumero(r.produtos_com_saldo) : undefined}
              icone={PackageCheck}
              tom="bom"
              carregando={carregandoResumo}
            />
            <MetricCard
              rotulo="Saldo negativo"
              valor={r ? formatarNumero(r.produtos_negativos) : undefined}
              icone={CircleMinus}
              tom={r?.produtos_negativos ? "critico" : "neutro"}
              dica="Soma das empresas abaixo de zero."
              carregando={carregandoResumo}
            />
            <MetricCard
              rotulo="Com reserva"
              valor={r ? formatarNumero(r.produtos_com_reserva) : undefined}
              icone={Lock}
              tom="info"
              carregando={carregandoResumo}
            />
            <MetricCard
              rotulo={empresa ? `Valor em estoque · ${empresa}` : "Valor em estoque"}
              valor={r ? formatarMoeda(valorEstoque ?? null) : undefined}
              detalhe={
                r?.precos_atualizados_em
                  ? `Custo gerencial · preços ${tempoRelativo(r.precos_atualizados_em)}`
                  : "Preços ainda não sincronizados"
              }
              icone={Coins}
              dica={
                "Saldo atual × custo gerencial, só saldos positivos." +
                (r?.linhas_sem_custo
                  ? ` ${formatarNumero(r.linhas_sem_custo)} linha(s) com saldo sem custo ficam fora.`
                  : "")
              }
              carregando={carregandoResumo}
            />
            <MetricCard
              rotulo="Dados do ERP"
              valor={dadosDe ? tempoRelativo(dadosDe) : undefined}
              detalhe={dadosDe ? formatarDataHora(dadosDe) : "Ainda não sincronizado"}
              tom={r?.ultima_sincronizacao?.status === "erro" ? "serio" : "neutro"}
              dica="Fim da última sincronização de estoque que gravou dados."
              carregando={carregandoResumo}
            />
          </section>
          {resumo.error && (
            <ErrorState titulo="Falha ao carregar o resumo" erro={resumo.error} aoTentarNovamente={resumo.recarregar} />
          )}
          {r && r.locais_perda.length > 0 && (
            <p role="note" aria-label="Locais de perda" className="-mt-1 text-xs text-texto-2">
              Fora do estoque (perda):{" "}
              {r.locais_perda
                .map(
                  (l) =>
                    `${l.descricao ?? `local ${l.id_local}`} da loja ${l.empresa.codigo} · ${l.motivo} · ` +
                    `${formatarMoeda(l.valor)} em ${formatarNumero(l.produtos)} produtos`,
                )
                .join("; ")}
              . Esses produtos não entram em saldo, valor nem cobertura.
            </p>
          )}

          <Panel
            titulo={nomeEmpresa ? `Cobertura · ${empresa} - ${nomeEmpresa}` : "Cobertura da rede"}
            subtitulo={
              (contagem.data
                ? `Saldo disponível ÷ venda média por dia de ${diaMes(contagem.data.janela.inicio)} a ${diaMes(contagem.data.janela.fim)}.`
                : "Saldo disponível ÷ venda média por dia.") + " Escolha uma faixa para filtrar a lista."
            }
            nivel={2}
            acao={
              <div className="flex items-center gap-2">
                <label htmlFor={ids.janela} className="text-xs font-medium text-texto-2">
                  Média de vendas
                </label>
                <select
                  id={ids.janela}
                  value={janelaDias}
                  onChange={(e) => filtrar(setJanelaDias)(Number(e.target.value))}
                  className="campo w-40"
                >
                  {JANELAS_VENDAS.map((d) => (
                    <option key={d} value={d}>
                      Últimos {d} dias
                    </option>
                  ))}
                </select>
              </div>
            }
          >
            {contagem.error ? (
              <ErrorState titulo="Falha ao carregar a cobertura" erro={contagem.error} aoTentarNovamente={contagem.recarregar} />
            ) : contagem.data && !contagem.data.tem_vendas ? (
              <p className="text-sm text-texto-2">
                Esta empresa não vendeu nada nos últimos {contagem.data.janela.dias} dias (depósito): não há ritmo de
                venda para calcular cobertura. Veja a rede toda ou uma loja.
              </p>
            ) : (
              <FaixasCobertura
                contagem={contagem.data?.produtos}
                selecionado={cobertura}
                carregando={contagem.loading}
                aoSelecionar={filtrarCobertura}
              />
            )}
          </Panel>

          <Panel
            titulo={nomeEmpresa ? `Estoque · ${empresa} - ${nomeEmpresa}` : "Estoque consolidado"}
            subtitulo={
              empresa
                ? "Soma dos locais de estoque desta empresa."
                : "Soma das empresas. Use “Por empresa” para ver cada loja e local."
            }
            nivel={2}
          >
            <div className="flex flex-col gap-4">
              <div className="flex flex-wrap items-end gap-3">
                <form role="search" aria-label="Buscar produto" onSubmit={buscarProduto} className="flex items-end gap-2">
                  <div className="flex w-40 flex-col gap-1.5">
                    <label htmlFor={ids.produto} className="text-xs font-medium text-texto-2">
                      Código do produto
                    </label>
                    <input
                      id={ids.produto}
                      type="search"
                      inputMode="numeric"
                      value={produtoDigitado}
                      onChange={(e) => {
                        setProdutoDigitado(e.target.value);
                        if (!e.target.value) filtrar(setProduto)("");
                      }}
                      placeholder="Ex.: 9798"
                      className="campo"
                    />
                  </div>
                  <button type="submit" className="btn btn-sm btn-secundario">
                    <Search aria-hidden className="size-4" />
                    Buscar
                  </button>
                </form>
                <div className="flex w-56 flex-col gap-1.5">
                  <label htmlFor={ids.empresa} className="text-xs font-medium text-texto-2">
                    Empresa
                  </label>
                  <select
                    id={ids.empresa}
                    value={empresa}
                    onChange={(e) => filtrar(setEmpresa)(e.target.value)}
                    className="campo"
                  >
                    <option value="">Todas (consolidado)</option>
                    {r?.por_empresa.map(({ empresa: e }) => (
                      <option key={e.id} value={e.codigo}>
                        {e.codigo} - {e.nome}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="flex w-72 flex-col gap-1.5">
                  <label htmlFor={ids.fornecedor} className="text-xs font-medium text-texto-2">
                    Fornecedor
                  </label>
                  <input
                    id={ids.fornecedor}
                    type="search"
                    list={ids.fornecedores}
                    value={fornecedorDigitado}
                    onChange={(e) => digitarFornecedor(e.target.value)}
                    onBlur={() => {
                      if (!fornecedor) setFornecedorDigitado("");
                    }}
                    placeholder="Digite o nome ou o CNPJ"
                    title="Itens com alguma compra deste fornecedor no histórico, não só na última."
                    className="campo"
                  />
                  <datalist id={ids.fornecedores}>
                    {fornecedores.data?.map((f) => (
                      <option key={f.cnpj} value={rotuloFornecedor(f)} />
                    ))}
                  </datalist>
                </div>
                <div className="flex w-36 flex-col gap-1.5">
                  <label htmlFor={ids.situacao} className="text-xs font-medium text-texto-2">
                    Situação
                  </label>
                  <select
                    id={ids.situacao}
                    value={situacao}
                    onChange={(e) => filtrar(setSituacao)(e.target.value as SituacaoEstoque | "")}
                    className="campo"
                  >
                    <option value="">Todas</option>
                    {(Object.keys(ROTULO_SITUACAO) as SituacaoEstoque[]).map((s) => (
                      <option key={s} value={s}>
                        {ROTULO_SITUACAO[s]}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="flex w-36 flex-col gap-1.5">
                  <label htmlFor={ids.cobertura} className="text-xs font-medium text-texto-2">
                    Cobertura
                  </label>
                  <select
                    id={ids.cobertura}
                    value={cobertura}
                    onChange={(e) => filtrarCobertura(e.target.value as StatusCobertura | "")}
                    className="campo"
                  >
                    <option value="">Todas</option>
                    {STATUS_COBERTURA.map((s) => (
                      <option key={s} value={s}>
                        {ROTULO_COBERTURA[s]}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="flex w-44 flex-col gap-1.5">
                  <label htmlFor={ids.ordenacao} className="text-xs font-medium text-texto-2">
                    Ordenar por
                  </label>
                  <select
                    id={ids.ordenacao}
                    value={ordenacao}
                    onChange={(e) => filtrar(setOrdenacao)(e.target.value as OrdenacaoEstoque)}
                    className="campo"
                  >
                    {(Object.keys(ROTULO_ORDENACAO) as OrdenacaoEstoque[]).map((o) => (
                      <option key={o} value={o}>
                        {ROTULO_ORDENACAO[o]}
                      </option>
                    ))}
                  </select>
                </div>
                {(temFiltro || ordenacao !== "produto" || janelaDias !== JANELA_PADRAO) && (
                  <button type="button" onClick={limpar} className="btn btn-sm btn-fantasma">
                    Limpar filtros
                  </button>
                )}
              </div>

              {lista.error ? (
                <ErrorState titulo="Falha ao carregar o estoque" erro={lista.error} aoTentarNovamente={lista.recarregar} />
              ) : !lista.data ? (
                <LoadingState rotulo="Carregando estoque…" />
              ) : lista.data.itens.length === 0 ? (
                <EmptyState
                  icone={PackageSearch}
                  titulo={temFiltro ? "Nenhum produto com esses filtros." : "Nenhum estoque sincronizado ainda."}
                  descricao={
                    produto
                      ? `O produto ${produto} não tem estoque registrado${empresa ? " nesta empresa" : ""}.`
                      : temFiltro
                        ? undefined
                        : "Os saldos aparecem aqui depois da primeira sincronização de estoque."
                  }
                />
              ) : (
                <>
                  <EstoqueTabela
                    itens={lista.data.itens}
                    porEmpresa={Boolean(empresa)}
                    janelaDias={lista.data.janela.dias}
                    comCobertura={lista.data.tem_vendas}
                    carregando={lista.loading}
                    aoAbrir={(item) => setAberto({ idProduto: item.id_produto, idSubproduto: item.id_subproduto })}
                  />
                  <Pagination
                    pagina={lista.data.pagina}
                    totalPaginas={lista.data.total_paginas}
                    totalRegistros={lista.data.total}
                    tamanhoPagina={lista.data.tamanho_pagina}
                    itensNaPagina={lista.data.itens.length}
                    aoMudarPagina={setPagina}
                    desabilitado={lista.loading}
                  />
                </>
              )}
            </div>
          </Panel>
        </>
      )}

      <ProdutoEstoqueDetalhe produto={aberto} janelaDias={janelaDias} aoFechar={() => setAberto(null)} />
    </AppShell>
  );
}
