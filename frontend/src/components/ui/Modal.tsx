import { X } from "lucide-react";
import { useEffect, useId, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";

interface ModalProps {
  aberto: boolean;
  titulo: ReactNode;
  aoFechar: () => void;
  children: ReactNode;

  rotuloFechar?: string;

  variante?: "lateral" | "central";

  papel?: "dialog" | "alertdialog";

  idDescricao?: string;
}

const FOCAVEIS =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), summary, [tabindex]:not([tabindex="-1"])';

function focaveisDe(raiz: HTMLElement): HTMLElement[] {
  return Array.from(raiz.querySelectorAll<HTMLElement>(FOCAVEIS)).filter((el) => !el.closest("[hidden],[inert]"));
}


export function Modal({
  aberto,
  titulo,
  aoFechar,
  children,
  rotuloFechar = "Fechar detalhes",
  variante = "lateral",
  papel = "dialog",
  idDescricao,
}: ModalProps) {
  const raiz = useRef<HTMLDivElement>(null);
  const painel = useRef<HTMLDivElement>(null);
  const idTitulo = useId();
  const aoFecharRef = useRef(aoFechar);
  aoFecharRef.current = aoFechar;

  useEffect(() => {
    if (!aberto || !painel.current || !raiz.current) return;
    const elPainel = painel.current;
    const elRaiz = raiz.current;
    const origem = document.activeElement instanceof HTMLElement ? document.activeElement : null;


    const inertes = Array.from(document.body.children).filter(
      (el): el is HTMLElement => el instanceof HTMLElement && el !== elRaiz && !el.hasAttribute("inert"),
    );
    for (const el of inertes) el.setAttribute("inert", "");

    const aoTeclar = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        aoFecharRef.current();
        return;
      }
      if (e.key !== "Tab") return;
      const focaveis = focaveisDe(elPainel);
      const primeiro = focaveis[0];
      const ultimo = focaveis.at(-1);
      if (!primeiro || !ultimo) {
        e.preventDefault();
        elPainel.focus();
        return;
      }
      const atual = document.activeElement;
      if (e.shiftKey && (atual === primeiro || atual === elPainel)) {
        e.preventDefault();
        ultimo.focus();
      } else if (!e.shiftKey && (atual === ultimo || !elPainel.contains(atual))) {
        e.preventDefault();
        primeiro.focus();
      }
    };

    const aoFocar = (e: FocusEvent) => {
      if (e.target instanceof Node && !elRaiz.contains(e.target)) elPainel.focus();
    };

    document.addEventListener("keydown", aoTeclar);
    document.addEventListener("focusin", aoFocar);
    const overflowAnterior = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    elPainel.focus();

    return () => {
      document.removeEventListener("keydown", aoTeclar);
      document.removeEventListener("focusin", aoFocar);
      document.body.style.overflow = overflowAnterior;
      for (const el of inertes) el.removeAttribute("inert");
      if (origem?.isConnected) origem.focus();
    };
  }, [aberto]);

  if (!aberto) return null;

  return createPortal(
    <div
      ref={raiz}
      className={`fixed inset-0 z-50 flex ${variante === "central" ? "items-center justify-center p-4" : "justify-end"}`}
    >
      <div aria-hidden className="absolute inset-0 bg-[rgb(12_14_20/0.55)] backdrop-blur-[2px]" onClick={aoFechar} />
      <div
        ref={painel}
        role={papel}
        aria-modal="true"
        aria-labelledby={idTitulo}
        aria-describedby={idDescricao}
        tabIndex={-1}
        className={
          variante === "central"
            ? "relative flex max-h-full w-full max-w-md flex-col overflow-hidden rounded-painel border border-borda bg-plano shadow-elevado outline-none"
            : "relative flex h-full w-full max-w-3xl flex-col border-l border-borda bg-plano shadow-elevado outline-none"
        }
      >
        <header className="flex items-center justify-between gap-4 border-b border-borda bg-superficie px-4 py-3 sm:px-5 sm:py-4">
          <h2 id={idTitulo} className="text-lg font-bold text-texto">
            {titulo}
          </h2>
          <button type="button" onClick={aoFechar} aria-label={rotuloFechar} className="btn btn-fantasma size-10 px-0 sm:size-9">
            <X aria-hidden className="size-5" />
          </button>
        </header>
        <div className="flex-1 overflow-y-auto overscroll-contain p-4 sm:p-5">{children}</div>
      </div>
    </div>,
    document.body,
  );
}
