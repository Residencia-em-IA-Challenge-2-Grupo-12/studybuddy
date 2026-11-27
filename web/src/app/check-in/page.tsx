"use client";

import { CheckinForm } from "@/modules/checkin/components/CheckinForm";
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
      <CheckinForm />
    </PassoShell>
  );
}
