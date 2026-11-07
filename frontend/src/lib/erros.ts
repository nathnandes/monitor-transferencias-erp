

import { ApiError } from "../services/apiClient";

export type CategoriaErro = "rede" | "timeout" | "api" | "resposta" | "desconhecido";

export interface ErroDescrito {
  categoria: CategoriaErro;

  rotulo: string;
}

export function descreverErro(erro: Error): ErroDescrito {
  if (!(erro instanceof ApiError)) return { categoria: "desconhecido", rotulo: "Erro inesperado" };
  switch (erro.tipo) {
    case "rede":
      return { categoria: "rede", rotulo: "Sem conexão com a API" };
    case "timeout":
      return { categoria: "timeout", rotulo: "Tempo de resposta esgotado" };
    case "resposta_invalida":
      return { categoria: "resposta", rotulo: "Resposta inválida da API" };
    case "http":
      return { categoria: "api", rotulo: erro.status ? `Erro da API · HTTP ${erro.status}` : "Erro da API" };
  }
}
