import { CalendarCheck, Check, Plus, X } from "lucide-react";
import { useState, type FormEvent } from "react";

import { ehDataValida } from "../../../lib/datas";
import { rotuloDiaCurto } from "../../../lib/format";
import { DIAS_DA_SEMANA, MAX_DIAS_ESCOLHIDOS, ultimosDiasDaSemana } from "../lib/vendas";

interface FiltroDiasProps {
  dias: string[];
  hoje: string;
  aoMudar: (dias: string[]) => void;
}


export function FiltroDias({ dias, hoje, aoMudar }: FiltroDiasProps) {
  const [aberto, setAberto] = useState(false);
  const [semana, setSemana] = useState(6);
  const [quantidade, setQuantidade] = useState("4");
  const [avulso, setAvulso] = useState("");
  const ativo = dias.length > 0;
  const qtd = Number(quantidade);
  const qtdValida = Number.isInteger(qtd) && qtd >= 1 && qtd <= MAX_DIAS_ESCOLHIDOS;

  const gerar = (e: FormEvent) => {
    e.preventDefault();
    if (!qtdValida) return;
    aoMudar(ultimosDiasDaSemana(semana, qtd, hoje));
  };

  const acrescentar = () => {
    if (!ehDataValida(avulso) || dias.includes(avulso) || dias.length >= MAX_DIAS_ESCOLHIDOS) return;
    aoMudar([...dias, avulso].sort());
    setAvulso("");
  };

  const limpar = () => {
    aoMudar([]);
    setAberto(false);
  };

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          aria-pressed={ativo}
          aria-expanded={aberto || ativo}
          onClick={() => (ativo ? limpar() : setAberto((a) => !a))}
          className={`btn btn-sm ${ativo ? "btn-primario" : "btn-secundario"}`}
          title={ativo ? "Voltar ao período do filtro" : "Escolher dias avulsos, ex.: os últimos sábados"}
        >
          <CalendarCheck aria-hidden className="size-3.5" />
          {ativo ? "Dias escolhidos" : "Escolher dias"}
          {ativo && <X aria-hidden className="size-3.5" />}
        </button>
        {(aberto || ativo) && (
          <form onSubmit={gerar} className="flex flex-wrap items-center gap-2" noValidate>
            <label className="flex items-center gap-1.5 text-xs text-texto-2">
              Últimos
              <input
                type="number"
                inputMode="numeric"
                min={1}
                max={MAX_DIAS_ESCOLHIDOS}
                className="campo h-9 w-16 sm:h-8"
                value={quantidade}
                onChange={(e) => setQuantidade(e.target.value)}
                aria-invalid={!qtdValida}
                aria-label="Quantidade de dias"
              />
            </label>
            <select
              className="campo h-9 w-auto sm:h-8"
              value={semana}
              onChange={(e) => setSemana(Number(e.target.value))}
              aria-label="Dia da semana"
            >
              {DIAS_DA_SEMANA.map((s) => (
                <option key={s.valor} value={s.valor}>
                  {s.plural}
                </option>
              ))}
            </select>
            <button type="submit" className="btn btn-sm btn-primario" disabled={!qtdValida}>
              <Check aria-hidden className="size-3.5" />
              Aplicar
            </button>
          </form>
        )}
      </div>

      {ativo && (
        <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Dias escolhidos">
          {dias.map((dia) => (
            <span
              key={dia}
              className="inline-flex h-7 items-center gap-1 rounded-md border border-borda bg-superficie-2 pl-2 text-xs font-medium text-texto-2"
            >
              {rotuloDiaCurto(dia)}
              <button
                type="button"
                onClick={() => aoMudar(dias.filter((d) => d !== dia))}
                className="grid size-6 place-items-center rounded text-texto-mudo hover:bg-superficie-3 hover:text-texto"
                aria-label={`Tirar ${rotuloDiaCurto(dia)}`}
              >
                <X aria-hidden className="size-3" />
              </button>
            </span>
          ))}
          <input
            type="date"
            className="campo h-7 w-auto text-xs"
            value={avulso}
            max={hoje}
            onChange={(e) => setAvulso(e.target.value)}
            aria-label="Dia para acrescentar"
          />
          <button
            type="button"
            className="btn btn-fantasma btn-sm"
            onClick={acrescentar}
            disabled={!ehDataValida(avulso) || dias.includes(avulso) || dias.length >= MAX_DIAS_ESCOLHIDOS}
          >
            <Plus aria-hidden className="size-3.5" />
            Acrescentar
          </button>
          <span className="text-xs text-texto-mudo">Substituem o período e a comparação.</span>
        </div>
      )}
    </div>
  );
}
