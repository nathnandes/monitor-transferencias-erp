import { CircleCheck, TriangleAlert, UserPlus, Users, X } from "lucide-react";
import { useCallback, useState } from "react";

import { AppShell } from "../../components/layout/AppShell";
import { Header } from "../../components/layout/Header";
import { IndicadorAtualizacao } from "../../components/layout/IndicadorAtualizacao";
import { ConfirmDialog } from "../../components/ui/ConfirmDialog";
import { EmptyState } from "../../components/ui/EmptyState";
import { ErrorState } from "../../components/ui/ErrorState";
import { LoadingState } from "../../components/ui/LoadingState";
import { Pagination } from "../../components/ui/Pagination";
import { Panel } from "../../components/ui/Panel";
import { useAsync } from "../../hooks/useAsync";
import { ativarUsuario, desativarUsuario, listarUsuarios } from "../../services/adminUsuariosService";
import { FILTROS_USUARIOS_VAZIOS, type FiltrosUsuarios as Filtros, type UsuarioAdmin } from "../../types/admin";
import { useSessao } from "../auth/AuthContext";
import { CriarUsuarioModal, AVISO_PRIMEIRO_LOGIN, AVISO_SEM_TROCA } from "./components/CriarUsuarioModal";
import { EditarUsuarioModal } from "./components/EditarUsuarioModal";
import { PerfisAcesso } from "./components/PerfisAcesso";
import { FiltrosUsuarios, temFiltroUsuarios } from "./components/FiltrosUsuarios";
import { RedefinirSenhaModal } from "./components/RedefinirSenhaModal";
import { UsuariosTabela } from "./components/UsuariosTabela";
import { AdminAbas } from "./components/AdminAbas";
import { mensagemErroAdmin } from "./lib/regrasAdmin";

export const TITULO_ADMIN_USUARIOS = "Administração · Usuários";
const TAMANHOS_PAGINA = [10, 20, 50, 100];
export const NOTA_PROPRIA_CONTA =
  "Na sua própria conta, Resetar senha e Desativar ficam indisponíveis, e o papel não pode ser alterado: peça a outro ADMIN.";

type Feedback = { tipo: "sucesso" | "erro"; texto: string };

type Aba = "usuarios" | "perfis";
const ABAS: { valor: Aba; rotulo: string }[] = [
  { valor: "usuarios", rotulo: "Usuários" },
  { valor: "perfis", rotulo: "Perfis de acesso" },
];


type Confirmacao = { tipo: "desativar" | "redefinir"; usuario: UsuarioAdmin };


export function AdminUsuariosPage() {
  const { usuario: eu } = useSessao();
  const [aba, setAba] = useState<Aba>("usuarios");
  const [filtros, setFiltros] = useState<Filtros>(FILTROS_USUARIOS_VAZIOS);
  const [pagina, setPagina] = useState(1);
  const [tamanhoPagina, setTamanhoPagina] = useState(20);
  const [rodada, setRodada] = useState(0);

  const [criando, setCriando] = useState(false);
  const [editandoId, setEditandoId] = useState<number | null>(null);
  const [confirmacao, setConfirmacao] = useState<Confirmacao | null>(null);
  const [redefinindo, setRedefinindo] = useState<UsuarioAdmin | null>(null);
  const [ocupadoId, setOcupadoId] = useState<number | null>(null);
  const [feedback, setFeedback] = useState<Feedback | null>(null);

  const lista = useAsync(
    (s) => listarUsuarios(filtros, pagina, tamanhoPagina, s),
    [filtros, pagina, tamanhoPagina],
    rodada,
  );
  const recarregar = useCallback(() => setRodada((r) => r + 1), []);

  const aplicarFiltros = (novos: Filtros) => {
    setFiltros(novos);
    setPagina(1);
  };
  const limparFiltros = () => aplicarFiltros(FILTROS_USUARIOS_VAZIOS);

  const executar = async (usuario: UsuarioAdmin, acao: () => Promise<unknown>, sucesso: string) => {
    setOcupadoId(usuario.id);
    setFeedback(null);
    try {
      await acao();
      setFeedback({ tipo: "sucesso", texto: sucesso });
      recarregar();
    } catch (erro) {

      setFeedback({ tipo: "erro", texto: `Não foi possível concluir: ${mensagemErroAdmin(erro)}` });
    } finally {
      setOcupadoId(null);
    }
  };

  const aoConfirmar = async () => {
    if (!confirmacao) return;
    const { tipo, usuario } = confirmacao;
    if (tipo === "redefinir") {

      setConfirmacao(null);
      setRedefinindo(usuario);
      return;
    }
    await executar(usuario, () => desativarUsuario(usuario.id), `Usuário ${usuario.username} desativado. As sessões abertas dele foram encerradas.`);
    setConfirmacao(null);
  };

  const dados = lista.data;
  const carregandoInicio = lista.loading && !dados;

  const header = (
    <Header
      titulo={TITULO_ADMIN_USUARIOS}
      subtitulo="Contas locais do sistema · somente ADMIN"
      acoes={<AdminAbas />}
      info={<IndicadorAtualizacao atualizadoEm={lista.atualizadoEm} atualizando={lista.loading} />}
      aoAtualizar={recarregar}
      atualizando={lista.loading}
    />
  );

  return (
    <AppShell header={header}>
      {feedback && (
        <div
          role={feedback.tipo === "erro" ? "alert" : "status"}
          className={`flex items-start gap-3 rounded-lg border px-4 py-3 text-sm ${
            feedback.tipo === "erro"
              ? "border-critico/40 bg-critico/10 text-critico-texto"
              : "border-bom/40 bg-bom/10 text-texto"
          }`}
        >
          {feedback.tipo === "erro" ? (
            <TriangleAlert aria-hidden className="mt-0.5 size-4 shrink-0" />
          ) : (
            <CircleCheck aria-hidden className="mt-0.5 size-4 shrink-0 text-bom-texto" />
          )}
          <p className="flex-1">{feedback.texto}</p>
          <button type="button" onClick={() => setFeedback(null)} aria-label="Fechar aviso" className="btn btn-fantasma size-8 px-0">
            <X aria-hidden className="size-4" />
          </button>
        </div>
      )}

      <div role="tablist" aria-label="Administração" className="flex gap-1 border-b border-borda">
        {ABAS.map((a) => (
          <button
            key={a.valor}
            type="button"
            role="tab"
            aria-selected={aba === a.valor}
            onClick={() => setAba(a.valor)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium ${
              aba === a.valor ? "border-acento text-texto" : "border-transparent text-texto-mudo hover:text-texto"
            }`}
          >
            {a.rotulo}
          </button>
        ))}
      </div>

      {aba === "perfis" ? (
        <PerfisAcesso aoConcluir={(texto) => setFeedback({ tipo: "sucesso", texto })} />
      ) : (
        <Panel
          titulo="Usuários"
          subtitulo="Criar, editar, ativar, desativar e redefinir senha"
          acao={
            <button type="button" onClick={() => setCriando(true)} className="btn btn-primario">
              <UserPlus aria-hidden className="size-4" />
              Criar usuário
            </button>
          }
        >
          <div className="flex flex-col gap-4">
            <FiltrosUsuarios aplicados={filtros} aoAplicar={aplicarFiltros} aoLimpar={limparFiltros} />

            {carregandoInicio && <LoadingState rotulo="Carregando usuários…" />}
            {lista.error && !lista.loading && (
              <ErrorState
                titulo="Falha ao carregar os usuários"
                erro={lista.error}
                mensagem={mensagemErroAdmin(lista.error)}
                aoTentarNovamente={lista.recarregar}
              />
            )}
            {dados && !lista.error && dados.itens.length === 0 && (
              <EmptyState
                icone={Users}
                titulo={temFiltroUsuarios(filtros) ? "Nenhum usuário atende aos filtros." : "Nenhum usuário cadastrado."}
                descricao={temFiltroUsuarios(filtros) ? "Ajuste a busca ou limpe os filtros." : undefined}
                acao={
                  temFiltroUsuarios(filtros) ? (
                    <button type="button" onClick={limparFiltros} className="btn btn-sm btn-secundario">
                      Limpar filtros
                    </button>
                  ) : undefined
                }
              />
            )}
            {dados && !lista.error && dados.itens.length > 0 && (
              <>
                <UsuariosTabela
                  itens={dados.itens}
                  idProprio={eu.id}
                  ocupadoId={ocupadoId}
                  aoEditar={(u) => setEditandoId(u.id)}
                  aoRedefinirSenha={(u) => setConfirmacao({ tipo: "redefinir", usuario: u })}
                  aoAtivar={(u) => void executar(u, () => ativarUsuario(u.id), `Usuário ${u.username} ativado.`)}
                  aoDesativar={(u) => setConfirmacao({ tipo: "desativar", usuario: u })}
                />
                {dados.itens.some((u) => u.id === eu.id) && (
                  <p className="text-xs text-texto-mudo">{NOTA_PROPRIA_CONTA}</p>
                )}
                <Pagination
                  pagina={dados.pagina}
                  totalPaginas={dados.total_paginas}
                  totalRegistros={dados.total}
                  tamanhoPagina={dados.tamanho_pagina}
                  itensNaPagina={dados.itens.length}
                  aoMudarPagina={setPagina}
                  opcoesTamanho={TAMANHOS_PAGINA}
                  aoMudarTamanho={(t) => {
                    setTamanhoPagina(t);
                    setPagina(1);
                  }}
                  desabilitado={lista.loading}
                />
              </>
            )}
          </div>
        </Panel>
      )}

      <CriarUsuarioModal
        aberto={criando}
        aoFechar={() => setCriando(false)}
        aoCriar={(u) => {
          setFeedback({ tipo: "sucesso", texto: `Usuário ${u.username} criado. ${u.must_change_password ? AVISO_PRIMEIRO_LOGIN : AVISO_SEM_TROCA}` });
          recarregar();
        }}
      />
      <EditarUsuarioModal
        usuarioId={editandoId}
        idProprio={eu.id}
        aoFechar={() => setEditandoId(null)}
        aoSalvar={(u) => {
          setEditandoId(null);
          setFeedback({ tipo: "sucesso", texto: `Alterações de ${u.username} salvas.` });
          recarregar();
        }}
      />
      <RedefinirSenhaModal
        usuario={redefinindo}
        aoFechar={() => setRedefinindo(null)}
        aoRedefinir={(u) => {
          setRedefinindo(null);
          setFeedback({
            tipo: "sucesso",
            texto: `Senha de ${u.username} redefinida. As sessões abertas foram encerradas${u.must_change_password ? ", e a pessoa deverá trocar a senha no próximo login" : ""}.`,
          });
          recarregar();
        }}
      />
      <ConfirmDialog
        aberto={confirmacao !== null}
        titulo={confirmacao?.tipo === "desativar" ? "Desativar usuário?" : "Redefinir senha?"}
        descricao={
          confirmacao?.tipo === "desativar" ? (
            <p>
              <strong className="font-mono text-texto">{confirmacao.usuario.username}</strong> não conseguirá mais entrar,
              e as sessões abertas dele deixam de valer na hora. Os módulos ficam guardados e voltam ao reativar.
            </p>
          ) : (
            <p>
              Você vai definir uma nova senha para{" "}
              <strong className="font-mono text-texto">{confirmacao?.usuario.username}</strong>. A senha atual deixa de
              funcionar e as sessões abertas são encerradas.
            </p>
          )
        }
        rotuloConfirmar={confirmacao?.tipo === "desativar" ? "Desativar" : "Continuar"}
        perigo={confirmacao?.tipo === "desativar"}
        processando={confirmacao !== null && ocupadoId === confirmacao.usuario.id}
        aoConfirmar={() => void aoConfirmar()}
        aoCancelar={() => setConfirmacao(null)}
      />
    </AppShell>
  );
}
