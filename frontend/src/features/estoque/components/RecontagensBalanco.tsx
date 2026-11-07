import { AlertTriangle, ChevronDown, RotateCcw, X } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

import { ErrorState } from "../../../components/ui/ErrorState";
import { LoadingState } from "../../../components/ui/LoadingState";
import { Panel } from "../../../components/ui/Panel";
import { useAsync } from "../../../hooks/useAsync";
import { useValorEstavel } from "../../../hooks/useValorEstavel";
import { formatarMoeda, formatarNumero, formatarQuantidade, rotuloDia, rotuloDiaCurto } from "../../../lib/format";
import { getRecontagens } from "../../../services/estoqueService";
import type { MarcaRecontagem, ParamsLivro, ParamsRecontagens, Recontagem } from "../../../types/api";
import { CodigoProduto } from "./CodigoProduto";

const TH = "px-3 py-2 font-semibold";
const TD = "px-3 py-2";
const MAIS_DE_PADRAO = 1;

interface AlertaRecontagensProps {

  params: ParamsLivro;
  rodada?: number;
  aoAbrir: (r: Recontagem) => void;
}


export function AlertaRecontagens({ params, rodada = 0, aoAbrir }: AlertaRecontagensProps) {
  const [maisDe, setMaisDe] = useState(String(MAIS_DE_PADRAO));
  const [desde, setDesde] = useState("");
  const [marcas, setMarcas] = useState<string[]>([]);
  const ids = { maisDe: useId(), desde: useId() };

  const n = Number.parseInt(maisDe, 10);
  const montados: ParamsRecontagens = { ...params, mais_de: Number.isFinite(n) && n >= 1 ? n : MAIS_DE_PADRAO };
  if (desde) montados.desde = desde;
  if (marcas.length) montados.marca = marcas;
  const filtros = useValorEstavel(montados);
  const recontagens = useAsync((s) => getRecontagens(filtros, s), [filtros], rodada);
  const d = recontagens.data;

  const [opcoesMarca, setOpcoesMarca] = useState<MarcaRecontagem[]>([]);
  useEffect(() => {
    if (d) setOpcoesMarca(d.marcas);
  }, [d]);
  const vezes = filtros.mais_de ?? MAIS_DE_PADRAO;

  return (
    <Panel
      titulo={
        <span className="inline-flex items-center gap-2">
          <AlertTriangle aria-hidden className="size-4 text-aviso-texto" />
          Itens recontados
          {d && d.total > 0 && (
            <span className="rounded-full bg-aviso/15 px-2 py-0.5 text-xs font-semibold text-aviso-texto">
              {formatarNumero(d.total)}
            </span>
          )}
        </span>
      }
      subtitulo={
        "Produtos contados em mais balanços do que o limite, por loja, no período e empresa acima. Cada documento " +
        "de balanço com o produto é uma contagem; o ERP só lança o item que teve diferença."
      }
      nivel={2}
    >
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex w-44 flex-col gap-1.5">
            <label htmlFor={ids.maisDe} className="text-xs font-medium text-texto-2">
              Contado mais de (vezes)
            </label>
            <input
              id={ids.maisDe}
              type="number"
              min={1}
              max={100}
              step={1}
              inputMode="numeric"
              value={maisDe}
              onChange={(e) => setMaisDe(e.target.value)}
              className="campo"
            />
          </div>
          <div className="flex w-44 flex-col gap-1.5">
            <label htmlFor={ids.desde} className="text-xs font-medium text-texto-2">
              Recontado a partir de
            </label>
            <input
              id={ids.desde}
              type="date"
              value={desde}
              min={params.data_inicial}
              max={params.data_final}
              onChange={(e) => setDesde(e.target.value)}
              className="campo"
            />
          </div>
          <SeletorMarcas opcoes={opcoesMarca} selecionadas={marcas} aoMudar={setMarcas} />
          {(desde || marcas.length > 0 || maisDe !== String(MAIS_DE_PADRAO)) && (
            <button
              type="button"
              onClick={() => {
                setMaisDe(String(MAIS_DE_PADRAO));
                setDesde("");
                setMarcas([]);
              }}
              className="btn btn-sm btn-fantasma"
            >
              <RotateCcw aria-hidden className="size-4" />
              Limpar
            </button>
          )}
        </div>
        {marcas.length > 0 && (
          <ul aria-label="Marcas escolhidas" className="flex flex-wrap gap-1.5">
            {marcas.map((m) => (
              <li key={m}>
                <button
                  type="button"
                  onClick={() => setMarcas(marcas.filter((x) => x !== m))}
                  aria-label={`Tirar a marca ${m}`}
                  className="inline-flex items-center gap-1 rounded-full border border-borda bg-superficie-2 px-2.5 py-0.5 text-xs font-medium text-texto hover:border-borda-forte"
                >
                  {m}
                  <X aria-hidden className="size-3 text-texto-mudo" />
                </button>
              </li>
            ))}
          </ul>
        )}

        {recontagens.error ? (
          <ErrorState erro={recontagens.error} aoTentarNovamente={recontagens.recarregar} />
        ) : !d ? (
          <LoadingState rotulo="Procurando itens recontados…" />
        ) : d.total === 0 ? (
          <p className="text-sm text-texto-2">
            Nenhum produto contado mais de {formatarNumero(vezes)} {vezes === 1 ? "vez" : "vezes"}
            {filtros.desde ? ` com recontagem a partir de ${rotuloDia(filtros.desde)}` : ""}
            {marcas.length ? " nas marcas escolhidas" : ""}.
          </p>
        ) : (
          <>
            <p role="status" className="rounded-md bg-aviso/10 px-3 py-2 text-sm text-aviso-texto">
              {formatarNumero(d.total)} {d.total === 1 ? "produto contado" : "produtos contados"} mais de{" "}
              {formatarNumero(vezes)} {vezes === 1 ? "vez" : "vezes"}
              {filtros.desde ? `, com recontagem a partir de ${rotuloDia(filtros.desde)}` : ""}
              {marcas.length ? ` (${marcas.length === 1 ? "marca" : "marcas"} ${marcas.join(", ")})` : ""}.
              {d.total > d.itens.length && ` Mostrando os ${formatarNumero(d.itens.length)} mais contados.`}
            </p>
            <div className="max-h-[50vh] overflow-auto md:rounded-lg md:border md:border-borda">
              <table className="w-full text-left text-sm">
                <caption className="sr-only">Itens recontados nos balanços</caption>
                <thead className="sticky top-0">
                  <tr className="bg-superficie-2 text-xs uppercase tracking-wide text-texto-mudo">
                    <th scope="col" className={TH}>Produto</th>
                    <th scope="col" className={TH}>Loja</th>
                    <th scope="col" className={`${TH} text-right`}>Contagens</th>
                    <th scope="col" className={TH}>Dias</th>
                    <th scope="col" className={`${TH} text-right`}>Ajuste</th>
                    <th scope="col" className={`${TH} text-right`}>Valor</th>
                  </tr>
                </thead>
                <tbody className="tabular">
                  {d.itens.map((x) => (
                    <tr key={`${x.empresa.id}/${x.id_produto}/${x.id_subproduto}`} className="border-t border-borda/60">
                      <td className={TD}>
                        <button type="button" onClick={() => aoAbrir(x)} className="text-left hover:underline">
                          <CodigoProduto idProduto={x.id_produto} idSubproduto={x.id_subproduto} />
                        </button>
                        {x.descricao && <span className="block text-xs text-texto-mudo">{x.descricao}</span>}
                        {x.marca && <span className="block text-[11px] uppercase tracking-wide text-texto-mudo">{x.marca}</span>}
                      </td>
                      <td className={TD}>{x.empresa.codigo}</td>
                      <td className={`${TD} text-right font-semibold`}>{formatarNumero(x.contagens)}</td>
                      <td className={`${TD} text-texto-2`}>
                        {x.dias.map((dia) => (
                          <span
                            key={dia}
                            title={rotuloDia(dia)}
                            className={`mr-1 inline-block ${filtros.desde && dia >= filtros.desde ? "font-semibold text-aviso-texto" : ""}`}
                          >
                            {rotuloDiaCurto(dia)}
                          </span>
                        ))}
                      </td>
                      <td className={`${TD} text-right`}>{formatarQuantidade(x.quantidade)}</td>
                      <td className={`${TD} text-right ${x.valor.trim().startsWith("-") ? "text-critico-texto" : ""}`}>
                        {formatarMoeda(x.valor)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </Panel>
  );
}

interface SeletorMarcasProps {
  opcoes: MarcaRecontagem[];
  selecionadas: string[];
  aoMudar: (marcas: string[]) => void;
}


function SeletorMarcas({ opcoes, selecionadas, aoMudar }: SeletorMarcasProps) {
  const [aberto, setAberto] = useState(false);
  const [busca, setBusca] = useState("");
  const raiz = useRef<HTMLDivElement>(null);
  const idLista = useId();
  const idBusca = useId();

  useEffect(() => {
    if (!aberto) return;
    const fora = (e: MouseEvent) => {
      if (raiz.current && !raiz.current.contains(e.target as Node)) setAberto(false);
    };
    const esc = (e: KeyboardEvent) => {
      if (e.key === "Escape") setAberto(false);
    };
    document.addEventListener("mousedown", fora);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("mousedown", fora);
      document.removeEventListener("keydown", esc);
    };
  }, [aberto]);

  const termo = busca.trim().toLocaleUpperCase("pt-BR");
  const visiveis = termo ? opcoes.filter((o) => o.marca.toLocaleUpperCase("pt-BR").includes(termo)) : opcoes;
  const alternar = (marca: string) =>
    aoMudar(selecionadas.includes(marca) ? selecionadas.filter((m) => m !== marca) : [...selecionadas, marca]);
  const rotulo =
    selecionadas.length === 0
      ? "Todas"
      : selecionadas.length === 1
        ? selecionadas[0]
        : `${formatarNumero(selecionadas.length)} marcas`;

  return (
    <div ref={raiz} className="relative flex w-56 flex-col gap-1.5">
      <span className="text-xs font-medium text-texto-2">Marcas</span>
      <button
        type="button"
        onClick={() => setAberto(!aberto)}
        aria-haspopup="true"
        aria-expanded={aberto}
        aria-controls={aberto ? idLista : undefined}
        aria-label={`Marcas: ${rotulo}`}
        className="campo flex items-center justify-between gap-2 text-left"
      >
        <span className="truncate">{rotulo}</span>
        <ChevronDown aria-hidden className="size-4 shrink-0 text-texto-mudo" />
      </button>
      {aberto && (
        <div
          id={idLista}
          className="absolute top-full z-20 mt-1 flex w-72 max-w-[calc(100vw-2rem)] flex-col gap-2 rounded-lg border border-borda bg-superficie p-2 shadow-lg"
        >
          <label htmlFor={idBusca} className="sr-only">
            Buscar marca
          </label>
          <input
            id={idBusca}
            type="search"
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
            placeholder="Buscar marca…"
            autoFocus
            className="campo"
          />
          {opcoes.length === 0 ? (
            <p className="px-1 py-2 text-sm text-texto-2">Nenhuma marca nos recontados.</p>
          ) : (
            <ul aria-label="Marcas dos recontados" className="max-h-64 overflow-auto">
              {visiveis.map((o) => (
                <li key={o.marca}>
                  <label className="flex cursor-pointer items-center gap-2 rounded px-1.5 py-1 text-sm hover:bg-superficie-2">
                    <input
                      type="checkbox"
                      checked={selecionadas.includes(o.marca)}
                      onChange={() => alternar(o.marca)}
                      className="accent-acento"
                    />
                    <span className="flex-1 truncate">{o.marca}</span>
                    <span className="tabular text-xs text-texto-mudo">{formatarNumero(o.produtos)}</span>
                  </label>
                </li>
              ))}
              {visiveis.length === 0 && <li className="px-1.5 py-1 text-sm text-texto-2">Nenhuma marca com “{busca}”.</li>}
            </ul>
          )}
          {selecionadas.length > 0 && (
            <button type="button" onClick={() => aoMudar([])} className="btn btn-sm btn-fantasma self-start">
              Limpar marcas
            </button>
          )}
        </div>
      )}
    </div>
  );
}
