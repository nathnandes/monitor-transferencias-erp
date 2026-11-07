import { useEffect } from "react";

import { useSessaoOpcional } from "../../auth/AuthContext";
import { gravarBusca } from "../../../hooks/useBuscaDaUrl";
import { nomeCurtoEmpresa } from "../../../lib/format";
import { ABAS, ehAba } from "../../../routes/abas";
import type { EmpresaResumo } from "../../../types/api";
import type { Aba } from "../../../types/auth";

const GERAL: Aba = "VENDAS.GERAL";


const ABAS_DE_LOJA = ABAS.filter((a) => a.aba.startsWith("VENDAS.EMPRESA_")).map((a) => a.aba);


function numeroDaAba(aba: Aba): number {
  return Number(aba.slice("VENDAS.EMPRESA_".length));
}


export function abaDaEmpresa(codigo: string): Aba | null {
  const aba = `VENDAS.EMPRESA_${Number(codigo)}`;
  return codigo && ehAba(aba) ? aba : null;
}

export interface AbaDeVendas {

  codigo: string;
  rotulo: string;
}


export function aguardarTroca<T>(): Promise<T> {
  return new Promise<T>(() => {});
}

export interface EscopoDeVendas {

  abas: AbaDeVendas[];

  empresasDoSeletor: EmpresaResumo[] | null;
  semConsolidado: boolean;

  liberada: boolean;
}


export function useEscopoDeVendas(
  empresas: EmpresaResumo[] | null,
  empresa: string,
  carregandoEmpresas = false,
): EscopoDeVendas {
  const sessao = useSessaoOpcional();
  const temAba = (aba: Aba) => sessao?.temAba(aba) ?? true;
  const comGeral = temAba(GERAL);


  const lojas = ABAS_DE_LOJA.filter(temAba).flatMap((aba) => {
    if (!empresas) return [{ codigo: String(numeroDaAba(aba)), rotulo: ABAS.find((a) => a.aba === aba)!.rotulo }];
    const daLista = empresas.find((e) => Number(e.codigo) === numeroDaAba(aba));
    return daLista ? [{ codigo: daLista.codigo, rotulo: nomeCurtoEmpresa(daLista.nome) }] : [];
  });
  const abas = carregandoEmpresas ? [] : [...(comGeral ? [{ codigo: "", rotulo: "Geral" }] : []), ...lojas];

  const liberada = temAba(abaDaEmpresa(empresa) ?? GERAL);
  const destino = liberada || carregandoEmpresas ? null : abas[0]?.codigo;
  useEffect(() => {
    if (destino === null || destino === undefined) return;
    const busca = new URLSearchParams(window.location.search);
    if (destino) busca.set("empresa", destino);
    else busca.delete("empresa");
    gravarBusca(busca, "replace");
  }, [destino]);

  const empresasDoSeletor =
    comGeral || !empresas ? empresas : empresas.filter((e) => lojas.some((l) => l.codigo === e.codigo));
  return { abas, empresasDoSeletor, semConsolidado: !comGeral, liberada };
}
