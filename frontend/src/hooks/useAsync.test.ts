import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { useAsync } from "./useAsync";

describe("useAsync", () => {
  it("carrega, registra atualizadoEm e recarrega mantendo o dado anterior", async () => {
    let n = 0;
    const carregar = vi.fn(async () => ++n);
    const { result } = renderHook(() => useAsync(carregar, []));

    expect(result.current).toMatchObject({ loading: true, data: null, atualizadoEm: null });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.data).toBe(1);
    expect(result.current.atualizadoEm).toBeInstanceOf(Date);

    act(() => result.current.recarregar());
    expect(result.current).toMatchObject({ loading: true, data: 1 });
    await waitFor(() => expect(result.current.data).toBe(2));
  });

  it("mantém o último dado quando a recarga falha", async () => {
    const carregar = vi.fn().mockResolvedValueOnce("ok").mockRejectedValueOnce(new Error("caiu"));
    const { result } = renderHook(() => useAsync(carregar, []));
    await waitFor(() => expect(result.current.data).toBe("ok"));

    act(() => result.current.recarregar());
    await waitFor(() => expect(result.current.error?.message).toBe("caiu"));
    expect(result.current.data).toBe("ok");
  });

  it("recarrega quando o gatilho muda, sem ele entrar nas deps", async () => {
    const carregar = vi.fn(async () => "ok");
    const { rerender } = renderHook(({ rodada }) => useAsync(carregar, [], rodada), {
      initialProps: { rodada: 0 },
    });
    await waitFor(() => expect(carregar).toHaveBeenCalledTimes(1));

    rerender({ rodada: 0 });
    rerender({ rodada: 1 });
    await waitFor(() => expect(carregar).toHaveBeenCalledTimes(2));
  });

  it("recarrega quando uma dependência muda e usa o valor novo", async () => {
    const carregar = vi.fn(async (_s: AbortSignal, empresa: string) => `dados de ${empresa}`);
    const { result, rerender } = renderHook(
      ({ empresa }) => useAsync((s) => carregar(s, empresa), [empresa]),
      { initialProps: { empresa: "01" } },
    );
    await waitFor(() => expect(result.current.data).toBe("dados de 01"));

    rerender({ empresa: "03" });
    await waitFor(() => expect(result.current.data).toBe("dados de 03"));
  });

  it("aborta ao desmontar e não atualiza estado depois", async () => {
    let sinal: AbortSignal | undefined;
    let resolver: (v: string) => void = () => {};
    const carregar = vi.fn((s: AbortSignal) => {
      sinal = s;
      return new Promise<string>((r) => (resolver = r));
    });
    const erroConsole = vi.spyOn(console, "error").mockImplementation(() => {});

    const { result, unmount } = renderHook(() => useAsync(carregar, []));
    unmount();
    expect(sinal?.aborted).toBe(true);

    resolver("tarde demais");
    await Promise.resolve();
    expect(result.current.data).toBeNull();
    expect(erroConsole).not.toHaveBeenCalled();
    erroConsole.mockRestore();
  });
});
