"use client";

import { useFluxo } from "@/modules/fluxo/FluxoProvider";
import { PassoShell, PASSOS } from "@/modules/fluxo/components/PassoShell";
import { MateriaisForm } from "@/modules/materiais/components/MateriaisForm";

export default function MateriaisPage() {
  const { contexto, checkin } = useFluxo();

  const faltando = !contexto
    ? { rotulo: "onboarding", href: "/onboarding" }
    : !checkin
      ? { rotulo: "check-in", href: "/check-in" }
      : null;

  return (
    <PassoShell numero={2} titulo={PASSOS[2].titulo} faltando={faltando}>
      <MateriaisForm />
    </PassoShell>
  );
}
