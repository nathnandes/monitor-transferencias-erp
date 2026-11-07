import { useCallback, useEffect, useState } from "react";

import { aoGravarBusca, gravarBusca } from "../../../hooks/useBuscaDaUrl";
import { FILTROS_VAZIOS, type FiltrosTransferencia } from "../../../types/api";
import {
  CHAVES_CONSULTA,
  consultaParaQuery,
  normalizarFiltros,
  queryParaConsulta,
  type ConsultaTransferencias,
} from "../lib/queryFilters";

type ModoHistorico = "push" | "replace";

function lerDaUrl(): ConsultaTransferencias {
  return queryParaConsulta(window.location.search);
}


export function useTransferQuery() {
  const [consulta, setConsulta] = useState<ConsultaTransferencias>(lerDaUrl);
  const [modo, setModo] = useState<ModoHistorico>("replace");


  useEffect(() => {
    const busca = new URLSearchParams(window.location.search);
    for (const chave of CHAVES_CONSULTA) busca.delete(chave);
    for (const [chave, valor] of new URLSearchParams(consultaParaQuery(consulta))) busca.set(chave, valor);
    gravarBusca(busca, modo);
  }, [consulta, modo]);


  useEffect(() => {
    const aoNavegar = () => {
      setModo("replace");
      setConsulta((atual) => {
        const lida = lerDaUrl();

        return consultaParaQuery(lida) === consultaParaQuery(atual) ? atual : lida;
      });
    };
    window.addEventListener("popstate", aoNavegar);
    const parar = aoGravarBusca(aoNavegar);
    return () => {
      window.removeEventListener("popstate", aoNavegar);
      parar();
    };
  }, []);

  const atualizar = useCallback(
    (novoModo: ModoHistorico, alterar: (atual: ConsultaTransferencias) => ConsultaTransferencias) => {
      setModo(novoModo);
      setConsulta(alterar);
    },
    [],
  );


  const aplicarFiltros = useCallback(
    (filtros: FiltrosTransferencia) =>
      atualizar("push", (c) => ({ ...c, filtros: normalizarFiltros(filtros), pagina: 1 })),
    [atualizar],
  );

  const limparFiltros = useCallback(
    () => atualizar("push", (c) => ({ ...c, filtros: FILTROS_VAZIOS, pagina: 1 })),
    [atualizar],
  );


  const irParaPagina = useCallback(
    (pagina: number) => atualizar("push", (c) => ({ ...c, pagina: Math.max(1, pagina) })),
    [atualizar],
  );

  const mudarTamanhoPagina = useCallback(
    (tamanhoPagina: number) => atualizar("push", (c) => ({ ...c, tamanhoPagina, pagina: 1 })),
    [atualizar],
  );

  const abrirDetalhe = useCallback(
    (id: number) => atualizar("replace", (c) => ({ ...c, detalheId: id })),
    [atualizar],
  );

  const fecharDetalhe = useCallback(
    () => atualizar("replace", (c) => ({ ...c, detalheId: null })),
    [atualizar],
  );

  return {
    consulta,
    aplicarFiltros,
    limparFiltros,
    irParaPagina,
    mudarTamanhoPagina,
    abrirDetalhe,
    fecharDetalhe,
  };
}
