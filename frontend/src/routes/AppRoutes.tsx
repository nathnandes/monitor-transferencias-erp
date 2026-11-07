import { Suspense } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router";

import { LoadingState } from "../components/ui/LoadingState";
import { LoginPage } from "../features/auth/LoginPage";
import { MinhaSenhaPage, ROTA_MINHA_SENHA } from "../features/auth/MinhaSenhaPage";
import { FalhaDeTela } from "./FalhaDeTela";
import { RequireAuth, RequireModulo, RotaInicial } from "./guards";
import { MODULOS, type InfoModulo } from "./modulos";
import { EmDesenvolvimentoPage, NaoEncontradaPage } from "./paginas";
import { AdminAlertasPage, AdminHistoricoPage, AdminUsuariosPage, AlertasPage, ControlePage, DashboardPage, EstoquePage, FinanceiroPage, MetasPage, TransferenciasPage, TvPage, VendasPage, VendasTvPage } from "./telas";

const INFO_DASHBOARD = MODULOS.find((m) => m.modulo === "DASHBOARD")!;
const INFO_TRANSFERENCIAS = MODULOS.find((m) => m.modulo === "TRANSFERENCIAS")!;
const INFO_VENDAS = MODULOS.find((m) => m.modulo === "VENDAS")!;
const INFO_ADMINISTRACAO = MODULOS.find((m) => m.modulo === "ADMINISTRACAO")!;

function telaDo(info: InfoModulo) {
  switch (info.modulo) {
    case "DASHBOARD":
      return <DashboardPage />;
    case "TRANSFERENCIAS":
      return <TransferenciasPage />;
    case "ESTOQUE":
      return <EstoquePage />;
    case "VENDAS":
      return <VendasPage />;
    case "FINANCEIRO":
      return <FinanceiroPage />;
    case "ALERTAS":
      return <AlertasPage />;
    case "ADMINISTRACAO":
      return <AdminUsuariosPage />;
    default:

      return <EmDesenvolvimentoPage info={info} />;
  }
}


export function AppRoutes() {
  const { pathname } = useLocation();
  return (
    <FalhaDeTela chave={pathname}>
      <Suspense fallback={<CarregandoTela />}>
        <Rotas />
      </Suspense>
    </FalhaDeTela>
  );
}

function CarregandoTela() {
  return (
    <div className="flex min-h-dvh items-center justify-center bg-plano">
      <LoadingState rotulo="Abrindo tela…" />
    </div>
  );
}

function Rotas() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<RequireAuth />}>
        <Route index element={<RotaInicial />} />
        {/* Qualquer usuário logado troca a própria senha: não exige módulo. */}
        <Route path={ROTA_MINHA_SENHA} element={<MinhaSenhaPage />} />
        {MODULOS.map((info) => (
          <Route
            key={info.modulo}
            path={info.rota}
            element={<RequireModulo info={info}>{telaDo(info)}</RequireModulo>}
          />
        ))}
        <Route
          path="/transferencias/controle"
          element={<RequireModulo info={INFO_TRANSFERENCIAS} aba="TRANSFERENCIAS.CONTROLE"><ControlePage /></RequireModulo>}
        />
        {/* Administração > Alertas: mesmo módulo e papel ADMIN da tela de usuários. */}
        <Route
          path="/admin/alertas"
          element={<RequireModulo info={INFO_ADMINISTRACAO}><AdminAlertasPage /></RequireModulo>}
        />
        <Route
          path="/admin/historico"
          element={<RequireModulo info={INFO_ADMINISTRACAO}><AdminHistoricoPage /></RequireModulo>}
        />
        {/* Modo TV: tela cheia sem menu; exige o mesmo módulo do dashboard. */}
        <Route path="/tv" element={<RequireModulo info={INFO_DASHBOARD} aba="DASHBOARD.TV"><TvPage /></RequireModulo>} />
        <Route path="/vendas/metas" element={<RequireModulo info={INFO_VENDAS}><MetasPage /></RequireModulo>} />
        <Route
          path="/vendas/tv"
          element={<RequireModulo info={INFO_VENDAS} aba="VENDAS.TV"><VendasTvPage /></RequireModulo>}
        />
        {/* Endereço da Sprint 11, antes da tela existir. */}
        <Route path="/administracao" element={<Navigate to="/admin/usuarios" replace />} />
        <Route path="*" element={<NaoEncontradaPage />} />
      </Route>
    </Routes>
  );
}
