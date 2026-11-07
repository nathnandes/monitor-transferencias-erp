import { useCallback, useEffect, useState, type DependencyList } from "react";

export interface EstadoAsync<T> {
  data: T | null;
  error: Error | null;
  loading: boolean;

  atualizadoEm: Date | null;
  recarregar: () => void;
}


export function useAsync<T>(
  carregar: (signal: AbortSignal) => Promise<T>,
  deps: DependencyList,
  gatilho: unknown = null,
): EstadoAsync<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState(true);
  const [atualizadoEm, setAtualizadoEm] = useState<Date | null>(null);
  const [versao, setVersao] = useState(0);

  const recarregar = useCallback(() => setVersao((v) => v + 1), []);

  useEffect(() => {
    const controle = new AbortController();
    setLoading(true);
    setError(null);

    carregar(controle.signal)
      .then((resultado) => {
        if (controle.signal.aborted) return;
        setData(resultado);
        setAtualizadoEm(new Date());
      })
      .catch((erro: unknown) => {
        if (controle.signal.aborted) return;
        setError(erro instanceof Error ? erro : new Error(String(erro)));
      })
      .finally(() => {
        if (!controle.signal.aborted) setLoading(false);
      });

    return () => controle.abort();


    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, gatilho, versao]);

  return { data, error, loading, atualizadoEm, recarregar };
}
