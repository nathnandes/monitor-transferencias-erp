import { ArrowLeftRight, Flame, Scale, TrendingDown, TrendingUp } from "lucide-react";
import { useId, useState } from "react";

import { EmptyState } from "../../../components/ui/EmptyState";
import { ErrorState } from "../../../components/ui/ErrorState";
import { LoadingState } from "../../../components/ui/LoadingState";
import { MetricCard } from "../../../components/ui/MetricCard";
import { Panel } from "../../../components/ui/Panel";
import { useAsync } from "../../../hooks/useAsync";
import { useValorEstavel } from "../../../hooks/useValorEstavel";
import { formatarMoeda, formatarNumero, formatarQuantidade } from "../../../lib/format";
import { hojeNoFuso } from "../../../lib/periodo";
import { getBalancos, getMovimentosEstoque } from "../../../services/estoqueService";
import type { AjusteProduto, EmpresaResumo, ParamsLivro, ResumoMovimentosDia } from "../../../types/api";
import { CodigoProduto } from "./CodigoProduto";
import { EventosBalanco, TabelaMovimentos } from "./MovimentosEstoque";
import type { ProdutoSelecionado } from "./ProdutoEstoqueDetalhe";
import { AlertaRecontagens } from "./RecontagensBalanco";

const TH = "px-3 py-2 font-semibold";
const TD = "px-3 py-2";

interface BalancoEstoqueProps {
  empresas: EmpresaResumo[];
  rodada?: number;
  aoAbrirProduto: (produto: ProdutoSelecionado) => void;
}

function Valor({ valor, forte = false }: { valor: string | null; forte?: boolean }) {
  const negativo = valor !== null && valor.trim().startsWith("-");
  return (
    <span className={`${negativo ? "text-critico-texto" : "text-texto"} ${forte ? "font-semibold" : ""}`}>
      {formatarMoeda(valor)}
    </span>
  );
}

function percentual(parte: number, todo: number): string {
  if (!todo) return "—";
  return `${Math.round((parte / todo) * 100)}%`;
}


export function BalancoEstoque({ empresas, rodada = 0, aoAbrirProduto }: BalancoEstoqueProps) {
  const hoje = hojeNoFuso();

  const [inicio, setInicio] = useState(hoje);
  const [fim, setFim] = useState(hoje);
  const [empresa, setEmpresa] = useState("");
  const [evento, setEvento] = useState<ResumoMovimentosDia | null>(null);
  const ids = { inicio: useId(), fim: useId(), empresa: useId() };

  const periodoValido = Boolean(inicio && fim && inicio <= fim);
  const montados: ParamsLivro = periodoValido ? { data_inicial: inicio, data_final: fim } : {};
  if (empresa) montados.empresa = empresa;
  const params = useValorEstavel(montados);
  const resumo = useAsync((s) => getBalancos(params, s), [params], rodada);
  const itensEvento = useAsync(
    (s) =>
      evento
        ? getMovimentosEstoque(
            { data_inicial: evento.dia, data_final: evento.dia, empresa: evento.empresa.codigo, tipo: "balanco" },
            1,
            100,
            s,
          )
        : Promise.resolve(null),
    [evento],
    rodada,
  );

  const r = resumo.data;
  const perda = r ? Number(r.totais.perda) : 0;
  const abrir = (a: { id_produto: string; id_subproduto: string }) =>
    aoAbrirProduto({ idProduto: a.id_produto, idSubproduto: a.id_subproduto });

  return (
    <div className="flex flex-col gap-4">
      <Panel
        titulo="Balanços de estoque"
        subtitulo={
          "Soma dos ajustes de cada item nos balanços (COI 2000) do período, a custo, como no relatório de balanço " +
          "do ERP Poder: perda = faltas, ganho = sobras."
        }
        nivel={2}
      >
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex w-40 flex-col gap-1.5">
            <label htmlFor={ids.inicio} className="text-xs font-medium text-texto-2">
              De
            </label>
            <input
              id={ids.inicio}
              type="date"
              value={inicio}
              max={fim || undefined}
              onChange={(e) => setInicio(e.target.value)}
              className="campo"
            />
          </div>
          <div className="flex w-40 flex-col gap-1.5">
            <label htmlFor={ids.fim} className="text-xs font-medium text-texto-2">
              Até
            </label>
            <input
              id={ids.fim}
              type="date"
              value={fim}
              min={inicio || undefined}
              onChange={(e) => setFim(e.target.value)}
              className="campo"
            />
          </div>
          <div className="flex w-56 flex-col gap-1.5">
            <label htmlFor={ids.empresa} className="text-xs font-medium text-texto-2">
              Empresa
            </label>
            <select id={ids.empresa} value={empresa} onChange={(e) => setEmpresa(e.target.value)} className="campo">
              <option value="">Todas</option>
              {empresas.map((e) => (
                <option key={e.id} value={e.codigo}>
                  {e.codigo} - {e.nome}
                </option>
              ))}
            </select>
          </div>
        </div>
      </Panel>

      {resumo.error ? (
        <ErrorState titulo="Falha ao carregar os balanços" erro={resumo.error} aoTentarNovamente={resumo.recarregar} />
      ) : !r ? (
        <LoadingState rotulo="Carregando balanços…" />
      ) : r.totais.balancos === 0 ? (
        <EmptyState icone={Scale} titulo="Nenhum balanço neste período." />
      ) : (
        <>
          <section aria-label="Resultado dos balanços" className="grid grid-cols-2 gap-3 xl:grid-cols-5">
            <MetricCard
              rotulo="Perda (faltas)"
              valor={formatarMoeda(r.totais.perda)}
              detalhe={`${formatarNumero(r.totais.produtos_com_falta)} produtos`}
              icone={TrendingDown}
              tom="critico"
            />
            <MetricCard
              rotulo="Ganho (sobras)"
              valor={formatarMoeda(r.totais.ganho)}
              detalhe={`${formatarNumero(r.totais.produtos_com_sobra)} produtos`}
              icone={TrendingUp}
              tom="bom"
            />
            <MetricCard
              rotulo="Resultado"
              valor={formatarMoeda(r.totais.resultado)}
              detalhe={`${formatarNumero(r.totais.balancos)} balanço(s) · ${formatarNumero(r.totais.itens)} itens`}
              icone={Scale}
              tom={Number(r.totais.resultado) < 0 ? "critico" : "bom"}
              destaque
            />
            <MetricCard
              rotulo="Prováveis transferências erradas"
              valor={formatarMoeda(r.valor_transferencias_provaveis)}
              detalhe={`${percentual(Number(r.valor_transferencias_provaveis), -perda)} da perda`}
              icone={ArrowLeftRight}
              tom="aviso"
              dica="Mesmo produto com falta numa loja e sobra em outra no período: a quantidade que casa dos dois lados, a custo."
            />
            {r.locais_perda.map((l) => (
              <MetricCard
                key={`${l.empresa.id}/${l.id_local}`}
                rotulo={`Perda · ${l.motivo}`}
                valor={formatarMoeda(l.valor)}
                detalhe={`${l.descricao ?? `Local ${l.id_local}`} · loja ${l.empresa.codigo} · ${formatarNumero(l.produtos)} produtos`}
                icone={Flame}
                tom="critico"
                dica="Estoque parado num local de perda, a custo: valor de hoje (não do período). Fica fora do saldo e dos totais do balanço."
              />
            ))}
          </section>

          <AlertaRecontagens params={params} rodada={rodada} aoAbrir={abrir} />

          <Panel titulo="Por loja" nivel={2}>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <caption className="sr-only">Perda e ganho dos balanços por loja</caption>
                <thead>
                  <tr className="bg-superficie-2 text-xs uppercase tracking-wide text-texto-mudo">
                    <th scope="col" className={TH}>Loja</th>
                    <th scope="col" className={`${TH} text-right`}>Balanços</th>
                    <th scope="col" className={`${TH} text-right`}>Perda</th>
                    <th scope="col" className={`${TH} text-right`}>Ganho</th>
                    <th scope="col" className={`${TH} text-right`}>Resultado</th>
                  </tr>
                </thead>
                <tbody className="tabular">
                  {r.por_loja.map((l) => (
                    <tr key={l.empresa.id} className="border-t border-borda/60">
                      <td className={TD}>
                        <span className="font-medium text-texto">{l.empresa.codigo}</span>{" "}
                        <span className="text-texto-2">{l.empresa.nome}</span>
                      </td>
                      <td className={`${TD} text-right`}>{formatarNumero(l.balancos)}</td>
                      <td className={`${TD} text-right`}>
                        <Valor valor={l.perda} />
                      </td>
                      <td className={`${TD} text-right`}>
                        <Valor valor={l.ganho} />
                      </td>
                      <td className={`${TD} text-right`}>
                        <Valor valor={l.resultado} forte />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>

          <Panel
            titulo="Prováveis transferências erradas"
            subtitulo={
              "Mesmo produto com falta numa loja e sobra em outra no período. Confira as transferências do produto entre " +
              "as duas lojas: mercadoria enviada para a loja errada, entrada não lançada ou quantidade digitada errada."
            }
            nivel={2}
          >
            {r.transferencias_provaveis.length === 0 ? (
              <p className="text-sm text-texto-2">Nenhum produto com falta numa loja e sobra em outra.</p>
            ) : (
              <div className="max-h-[60vh] overflow-auto">
                <table className="w-full text-left text-sm">
                  <caption className="sr-only">Prováveis transferências erradas</caption>
                  <thead className="sticky top-0">
                    <tr className="bg-superficie-2 text-xs uppercase tracking-wide text-texto-mudo">
                      <th scope="col" className={TH}>Produto</th>
                      <th scope="col" className={TH}>Falta em</th>
                      <th scope="col" className={TH}>Sobra em</th>
                      <th scope="col" className={`${TH} text-right`}>Casa</th>
                      <th scope="col" className={`${TH} text-right`}>Valor</th>
                    </tr>
                  </thead>
                  <tbody className="tabular">
                    {r.transferencias_provaveis.map((p) => (
                      <tr
                        key={`${p.id_produto}/${p.id_subproduto}/${p.loja_falta.id}/${p.loja_sobra.id}`}
                        className="border-t border-borda/60"
                      >
                        <td className={TD}>
                          <button type="button" onClick={() => abrir(p)} className="text-left hover:underline">
                            <CodigoProduto idProduto={p.id_produto} idSubproduto={p.id_subproduto} />
                          </button>
                          {p.descricao && <span className="block text-xs text-texto-mudo">{p.descricao}</span>}
                        </td>
                        <td className={TD}>
                          {p.loja_falta.codigo} <span className="text-critico-texto">{formatarQuantidade(p.quantidade_falta)}</span>
                        </td>
                        <td className={TD}>
                          {p.loja_sobra.codigo} <span className="text-bom-texto">+{formatarQuantidade(p.quantidade_sobra)}</span>
                        </td>
                        <td className={`${TD} text-right`}>{formatarQuantidade(p.quantidade)}</td>
                        <td className={`${TD} text-right`}>
                          <Valor valor={p.valor} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>

          <div className="grid gap-4 xl:grid-cols-2">
            <TabelaAjustes titulo="Maiores perdas" ajustes={r.maiores_perdas} aoAbrir={abrir} />
            <TabelaAjustes titulo="Maiores sobras" ajustes={r.maiores_ganhos} aoAbrir={abrir} />
          </div>

          <Panel
            titulo="Balanços do período"
            subtitulo="Um por loja e dia, com o total de falta e de sobra. Os itens abrem logo abaixo do balanço."
            nivel={2}
          >
            <EventosBalanco
              eventos={r.eventos}
              aberto={evento}
              aoAlternar={setEvento}
              detalhe={
                itensEvento.error ? (
                  <ErrorState erro={itensEvento.error} aoTentarNovamente={itensEvento.recarregar} />
                ) : !itensEvento.data ? (
                  <LoadingState rotulo="Carregando itens do balanço…" />
                ) : (
                  <div className="flex flex-col gap-2">
                    <p className="text-xs text-texto-mudo">Até 100 itens, do mais recente.</p>
                    <TabelaMovimentos itens={itensEvento.data.itens} aoAbrirProduto={aoAbrirProduto} />
                  </div>
                )
              }
            />
          </Panel>
        </>
      )}
    </div>
  );
}

function TabelaAjustes({
  titulo,
  ajustes,
  aoAbrir,
}: {
  titulo: string;
  ajustes: AjusteProduto[];
  aoAbrir: (a: AjusteProduto) => void;
}) {
  return (
    <Panel titulo={titulo} subtitulo="Ajuste líquido do produto na loja, a custo." nivel={2}>
      {ajustes.length === 0 ? (
        <p className="text-sm text-texto-2">Nenhum.</p>
      ) : (
        <table className="w-full text-left text-sm">
          <caption className="sr-only">{titulo}</caption>
          <thead>
            <tr className="bg-superficie-2 text-xs uppercase tracking-wide text-texto-mudo">
              <th scope="col" className={TH}>Produto</th>
              <th scope="col" className={TH}>Loja</th>
              <th scope="col" className={`${TH} text-right`}>Qtd.</th>
              <th scope="col" className={`${TH} text-right`}>Valor</th>
            </tr>
          </thead>
          <tbody className="tabular">
            {ajustes.map((a) => (
              <tr key={`${a.empresa.id}/${a.id_produto}/${a.id_subproduto}`} className="border-t border-borda/60">
                <td className={TD}>
                  <button type="button" onClick={() => aoAbrir(a)} className="text-left hover:underline">
                    <CodigoProduto idProduto={a.id_produto} idSubproduto={a.id_subproduto} />
                  </button>
                  {a.descricao && <span className="block text-xs text-texto-mudo">{a.descricao}</span>}
                </td>
                <td className={TD}>{a.empresa.codigo}</td>
                <td className={`${TD} text-right`}>{formatarQuantidade(a.quantidade)}</td>
                <td className={`${TD} text-right`}>
                  <Valor valor={a.valor} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Panel>
  );
}
