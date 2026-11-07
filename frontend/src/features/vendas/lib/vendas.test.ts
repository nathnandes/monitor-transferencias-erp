import { describe, expect, it } from "vitest";

import { descreverDias, lerDias, ultimosDiasDaSemana } from "./vendas";

describe("dias escolhidos", () => {
  it("os últimos sábados até hoje, do mais antigo ao mais novo", () => {

    expect(ultimosDiasDaSemana(6, 3, "2026-10-27")).toEqual(["2026-10-10", "2026-10-17", "2026-10-24"]);

    expect(ultimosDiasDaSemana(2, 2, "2026-10-27")).toEqual(["2026-10-20", "2026-10-27"]);
  });

  it("lê a URL tirando datas inválidas e repetidas", () => {
    expect(lerDias("2026-10-24,lixo,2026-10-17,2026-10-24,2026-02-30")).toEqual(["2026-10-17", "2026-10-24"]);
    expect(lerDias(null)).toEqual([]);
  });

  it("descreve pelo dia da semana quando todos são iguais", () => {
    expect(descreverDias(["2026-10-17", "2026-10-24"])).toBe("2 sábados");
    expect(descreverDias(["2026-10-24"])).toBe("1 sábado");
    expect(descreverDias(["2026-10-24", "2026-10-25"])).toBe("2 dias escolhidos");
  });
});
