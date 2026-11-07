import { useSyncExternalStore } from "react";


export function useMediaQuery(consulta: string, padrao = true): boolean {
  return useSyncExternalStore(
    (avisar) => {
      if (typeof window.matchMedia !== "function") return () => {};
      const lista = window.matchMedia(consulta);
      lista.addEventListener("change", avisar);
      return () => lista.removeEventListener("change", avisar);
    },
    () => (typeof window.matchMedia === "function" ? window.matchMedia(consulta).matches : padrao),
    () => padrao,
  );
}
