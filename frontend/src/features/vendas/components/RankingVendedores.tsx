import { useState } from "react";

import { formatarMoeda, formatarNumero } from "../../../lib/format";
import { calcularVariacao } from "../../../lib/variacao";
import type { RankingVendedores as Ranking } from "../../../types/api";
import { IndicadorVariacao } from "../../../components/ui/IndicadorVariacao";
import { formatarPercentual, nomeProprio, paraNumero } from "../lib/vendas";

const CELULA = "px-3 py-2.5";

type Visao = "todos" | "abaixo";

interface RankingVendedoresProps {
  dados: Ranking;

  rotuloComparacao?: string;
}


export function RankingVendedores({ dados, rotuloComparacao }: RankingVendedoresProps) {
  const [visao, setVisao] = useState<Visao>("todos");
  const media = paraNumero(dados.media_faturamento);
  const maior = Math.max(...dados.vendedores.map((v) => paraNumero(v.faturamento)), 0);
  const abaixo = dados.vendedores.filter((v) => v.abaixo_da_media).length;
  const comComparacao = Boolean(rotuloComparacao) && dados.vendedores.some((v) => v.faturamento_comparacao !== null);
  const linhas = dados.vendedores
    .map((v, i) => ({ ...v, posicao: i + 1 }))
    .filter((v) => visao === "todos" || v.abaixo_da_media);
  const posicaoMedia = maior > 0 ? (media / maior) * 100 : 0;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <dl className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
          <div className="flex gap-1.5">
            <dt className="text-texto-mudo">Vendedores</dt>
            <dd className="tabular font-semibold text-texto">{formatarNumero(dados.vendedores.length)}</dd>
          </div>
          <div className="flex gap-1.5">
            <dt className="text-texto-mudo">Média por vendedor</dt>
            <dd className="tabular font-semibold text-texto">{formatarMoeda(dados.media_faturamento)}</dd>
          </div>
          <div className="flex gap-1.5">
            <dt className="text-texto-mudo">Abaixo da média</dt>
            <dd className="tabular font-semibold text-critico-texto">{formatarNumero(abaixo)}</dd>
          </div>
        </dl>
        <div role="group" aria-label="Vendedores exibidos" className="flex rounded-lg border border-borda bg-superficie-2 p-0.5">
          {(
            [
              { valor: "todos", rotulo: "Todos" },
              { valor: "abaixo", rotulo: "Abaixo da média" },
            ] as const
          ).map((o) => {
            const ativo = o.valor === visao;
            return (
              <button
                key={o.valor}
                type="button"
                aria-pressed={ativo}
                onClick={() => setVisao(o.valor)}
                className={`h-8 rounded-md px-3 text-xs font-semibold transition-colors sm:h-7 ${
                  ativo ? "bg-texto text-superficie shadow-sm" : "text-texto-2 hover:bg-superficie-3 hover:text-texto"
                }`}
              >
                {o.rotulo}
              </button>
            );
          })}
        </div>
      </div>

      <div className="-mx-1 overflow-x-auto">
        <table className="w-full min-w-[44rem] text-sm">
          <thead>
            <tr className="border-b border-borda text-left text-[11px] font-semibold uppercase tracking-wide text-texto-mudo">
              <th scope="col" className={`${CELULA} w-10`}>
                #
              </th>
              <th scope="col" className={CELULA}>
                Vendedor
              </th>
              <th scope="col" className={`${CELULA} w-[34%]`}>
                Faturamento
              </th>
              <th scope="col" className={`${CELULA} text-right`}>
                % da média
              </th>
              <th scope="col" className={`${CELULA} text-right`}>
                Notas
              </th>
              <th scope="col" className={`${CELULA} text-right`}>
                Ticket médio
              </th>
              {comComparacao && (
                <th scope="col" className={`${CELULA} text-right`}>
                  Variação
                </th>
              )}
            </tr>
          </thead>
          <tbody>
            {linhas.map((v) => {
              const faturamento = paraNumero(v.faturamento);
              const largura = maior > 0 ? (faturamento / maior) * 100 : 0;
              const daMedia = media > 0 ? (faturamento / media) * 100 : 0;
              return (
                <tr key={v.id_vendedor} className="border-b border-borda/70 last:border-0 hover:bg-superficie-2">
                  <td className={`${CELULA} tabular font-bold text-texto-mudo`}>{v.posicao}</td>
                  <td className={CELULA}>
                    <p className="font-medium text-texto" title={v.nome ?? undefined}>
                      {v.nome ? nomeProprio(v.nome) : `Vendedor ${v.id_vendedor}`}
                    </p>
                    <p className="text-xs text-texto-mudo">
                      <span className="tabular">Cód. {v.id_vendedor}</span> · {v.empresas.length === 1 ? "Loja" : "Lojas"}{" "}
                      {v.empresas.map((e) => e.codigo).join(", ")}
                    </p>
                  </td>
                  <td className={CELULA}>
                    <p className="tabular font-semibold text-texto">{formatarMoeda(v.faturamento)}</p>
                    <div className="relative mt-1.5 h-1.5 rounded-sm bg-superficie-3" aria-hidden>
                      <div
                        className={`h-full rounded-sm ${v.abaixo_da_media ? "bg-critico" : "bg-texto"}`}
                        style={{ width: `${largura}%` }}
                      />
                      <div className="absolute -top-1 h-4 w-0.5 bg-texto-mudo" style={{ left: `${posicaoMedia}%` }} />
                    </div>
                  </td>
                  <td className={`${CELULA} tabular text-right font-semibold`}>
                    <span className={v.abaixo_da_media ? "text-critico-texto" : "text-bom-texto"}>
                      {formatarPercentual(daMedia)}
                    </span>
                    {v.abaixo_da_media && <span className="sr-only"> (abaixo da média)</span>}
                  </td>
                  <td className={`${CELULA} tabular text-right text-texto-2`}>{formatarNumero(v.notas)}</td>
                  <td className={`${CELULA} tabular text-right text-texto-2`}>{formatarMoeda(v.ticket_medio)}</td>
                  {comComparacao && rotuloComparacao && (
                    <td className={`${CELULA} text-right text-xs`}>
                      {v.faturamento_comparacao !== null && (
                        <IndicadorVariacao
                          className="justify-end"
                          rotulo={rotuloComparacao}
                          variacao={calcularVariacao(
                            faturamento,
                            paraNumero(v.faturamento_comparacao),
                            rotuloComparacao,
                            "subir",
                          )}
                        />
                      )}
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {dados.sem_vendedor_notas > 0 && (
        <p className="text-xs text-texto-mudo">
          {formatarNumero(dados.sem_vendedor_notas)} {dados.sem_vendedor_notas === 1 ? "nota" : "notas"} sem vendedor (
          {formatarMoeda(dados.sem_vendedor_faturamento)}) ficam fora do ranking e da média.
        </p>
      )}
    </div>
  );
}
