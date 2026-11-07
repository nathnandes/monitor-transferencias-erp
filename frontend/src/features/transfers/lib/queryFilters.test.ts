import { describe, expect, it } from "vitest";

import { FILTROS_VAZIOS } from "../../../types/api";
import {
  CONSULTA_INICIAL,
  TAMANHOS_PAGINA,
  consultaParaQuery,
  filtrosParaParams,
  linkTransferencias,
  queryParaConsulta,
} from "./queryFilters";

const completos = {
  empresa_origem: "01",
  empresa_destino: "03",
  status: "PENDENTE",
  situacao_coi: "ERRADO",
  emitida_por: "BEATRIZ",
  ocorrencia: "DIVERGENTE",
};

describe("filtros → query params", () => {
  it("usa os nomes da API e omite campos vazios", () => {
    expect(filtrosParaParams(FILTROS_VAZIOS)).toEqual({});
    expect(filtrosParaParams({ ...FILTROS_VAZIOS, empresa_origem: " 01 ", status: "" })).toEqual({ empresa_origem: "01" });
    expect(filtrosParaParams(completos)).toEqual(completos);
  });

  it("gera a query da URL omitindo os padrões", () => {
    expect(consultaParaQuery(CONSULTA_INICIAL)).toBe("");
    expect(
      consultaParaQuery({ filtros: completos, pagina: 2, tamanhoPagina: 50, detalheId: 7 }),
    ).toBe(
      "?empresa_origem=01&empresa_destino=03&status=PENDENTE&situacao_coi=ERRADO&emitida_por=BEATRIZ&ocorrencia=DIVERGENTE&pagina=2&tamanho_pagina=50&detalhe=7",
    );
  });

  it("ida e volta pela URL preserva a consulta", () => {
    const consulta = { filtros: completos, pagina: 3, tamanhoPagina: 10, detalheId: 42 };
    expect(queryParaConsulta(consultaParaQuery(consulta))).toEqual(consulta);
  });
});

describe("URL → consulta (entrada não confiável)", () => {
  it("descarta valores inválidos", () => {
    const c = queryParaConsulta(
      "?pagina=0&tamanho_pagina=500&detalhe=abc&status=pendente&empresa_origem=%2001%20",
    );
    expect(c.pagina).toBe(1);
    expect(c.tamanhoPagina).toBe(20);
    expect(c.detalheId).toBeNull();
    expect(c.filtros.status).toBe("PENDENTE");
    expect(c.filtros.empresa_origem).toBe("01");
  });

  it("ignora as chaves do filtro global (empresa, período e datas)", () => {
    const c = queryParaConsulta("?empresa=03&periodo=mes&data_inicial=2026-09-01&status=ERRO");
    expect(c.filtros).toEqual({ ...FILTROS_VAZIOS, status: "ERRO" });
  });

  it("link de outra tela: filtro global + filtros da consulta + detalhe", () => {
    expect(linkTransferencias("?empresa=03&periodo=mes", { ocorrencia: "fora_do_prazo" })).toBe(
      "/transferencias?empresa=03&periodo=mes&ocorrencia=FORA_DO_PRAZO",
    );
    expect(linkTransferencias("", { emitida_por: " JOAO " }, 9)).toBe("/transferencias?emitida_por=JOAO&detalhe=9");
    expect(linkTransferencias("", {})).toBe("/transferencias");
  });

  it("nunca oferece tamanho de página acima de 100", () => {
    expect(Math.max(...TAMANHOS_PAGINA)).toBeLessThanOrEqual(100);
  });
});
