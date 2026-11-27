"use client";

import { useFluxo } from "@/modules/fluxo/FluxoProvider";
import { PassoShell, PASSOS } from "@/modules/fluxo/components/PassoShell";

export default function PlanoPage() {
  const { contexto, checkin, materiais } = useFluxo();

  const faltando = !contexto
    ? { rotulo: "onboarding", href: "/onboarding" }
    : !checkin
      ? { rotulo: "check-in", href: "/check-in" }
      : materiais === null
        ? { rotulo: "materiais", href: "/materiais" }
        : null;

  return (
    <PassoShell numero={3} titulo={PASSOS[3].titulo} faltando={faltando}>
      <p className="secundario">A grade da semana entra na Fase 5.</p>
    </PassoShell>
  );
}
