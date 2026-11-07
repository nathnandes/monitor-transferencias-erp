import { useMemo } from "react";


export function useValorEstavel<T>(valor: T): T {
  const chave = JSON.stringify(valor);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  return useMemo(() => valor, [chave]);
}
