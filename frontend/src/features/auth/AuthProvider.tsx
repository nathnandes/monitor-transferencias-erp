import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { ApiError, configurarAutenticacao } from "../../services/apiClient";
import * as authService from "../../services/authService";
import type { PermissoesUsuario, TokenAcesso, Usuario } from "../../types/auth";
import { AuthContext, type EstadoAuth, type MotivoSaida, type ValorAuth } from "./AuthContext";
import { calcularExpiracao, lerSessao, limparSessao, salvarSessao, type SessaoArmazenada } from "./sessaoArmazenada";



export function antecedenciaRenovacao(restanteMs: number): number {
  return Math.min(5 * 60_000, restanteMs / 2);
}


export const NOVA_TENTATIVA_RENOVACAO_MS = 30_000;

function autenticado(usuario: Usuario, permissoes: PermissoesUsuario): EstadoAuth {
  return {
    status: "autenticado",
    usuario,
    modulos: permissoes.modulos,
    abas: permissoes.abas ?? null,
    telaInicial: permissoes.tela_inicial ?? null,
  };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [guardada] = useState(lerSessao);
  const sessaoRef = useRef<SessaoArmazenada | null>(guardada);
  const [estado, setEstado] = useState<EstadoAuth>(
    guardada ? { status: "verificando" } : { status: "anonimo", motivo: null },
  );
  const [tentativa, setTentativa] = useState(0);

  const encerrar = useCallback((motivo: MotivoSaida) => {
    sessaoRef.current = null;
    limparSessao();
    setEstado({ status: "anonimo", motivo });
  }, []);

  const guardar = useCallback((resposta: TokenAcesso) => {
    const sessao = { token: resposta.access_token, expiraEm: calcularExpiracao(resposta.expires_in) };
    sessaoRef.current = sessao;
    salvarSessao(sessao);
  }, []);


  useLayoutEffect(
    () =>
      configurarAutenticacao({
        obterToken: () => sessaoRef.current?.token ?? null,
        aoRecusarToken: (tokenEnviado) => {

          if (sessaoRef.current?.token === tokenEnviado) encerrar("expirada");
        },
      }),
    [encerrar],
  );


  const verificando = estado.status === "verificando";
  useEffect(() => {
    const token = sessaoRef.current?.token;
    if (!verificando || !token) return;
    const controle = new AbortController();
    Promise.all([authService.getMe(token, controle.signal), authService.getPermissoes(token, controle.signal)])
      .then(([usuario, permissoes]) => {
        if (!controle.signal.aborted) setEstado(autenticado(usuario, permissoes));
      })
      .catch((erro: unknown) => {
        if (controle.signal.aborted) return;
        if (erro instanceof ApiError && erro.status === 401) return;
        setEstado({ status: "erro", erro: erro instanceof Error ? erro : new Error(String(erro)) });
      });
    return () => controle.abort();
  }, [verificando, tentativa]);



  useEffect(() => {
    const sessao = sessaoRef.current;
    if (estado.status !== "autenticado" || !sessao) return;
    const restante = sessao.expiraEm - Date.now();
    const temporizador = setTimeout(() => encerrar("expirada"), Math.max(0, restante));
    if (!estado.usuario.sessao_continua) return () => clearTimeout(temporizador);

    let ativo = true;
    let renovacao: ReturnType<typeof setTimeout> | undefined;
    const renovar = () => {
      const tokenAtual = sessaoRef.current?.token;
      authService
        .renovar()
        .then((resposta) => {

          if (!ativo || sessaoRef.current?.token !== tokenAtual) return;
          guardar(resposta);
          setEstado((atual) => (atual.status === "autenticado" ? { ...atual, usuario: resposta.user } : atual));
        })
        .catch((erro: unknown) => {
          if (!ativo) return;

          if (erro instanceof ApiError && (erro.status === 401 || erro.status === 403)) return;

          const resta = (sessaoRef.current?.expiraEm ?? 0) - Date.now();
          if (resta > 1_000) renovacao = setTimeout(renovar, Math.min(NOVA_TENTATIVA_RENOVACAO_MS, resta / 2));
        });
    };
    renovacao = setTimeout(renovar, Math.max(0, restante - antecedenciaRenovacao(restante)));
    return () => {
      ativo = false;
      clearTimeout(temporizador);
      clearTimeout(renovacao);
    };
  }, [estado, encerrar, guardar]);

  const entrar = useCallback(
    async (username: string, password: string) => {
      const resposta = await authService.login(username, password);
      const token = resposta.access_token;
      const [usuario, permissoes] = await Promise.all([authService.getMe(token), authService.getPermissoes(token)]);
      guardar(resposta);
      setEstado(autenticado(usuario, permissoes));
    },
    [guardar],
  );

  const sair = useCallback(() => {
    const token = sessaoRef.current?.token;
    encerrar("logout");
    if (token) void authService.logout(token);
  }, [encerrar]);

  const trocarSenha = useCallback(
    async (senhaAtual: string, novaSenha: string) => {
      const resposta = await authService.trocarSenha(senhaAtual, novaSenha);
      guardar(resposta);
      setEstado((atual) =>
        atual.status === "autenticado" ? { ...atual, usuario: resposta.user } : atual,
      );
    },
    [guardar],
  );

  const tentarNovamente = useCallback(() => {
    setEstado({ status: "verificando" });
    setTentativa((t) => t + 1);
  }, []);

  const valor = useMemo<ValorAuth>(
    () => ({ estado, entrar, sair, trocarSenha, tentarNovamente }),
    [estado, entrar, sair, trocarSenha, tentarNovamente],
  );

  return <AuthContext value={valor}>{children}</AuthContext>;
}
