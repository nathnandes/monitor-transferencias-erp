import { KeyRound, LogOut } from "lucide-react";
import { Link, NavLink } from "react-router";

import { useSessaoOpcional } from "../../features/auth/AuthContext";
import { ROTA_MINHA_SENHA } from "../../features/auth/MinhaSenhaPage";
import { useFiltroGlobal } from "../../hooks/useFiltroGlobal";
import { MARCA } from "../../lib/marca";
import { modulosPermitidos, rotaInicial } from "../../routes/modulos";
import { precarregarTela } from "../../routes/telas";

const ROTULO_PAPEL = { ADMIN: "Administrador", OPERADOR: "Operador" } as const;


function useDestino() {
  const { query } = useFiltroGlobal();
  return (rota: string, somenteAdmin?: boolean) => ({ pathname: rota, search: somenteAdmin ? "" : query });
}


function iniciais(nome: string): string {
  const palavras = nome.trim().split(/\s+/).filter(Boolean);
  const nomes = palavras.filter((p) => p.length > 2);
  const usadas = nomes.length > 0 ? nomes : palavras;
  if (usadas.length === 0) return "?";
  const letras = usadas.length > 1 ? usadas[0]!.charAt(0) + usadas.at(-1)!.charAt(0) : usadas[0]!.slice(0, 2);
  return letras.toUpperCase();
}


export function BarraSuperior() {
  const sessao = useSessaoOpcional();
  const itens = sessao ? modulosPermitidos(sessao.modulos, sessao.usuario.role) : [];
  const inicio = sessao ? rotaInicial(sessao.modulos, sessao.usuario.role, sessao.telaInicial, sessao.abas) : null;
  const destino = useDestino();

  const linkInicio = inicio?.includes("?") ? inicio : inicio ? destino(inicio) : "/";

  const links = (compacto: boolean) =>
    itens.map(({ modulo, rota, rotulo, icone: Icone, somenteAdmin }) => (
      <NavLink
        key={rota}
        to={destino(rota, somenteAdmin)}
        onMouseEnter={() => precarregarTela(modulo)}
        onTouchStart={() => precarregarTela(modulo)}
        onFocus={() => precarregarTela(modulo)}
        className={({ isActive }) =>
          `group relative flex shrink-0 items-center gap-2 font-medium transition-colors ${
            compacto ? "h-11 px-3 text-xs" : "h-full px-3 text-sm"
          } ${isActive ? "text-texto" : "text-texto-mudo hover:text-texto"}`
        }
      >
        {({ isActive }) => (
          <>
            <Icone aria-hidden className={`size-4 shrink-0 ${isActive ? "text-acento" : ""}`} />
            {rotulo}
            <span
              aria-hidden
              className={`absolute inset-x-3 bottom-0 h-[3px] rounded-t-full transition-colors ${
                isActive ? "bg-acento" : "bg-transparent group-hover:bg-borda-forte"
              }`}
            />
          </>
        )}
      </NavLink>
    ));

  const assinatura = (
    <>
      <span className="hidden leading-tight sm:block">
        <span className="marca block text-[17px] text-texto">
          {MARCA.partes[0]} <span className="text-acento">{MARCA.partes[1]}</span>
        </span>
        <span className="marca-apoio block text-[9px] text-texto-mudo">ERP Automation</span>
      </span>
    </>
  );

  return (
    <div className="tema-escuro relative z-40 border-b border-borda bg-plano text-texto">
      <div className="mx-auto flex h-16 max-w-[1600px] items-stretch gap-6 px-4 sm:px-6 xl:gap-10">
        {sessao ? (
          <Link
            to={linkInicio}
            aria-label={`${MARCA.curta} · ERP Automation, página inicial`}
            className="flex shrink-0 items-center gap-3 self-center rounded-md"
          >
            {assinatura}
          </Link>
        ) : (
          <div className="flex shrink-0 items-center gap-3 self-center">{assinatura}</div>
        )}

        {sessao && (

          <nav
            aria-label="Módulos"
            className="hidden min-w-0 items-stretch gap-0.5 overflow-x-auto [scrollbar-width:none] lg:flex"
          >
            {links(false)}
          </nav>
        )}

        {sessao && (
          <div className="ml-auto flex shrink-0 items-center gap-3">
            <div className="flex items-center gap-2.5">
              <span
                aria-hidden
                className="grid size-8 shrink-0 place-items-center rounded-md border border-borda-forte bg-superficie-2 text-[11px] font-semibold tracking-wide text-texto-2"
              >
                {iniciais(sessao.usuario.nome_exibicao)}
              </span>
              <div className="hidden min-w-0 max-w-48 leading-tight md:block lg:hidden 2xl:block">
                <p className="truncate text-sm font-semibold text-texto">{sessao.usuario.nome_exibicao}</p>
                <p className="truncate text-[11px] text-texto-mudo">
                  {ROTULO_PAPEL[sessao.usuario.role]}
                  {sessao.usuario.sessao_continua && " · sessão contínua"}
                </p>
              </div>
            </div>
            <span aria-hidden className="hidden h-7 w-px bg-borda-forte md:block lg:hidden 2xl:block" />
            <Link
              to={ROTA_MINHA_SENHA}
              aria-label="Minha senha"
              title="Trocar a minha senha"
              className="btn btn-sm btn-fantasma"
            >
              <KeyRound aria-hidden className="size-4" />
              <span className="hidden sm:inline lg:hidden 2xl:inline">Minha senha</span>
            </Link>
            <button
              type="button"
              onClick={sessao.sair}
              title={`Sair (${sessao.usuario.username})`}
              className="btn btn-sm btn-fantasma"
            >
              <LogOut aria-hidden className="size-4" />
              Sair
            </button>
          </div>
        )}
      </div>

      {sessao && (
        <nav aria-label="Módulos" className="flex overflow-x-auto border-t border-borda px-1 [scrollbar-width:none] sm:px-3 lg:hidden">
          {links(true)}
        </nav>
      )}
    </div>
  );
}
