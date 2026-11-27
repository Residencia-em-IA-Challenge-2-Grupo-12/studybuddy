"use client";

import { useFluxo } from "@/modules/fluxo/FluxoProvider";
import { PassoShell, PASSOS } from "@/modules/fluxo/components/PassoShell";

export default function CheckInPage() {
  const { contexto } = useFluxo();

  return (
    <PassoShell
      numero={1}
      titulo={PASSOS[1].titulo}
      faltando={contexto ? null : { rotulo: "onboarding", href: "/onboarding" }}
    >
      <p className="secundario">As escalas do check-in entram na Fase 3.</p>
    </PassoShell>
  );
}
