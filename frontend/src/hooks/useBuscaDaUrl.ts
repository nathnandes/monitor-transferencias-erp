import { useSyncExternalStore } from "react";


const EVENTO = "erp:busca";

export function gravarBusca(busca: URLSearchParams, modo: "push" | "replace") {
  const texto = busca.toString();
  const search = texto ? `?${texto}` : "";
  if (search === window.location.search) return;
  const url = `${window.location.pathname}${search}${window.location.hash}`;
  if (modo === "push") window.history.pushState(null, "", url);
  else window.history.replaceState(null, "", url);
  window.dispatchEvent(new Event(EVENTO));
}

function assinar(aoMudar: () => void) {
  window.addEventListener("popstate", aoMudar);
  window.addEventListener(EVENTO, aoMudar);
  return () => {
    window.removeEventListener("popstate", aoMudar);
    window.removeEventListener(EVENTO, aoMudar);
  };
}

const lerBusca = () => window.location.search;


export function useBuscaDaUrl(): string {
  return useSyncExternalStore(assinar, lerBusca);
}


export function aoGravarBusca(aoMudar: () => void): () => void {
  window.addEventListener(EVENTO, aoMudar);
  return () => window.removeEventListener(EVENTO, aoMudar);
}
