import { useEffect } from "react";


export const INTERVALO_TELAS_MS = 60_000;


export function useAtualizacaoAutomatica(recarregar: () => void, intervaloMs: number = INTERVALO_TELAS_MS) {
  useEffect(() => {
    let timer: ReturnType<typeof setInterval> | undefined;
    const iniciar = () => {
      clearInterval(timer);
      timer = setInterval(recarregar, intervaloMs);
    };
    const aoMudarVisibilidade = () => {
      if (document.hidden) {
        clearInterval(timer);
      } else {
        recarregar();
        iniciar();
      }
    };
    iniciar();
    document.addEventListener("visibilitychange", aoMudarVisibilidade);
    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", aoMudarVisibilidade);
    };
  }, [recarregar, intervaloMs]);
}
