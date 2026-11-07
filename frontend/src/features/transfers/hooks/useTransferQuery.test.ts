import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { FILTROS_VAZIOS } from "../../../types/api";
import { useTransferQuery } from "./useTransferQuery";

beforeEach(() => {
  window.history.replaceState(null, "", "/");
});

describe("useTransferQuery", () => {
  it("lê a consulta inicial da URL", () => {
    window.history.replaceState(null, "", "/?status=erro&pagina=2&detalhe=5");
    const { result } = renderHook(() => useTransferQuery());
    expect(result.current.consulta).toMatchObject({
      filtros: { ...FILTROS_VAZIOS, status: "ERRO" },
      pagina: 2,
      detalheId: 5,
    });
  });

  it("aplicar filtros volta para a página 1 e grava na URL com pushState", () => {
    window.history.replaceState(null, "", "/?pagina=3");
    const antes = window.history.length;
    const { result } = renderHook(() => useTransferQuery());

    act(() => result.current.aplicarFiltros({ ...FILTROS_VAZIOS, empresa_origem: "01" }));
    expect(result.current.consulta.pagina).toBe(1);
    expect(window.location.search).toBe("?empresa_origem=01");
    expect(window.history.length).toBe(antes + 1);
  });

  it("trocar de página preserva os filtros", () => {
    window.history.replaceState(null, "", "/?empresa_destino=02");
    const { result } = renderHook(() => useTransferQuery());
    act(() => result.current.irParaPagina(2));
    expect(window.location.search).toBe("?empresa_destino=02&pagina=2");
  });

  it("abrir/fechar detalhe usa replaceState e preserva filtros e página", () => {
    window.history.replaceState(null, "", "/?status=PENDENTE&pagina=2");
    const antes = window.history.length;
    const { result } = renderHook(() => useTransferQuery());

    act(() => result.current.abrirDetalhe(9));
    expect(window.location.search).toBe("?status=PENDENTE&pagina=2&detalhe=9");
    act(() => result.current.fecharDetalhe());
    expect(window.location.search).toBe("?status=PENDENTE&pagina=2");
    expect(window.history.length).toBe(antes);
  });

  it("Voltar do navegador (popstate) relê a URL", () => {
    const { result } = renderHook(() => useTransferQuery());
    act(() => {
      window.history.replaceState(null, "", "/?status=ERRO");
      window.dispatchEvent(new PopStateEvent("popstate"));
    });
    expect(result.current.consulta.filtros.status).toBe("ERRO");
  });
});
