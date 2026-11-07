import { LoaderCircle, Pencil, Plus, Save, ShieldCheck, Trash2 } from "lucide-react";
import { useId, useState, type FormEvent } from "react";

import { ConfirmDialog } from "../../../components/ui/ConfirmDialog";
import { EmptyState } from "../../../components/ui/EmptyState";
import { ErrorState } from "../../../components/ui/ErrorState";
import { LoadingState } from "../../../components/ui/LoadingState";
import { Modal } from "../../../components/ui/Modal";
import { Panel } from "../../../components/ui/Panel";
import { useAsync } from "../../../hooks/useAsync";
import { ABAS, ehAba, infoAba } from "../../../routes/abas";
import { MODULOS } from "../../../routes/modulos";
import { atualizarPerfil, criarPerfil, excluirPerfil, listarPerfis } from "../../../services/adminUsuariosService";
import type { ModuloDePerfil, PerfilAdmin, PerfilEntrada } from "../../../types/admin";
import type { Aba } from "../../../types/auth";
import { mensagemErroAdmin } from "../lib/regrasAdmin";
import { AlertaFormulario, Campo } from "./CamposFormulario";


const MODULOS_DE_PERFIL = MODULOS.filter(
  (m): m is (typeof MODULOS)[number] & { modulo: ModuloDePerfil } => m.modulo !== "ADMINISTRACAO",
);

const PERFIL_VAZIO: PerfilEntrada = { nome: "", descricao: null, modulos: [], abas: [], tela_inicial: null };


function rotuloTela(codigo: string): string {
  if (ehAba(codigo)) {
    const info = infoAba(codigo);
    return `${MODULOS.find((m) => m.modulo === info.modulo)?.rotulo ?? info.modulo} › ${info.rotulo}`;
  }
  return MODULOS.find((m) => m.modulo === codigo)?.rotulo ?? codigo;
}

interface PerfisAcessoProps {

  aoConcluir: (texto: string) => void;
}


export function PerfisAcesso({ aoConcluir }: PerfisAcessoProps) {
  const [rodada, setRodada] = useState(0);
  const [editando, setEditando] = useState<PerfilAdmin | "novo" | null>(null);
  const [excluindo, setExcluindo] = useState<PerfilAdmin | null>(null);
  const [processando, setProcessando] = useState(false);
  const [falhaExcluir, setFalhaExcluir] = useState<string | null>(null);
  const perfis = useAsync((s) => listarPerfis(s), [], rodada);
  const recarregar = () => setRodada((r) => r + 1);

  const confirmarExclusao = async () => {
    if (!excluindo) return;
    setProcessando(true);
    setFalhaExcluir(null);
    try {
      await excluirPerfil(excluindo.id);
      aoConcluir(`Perfil ${excluindo.nome} excluído.`);
      setExcluindo(null);
      recarregar();
    } catch (erro) {
      setFalhaExcluir(mensagemErroAdmin(erro));
    } finally {
      setProcessando(false);
    }
  };

  const lista = perfis.data;
  return (
    <Panel
      titulo="Perfis de acesso"
      subtitulo="Quais abas e sub-abas existem para quem usa o perfil, e qual tela abre no login"
      acao={
        <button type="button" onClick={() => setEditando("novo")} className="btn btn-primario">
          <Plus aria-hidden className="size-4" />
          Criar perfil
        </button>
      }
    >
      {perfis.loading && !lista && <LoadingState rotulo="Carregando perfis…" />}
      {perfis.error && !perfis.loading && (
        <ErrorState
          titulo="Falha ao carregar os perfis"
          erro={perfis.error}
          mensagem={mensagemErroAdmin(perfis.error)}
          aoTentarNovamente={perfis.recarregar}
        />
      )}
      {lista && !perfis.error && lista.length === 0 && (
        <EmptyState
          icone={ShieldCheck}
          titulo="Nenhum perfil cadastrado."
          descricao="Sem perfil, cada usuário vê todas as abas dos módulos liberados para ele."
        />
      )}
      {lista && !perfis.error && lista.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] border-collapse text-sm">
            <caption className="sr-only">Perfis de acesso</caption>
            <thead className="bg-superficie-2">
              <tr>
                <th scope="col" className={TH}>Perfil</th>
                <th scope="col" className={TH}>Abas</th>
                <th scope="col" className={TH}>Abre em</th>
                <th scope="col" className={`${TH} text-right`}>Usuários</th>
                <th scope="col" className={`${TH} text-right`}>Ações</th>
              </tr>
            </thead>
            <tbody>
              {lista.map((p) => (
                <tr key={p.id} className="border-t border-borda align-top hover:bg-superficie-2/40">
                  <td className={TD}>
                    <p className="font-medium text-texto">{p.nome}</p>
                    {p.descricao && <p className="text-xs text-texto-mudo">{p.descricao}</p>}
                  </td>
                  <td className={`${TD} text-texto-2`}>{resumoAbas(p)}</td>
                  <td className={`${TD} whitespace-nowrap text-texto-2`}>
                    {p.tela_inicial ? rotuloTela(p.tela_inicial) : "Primeiro módulo"}
                  </td>
                  <td className={`${TD} tabular text-right text-texto-2`}>{p.usuarios}</td>
                  <td className={`${TD} text-right`}>
                    <div className="flex justify-end gap-1.5">
                      <button
                        type="button"
                        onClick={() => setEditando(p)}
                        aria-label={`Editar perfil ${p.nome}`}
                        className="btn btn-sm btn-secundario"
                      >
                        <Pencil aria-hidden className="size-3.5" />
                        Editar
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setFalhaExcluir(null);
                          setExcluindo(p);
                        }}
                        aria-label={`Excluir perfil ${p.nome}`}
                        className="btn btn-sm btn-fantasma"
                      >
                        <Trash2 aria-hidden className="size-3.5" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Modal
        aberto={editando !== null}
        titulo={editando === "novo" ? "Criar perfil" : "Editar perfil"}
        aoFechar={() => setEditando(null)}
        rotuloFechar="Fechar perfil"
      >
        {editando !== null && (
          <FormPerfil
            key={editando === "novo" ? "novo" : editando.id}
            original={editando === "novo" ? null : editando}
            aoFechar={() => setEditando(null)}
            aoSalvar={(p, novo) => {
              setEditando(null);
              aoConcluir(
                novo
                  ? `Perfil ${p.nome} criado.`
                  : `Perfil ${p.nome} salvo. Quem usa o perfil vê as mudanças no próximo login.`,
              );
              recarregar();
            }}
          />
        )}
      </Modal>

      <ConfirmDialog
        aberto={excluindo !== null}
        titulo="Excluir perfil?"
        descricao={
          <>
            <p>
              O perfil <strong className="text-texto">{excluindo?.nome}</strong> deixa de existir.
              {excluindo && excluindo.usuarios > 0 && ` Ele tem ${excluindo.usuarios} usuário(s): troque o perfil deles antes.`}
            </p>
            {falhaExcluir && <p className="mt-2 text-critico-texto">{falhaExcluir}</p>}
          </>
        }
        rotuloConfirmar="Excluir"
        perigo
        processando={processando}
        aoConfirmar={() => void confirmarExclusao()}
        aoCancelar={() => setExcluindo(null)}
      />
    </Panel>
  );
}

const TH = "px-3 py-2.5 text-left text-[11px] font-semibold uppercase tracking-wider text-texto-mudo";
const TD = "px-3 py-2.5";


function resumoAbas(p: PerfilAdmin): string {
  return p.modulos
    .map((m) => {
      const rotulo = MODULOS.find((i) => i.modulo === m)?.rotulo ?? m;
      const subs = ABAS.filter((a) => a.modulo === m);
      if (subs.length === 0) return rotulo;
      const marcadas = subs.filter((a) => p.abas.includes(a.aba));
      if (marcadas.length === subs.length) return `${rotulo} (todas)`;
      if (marcadas.length === 0) return rotulo;
      return `${rotulo} (${marcadas.map((a) => a.rotulo.replace(/ \(.*\)$/, "")).join(", ")})`;
    })
    .join(" · ");
}

interface FormPerfilProps {
  original: PerfilAdmin | null;
  aoFechar: () => void;
  aoSalvar: (perfil: PerfilAdmin, novo: boolean) => void;
}

function FormPerfil({ original, aoFechar, aoSalvar }: FormPerfilProps) {
  const [form, setForm] = useState<PerfilEntrada>(
    original
      ? {
          nome: original.nome,
          descricao: original.descricao,
          modulos: original.modulos,
          abas: original.abas,
          tela_inicial: original.tela_inicial,
        }
      : PERFIL_VAZIO,
  );
  const [tentou, setTentou] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [falha, setFalha] = useState<string | null>(null);
  const idNome = useId();
  const idDescricao = useId();
  const idTela = useId();

  const erroNome = tentou && !form.nome.trim() ? "Informe o nome do perfil." : null;


  const aplicar = (modulos: ModuloDePerfil[], abas: Aba[]) =>
    setForm((f) => {
      const telas = telasPossiveis(modulos, abas);
      return { ...f, modulos, abas, tela_inicial: f.tela_inicial && telas.includes(f.tela_inicial) ? f.tela_inicial : null };
    });


  const alternarModulo = (modulo: ModuloDePerfil, marcado: boolean) => {
    const subs = ABAS.filter((a) => a.modulo === modulo).map((a) => a.aba);
    const modulos = marcado ? [...form.modulos, modulo] : form.modulos.filter((m) => m !== modulo);
    const abas = marcado ? [...new Set([...form.abas, ...subs])] : form.abas.filter((a) => !subs.includes(a));
    aplicar(ordenarModulos(modulos), ordenarAbas(abas));
  };


  const alternarAba = (aba: Aba, marcado: boolean) => {
    const info = infoAba(aba);
    let abas: Aba[];
    if (marcado) abas = [...form.abas, aba, ...(info.pai ? [info.pai] : [])];
    else abas = form.abas.filter((a) => a !== aba && infoAba(a).pai !== aba);
    const modulos = marcado && !form.modulos.includes(info.modulo as ModuloDePerfil)
      ? [...form.modulos, info.modulo as ModuloDePerfil]
      : form.modulos;
    aplicar(ordenarModulos(modulos), ordenarAbas(abas));
  };

  const aoEnviar = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (enviando) return;
    setTentou(true);
    if (!form.nome.trim()) return;
    setEnviando(true);
    setFalha(null);
    const dados = { ...form, nome: form.nome.trim(), descricao: form.descricao?.trim() || null };
    try {
      const salvo = original ? await atualizarPerfil(original.id, dados) : await criarPerfil(dados);
      aoSalvar(salvo, original === null);
    } catch (erro) {

      setFalha(mensagemErroAdmin(erro));
      setEnviando(false);
    }
  };

  const telas = telasPossiveis(form.modulos, form.abas);
  return (
    <form noValidate onSubmit={aoEnviar} className="flex flex-col gap-4">
      {falha && <AlertaFormulario mensagem={falha} />}
      <Campo id={idNome} rotulo="Nome do perfil" erro={erroNome}>
        {(aria) => (
          <input
            id={idNome}
            type="text"
            autoComplete="off"
            autoFocus
            maxLength={60}
            value={form.nome}
            onChange={(e) => setForm((f) => ({ ...f, nome: e.target.value }))}
            disabled={enviando}
            className="campo"
            {...aria}
          />
        )}
      </Campo>
      <Campo id={idDescricao} rotulo="Descrição (opcional)">
        {(aria) => (
          <input
            id={idDescricao}
            type="text"
            autoComplete="off"
            maxLength={200}
            value={form.descricao ?? ""}
            onChange={(e) => setForm((f) => ({ ...f, descricao: e.target.value }))}
            disabled={enviando}
            className="campo"
            {...aria}
          />
        )}
      </Campo>

      <fieldset className="rounded-lg border border-borda bg-superficie-2/30 p-3">
        <legend className="px-1 text-sm font-medium text-texto-2">Abas e sub-abas</legend>
        <p className="mb-2 px-1 text-xs text-texto-mudo">
          Desmarcada, a aba deixa de existir para quem usa o perfil. Administração acompanha o papel ADMIN.
        </p>
        <ul className="flex flex-col gap-1">
          {MODULOS_DE_PERFIL.map(({ modulo, rotulo }) => {
            const subs = ABAS.filter((a) => a.modulo === modulo);
            return (
              <li key={modulo}>
                <label className="flex cursor-pointer items-center gap-2 rounded-md px-1.5 py-1 text-sm font-medium text-texto">
                  <input
                    type="checkbox"
                    checked={form.modulos.includes(modulo)}
                    onChange={(e) => alternarModulo(modulo, e.target.checked)}
                    disabled={enviando}
                    className="accent-acento"
                  />
                  {rotulo}
                </label>
                {subs.length > 0 && (
                  <ul aria-label={`Sub-abas de ${rotulo}`} className="ml-6 flex flex-col gap-0.5">
                    {subs.map((a) => (
                      <li key={a.aba} className={a.pai ? "ml-6" : undefined}>
                        <label className="flex cursor-pointer items-center gap-2 rounded-md px-1.5 py-0.5 text-sm text-texto-2">
                          <input
                            type="checkbox"
                            checked={form.abas.includes(a.aba)}
                            onChange={(e) => alternarAba(a.aba, e.target.checked)}
                            disabled={enviando}
                            className="accent-acento"
                          />
                          {a.rotulo}
                        </label>
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            );
          })}
        </ul>
      </fieldset>

      <Campo id={idTela} rotulo="Tela que abre no login" dica="Só as abas marcadas acima.">
        {(aria) => (
          <select
            id={idTela}
            value={form.tela_inicial ?? ""}
            onChange={(e) => setForm((f) => ({ ...f, tela_inicial: e.target.value || null }))}
            disabled={enviando}
            className="campo"
            {...aria}
          >
            <option value="">Primeiro módulo liberado</option>
            {telas.map((t) => (
              <option key={t} value={t}>
                {rotuloTela(t)}
              </option>
            ))}
          </select>
        )}
      </Campo>

      <div className="flex flex-wrap justify-end gap-2">
        <button type="button" onClick={aoFechar} disabled={enviando} className="btn btn-fantasma">
          Cancelar
        </button>
        <button type="submit" disabled={enviando} aria-busy={enviando} className="btn btn-primario">
          {enviando ? <LoaderCircle aria-hidden className="size-4 animate-spin" /> : <Save aria-hidden className="size-4" />}
          {enviando ? "Salvando…" : "Gravar perfil"}
        </button>
      </div>
    </form>
  );
}

function ordenarModulos(modulos: ModuloDePerfil[]): ModuloDePerfil[] {
  return MODULOS_DE_PERFIL.map((m) => m.modulo).filter((m) => modulos.includes(m));
}

function ordenarAbas(abas: Aba[]): Aba[] {
  return ABAS.map((a) => a.aba).filter((a) => abas.includes(a));
}


function telasPossiveis(modulos: readonly ModuloDePerfil[], abas: readonly Aba[]): string[] {
  const telas: string[] = [];
  for (const m of ordenarModulos([...modulos])) {
    telas.push(m);
    for (const a of ABAS) if (a.modulo === m && !a.pai && abas.includes(a.aba)) telas.push(a.aba);
  }
  return telas;
}
