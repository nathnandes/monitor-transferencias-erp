import { useEffect, useMemo, useState } from "react";

import { EmptyState } from "../../../components/ui/EmptyState";
import { ErrorState } from "../../../components/ui/ErrorState";
import { LoadingState } from "../../../components/ui/LoadingState";
import { Pagination } from "../../../components/ui/Pagination";
import { StatusBadge } from "../../../components/ui/StatusBadge";
import { useAsync } from "../../../hooks/useAsync";
import { formatarMoeda, formatarNumero, rotuloDia } from "../../../lib/format";
import type { Tom } from "../../../lib/status";
import { getParcelas } from "../../../services/financeiroService";
import type {
  DataParcela,
  Parcela,
  ParamsFinanceiro,
  SituacaoParcela,
} from "../../../types/api";
import { nomeForma } from "../lib/financeiro";

const TH =
  "px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-wider text-texto-mudo";
const TH_NUM = `${TH} text-right`;
const TD = "px-3 py-2 align-top whitespace-nowrap";
const TD_NUM = `${TD} text-right tabular-nums`;

const TAMANHO_PAGINA = 50;

const SITUACAO: Record<Parcela["situacao"], { rotulo: string; tom: Tom }> = {
  PAGA: { rotulo: "Paga", tom: "bom" },
  PARCIAL: { rotulo: "Parcial", tom: "aviso" },
  PENDENTE: { rotulo: "Pendente", tom: "critico" },
};

interface TabelaParcelasProps {

  base: ParamsFinanceiro;

  formas: string[];

  rodada: number;
}

function dia(valor: string | null | undefined): string {
  return valor ? rotuloDia(valor) : "—";
}


export function TabelaParcelas({ base, formas, rodada }: TabelaParcelasProps) {
  const [dataPor, setDataPor] = useState<DataParcela>("lancamento");
  const [situacao, setSituacao] = useState<SituacaoParcela>("todas");
  const [forma, setForma] = useState("");
  const [pagina, setPagina] = useState(1);


  useEffect(() => setPagina(1), [base, dataPor, situacao, forma]);

  const params = useMemo(
    () => ({
      ...base,
      data_por: dataPor,
      situacao,
      forma: forma || undefined,
      pagina,
      tamanho_pagina: TAMANHO_PAGINA,
    }),
    [base, dataPor, situacao, forma, pagina],
  );
  const lista = useAsync((s) => getParcelas(params, s), [params], rodada);
  const dados = lista.data;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1.5">
          <label htmlFor="parcelas-data" className="text-xs font-medium text-texto-2">
            Período pelo dia
          </label>
          <select
            id="parcelas-data"
            className="campo"
            value={dataPor}
            onChange={(e) => setDataPor(e.target.value as DataParcela)}
          >
            <option value="lancamento">da venda (bate com o Vendido)</option>
            <option value="pagamento">do pagamento (bate com o Recebido)</option>
          </select>
        </div>
        <div className="flex flex-col gap-1.5">
          <label htmlFor="parcelas-situacao" className="text-xs font-medium text-texto-2">
            Situação
          </label>
          <select
            id="parcelas-situacao"
            className="campo"
            value={situacao}
            onChange={(e) => setSituacao(e.target.value as SituacaoParcela)}
          >
            <option value="todas">Todas</option>
            <option value="pagas">Pagas</option>
            <option value="pendentes">Pendentes (e parciais)</option>
          </select>
        </div>
        <div className="flex flex-col gap-1.5">
          <label htmlFor="parcelas-forma" className="text-xs font-medium text-texto-2">
            Forma
          </label>
          <select
            id="parcelas-forma"
            className="campo"
            value={forma}
            onChange={(e) => setForma(e.target.value)}
          >
            <option value="">Todas</option>
            {formas.map((f) => (
              <option key={f} value={f}>
                {nomeForma(f)}
              </option>
            ))}
          </select>
        </div>
      </div>

      {dados && (
        <p className="text-xs text-texto-mudo" aria-live="polite">
          {formatarNumero(dados.total)} parcelas · valor {formatarMoeda(dados.valor)} · pago{" "}
          {formatarMoeda(dados.valor_pago)} · pendente {formatarMoeda(dados.valor_pendente)}
        </p>
      )}

      {lista.loading && !dados ? (
        <LoadingState rotulo="Carregando as parcelas..." />
      ) : lista.error && !dados ? (
        <ErrorState erro={lista.error} aoTentarNovamente={lista.recarregar} />
      ) : !dados || dados.itens.length === 0 ? (
        <EmptyState titulo="Nenhuma parcela com esse filtro." />
      ) : (
        <>
          <div className="overflow-x-auto rounded border border-borda">
            <table className="w-full min-w-[980px] border-collapse text-sm">
              <caption className="sr-only">Parcelas, uma a uma</caption>
              <thead className="bg-superficie-2">
                <tr>
                  <th scope="col" className={TH}>Loja</th>
                  <th scope="col" className={TH}>Documento</th>
                  <th scope="col" className={TH}>Forma</th>
                  <th scope="col" className={TH}>Venda</th>
                  <th scope="col" className={TH}>Vencimento</th>
                  <th scope="col" className={TH}>Pagamento</th>
                  <th scope="col" className={TH_NUM}>Valor</th>
                  <th scope="col" className={TH_NUM}>Pago</th>
                  <th scope="col" className={TH_NUM}>Pendente</th>
                  <th scope="col" className={TH}>Situação</th>
                </tr>
              </thead>
              <tbody>
                {dados.itens.map((p) => (
                  <tr
                    key={`${p.empresa}-${p.documento}-${p.titulo}-${p.parcela}`}
                    className="border-t border-borda"
                  >
                    <td className={`${TD} text-texto-2`} title={p.empresa_nome}>
                      {p.empresa}
                    </td>
                    <td className={`${TD} font-mono text-xs text-texto`}>
                      {p.documento}
                      <span className="text-texto-mudo">
                        {" "}
                        · tít. {p.titulo}/{p.parcela}
                      </span>
                    </td>
                    <td className={`${TD} text-texto-2`} title={p.forma}>
                      {nomeForma(p.forma)}
                    </td>
                    <td className={`${TD} text-texto-2`}>{dia(p.dia_lancamento)}</td>
                    <td className={`${TD} text-texto-2`}>{dia(p.vencimento)}</td>
                    <td className={`${TD} text-texto-2`}>{dia(p.dia_pagamento)}</td>
                    <td className={TD_NUM}>{formatarMoeda(p.valor)}</td>
                    <td className={TD_NUM}>{formatarMoeda(p.valor_pago)}</td>
                    <td className={TD_NUM}>{formatarMoeda(p.valor_pendente)}</td>
                    <td className={TD}>
                      <StatusBadge tom={SITUACAO[p.situacao].tom}>
                        {SITUACAO[p.situacao].rotulo}
                      </StatusBadge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination
            pagina={dados.pagina}
            totalPaginas={dados.total_paginas}
            totalRegistros={dados.total}
            tamanhoPagina={dados.tamanho_pagina}
            itensNaPagina={dados.itens.length}
            aoMudarPagina={setPagina}
            desabilitado={lista.loading}
          />
        </>
      )}
    </div>
  );
}
