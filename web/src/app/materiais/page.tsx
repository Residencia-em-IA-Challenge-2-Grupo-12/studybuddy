"use client";

import { useFluxo } from "@/modules/fluxo/FluxoProvider";
import { PassoShell, PASSOS } from "@/modules/fluxo/components/PassoShell";

export default function MateriaisPage() {
  const { contexto, checkin } = useFluxo();

  const faltando = !contexto
    ? { rotulo: "onboarding", href: "/onboarding" }
    : !checkin
      ? { rotulo: "check-in", href: "/check-in" }
      : null;

  return (
    <PassoShell numero={2} titulo={PASSOS[2].titulo} faltando={faltando}>
      <p className="secundario">O cadastro de materiais entra na Fase 4.</p>
    </PassoShell>
  );
}
