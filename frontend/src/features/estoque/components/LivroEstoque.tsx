import { BookOpen, ListFilter } from "lucide-react";
import { useId, useState } from "react";

import { EmptyState } from "../../../components/ui/EmptyState";
import { ErrorState } from "../../../components/ui/ErrorState";
import { LoadingState } from "../../../components/ui/LoadingState";
import { Panel } from "../../../components/ui/Panel";
import { useAsync } from "../../../hooks/useAsync";
import { useValorEstavel } from "../../../hooks/useValorEstavel";
import { formatarMoeda, formatarMoedaNumero, formatarNumero } from "../../../lib/format";
import { hojeNoFuso } from "../../../lib/periodo";
import { getLivroEstoque } from "../../../services/estoqueService";
import type { CategoriaMovimento, EmpresaResumo, LinhaLivro, ParamsLivro } from "../../../types/api";
import { AvisoAfeta, ROTULO_CATEGORIA, SeloCategoria } from "./CategoriaMovimento";
import { NotasLivro } from "./NotasLivro";

const CATEGORIAS = (Object.keys(ROTULO_CATEGORIA) as CategoriaMovimento[]).sort((a, b) =>
  ROTULO_CATEGORIA[a].localeCompare(ROTULO_CATEGORIA[b], "pt-BR"),
);


interface LivroEstoqueProps {
  empresas: EmpresaResumo[];
  rodada?: number;
}


function Valor({ valor }: { valor: number | string | null }) {
  if (valor === null) return <span className="text-texto-mudo">—</span>;
  const negativo = Number(valor) < 0;
  return <span className={negativo ? "text-critico-texto" : "text-texto"}>{typeof valor === "number" ? formatarMoedaNumero(valor) : formatarMoeda(valor)}</span>;
}

interface Loja {
  empresa: EmpresaResumo;
  linhas: LinhaLivro[];
  entradas: number;
  saidas: number;
}


export function porLoja(linhas: LinhaLivro[]): Loja[] {
  const lojas = new Map<number, Loja>();
  for (const linha of linhas) {
    const loja = lojas.get(linha.empresa.id) ?? { empresa: linha.empresa, linhas: [], entradas: 0, saidas: 0 };
    loja.linhas.push(linha);
    if (linha.afeta && linha.valor !== null) {
      const valor = Number(linha.valor);
      if (valor > 0) loja.entradas += valor;
      else loja.saidas += valor;
    }
    lojas.set(linha.empresa.id, loja);
  }
  return [...lojas.values()];
}

const TH = "px-3 py-2 font-semibold";


export function LivroEstoque({ empresas, rodada = 0 }: LivroEstoqueProps) {
  const hoje = hojeNoFuso();

  const [inicio, setInicio] = useState(hoje);
  const [fim, setFim] = useState(hoje);
  const [empresa, setEmpresa] = useState("");
  const [categoria, setCategoria] = useState<CategoriaMovimento | "">("");

  const [coi, setCoi] = useState<{ empresa: string; coi: number } | null>(null);
  const ids = { inicio: useId(), fim: useId(), empresa: useId(), categoria: useId() };

  const periodoValido = Boolean(inicio && fim && inicio <= fim);
  const montados: ParamsLivro = periodoValido ? { data_inicial: inicio, data_final: fim } : {};
  if (empresa) montados.empresa = empresa;
  if (categoria) montados.categoria = categoria;
  const params = useValorEstavel(montados);
  const livro = useAsync((s) => getLivroEstoque(params, s), [params], rodada);
  const lojas = livro.data ? porLoja(livro.data.linhas) : [];

  return (
    <div className="flex flex-col gap-4">
      <Panel
        titulo="Entradas e saídas por loja"
        subtitulo={
          "Tudo o que o ERP movimentou em cada loja, por operação (COI): vendas, compras, transferências, " +
          "devoluções, perdas, uso e consumo, avulsas e balanços. Valor com o efeito no estoque: entrada positiva, " +
          "saída negativa. Operações que não mexem no estoque (ou a confirmar) aparecem, mas ficam fora dos totais. " +
          "Em Notas, abaixo, cada documento com a data e a hora, quem lançou e os produtos."
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
            <select
              id={ids.empresa}
              value={empresa}
              onChange={(e) => {
                setEmpresa(e.target.value);
                setCoi(null);
              }}
              className="campo"
            >
              <option value="">Todas</option>
              {empresas.map((e) => (
                <option key={e.id} value={e.codigo}>
                  {e.codigo} - {e.nome}
                </option>
              ))}
            </select>
          </div>
          <div className="flex w-56 flex-col gap-1.5">
            <label htmlFor={ids.categoria} className="text-xs font-medium text-texto-2">
              Categoria
            </label>
            <select
              id={ids.categoria}
              value={categoria}
              onChange={(e) => {
                setCategoria(e.target.value as CategoriaMovimento | "");
                setCoi(null);
              }}
              className="campo"
            >
              <option value="">Todas</option>
              {CATEGORIAS.map((c) => (
                <option key={c} value={c}>
                  {ROTULO_CATEGORIA[c]}
                </option>
              ))}
            </select>
          </div>
        </div>
        {livro.data && livro.data.dias_sem_leitura > 0 && (
          <p role="status" className="mt-3 rounded-lg bg-aviso/12 px-3 py-2 text-sm text-aviso-texto">
            O livro ainda está carregando o histórico: {formatarNumero(livro.data.dias_sem_leitura)} dia(s) × loja
            deste período ainda não foram lidos do ERP. Os números podem estar incompletos.
          </p>
        )}
      </Panel>

      {livro.error ? (
        <ErrorState titulo="Falha ao carregar o livro" erro={livro.error} aoTentarNovamente={livro.recarregar} />
      ) : !livro.data ? (
        <LoadingState rotulo="Carregando entradas e saídas…" />
      ) : lojas.length === 0 ? (
        <EmptyState icone={BookOpen} titulo="Nenhum movimento neste período." />
      ) : (
        lojas.map((loja) => (
          <Panel
            key={loja.empresa.id}
            titulo={`${loja.empresa.codigo} · ${loja.empresa.nome}`}
            subtitulo={
              <span className="tabular">
                Entradas <Valor valor={loja.entradas.toFixed(2)} /> · Saídas <Valor valor={loja.saidas.toFixed(2)} />
              </span>
            }
          >
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <caption className="sr-only">Movimentos da loja {loja.empresa.codigo} por operação</caption>
                <thead>
                  <tr className="bg-superficie-2 text-xs uppercase tracking-wide text-texto-mudo">
                    <th scope="col" className={TH}>Categoria</th>
                    <th scope="col" className={TH}>Operação (COI)</th>
                    <th scope="col" className={`${TH} text-right`}>Documentos</th>
                    <th scope="col" className={`${TH} text-right`}>Itens</th>
                    <th scope="col" className={`${TH} text-right`}>Valor</th>
                    <th scope="col" className={TH}>
                      <span className="sr-only">Notas</span>
                    </th>
                  </tr>
                </thead>
                <tbody className="tabular">
                  {loja.linhas.map((l) => (
                    <tr key={l.coi} className={`border-t border-borda/60 ${l.afeta ? "" : "opacity-70"}`}>
                      <td className="px-3 py-2">
                        <SeloCategoria categoria={l.categoria} />
                      </td>
                      <td className="px-3 py-2">
                        <span className="font-medium text-texto">{l.coi}</span>
                        {l.operacao && <span className="text-texto-2"> · {l.operacao}</span>}
                        <span className="block">
                          <AvisoAfeta afeta={l.afeta} />
                        </span>
                      </td>
                      <td className="px-3 py-2 text-right">{formatarNumero(l.documentos)}</td>
                      <td className="px-3 py-2 text-right">{formatarNumero(l.itens)}</td>
                      <td className="px-3 py-2 text-right">
                        <Valor valor={l.valor} />
                      </td>
                      <td className="px-3 py-2 text-right">
                        <button
                          type="button"
                          onClick={() => {
                            setCoi({ empresa: loja.empresa.codigo, coi: l.coi });
                            document.getElementById("notas-livro")?.scrollIntoView?.({ behavior: "smooth" });
                          }}
                          aria-label={`Ver notas do COI ${l.coi} da loja ${loja.empresa.codigo}`}
                          className="btn btn-sm btn-fantasma whitespace-nowrap"
                        >
                          <ListFilter aria-hidden className="size-3.5" />
                          Ver notas
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        ))
      )}

      {!livro.error && (
        <div id="notas-livro" className="scroll-mt-4">
          <NotasLivro
            params={coi && !empresa ? { ...params, empresa: coi.empresa } : params}
            coi={coi?.coi ?? null}
            aoLimparCoi={() => setCoi(null)}
            rodada={rodada}
          />
        </div>
      )}
    </div>
  );
}
