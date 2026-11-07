import { History } from "lucide-react";
import { useState } from "react";

import { AppShell } from "../../components/layout/AppShell";
import { Header } from "../../components/layout/Header";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { LoadingState } from "../../components/ui/LoadingState";
import { Pagination } from "../../components/ui/Pagination";
import { Panel } from "../../components/ui/Panel";
import { useAsync } from "../../hooks/useAsync";
import { formatarDataHora } from "../../lib/format";
import {
  FILTROS_ATIVIDADES_VAZIOS,
  type FiltrosAtividades,
  listarAtividades,
} from "../../services/atividadesService";
import { AdminAbas } from "./components/AdminAbas";
import { mensagemErroAdmin } from "./lib/regrasAdmin";

export const TITULO_ADMIN_HISTORICO = "Administração · Histórico";

const TH = "px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-wider text-texto-mudo";
const TD = "px-3 py-2.5 align-top";


export function AdminHistoricoPage() {
  const [rascunho, setRascunho] = useState<FiltrosAtividades>(FILTROS_ATIVIDADES_VAZIOS);
  const [filtros, setFiltros] = useState<FiltrosAtividades>(FILTROS_ATIVIDADES_VAZIOS);
  const [pagina, setPagina] = useState(1);
  const lista = useAsync((s) => listarAtividades(filtros, pagina, s), [filtros, pagina]);
  const dados = lista.data;

  const aplicar = (novos: FiltrosAtividades) => {
    setFiltros(novos);
    setPagina(1);
  };

  const header = (
    <Header
      titulo={TITULO_ADMIN_HISTORICO}
      subtitulo="Entradas, saídas e alterações no sistema · somente ADMIN"
      acoes={<AdminAbas />}
      aoAtualizar={lista.recarregar}
      atualizando={lista.loading}
    />
  );

  return (
    <AppShell header={header}>
      <Panel titulo="Atividades" subtitulo="Para receber no Telegram, ligue o tipo em Administração › Alertas › Uso do sistema.">
        <form
          className="mb-4 flex flex-wrap items-end gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            aplicar(rascunho);
          }}
        >
          <div className="flex flex-col gap-1.5">
            <label htmlFor="historico-tipo" className="text-xs font-medium text-texto-2">
              Tipo
            </label>
            <select
              id="historico-tipo"
              className="campo"
              value={rascunho.tipo}
              onChange={(e) => {
                const novos = { ...rascunho, tipo: e.target.value };
                setRascunho(novos);
                aplicar(novos);
              }}
            >
              <option value="">Todos</option>
              {(dados?.tipos ?? []).map((t) => (
                <option key={t.chave} value={t.chave}>
                  {t.nome}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1.5">
            <label htmlFor="historico-usuario" className="text-xs font-medium text-texto-2">
              Quem
            </label>
            <input
              id="historico-usuario"
              className="campo"
              maxLength={100}
              value={rascunho.usuario}
              placeholder="Parte do nome"
              onChange={(e) => setRascunho({ ...rascunho, usuario: e.target.value })}
            />
          </div>
          <button type="submit" className="btn btn-secundario">
            Filtrar
          </button>
        </form>

        {lista.error && !dados && (
          <ErrorState
            titulo="Falha ao carregar o histórico"
            erro={lista.error}
            mensagem={mensagemErroAdmin(lista.error)}
            aoTentarNovamente={lista.recarregar}
          />
        )}
        {!dados && !lista.error && <LoadingState rotulo="Carregando histórico…" />}
        {dados && dados.itens.length === 0 && (
          <EmptyState icone={History} titulo="Nenhuma atividade" descricao="Nada registrado com esses filtros." />
        )}
        {dados && dados.itens.length > 0 && (
          <div className="flex flex-col gap-4">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[760px] border-collapse text-sm">
                <caption className="sr-only">Atividades no sistema</caption>
                <thead className="bg-superficie-2">
                  <tr>
                    <th scope="col" className={TH}>Quando</th>
                    <th scope="col" className={TH}>Tipo</th>
                    <th scope="col" className={TH}>O que aconteceu</th>
                    <th scope="col" className={TH}>IP</th>
                  </tr>
                </thead>
                <tbody>
                  {dados.itens.map((a) => (
                    <tr key={a.id} className="border-t border-borda">
                      <td className={`${TD} whitespace-nowrap text-texto-2`}>{formatarDataHora(a.ocorrida_em)}</td>
                      <td className={`${TD} whitespace-nowrap text-texto-2`}>{a.tipo_nome}</td>
                      <td className={`${TD} text-texto`}>
                        {a.resumo}
                        {a.detalhe && (
                          <p className="mt-0.5 whitespace-pre-wrap text-xs text-texto-mudo">{a.detalhe}</p>
                        )}
                      </td>
                      <td className={`${TD} whitespace-nowrap font-mono text-xs text-texto-mudo`}>{a.ip ?? "—"}</td>
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
          </div>
        )}
      </Panel>
    </AppShell>
  );
}
