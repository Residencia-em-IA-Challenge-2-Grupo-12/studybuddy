"use client";

import { PassoShell, PASSOS } from "@/modules/fluxo/components/PassoShell";

export default function OnboardingPage() {
  return (
    <PassoShell numero={0} titulo={PASSOS[0].titulo}>
      <p className="secundario">
        Cronotipo, janela de sono, refeições e a conexão da agenda entram na Fase 2.
      </p>
    </PassoShell>
  );
}
