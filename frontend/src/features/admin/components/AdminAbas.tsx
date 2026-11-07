import { BellRing, History, Users } from "lucide-react";
import { NavLink } from "react-router";

const ABAS = [
  { rota: "/admin/usuarios", rotulo: "Usuários e perfis", icone: Users },
  { rota: "/admin/alertas", rotulo: "Alertas", icone: BellRing },
  { rota: "/admin/historico", rotulo: "Histórico", icone: History },
];


export function AdminAbas() {
  return (
    <nav aria-label="Seções da administração" className="flex gap-1">
      {ABAS.map(({ rota, rotulo, icone: Icone }) => (
        <NavLink
          key={rota}
          to={rota}
          className={({ isActive }) =>
            `btn btn-sm ${isActive ? "btn-primario" : "btn-secundario"}`
          }
        >
          <Icone aria-hidden className="size-3.5" />
          {rotulo}
        </NavLink>
      ))}
    </nav>
  );
}
