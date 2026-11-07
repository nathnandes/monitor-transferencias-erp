import {
  AlertTriangle,
  ArrowLeftRight,
  CheckCircle2,
  ClipboardPen,
  Link2Off,
  ListChecks,
  PencilLine,
} from "lucide-react";
import { Fragment, useEffect, useId, useRef, useState, type FormEvent } from "react";

import { ErrorState } from "../../../components/ui/ErrorState";
import { LoadingState } from "../../../components/ui/LoadingState";
import { Pagination } from "../../../components/ui/Pagination";
import { Panel } from "../../../components/ui/Panel";
import { useAsync } from "../../../hooks/useAsync";
import { useValorEstavel } from "../../../hooks/useValorEstavel";
import { formatarDataHora, formatarMoeda, formatarNumero, formatarQuantidade, rotuloDia } from "../../../lib/format";
import {
  definirCorteAvulsas,
  desfazerVinculo,
  getCandidatosVinculo,
  getDocumentosAvulsos,
  getItensNotaLivro,
  justificarAvulsa,
  justificarAvulsasEmLote,
  relacionarAvulsas,
} from "../../../services/estoqueService";
import type {
  AlertaAvulsa,
  CorteAvulsas,
  DocumentoAvulso,
  MotivoAvulsa,
  NovaJustificativaAvulsa,
  ParamsDocumentosAvulsos,
  ParamsLivro,
  RegraAlerta,
  SituacaoJustificativa,
  TipoAvulsa,
} from "../../../types/api";
import { useSessaoOpcional } from "../../auth/AuthContext";
import { CodigoProduto } from "./CodigoProduto";
import { SeloTipo } from "./MovimentosEstoque";
import type { ProdutoSelecionado } from "./ProdutoEstoqueDetalhe";

const TAMANHO_PAGINA = 50;
const TH = "px-3 py-2 font-semibold";
const TD = "px-3 py-2 align-top";

const SITUACOES: { valor: SituacaoJustificativa; rotulo: string }[] = [
  { valor: "pendente", rotulo: "Pendentes" },
  { valor: "justificada", rotulo: "Justificadas" },
  { valor: "todas", rotulo: "Todas" },
];

interface JustificativasAvulsasProps {

  params: ParamsLivro;
  tipo?: TipoAvulsa;
  rodada?: number;
  aoAbrirProduto: (produto: ProdutoSelecionado) => void;
}

const chave = (d: DocumentoAvulso) => `${d.empresa.id}/${d.id_planilha}`;


export function JustificativasAvulsas({ params, tipo, rodada = 0, aoAbrirProduto }: JustificativasAvulsasProps) {
  const [situacao, setSituacao] = useState<SituacaoJustificativa>("pendente");
  const [alerta, setAlerta] = useState("");
  const [pagina, setPagina] = useState(1);
  const [aberto, setAberto] = useState<string | null>(null);
  const [gravacoes, setGravacoes] = useState(0);

  const [selecionados, setSelecionados] = useState<ReadonlyMap<string, DocumentoAvulso>>(new Map());
  const [loteAberto, setLoteAberto] = useState(false);
  const idAlerta = useId();

  const montados: ParamsDocumentosAvulsos = { ...params, situacao };
  if (tipo) montados.tipo = tipo;
  if (alerta) montados.alerta = alerta;
  const filtros = useValorEstavel(montados);

  useEffect(() => {
    setPagina(1);
    setAberto(null);
    setSelecionados(new Map());
    setLoteAberto(false);
  }, [filtros]);
  const docs = useAsync(
    (s) => getDocumentosAvulsos(filtros, pagina, TAMANHO_PAGINA, s),
    [filtros, pagina],

    `${rodada}/${gravacoes}`,
  );
  const d = docs.data;
  const pendentes = d?.pendentes_desde_o_corte.documentos ?? 0;
  const regras = d?.regras ?? [];
  const daPagina = d?.documentos ?? [];
  const marcadosNaPagina = daPagina.filter((doc) => selecionados.has(chave(doc))).length;

  function alternar(doc: DocumentoAvulso) {
    setSelecionados((atual) => {
      const novo = new Map(atual);
      if (novo.has(chave(doc))) novo.delete(chave(doc));
      else novo.set(chave(doc), doc);
      return novo;
    });
  }

  function alternarPagina(marcar: boolean) {
    setSelecionados((atual) => {
      const novo = new Map(atual);
      for (const doc of daPagina) {
        if (marcar) novo.set(chave(doc), doc);
        else novo.delete(chave(doc));
      }
      return novo;
    });
  }

  function limparSelecao() {
    setSelecionados(new Map());
    setLoteAberto(false);
  }

  return (
    <Panel
      titulo={
        <span className="inline-flex items-center gap-2">
          <ClipboardPen aria-hidden className="size-4 text-texto-mudo" />
          Justificativas
          {pendentes > 0 && (
            <span
              title={d?.justificar_desde ? "Pendentes desde o dia de corte" : "Todas as avulsas sem justificativa"}
              className="rounded-full bg-aviso/15 px-2 py-0.5 text-xs font-semibold text-aviso-texto"
            >
              {formatarNumero(pendentes)} pendente{pendentes === 1 ? "" : "s"}
            </span>
          )}
        </span>
      }
      subtitulo={
        (d?.justificar_desde
          ? `Toda entrada e saída avulsa a partir de ${rotuloDia(d.justificar_desde)} precisa de justificativa: `
          : "Toda entrada e saída avulsa precisa de justificativa: ") +
        "uma por documento, com o motivo e uma observação. Marque vários para justificar juntos."
      }
      nivel={2}
    >
      <div className="flex flex-col gap-3">
        {d && <DiaDeCorte corte={d.corte} aoMudar={() => setGravacoes((n) => n + 1)} />}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div role="radiogroup" aria-label="Situação da justificativa" className="flex gap-1.5">
            {SITUACOES.map((s) => {
              const n = !d ? null : s.valor === "pendente" ? d.pendentes.documentos : s.valor === "justificada" ? d.justificadas : null;
              return (
                <label
                  key={s.valor}
                  className={`flex h-8 cursor-pointer items-center gap-1.5 rounded-md border px-3 text-xs font-medium transition-colors has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-foco ${
                    situacao === s.valor
                      ? "border-texto bg-superficie-2 text-texto"
                      : "border-borda text-texto-2 hover:border-borda-forte"
                  }`}
                >
                  <input
                    type="radio"
                    name="situacao-justificativa"
                    value={s.valor}
                    checked={situacao === s.valor}
                    onChange={() => setSituacao(s.valor)}
                    className="sr-only"
                  />
                  {s.rotulo}
                  {n !== null && <span className="tabular text-texto-mudo">{formatarNumero(n)}</span>}
                </label>
              );
            })}
          </div>
          {regras.length > 0 && (
            <div className="flex items-center gap-2">
              <label htmlFor={idAlerta} className="text-xs font-medium text-texto-2">
                Avisos
              </label>
              <select id={idAlerta} value={alerta} onChange={(e) => setAlerta(e.target.value)} className="campo w-auto">
                <option value="">Todos os documentos</option>
                {regras.map((r) => (
                  <option key={r.codigo} value={r.codigo}>
                    Só entradas: {r.rotulo.toLowerCase()}
                  </option>
                ))}
              </select>
            </div>
          )}
          {d && d.pendentes.documentos > 0 && (
            <p className="text-xs text-texto-2">
              No período: <span className="font-semibold text-aviso-texto">{formatarNumero(d.pendentes.documentos)}</span>{" "}
              sem justificativa, {formatarMoeda(d.pendentes.valor)} movimentados.
            </p>
          )}
        </div>

        {docs.error ? (
          <ErrorState erro={docs.error} aoTentarNovamente={docs.recarregar} />
        ) : !d ? (
          <LoadingState rotulo="Carregando documentos avulsos…" />
        ) : d.documentos.length === 0 ? (
          <p className="flex items-center gap-2 text-sm text-texto-2">
            {situacao === "pendente" && <CheckCircle2 aria-hidden className="size-4 text-bom-texto" />}
            {alerta
              ? "Nenhuma entrada com esse aviso no período."
              : situacao === "pendente"
                ? "Nenhuma avulsa sem justificativa no período."
                : situacao === "justificada"
                  ? "Nenhuma avulsa justificada no período."
                  : "Nenhuma avulsa no período."}
          </p>
        ) : (
          <>
            {selecionados.size > 0 && (
              <BarraSelecao
                documentos={[...selecionados.values()]}
                motivos={d.motivos}
                aberto={loteAberto}
                aoAbrir={() => {
                  setAberto(null);
                  setLoteAberto(true);
                }}
                aoFechar={() => setLoteAberto(false)}
                aoLimpar={limparSelecao}
                aoGravar={() => {
                  limparSelecao();
                  setGravacoes((n) => n + 1);
                }}
              />
            )}
            <div
              aria-busy={docs.loading}
              className={`overflow-auto transition-opacity md:rounded-lg md:border md:border-borda ${docs.loading ? "opacity-60" : ""}`}
            >
              <table className="w-full text-left text-sm">
                <caption className="sr-only">Documentos avulsos e justificativas</caption>
                <thead>
                  <tr className="bg-superficie-2 text-xs uppercase tracking-wide text-texto-mudo">
                    <th scope="col" className={`${TH} w-8`}>
                      <CaixaPagina marcados={marcadosNaPagina} total={daPagina.length} aoMudar={alternarPagina} />
                    </th>
                    <th scope="col" className={TH}>Dia</th>
                    <th scope="col" className={TH}>Loja</th>
                    <th scope="col" className={TH}>Tipo</th>
                    <th scope="col" className={TH}>Documento</th>
                    <th scope="col" className={TH}>Produto</th>
                    <th scope="col" className={`${TH} text-right`}>Valor</th>
                    <th scope="col" className={TH}>Justificativa</th>
                  </tr>
                </thead>
                <tbody className="tabular">
                  {d.documentos.map((doc) => {
                    const estaAberto = aberto === chave(doc);
                    const marcado = selecionados.has(chave(doc));
                    return (
                      <Fragment key={chave(doc)}>
                        <tr
                          className={`border-t border-borda/60 ${estaAberto ? "bg-superficie-2" : marcado ? "bg-superficie-2/60" : ""}`}
                        >
                          <td className={TD}>
                            <input
                              type="checkbox"
                              checked={marcado}
                              onChange={() => alternar(doc)}
                              aria-label={`Selecionar documento ${doc.id_planilha}`}
                              className="mt-0.5 accent-acento"
                            />
                          </td>
                          <td className={TD}>{rotuloDia(doc.dia)}</td>
                          <td className={TD}>{doc.empresa.codigo}</td>
                          <td className={TD}>
                            <SeloTipo tipo={doc.tipo} />
                          </td>
                          <td className={`${TD} text-texto-2`}>{doc.id_planilha}</td>
                          <td className={TD}>
                            <button
                              type="button"
                              onClick={() => aoAbrirProduto({ idProduto: doc.id_produto, idSubproduto: doc.id_subproduto })}
                              className="text-left font-medium text-texto hover:underline"
                            >
                              <CodigoProduto idProduto={doc.id_produto} idSubproduto={doc.id_subproduto} />
                            </button>
                            {doc.descricao && <span className="block text-xs text-texto-mudo">{doc.descricao}</span>}
                            {doc.itens > 1 && (
                              <span className="block text-xs text-texto-mudo">+ {formatarNumero(doc.itens - 1)} item(ns)</span>
                            )}
                            <Avisos alertas={doc.alertas} regras={regras} resumido />
                          </td>
                          <td className={`${TD} text-right ${doc.valor.trim().startsWith("-") ? "text-critico-texto" : ""}`}>
                            {formatarMoeda(doc.valor)}
                          </td>
                          <td className={TD}>
                            <ResumoJustificativa
                              documento={doc}
                              aberto={estaAberto}
                              aoAlternar={() => setAberto(estaAberto ? null : chave(doc))}
                            />
                          </td>
                        </tr>
                        {estaAberto && (
                          <tr>
                            <td colSpan={8} className="border-t border-borda/60 bg-superficie-2/50 p-3">
                              <FormularioJustificativa
                                documento={doc}
                                motivos={d.motivos}
                                regras={regras}
                                aoCancelar={() => setAberto(null)}
                                aoGravar={() => {
                                  setAberto(null);
                                  setGravacoes((n) => n + 1);
                                }}
                              />
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <Pagination
              pagina={d.pagina}
              totalPaginas={d.total_paginas}
              totalRegistros={d.total}
              tamanhoPagina={d.tamanho_pagina}
              itensNaPagina={d.documentos.length}
              aoMudarPagina={setPagina}
              desabilitado={docs.loading}
            />
          </>
        )}
      </div>
    </Panel>
  );
}


function SeloVinculo({ documento }: { documento: DocumentoAvulso }) {
  const v = documento.vinculo;
  if (!v) return null;
  return (
    <span
      title={`Relacionada por ${v.usuario_nome} em ${formatarDataHora(v.criado_em)}`}
      className="inline-flex items-center gap-1 rounded-full border border-borda bg-superficie-2 px-2 py-0.5 text-[11px] font-medium text-texto"
    >
      <ArrowLeftRight aria-hidden className="size-3 text-texto-mudo" />
      {v.tipo === "saida_avulsa" ? "Saída" : "Entrada"} {v.id_planilha}
      {v.dia && <span className="text-texto-mudo">· {rotuloDia(v.dia)}</span>}
    </span>
  );
}


function Avisos({
  alertas,
  regras,
  resumido = false,
}: {
  alertas: AlertaAvulsa[];
  regras: RegraAlerta[];
  resumido?: boolean;
}) {
  if (alertas.length === 0) return null;
  const mostrar = resumido ? alertas.slice(0, 1) : alertas;
  const rotulo = (codigo: string) => regras.find((r) => r.codigo === codigo)?.rotulo ?? codigo;
  return (
    <ul
      aria-label="Avisos da entrada"
      className={`mt-1 flex flex-col gap-0.5 text-xs text-aviso-texto ${resumido ? "" : "rounded-md bg-aviso/10 px-2.5 py-2"}`}
    >
      {mostrar.map((a) => (
        <li key={`${a.regra}/${a.id_produto}/${a.id_subproduto}`} className="flex items-start gap-1">
          <AlertTriangle aria-hidden className="mt-0.5 size-3 shrink-0" />
          <span>
            {!resumido && (
              <>
                <CodigoProduto idProduto={a.id_produto} idSubproduto={a.id_subproduto} />
                {a.descricao ? ` ${a.descricao}` : ""}:{" "}
              </>
            )}
            {rotulo(a.regra)} ({rotuloDia(a.dia)}, {a.numero ? `nota ${a.numero}` : `doc. ${a.id_planilha}`}):{" "}
            {formatarQuantidade(a.quantidade.replace("-", ""))} un. ({formatarMoeda(a.valor.replace("-", ""))})
          </span>
        </li>
      ))}
      {resumido && alertas.length > 1 && <li>e mais {formatarNumero(alertas.length - 1)} aviso(s)</li>}
    </ul>
  );
}


function DiaDeCorte({ corte, aoMudar }: { corte: CorteAvulsas; aoMudar: () => void }) {
  const ehAdmin = useSessaoOpcional()?.usuario.role === "ADMIN";
  const [editando, setEditando] = useState(false);
  const [dia, setDia] = useState(corte.justificar_desde ?? "");
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const idDia = useId();

  function abrir() {
    setDia(corte.justificar_desde ?? "");
    setErro(null);
    setEditando(true);
  }

  async function gravar(evento: FormEvent) {
    evento.preventDefault();
    setEnviando(true);
    setErro(null);
    try {
      await definirCorteAvulsas(dia || null);
      setEditando(false);
      aoMudar();
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Não foi possível gravar o dia de corte.");
    } finally {
      setEnviando(false);
    }
  }

  if (editando) {
    return (
      <form
        onSubmit={gravar}
        aria-label="Dia de corte das justificativas"
        className="flex flex-wrap items-end gap-2 rounded-md border border-borda bg-superficie-2 p-2.5"
      >
        <div className="flex flex-col gap-1">
          <label htmlFor={idDia} className="text-xs font-medium text-texto-2">
            Cobrar as avulsas a partir de
          </label>
          <input id={idDia} type="date" value={dia} onChange={(e) => setDia(e.target.value)} className="campo" />
        </div>
        <p className="max-w-xs pb-1.5 text-xs text-texto-mudo">
          Deixe vazio para cobrar todas as avulsas sem justificativa.
        </p>
        <div className="ml-auto flex gap-2">
          <button type="button" onClick={() => setEditando(false)} className="btn btn-sm btn-fantasma">
            Cancelar
          </button>
          <button type="submit" disabled={enviando} className="btn btn-sm btn-primario">
            {enviando ? "Gravando…" : "Gravar dia de corte"}
          </button>
        </div>
        {erro && (
          <p role="alert" className="w-full text-xs text-critico-texto">
            {erro}
          </p>
        )}
      </form>
    );
  }

  return (
    <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-texto-2">
      <span>
        Dia de corte:{" "}
        <span className="font-semibold text-texto">
          {corte.justificar_desde ? rotuloDia(corte.justificar_desde) : "nenhum (todas são cobradas)"}
        </span>
      </span>
      <span className="text-texto-mudo">
        {corte.definido_por && corte.atualizado_em
          ? `· alterado por ${corte.definido_por} em ${formatarDataHora(corte.atualizado_em)}`
          : "· padrão do servidor"}
      </span>
      {ehAdmin && (
        <button type="button" onClick={abrir} className="btn btn-sm btn-fantasma">
          <PencilLine aria-hidden className="size-3.5" />
          Alterar
        </button>
      )}
    </p>
  );
}


function CaixaPagina({
  marcados,
  total,
  aoMudar,
}: {
  marcados: number;
  total: number;
  aoMudar: (marcar: boolean) => void;
}) {
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.indeterminate = marcados > 0 && marcados < total;
  }, [marcados, total]);
  return (
    <input
      ref={ref}
      type="checkbox"
      checked={total > 0 && marcados === total}
      onChange={(e) => aoMudar(e.target.checked)}
      aria-label="Selecionar todos da página"
      className="accent-acento"
    />
  );
}

interface BarraSelecaoProps {
  documentos: DocumentoAvulso[];
  motivos: MotivoAvulsa[];
  aberto: boolean;
  aoAbrir: () => void;
  aoFechar: () => void;
  aoLimpar: () => void;
  aoGravar: () => void;
}


function BarraSelecao({ documentos, motivos, aberto, aoAbrir, aoFechar, aoLimpar, aoGravar }: BarraSelecaoProps) {
  const n = documentos.length;
  const tipos = [...new Set(documentos.map((doc) => doc.tipo))];

  const comuns = motivos.filter((m) => tipos.every((t) => m.tipos.includes(t)));
  const jaJustificados = documentos.filter((doc) => doc.justificativa).length;
  const valor = documentos.reduce((soma, doc) => soma + Math.abs(Number(doc.valor)), 0);

  return (
    <section
      aria-label="Documentos selecionados"
      className="flex flex-col gap-3 rounded-md border border-borda-forte bg-superficie-2 p-3"
    >
      <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
        <span className="inline-flex items-center gap-2 text-texto">
          <ListChecks aria-hidden className="size-4 text-texto-mudo" />
          <span>
            <span className="font-semibold">{formatarNumero(n)}</span> documento
            {n === 1 ? "" : "s"} selecionado
            {n === 1 ? "" : "s"} · {formatarMoeda(valor.toFixed(2))} movimentados
          </span>
        </span>
        <div className="flex gap-2">
          <button type="button" onClick={aoLimpar} className="btn btn-sm btn-fantasma">
            Limpar seleção
          </button>
          {!aberto && (
            <button type="button" onClick={aoAbrir} className="btn btn-sm btn-primario">
              Justificar {n === 1 ? "selecionado" : `os ${formatarNumero(n)} juntos`}
            </button>
          )}
        </div>
      </div>
      {aberto && (
        <div className="flex flex-col gap-2 border-t border-borda/60 pt-3">
          {tipos.length > 1 && (
            <p className="text-xs text-texto-2">
              Entradas e saídas juntas: só aparecem os motivos que valem para as duas.
            </p>
          )}
          {jaJustificados > 0 && (
            <p className="text-xs text-aviso-texto">
              {formatarNumero(jaJustificados)} já {jaJustificados === 1 ? "tem" : "têm"} justificativa: a nova substitui
              a anterior.
            </p>
          )}
          <CamposJustificativa
            rotulo={`Justificativa dos ${formatarNumero(n)} documentos selecionados`}
            motivos={comuns}
            textoBotao={`Gravar nos ${formatarNumero(n)}`}
            aoCancelar={aoFechar}
            aoEnviar={async (dados) => {
              await justificarAvulsasEmLote(documentos, dados);
              aoGravar();
            }}
          />
        </div>
      )}
    </section>
  );
}

function ResumoJustificativa({
  documento,
  aberto,
  aoAlternar,
}: {
  documento: DocumentoAvulso;
  aberto: boolean;
  aoAlternar: () => void;
}) {
  const j = documento.justificativa;
  const rotuloDoc = `documento ${documento.id_planilha}`;
  if (!j) {
    return (
      <div className="flex flex-col items-start gap-1">
        <SeloVinculo documento={documento} />
        {documento.exige_justificativa ? (
          <span className="text-xs font-medium text-aviso-texto">Pendente</span>
        ) : (
          <span className="text-xs text-texto-mudo">Antes do corte</span>
        )}
        <button
          type="button"
          onClick={aoAlternar}
          aria-expanded={aberto}
          aria-label={`${aberto ? "Fechar" : "Justificar"} ${rotuloDoc}`}
          className={`btn btn-sm ${documento.exige_justificativa && !aberto ? "btn-primario" : "btn-fantasma"}`}
        >
          {aberto ? "Fechar" : "Justificar"}
        </button>
      </div>
    );
  }
  return (
    <div className="flex max-w-xs flex-col items-start gap-0.5">
      <SeloVinculo documento={documento} />
      <span className="font-medium text-texto">{j.motivo_rotulo}</span>
      {j.observacao && <span className="whitespace-pre-line text-xs text-texto-2">{j.observacao}</span>}
      <span className="text-[11px] text-texto-mudo">
        {j.usuario_nome} · {formatarDataHora(j.atualizado_em)}
      </span>
      <button
        type="button"
        onClick={aoAlternar}
        aria-expanded={aberto}
        aria-label={`${aberto ? "Fechar" : "Editar"} justificativa do ${rotuloDoc}`}
        className="btn btn-sm btn-fantasma mt-1"
      >
        <PencilLine aria-hidden className="size-3.5" />
        {aberto ? "Fechar" : "Editar"}
      </button>
    </div>
  );
}

interface FormularioJustificativaProps {
  documento: DocumentoAvulso;
  motivos: MotivoAvulsa[];
  regras: RegraAlerta[];
  aoCancelar: () => void;
  aoGravar: () => void;
}


function FormularioJustificativa({ documento, motivos, regras, aoCancelar, aoGravar }: FormularioJustificativaProps) {
  const itens = useAsync(
    (s) => getItensNotaLivro(documento.empresa.codigo, documento.id_planilha, s),
    [documento.empresa.codigo, documento.id_planilha],
  );

  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,22rem)]">
      <div className="min-w-0">
        <p className="mb-1.5 text-xs font-medium text-texto-2">
          Itens do documento {documento.id_planilha} · loja {documento.empresa.codigo} · {rotuloDia(documento.dia)}
        </p>
        {itens.error ? (
          <ErrorState erro={itens.error} aoTentarNovamente={itens.recarregar} />
        ) : !itens.data ? (
          <LoadingState rotulo="Carregando itens…" />
        ) : (
          <table className="w-full text-left text-xs">
            <caption className="sr-only">Itens do documento {documento.id_planilha}</caption>
            <tbody className="tabular">
              {itens.data.map((i) => (
                <tr key={`${i.sequencia}/${i.id_subproduto}`} className="border-t border-borda/60 first:border-t-0">
                  <td className="py-1 pr-2">
                    <CodigoProduto idProduto={i.id_produto} idSubproduto={i.id_subproduto} />
                    {i.descricao && <span className="block text-texto-mudo">{i.descricao}</span>}
                  </td>
                  <td className="py-1 pr-2 text-right">{formatarQuantidade(i.quantidade)}</td>
                  <td className="py-1 text-right">{formatarMoeda(i.valor)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <Avisos alertas={documento.alertas} regras={regras} />
        <PainelVinculo documento={documento} aoMudar={aoGravar} />
      </div>

      <CamposJustificativa
        rotulo={`Justificativa do documento ${documento.id_planilha}`}
        motivos={motivos.filter((m) => m.tipos.includes(documento.tipo))}
        inicial={documento.justificativa}
        textoBotao="Gravar justificativa"
        aoCancelar={aoCancelar}
        aoEnviar={async (dados) => {
          await justificarAvulsa(documento, dados);
          aoGravar();
        }}
      />
    </div>
  );
}

interface CamposJustificativaProps {

  rotulo: string;

  motivos: MotivoAvulsa[];
  inicial?: { motivo: string; observacao?: string | null } | null;
  textoBotao: string;
  aoCancelar: () => void;
  aoEnviar: (dados: NovaJustificativaAvulsa) => Promise<void>;
}


function CamposJustificativa({ rotulo, motivos, inicial, textoBotao, aoCancelar, aoEnviar }: CamposJustificativaProps) {
  const [motivo, setMotivo] = useState(inicial?.motivo ?? "");
  const [observacao, setObservacao] = useState(inicial?.observacao ?? "");
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const ids = { motivo: useId(), observacao: useId() };
  const refMotivo = useRef<HTMLSelectElement>(null);
  const exigeTexto = motivos.find((m) => m.codigo === motivo)?.exige_observacao ?? false;

  useEffect(() => {
    refMotivo.current?.focus();
    refMotivo.current?.scrollIntoView?.({ block: "nearest", behavior: "smooth" });
  }, []);

  async function enviar(evento: FormEvent) {
    evento.preventDefault();
    if (!motivo) {
      setErro("Escolha o motivo.");
      return;
    }
    if (exigeTexto && !observacao.trim()) {
      setErro("Descreva o motivo na observação.");
      return;
    }
    setEnviando(true);
    setErro(null);
    try {
      await aoEnviar({ motivo, observacao: observacao.trim() || null });
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Não foi possível gravar a justificativa.");
    } finally {
      setEnviando(false);
    }
  }

  return (
    <form onSubmit={enviar} aria-label={rotulo} className="flex flex-col gap-2">
      <label htmlFor={ids.motivo} className="text-xs font-medium text-texto-2">
        Motivo
      </label>
      <select
        id={ids.motivo}
        ref={refMotivo}
        value={motivo}
        onChange={(e) => setMotivo(e.target.value)}
        className="campo"
        required
      >
        <option value="" disabled>
          Escolha…
        </option>
        {motivos.map((m) => (
          <option key={m.codigo} value={m.codigo}>
            {m.rotulo}
          </option>
        ))}
      </select>
      <label htmlFor={ids.observacao} className="text-xs font-medium text-texto-2">
        Observação {exigeTexto ? "(obrigatória)" : "(opcional)"}
      </label>
      <textarea
        id={ids.observacao}
        value={observacao}
        onChange={(e) => setObservacao(e.target.value)}
        rows={3}
        maxLength={2000}
        placeholder="Ex.: 2 latas usadas na pintura da fachada da loja."
        className="w-full rounded-md border border-borda bg-superficie px-3 py-2 text-sm text-texto placeholder:text-texto-mudo focus:border-borda-forte"
      />
      {erro && (
        <p role="alert" className="text-xs text-critico-texto">
          {erro}
        </p>
      )}
      <div className="flex justify-end gap-2">
        <button type="button" onClick={aoCancelar} className="btn btn-sm btn-fantasma">
          Cancelar
        </button>
        <button type="submit" disabled={enviando} className="btn btn-sm btn-primario">
          {enviando ? "Gravando…" : textoBotao}
        </button>
      </div>
    </form>
  );
}


function PainelVinculo({ documento, aoMudar }: { documento: DocumentoAvulso; aoMudar: () => void }) {
  const [enviando, setEnviando] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const v = documento.vinculo;
  const outro = documento.tipo === "entrada_avulsa" ? "saída" : "entrada";
  const candidatos = useAsync(
    (s) => (v ? Promise.resolve([]) : getCandidatosVinculo(documento, s)),
    [documento, v],
  );

  async function executar(chaveAcao: string, acao: () => Promise<unknown>) {
    setEnviando(chaveAcao);
    setErro(null);
    try {
      await acao();
      aoMudar();
    } catch (e) {
      setErro(e instanceof Error ? e.message : "Não foi possível gravar o vínculo.");
    } finally {
      setEnviando(null);
    }
  }

  return (
    <section aria-label={`Relacionar com ${outro} avulsa`} className="mt-3 rounded-md border border-borda bg-superficie p-2.5">
      <h4 className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold text-texto">
        <ArrowLeftRight aria-hidden className="size-3.5 text-texto-mudo" />
        Relacionar com {outro} avulsa
      </h4>
      {v ? (
        <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-texto-2">
          <span>
            Relacionada com a {outro} <span className="font-semibold text-texto">{v.id_planilha}</span>
            {v.dia ? ` de ${rotuloDia(v.dia)}` : ""}, por {v.usuario_nome} em {formatarDataHora(v.criado_em)}.
          </span>
          <button
            type="button"
            onClick={() => executar("desfazer", () => desfazerVinculo(documento))}
            disabled={enviando !== null}
            className="btn btn-sm btn-fantasma"
          >
            <Link2Off aria-hidden className="size-3.5" />
            {enviando === "desfazer" ? "Desfazendo…" : "Desfazer vínculo"}
          </button>
        </div>
      ) : candidatos.error ? (
        <ErrorState erro={candidatos.error} aoTentarNovamente={candidatos.recarregar} />
      ) : !candidatos.data ? (
        <LoadingState rotulo={`Procurando ${outro}s da loja…`} />
      ) : candidatos.data.length === 0 ? (
        <p className="text-xs text-texto-mudo">
          Nenhuma {outro} avulsa da loja {documento.empresa.codigo} com os mesmos produtos, 30 dias antes ou depois, sem
          vínculo.
        </p>
      ) : (
        <ul aria-label={`${outro === "saída" ? "Saídas" : "Entradas"} que podem ser o par`} className="flex flex-col gap-1">
          {candidatos.data.map((c) => (
            <li key={c.id_planilha} className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded px-1.5 py-1 text-xs hover:bg-superficie-2">
              <span className="font-semibold text-texto">{c.id_planilha}</span>
              <span className="text-texto-mudo">{rotuloDia(c.dia)}</span>
              <span className="min-w-0 flex-1 truncate text-texto-2">
                <CodigoProduto idProduto={c.id_produto} idSubproduto={c.id_subproduto} />
                {c.descricao ? ` ${c.descricao}` : ""}
                {c.itens > 1 ? ` (+${formatarNumero(c.itens - 1)})` : ""}
              </span>
              <span className="tabular">{formatarQuantidade(c.quantidade)}</span>
              <span className="tabular">{formatarMoeda(c.valor)}</span>
              {c.exato ? (
                <span className="rounded-full bg-bom/15 px-2 py-0.5 font-semibold text-bom-texto">Mesmos itens</span>
              ) : (
                <span className="text-texto-mudo">{formatarNumero(c.em_comum)} em comum</span>
              )}
              <button
                type="button"
                onClick={() => executar(c.id_planilha, () => relacionarAvulsas(documento, c.id_planilha))}
                disabled={enviando !== null}
                aria-label={`Relacionar com ${outro} ${c.id_planilha}`}
                className="btn btn-sm btn-secundario"
              >
                {enviando === c.id_planilha ? "Relacionando…" : "Relacionar"}
              </button>
            </li>
          ))}
        </ul>
      )}
      {erro && (
        <p role="alert" className="mt-1.5 text-xs text-critico-texto">
          {erro}
        </p>
      )}
      {!v && candidatos.data && candidatos.data.length > 0 && (
        <p className="mt-1.5 text-[11px] text-texto-mudo">
          Relacionar justifica as duas como "Correção de lançamento" (as que ainda não tinham justificativa).
        </p>
      )}
    </section>
  );
}
