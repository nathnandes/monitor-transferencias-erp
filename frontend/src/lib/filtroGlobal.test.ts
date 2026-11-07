import { describe, expect, it } from "vitest";

import { escreverFiltroGlobal, FILTRO_GLOBAL_PADRAO, lerFiltroGlobal, queryDoFiltroGlobal } from "./filtroGlobal";

describe("filtro global ⇄ URL", () => {
  it("sem parâmetros: consolidado, hoje", () => {
    expect(lerFiltroGlobal("")).toEqual(FILTRO_GLOBAL_PADRAO);
  });

  it("lê empresa e período", () => {
    expect(lerFiltroGlobal("?empresa=03&periodo=mes")).toEqual({ ...FILTRO_GLOBAL_PADRAO, empresa: "03", periodo: "mes" });
  });

  it("link antigo de transferências com datas abre como personalizado", () => {
    expect(lerFiltroGlobal("?data_inicial=2026-09-01&data_final=2026-09-10")).toEqual({
      ...FILTRO_GLOBAL_PADRAO,
      periodo: "personalizado",
      dataInicial: "2026-09-01",
      dataFinal: "2026-09-10",
    });
  });

  it("descarta o que for inválido", () => {
    expect(lerFiltroGlobal("?periodo=semana").periodo).toBe("hoje");
    expect(lerFiltroGlobal("?periodo=personalizado&data_inicial=2026-02-30").dataInicial).toBe("");
    expect(lerFiltroGlobal("?periodo=personalizado&data_inicial=2026-09-20&data_final=2026-09-10").dataFinal).toBe("");

    expect(lerFiltroGlobal("?periodo=mes&data_inicial=2026-09-01").dataInicial).toBe("");
  });

  it("grava só as próprias chaves, omitindo os padrões", () => {
    const busca = new URLSearchParams("status=ERRO&empresa=01&periodo=mes");
    escreverFiltroGlobal(busca, { ...FILTRO_GLOBAL_PADRAO, empresa: "02" });
    expect(busca.toString()).toBe("status=ERRO&empresa=02");
  });

  it("ida e volta preserva o filtro", () => {
    const filtro = { empresa: "05", periodo: "personalizado" as const, dataInicial: "2026-09-01", dataFinal: "2026-09-03" };
    expect(lerFiltroGlobal(queryDoFiltroGlobal(filtro))).toEqual(filtro);
    expect(queryDoFiltroGlobal(FILTRO_GLOBAL_PADRAO)).toBe("");
  });
});
