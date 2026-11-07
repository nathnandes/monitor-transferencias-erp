import { useCallback, useMemo } from "react";

import { escreverFiltroGlobal, lerFiltroGlobal, queryDoFiltroGlobal, type FiltroGlobal } from "../lib/filtroGlobal";
import { comparacaoDoPeriodo, descreverPeriodo, hojeNoFuso, intervaloDoPeriodo } from "../lib/periodo";
import { gravarBusca, useBuscaDaUrl } from "./useBuscaDaUrl";


export function useFiltroGlobal() {
  const search = useBuscaDaUrl();
  const hoje = hojeNoFuso();

  const valor = useMemo(() => {
    const filtro = lerFiltroGlobal(search);
    const intervalo = intervaloDoPeriodo(filtro.periodo, hoje, {
      inicio: filtro.dataInicial,
      fim: filtro.dataFinal,
    });
    return {
      filtro,
      intervalo,
      comparacao: comparacaoDoPeriodo(filtro.periodo, intervalo),
      descricaoPeriodo: descreverPeriodo(filtro.periodo, intervalo),

      query: queryDoFiltroGlobal(filtro),
    };
  }, [search, hoje]);


  const definir = useCallback((novo: FiltroGlobal) => {
    const busca = escreverFiltroGlobal(new URLSearchParams(window.location.search), novo);
    busca.delete("pagina");
    gravarBusca(busca, "push");
  }, []);

  return { ...valor, definir };
}

export type EstadoFiltroGlobal = ReturnType<typeof useFiltroGlobal>;
