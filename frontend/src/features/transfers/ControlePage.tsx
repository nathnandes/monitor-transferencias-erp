import { ArrowLeft, ArrowRight, Clock, FileWarning, Grid3x3, Info, PackageX, Scale, Timer, Truck, UserRound } from "lucide-react";
import { useCallback, useState, type ReactNode } from "react";
import { Link } from "react-router";

import { AppShell } from "../../components/layout/AppShell";
import { FiltroGlobalBar } from "../../components/layout/FiltroGlobalBar";
import { Header } from "../../components/layout/Header";
import { IndicadorAtualizacao } from "../../components/layout/IndicadorAtualizacao";
import { EmptyState } from "../../components/ui/EmptyState";
import { AvisoFalhaAtualizacao } from "../../components/ui/AvisoFalhaAtualizacao";
import { ErrorState } from "../../components/ui/ErrorState";
import { LoadingState } from "../../components/ui/LoadingState";
import { MetricCard } from "../../components/ui/MetricCard";
import { Panel } from "../../components/ui/Panel";
import { SectionHeader } from "../../components/ui/SectionHeader";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { useAsync } from "../../hooks/useAsync";
import { useValorEstavel } from "../../hooks/useValorEstavel";
import { useAtualizacaoAutomatica } from "../../hooks/useAtualizacaoAutomatica";
import { useFiltroGlobal } from "../../hooks/useFiltroGlobal";
import { queryDoFiltroGlobal } from "../../lib/filtroGlobal";
import { formatarDataHora, formatarMoeda, formatarNumero, formatarQuantidade, nomeCurtoEmpresa, tempoRelativo } from "../../lib/format";
import { getAnomalias, getPainelControle, type ParamsControle } from "../../services/controleTransferenciasService";
import { getEmpresas } from "../../services/empresasService";
import type { FiltrosTransferencia, PainelControle, RotaControle, TipoProblemaFiscal, TransferenciaRefControle } from "../../types/api";
import { useSessao } from "../auth/AuthContext";
import { LimitesPendenciaPanel } from "./components/LimitesPendenciaPanel";
import { PrazosRotaPanel } from "./components/PrazosRotaPanel";
import { ROTULO_TRATATIVA } from "./components/TratativasPanel";
import { linkTransferencias } from "./lib/queryFilters";

export const TITULO_CONTROLE = "Controle de transferências";

const ROTULO_FISCAL: Record<TipoProblemaFiscal, string> = {
  CFOP_SAIDA: "CFOP de saída",
  CFOP_ENTRADA: "CFOP de entrada",
  CANCELADA: "Nota cancelada",
  ENTRADA_OUTRA_EMPRESA: "Entrada em outra empresa",
};


type Abrir = (filtros: Partial<FiltrosTransferencia>, detalheId?: number) => string;

const LINK = "underline decoration-borda-forte underline-offset-2 hover:text-texto hover:decoration-texto";


export function ControlePage() {
  const [rodada, setRodada] = useState(0);
  const filtroGlobal = useFiltroGlobal();
  const abrir: Abrir = (filtros, detalheId) => linkTransferencias(filtroGlobal.query, filtros, detalheId ?? null);

  const queryTudo = queryDoFiltroGlobal({ ...filtroGlobal.filtro, periodo: "tudo", dataInicial: "", dataFinal: "" });
  const abrirTransito: Abrir = (filtros) => linkTransferencias(queryTudo, { ...filtros, status: "PENDENTE" });
  const { temModulo, usuario } = useSessao();
  const podeListarEmpresas = temModulo("DASHBOARD");

  const montados: ParamsControle = {};
  if (filtroGlobal.filtro.empresa) montados.empresa = filtroGlobal.filtro.empresa;
  if (filtroGlobal.intervalo) {
    montados.data_inicial = filtroGlobal.intervalo.inicio;
    montados.data_final = filtroGlobal.intervalo.fim;
  }
  const params = useValorEstavel(montados);

  const empresas = useAsync((s) => (podeListarEmpresas ? getEmpresas(s) : Promise.resolve([])), [podeListarEmpresas], rodada);
  const painel = useAsync((s) => getPainelControle(params, s), [params], rodada);
  const atualizar = useCallback(() => setRodada((r) => r + 1), []);
  useAtualizacaoAutomatica(atualizar);

  const header = (
    <Header
      titulo={TITULO_CONTROLE}
      subtitulo="Trânsito, prazo por rota, divergências, conferência fiscal e tratativas"
      info={<IndicadorAtualizacao atualizadoEm={painel.atualizadoEm} atualizando={painel.loading} fontes={["transferencias"]} />}
      aoAtualizar={atualizar}
      atualizando={painel.loading}
      acoes={
        <Link to={`/transferencias${filtroGlobal.query}`} className="btn btn-secundario shrink-0">
          <ArrowLeft aria-hidden className="size-4" />
          Consulta
        </Link>
      }
      filtros={
        <FiltroGlobalBar
          estado={filtroGlobal}
          empresas={podeListarEmpresas ? empresas.data : null}
          carregandoEmpresas={empresas.loading && !empresas.data}
        />
      }
    />
  );

  const dados = painel.data;
  return (
    <AppShell header={header}>
      {painel.error && !dados ? (
        <ErrorState titulo="Não foi possível carregar o controle" erro={painel.error} aoTentarNovamente={painel.recarregar} />
      ) : !dados ? (
        <LoadingState rotulo="Montando o controle..." />
      ) : (
        <div aria-busy={painel.loading} className={`flex flex-col gap-secao transition-opacity ${painel.loading ? "opacity-70" : ""}`}>
          <AvisoFalhaAtualizacao erro={painel.error} aoTentarNovamente={painel.recarregar} />
          <Resumo dados={dados} periodo={filtroGlobal.descricaoPeriodo} abrir={abrir} abrirTransito={abrirTransito} />
          <Transito dados={dados} abrirTransito={abrirTransito} />
          <Rotas dados={dados} abrir={abrir} />
          <Divergencias dados={dados} abrir={abrir} />
          <Anomalias params={params} rodada={rodada} abrir={abrir} />
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            <Fiscal dados={dados} abrir={abrir} />
            <Emissores dados={dados} abrir={abrir} />
          </div>
          <LimitesPendenciaPanel ehAdmin={usuario.role === "ADMIN"} aoSalvar={atualizar} />
          <PrazosRotaPanel rotas={dados.rotas} padrao={dados.prazo_padrao_horas} ehAdmin={usuario.role === "ADMIN"} aoSalvar={atualizar} />
          <Limitacoes />
        </div>
      )}
    </AppShell>
  );
}

function Resumo({ dados, periodo, abrir, abrirTransito }: { dados: PainelControle; periodo: string; abrir: Abrir; abrirTransito: Abrir }) {
  const r = dados.resumo;
  return (
    <section aria-labelledby="titulo-resumo-controle">
      <SectionHeader
        id="titulo-resumo-controle"
        titulo="Resumo"
        descricao={`${periodo} · trânsito é a situação de agora · clique para abrir as notas`}
        icone={Scale}
      />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <MetricCard
          destaque
          rotulo="Em trânsito"
          para={abrirTransito({})}
          valor={formatarMoeda(r.em_transito_valor)}
          detalhe={`${formatarNumero(r.em_transito_quantidade)} notas sem entrada`}
          icone={Truck}
          dica="Valor das notas de transferência ainda sem entrada no destino, de qualquer data."
        />
        <MetricCard
          rotulo="Fora do prazo"
          para={abrir({ ocorrencia: "FORA_DO_PRAZO" })}
          valor={formatarNumero(r.fora_do_prazo)}
          tom={r.fora_do_prazo ? "aviso" : "bom"}
          icone={Timer}
          dica="Entrada depois do prazo da rota ou, sem entrada, prazo já vencido."
        />
        <MetricCard
          rotulo="Divergências"
          para={abrir({ ocorrencia: "DIVERGENTE" })}
          valor={formatarMoeda(r.valor_divergencia)}
          detalhe={`${formatarNumero(r.divergentes)} transferências`}
          tom={r.divergentes ? "serio" : "bom"}
          icone={PackageX}
          dica="Diferença entre enviado e recebido, em R$ pelo valor da saída (ou custo). Positivo = faltou no destino."
        />
        <MetricCard
          rotulo="Problemas fiscais"
          para={abrir({ ocorrencia: "FISCAL" })}
          valor={formatarNumero(r.problemas_fiscais)}
          tom={r.problemas_fiscais ? "critico" : "bom"}
          icone={FileWarning}
          dica="CFOP fora dos de transferência, nota cancelada ou entrada registrada em outra empresa."
        />
        <MetricCard
          rotulo="Sem tratativa"
          para={abrir({ ocorrencia: "SEM_TRATATIVA" })}
          valor={formatarNumero(r.sem_tratativa)}
          tom={r.sem_tratativa ? "aviso" : "bom"}
          icone={Clock}
          dica="Transferências que precisam de atenção e ainda não foram marcadas como resolvidas."
        />
      </div>
    </section>
  );
}


function LinkNota({ t, para }: { t: TransferenciaRefControle; para: string }) {
  return (
    <Link to={para} className={`font-semibold text-texto ${LINK}`}>
      {t.numero_nota ?? `#${t.id}`}
    </Link>
  );
}

function RotaTexto({ t, abrir }: { t: TransferenciaRefControle; abrir: Abrir }) {
  const texto = (
    <>
      {t.origem.codigo} <ArrowRight aria-label="para" className="inline size-3 text-texto-mudo" /> {t.destino?.codigo ?? "?"}
    </>
  );
  if (!t.destino) return <span className="tabular whitespace-nowrap text-texto-2">{texto}</span>;
  return (
    <Link
      to={abrir({ empresa_origem: t.origem.codigo, empresa_destino: t.destino.codigo })}
      title={`Transferências ${t.origem.nome} → ${t.destino.nome}`}
      className={`tabular whitespace-nowrap text-texto-2 ${LINK}`}
    >
      {texto}
    </Link>
  );
}

function LinkEmissor({ usuario, abrir }: { usuario: string | null; abrir: Abrir }) {
  if (!usuario) return <span className="text-texto-mudo">—</span>;
  return (
    <Link to={abrir({ emitida_por: usuario })} title={`Transferências emitidas por ${usuario}`} className={`text-texto-2 ${LINK}`}>
      {usuario}
    </Link>
  );
}

function SeloTratativa({ t }: { t: TransferenciaRefControle }) {
  if (!t.tratativa) return <StatusBadge tom="neutro">Sem tratativa</StatusBadge>;
  return (
    <span title={`${t.tratativa.usuario_nome}: ${t.tratativa.observacao}`}>
      <StatusBadge tom={t.tratativa.situacao === "RESOLVIDA" ? "bom" : "aviso"}>{ROTULO_TRATATIVA[t.tratativa.situacao]}</StatusBadge>
    </span>
  );
}

function Tabela({ cabecalho, children, legenda }: { cabecalho: string[]; children: ReactNode; legenda: string }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-borda">
      <table className="w-full min-w-[560px] text-left text-sm">
        <caption className="sr-only">{legenda}</caption>
        <thead className="bg-superficie-2 text-[11px] uppercase tracking-wide text-texto-mudo">
          <tr>
            {cabecalho.map((c, i) => (
              <th key={c} scope="col" className={`px-3 py-2 font-semibold ${i > 0 && /^(Valor|Qtd|Notas|Env|Fora|Div|Fisc)/.test(c) ? "text-right" : ""}`}>
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="tabular">{children}</tbody>
      </table>
    </div>
  );
}

function Transito({ dados, abrirTransito }: { dados: PainelControle; abrirTransito: Abrir }) {
  const maior = Math.max(...dados.em_transito.map((t) => Number(t.valor)), 1);
  return (
    <Panel titulo="Parado em trânsito, por destino" subtitulo="Notas emitidas e ainda sem entrada no destino, de qualquer data. Barra = valor.">
      {dados.em_transito.length === 0 ? (
        <EmptyState titulo="Nada em trânsito" descricao="Todas as transferências já tiveram entrada." />
      ) : (
        <ul className="flex flex-col gap-2.5">
          {dados.em_transito.map((t) => {
            const linha = (
              <>
              <span className="truncate font-medium text-texto" title={t.empresa?.nome}>
                {t.empresa ? (
                  <>
                    <span className="tabular text-texto-mudo">{t.empresa.codigo}</span> {nomeCurtoEmpresa(t.empresa.nome)}
                  </>
                ) : (
                  "Fora das empresas"
                )}
              </span>
              <span className="h-3 overflow-hidden rounded-sm bg-superficie-3" aria-hidden>
                <span className="block h-full rounded-sm bg-texto-2" style={{ width: `${(Number(t.valor) / maior) * 100}%` }} />
              </span>
              <span className="tabular text-right text-xs text-texto-2">
                <strong className="text-sm font-semibold text-texto">{formatarMoeda(t.valor)}</strong> · {t.quantidade} notas
                {t.mais_antiga && <span className="text-texto-mudo"> · mais antiga {tempoRelativo(t.mais_antiga)}</span>}
              </span>
              </>
            );
            const grade = "grid grid-cols-[minmax(7rem,12rem)_1fr_auto] items-center gap-3 text-sm";
            return (
              <li key={t.empresa?.codigo ?? "fora"}>
                {t.empresa ? (
                  <Link
                    to={abrirTransito({ empresa_destino: t.empresa.codigo })}
                    title={`Abrir as notas em trânsito para ${t.empresa.nome}`}
                    className={`${grade} -mx-2 rounded px-2 py-1 hover:bg-superficie-2`}
                  >
                    {linha}
                  </Link>
                ) : (

                  <div className={`${grade} py-1`}>{linha}</div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </Panel>
  );
}


function fundoDaCelula(r: RotaControle): string {
  if (!r.enviadas) return "transparent";
  const fracao = r.fora_do_prazo / r.enviadas;
  return fracao === 0 ? "transparent" : `color-mix(in srgb, var(--color-aviso) ${Math.round(12 + fracao * 50)}%, transparent)`;
}

function Rotas({ dados, abrir }: { dados: PainelControle; abrir: Abrir }) {
  const codigos = [...new Set(dados.rotas.flatMap((r) => [r.origem.codigo, r.destino.codigo]))].sort();
  const nomes = new Map(dados.rotas.flatMap((r) => [[r.origem.codigo, r.origem.nome], [r.destino.codigo, r.destino.nome]] as const));
  const rota = (o: string, d: string) => dados.rotas.find((r) => r.origem.codigo === o && r.destino.codigo === d);

  return (
    <Panel
      titulo="Rotas: origem × destino"
      subtitulo={`Cada célula: notas enviadas, quantas passaram do prazo e o tempo médio até a entrada. Prazo padrão ${dados.prazo_padrao_horas} h; cor mais forte = mais notas fora do prazo. Clique num número para abrir as notas.`}
      acao={<Grid3x3 aria-hidden className="size-4 text-texto-mudo" />}
    >
      {dados.rotas.length === 0 ? (
        <EmptyState titulo="Nenhuma transferência no período" />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] border-separate border-spacing-1 text-sm">
            <caption className="sr-only">Transferências por rota, origem nas linhas e destino nas colunas</caption>
            <thead>
              <tr>
                <th scope="col" className="w-28 text-left text-[11px] font-semibold uppercase tracking-wide text-texto-mudo">
                  Origem ↓ Destino →
                </th>
                {codigos.map((d) => (
                  <th key={d} scope="col" title={nomes.get(d)} className="text-xs font-semibold text-texto-2">
                    {d} · {nomeCurtoEmpresa(nomes.get(d) ?? "")}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="tabular">
              {codigos.map((o) => (
                <tr key={o}>
                  <th scope="row" title={nomes.get(o)} className="text-left text-xs font-semibold text-texto-2">
                    {o} · {nomeCurtoEmpresa(nomes.get(o) ?? "")}
                  </th>
                  {codigos.map((d) => {
                    const r = rota(o, d);
                    if (o === d) return <td key={d} className="rounded bg-superficie-3/50" aria-label="mesma empresa" />;
                    if (!r) return <td key={d} className="rounded border border-dashed border-borda text-center text-xs text-texto-mudo/60">—</td>;
                    const daRota = { empresa_origem: o, empresa_destino: d };
                    return (
                      <td
                        key={d}
                        className="rounded border border-borda px-2 py-1.5 align-top"
                        style={{ background: fundoDaCelula(r) }}
                        title={`${r.origem.nome} → ${r.destino.nome}\nValor enviado: ${formatarMoeda(r.valor_enviado)}\nPrazo: ${r.prazo_horas} h${r.prazo_padrao ? " (padrão)" : ""}`}
                      >
                        <Link
                          to={abrir(daRota)}
                          aria-label={`${r.enviadas} notas de ${r.origem.nome} para ${r.destino.nome}`}
                          className={`block text-base font-bold leading-tight text-texto ${LINK}`}
                        >
                          {r.enviadas}
                        </Link>
                        <p className="text-[11px] leading-snug text-texto-2">
                          {r.fora_do_prazo > 0 ? (
                            <Link to={abrir({ ...daRota, ocorrencia: "FORA_DO_PRAZO" })} className={`font-semibold text-aviso-texto ${LINK}`}>
                              {r.fora_do_prazo} fora do prazo
                            </Link>
                          ) : (
                            "no prazo"
                          )}
                          {r.pendentes > 0 && (
                            <>
                              {" · "}
                              <Link to={abrir({ ...daRota, status: "PENDENTE" })} className={LINK}>
                                {r.pendentes} pend.
                              </Link>
                            </>
                          )}
                        </p>
                        <p className="text-[11px] text-texto-mudo">
                          {r.tempo_medio_horas !== null ? `${r.tempo_medio_horas.toLocaleString("pt-BR")} h méd.` : "sem entrada"}
                          {r.divergentes > 0 && (
                            <>
                              {" · "}
                              <Link to={abrir({ ...daRota, ocorrencia: "DIVERGENTE" })} className={`text-serio-texto ${LINK}`}>
                                {r.divergentes} div.
                              </Link>
                            </>
                          )}
                        </p>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

function Divergencias({ dados, abrir }: { dados: PainelControle; abrir: Abrir }) {
  return (
    <Panel
      titulo="Divergências de quantidade"
      subtitulo="Item recebido em quantidade diferente da enviada, ou produto que entrou sem estar na nota. Maior valor primeiro."
    >
      {dados.divergencias.length === 0 ? (
        <EmptyState titulo="Nenhuma divergência no período" descricao="Tudo o que entrou bate com o que saiu." />
      ) : (
        <Tabela cabecalho={["Nota", "Rota", "Emitida por", "Itens", "Valor", "Tratativa"]} legenda="Transferências com divergência">
          {dados.divergencias.map((d) => (
            <tr key={d.transferencia.id} className="border-t border-borda align-top">
              <td className="px-3 py-2">
                <LinkNota t={d.transferencia} para={abrir({ ocorrencia: "DIVERGENTE" }, d.transferencia.id)} />
                <p className="text-[11px] text-texto-mudo">{formatarDataHora(d.transferencia.data_criacao)}</p>
              </td>
              <td className="px-3 py-2"><RotaTexto t={d.transferencia} abrir={abrir} /></td>
              <td className="px-3 py-2"><LinkEmissor usuario={d.transferencia.usuario_emissao} abrir={abrir} /></td>
              <td className="px-3 py-2">
                <ul className="flex flex-col gap-0.5 text-xs">
                  {d.itens.slice(0, 4).map((i) => (
                    <li key={i.id_produto} className="text-texto-2">
                      <span className="text-texto">{i.descricao ?? i.id_produto}</span>{" "}
                      {i.sem_saida ? (
                        <span className="text-info-texto">entrou {formatarQuantidade(i.recebida)} sem estar na nota</span>
                      ) : (
                        <span className="text-serio-texto">
                          enviou {formatarQuantidade(i.enviada)}, recebeu {formatarQuantidade(i.recebida)}
                        </span>
                      )}
                    </li>
                  ))}
                  {d.itens.length > 4 && <li className="text-texto-mudo">+ {d.itens.length - 4} itens</li>}
                </ul>
              </td>
              <td className="px-3 py-2 text-right font-semibold text-texto">{formatarMoeda(d.valor_diferenca)}</td>
              <td className="px-3 py-2"><SeloTratativa t={d.transferencia} /></td>
            </tr>
          ))}
        </Tabela>
      )}
    </Panel>
  );
}


function Anomalias({ params, rodada, abrir }: { params: ParamsControle; rodada: number; abrir: Abrir }) {
  const painel = useAsync((s) => getAnomalias(params, s), [params], rodada);
  const dados = painel.data;
  const execucao = dados?.execucao ?? null;
  return (
    <Panel
      titulo="Fora do padrão (IA)"
      subtitulo="Notas diferentes do histórico da rota, da mais estranha para a menos. Fora do padrão não significa erro nem fraude: é um pedido de conferência."
    >
      {painel.error && !dados ? (
        <EmptyState titulo="Não foi possível carregar as anomalias" descricao="O restante do controle não foi afetado." />
      ) : !dados ? (
        <LoadingState rotulo="Buscando as anomalias..." />
      ) : !execucao ? (
        <EmptyState titulo="O detector ainda não rodou" descricao="As notas aparecem aqui depois da primeira rodada." />
      ) : (
        <>
          <p className="mb-3 text-xs text-texto-2">
            {formatarNumero(dados.sinalizadas)} de {formatarNumero(dados.analisadas)} notas avaliadas no período · última rodada{" "}
            {tempoRelativo(execucao.concluida_em)} · aprendeu com {formatarNumero(execucao.notas_treino)} notas
          </p>
          {execucao.status !== "sucesso" && (
            <p role="status" className="mb-3 text-xs text-aviso-texto">
              {execucao.status === "erro" ? "A última rodada falhou. O que aparece aqui é de rodadas anteriores." : execucao.mensagem}
            </p>
          )}
          {dados.lista.length === 0 ? (
            <EmptyState titulo="Nenhuma nota sinalizada no período" />
          ) : (
            <Tabela cabecalho={["Nota", "Rota", "Por que chamou atenção", "Valor", "Tratativa"]} legenda="Transferências fora do padrão">
              {dados.lista.map((a) => (
                <tr key={a.transferencia.id} className="border-t border-borda align-top">
                  <td className="px-3 py-2">
                    <LinkNota t={a.transferencia} para={abrir({}, a.transferencia.id)} />
                    <p className="text-[11px] text-texto-mudo">{formatarDataHora(a.transferencia.data_criacao)}</p>
                  </td>
                  <td className="px-3 py-2"><RotaTexto t={a.transferencia} abrir={abrir} /></td>
                  <td className="px-3 py-2">
                    <ul className="flex flex-col gap-0.5 text-xs text-texto-2">
                      {a.motivos.map((motivo) => (
                        <li key={motivo}>{motivo}</li>
                      ))}
                    </ul>
                  </td>
                  <td className="px-3 py-2 text-right font-semibold text-texto">{formatarMoeda(a.transferencia.valor_total)}</td>
                  <td className="px-3 py-2"><SeloTratativa t={a.transferencia} /></td>
                </tr>
              ))}
            </Tabela>
          )}
        </>
      )}
    </Panel>
  );
}

function Fiscal({ dados, abrir }: { dados: PainelControle; abrir: Abrir }) {
  return (
    <Panel
      titulo="Conferência fiscal"
      subtitulo={`CFOPs aceitos: saída ${dados.cfops_saida.join(", ")}; entrada ${dados.cfops_entrada.join(", ")}.`}
    >
      {dados.fiscal.length === 0 ? (
        <EmptyState titulo="Nada fora do padrão fiscal" />
      ) : (
        <ul className="flex flex-col divide-y divide-borda">
          {dados.fiscal.map((p) => (
            <li key={`${p.transferencia.id}-${p.tipo}`} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2 text-sm">
              <StatusBadge tom={p.tipo === "CANCELADA" ? "neutro" : "critico"}>{ROTULO_FISCAL[p.tipo]}</StatusBadge>
              <LinkNota t={p.transferencia} para={abrir({ ocorrencia: "FISCAL" }, p.transferencia.id)} />
              <RotaTexto t={p.transferencia} abrir={abrir} />
              <span className="min-w-0 flex-1 text-xs text-texto-2">{p.detalhe}</span>
              <SeloTratativa t={p.transferencia} />
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

function Emissores({ dados, abrir }: { dados: PainelControle; abrir: Abrir }) {
  return (
    <Panel titulo="Por quem emitiu" subtitulo="Usuário do ERP que emitiu a nota de saída. Quem deu a entrada o ERP não informa.">
      {dados.emissores.length === 0 ? (
        <EmptyState titulo="Nenhuma nota no período" />
      ) : (
        <Tabela cabecalho={["Usuário", "Enviadas", "Fora do prazo", "Divergentes", "Fiscais"]} legenda="Ocorrências por emissor">
          {dados.emissores.map((e) => {

            const doEmissor = e.usuario === "Não informado" ? null : { emitida_por: e.usuario };
            return (
              <tr key={e.usuario} className="border-t border-borda">
                <td className="px-3 py-2 text-texto">
                  <UserRound aria-hidden className="mr-1.5 inline size-3.5 text-texto-mudo" />
                  {doEmissor ? (
                    <Link to={abrir(doEmissor)} title={`Transferências emitidas por ${e.usuario}`} className={LINK}>
                      {e.usuario}
                    </Link>
                  ) : (
                    e.usuario
                  )}
                </td>
                <Contagem valor={e.enviadas} classe="text-texto-2" para={doEmissor && abrir(doEmissor)} />
                <Contagem valor={e.fora_do_prazo} classe="text-aviso-texto" para={doEmissor && abrir({ ...doEmissor, ocorrencia: "FORA_DO_PRAZO" })} />
                <Contagem valor={e.divergentes} classe="text-serio-texto" para={doEmissor && abrir({ ...doEmissor, ocorrencia: "DIVERGENTE" })} />
                <Contagem valor={e.problemas_fiscais} classe="text-critico-texto" para={doEmissor && abrir({ ...doEmissor, ocorrencia: "FISCAL" })} />
              </tr>
            );
          })}
        </Tabela>
      )}
    </Panel>
  );
}

function Contagem({ valor, classe, para }: { valor: number; classe: string; para: string | null }) {
  return (
    <td className={`px-3 py-2 text-right ${valor ? `font-semibold ${classe}` : "text-texto-mudo/60"}`}>
      {valor && para ? (
        <Link to={para} className={LINK}>
          {valor}
        </Link>
      ) : (
        valor
      )}
    </td>
  );
}

function Limitacoes() {
  return (
    <aside className="flex gap-3 rounded-painel border border-borda bg-superficie-2 p-4 text-sm text-texto-2">
      <Info aria-hidden className="mt-0.5 size-4 shrink-0 text-texto-mudo" />
      <div>
        <p className="font-semibold text-texto">O que o ERP ainda não fornece</p>
        <ul className="mt-1 list-disc pl-4 text-xs leading-relaxed">
          <li>Quem deu a entrada da nota no destino (a nota de entrada não traz o usuário).</li>
          <li>Carga, veículo, motorista e horário de expedição: não há serviço de logística liberado.</li>
          <li>Motivo da transferência (reposição, pedido de cliente, devolução).</li>
          <li>Nota denegada e data do cancelamento na SEFAZ.</li>
        </ul>
      </div>
    </aside>
  );
}
