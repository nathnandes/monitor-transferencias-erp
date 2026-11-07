import { useId, useState } from "react";

import { ErrorState } from "../../../components/ui/ErrorState";
import { LoadingState } from "../../../components/ui/LoadingState";
import { useAsync } from "../../../hooks/useAsync";
import { formatarNumero, rotuloDia } from "../../../lib/format";
import { hojeNoFuso } from "../../../lib/periodo";
import { getExtratoProduto } from "../../../services/estoqueService";
import type { EmpresaResumo, ExtratoProduto as Extrato } from "../../../types/api";
import { AvisoAfeta, ROTULO_CATEGORIA, SeloCategoria } from "./CategoriaMovimento";
import { Quantidade } from "./EstoqueTabela";
import type { ProdutoSelecionado } from "./ProdutoEstoqueDetalhe";


interface ExtratoProdutoProps {
  produto: ProdutoSelecionado;

  empresas: EmpresaResumo[];
}


export function ExtratoProduto({ produto, empresas }: ExtratoProdutoProps) {
  const hoje = hojeNoFuso();
  const [empresa, setEmpresa] = useState(empresas[0]?.codigo ?? "");

  const [inicio, setInicio] = useState(hoje);
  const ids = { empresa: useId(), inicio: useId() };
  const extrato = useAsync(
    (s) =>
      getExtratoProduto(
        produto.idProduto,
        produto.idSubproduto,
        { empresa, data_inicial: inicio, data_final: hoje },
        s,
      ),
    [produto.idProduto, produto.idSubproduto, empresa, inicio, hoje],
  );

  if (!empresa) return null;
  return (
    <section aria-label="Extrato do produto" className="flex flex-col gap-3">
      <h3 className="font-semibold text-texto">Entradas e saídas</h3>
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex w-56 flex-col gap-1.5">
          <label htmlFor={ids.empresa} className="text-xs font-medium text-texto-2">
            Loja do extrato
          </label>
          <select id={ids.empresa} value={empresa} onChange={(e) => setEmpresa(e.target.value)} className="campo">
            {empresas.map((e) => (
              <option key={e.id} value={e.codigo}>
                {e.codigo} - {e.nome}
              </option>
            ))}
          </select>
        </div>
        <div className="flex w-40 flex-col gap-1.5">
          <label htmlFor={ids.inicio} className="text-xs font-medium text-texto-2">
            Desde
          </label>
          <input
            id={ids.inicio}
            type="date"
            value={inicio}
            max={hoje}
            onChange={(e) => e.target.value && setInicio(e.target.value)}
            className="campo"
          />
        </div>
      </div>
      {extrato.error ? (
        <ErrorState titulo="Falha ao carregar o extrato" erro={extrato.error} aoTentarNovamente={extrato.recarregar} />
      ) : !extrato.data ? (
        <LoadingState rotulo="Carregando extrato…" />
      ) : (
        <ConteudoExtrato extrato={extrato.data} />
      )}
    </section>
  );
}

function Total({ rotulo, valor }: { rotulo: string; valor: string | null }) {
  return (
    <div className="rounded-lg border border-borda bg-superficie-2/50 px-3 py-2">
      <dt className="text-xs text-texto-mudo">{rotulo}</dt>
      <dd className="tabular mt-0.5 text-base">
        <Quantidade valor={valor} forte />
      </dd>
    </div>
  );
}

export function ConteudoExtrato({ extrato }: { extrato: Extrato }) {
  const faltam = extrato.dias_sem_leitura.length;
  let diaAnterior = "";
  return (
    <div className="flex flex-col gap-3">
      <dl className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Total rotulo={`Saldo em ${rotuloDia(extrato.data_inicial)}`} valor={extrato.saldo_inicial} />
        <Total rotulo="Entradas" valor={extrato.entradas} />
        <Total rotulo="Saídas" valor={extrato.saidas} />
        <Total rotulo="Saldo hoje" valor={extrato.saldo_final} />
      </dl>
      {faltam > 0 && (
        <p role="status" className="rounded-lg bg-aviso/12 px-3 py-2 text-xs text-aviso-texto">
          {faltam} dia(s) entre {rotuloDia(extrato.data_inicial)} e hoje ainda não foram lidos do ERP (o histórico
          ainda está carregando): o saldo reconstruído pode estar errado.
        </p>
      )}
      {extrato.por_categoria.length > 0 && (
        <p className="text-xs text-texto-2">
          {extrato.por_categoria
            .filter((c) => c.afeta)
            .map((c) => `${ROTULO_CATEGORIA[c.categoria]}: ${formatarNumero(c.itens)}`)
            .join(" · ")}
        </p>
      )}
      {extrato.itens.length === 0 ? (
        <p className="text-sm text-texto-2">Nenhuma entrada ou saída deste produto nesta loja no período.</p>
      ) : (
        <div className="max-h-[50vh] overflow-auto rounded-lg border border-borda">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">Extrato do produto na loja {extrato.empresa.codigo}</caption>
            <thead className="sticky top-0 bg-superficie-2">
              <tr className="text-xs uppercase tracking-wide text-texto-mudo">
                <th scope="col" className="px-3 py-1.5 font-semibold">Dia</th>
                <th scope="col" className="px-3 py-1.5 font-semibold">Operação</th>
                <th scope="col" className="px-3 py-1.5 font-semibold">Documento</th>
                <th scope="col" className="px-3 py-1.5 text-right font-semibold">Qtd.</th>
                <th scope="col" className="px-3 py-1.5 text-right font-semibold">Saldo no fim do dia</th>
              </tr>
            </thead>
            <tbody className="tabular">
              {extrato.itens.map((m) => {
                const primeiroDoDia = m.dia !== diaAnterior;
                diaAnterior = m.dia;
                return (
                  <tr
                    key={`${m.id_planilha}/${m.sequencia ?? ""}/${m.coi}`}
                    className={`border-t border-borda/60 ${m.afeta ? "" : "opacity-60"}`}
                  >
                    <td className="whitespace-nowrap px-3 py-1.5">{primeiroDoDia ? rotuloDia(m.dia) : ""}</td>
                    <td className="px-3 py-1.5">
                      <SeloCategoria categoria={m.categoria} />
                      <span className="block text-[11px] text-texto-mudo">
                        {m.coi}
                        {m.operacao && ` · ${m.operacao}`}
                      </span>
                      <AvisoAfeta afeta={m.afeta} />
                    </td>
                    <td className="px-3 py-1.5 text-texto-2">{m.id_planilha}</td>
                    <td className="px-3 py-1.5 text-right">
                      <Quantidade valor={m.quantidade} forte />
                    </td>
                    <td className="px-3 py-1.5 text-right">
                      {primeiroDoDia ? <Quantidade valor={m.saldo_fim_dia} /> : ""}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {extrato.total_itens > extrato.itens.length && (
        <p className="text-xs text-texto-mudo">
          Mostrando os {formatarNumero(extrato.itens.length)} mais recentes de {formatarNumero(extrato.total_itens)}.
          Diminua o período para ver os mais antigos.
        </p>
      )}
    </div>
  );
}
