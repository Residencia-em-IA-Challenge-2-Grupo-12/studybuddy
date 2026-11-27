"use client";

import { PassoShell, PASSOS } from "@/modules/fluxo/components/PassoShell";
import { OnboardingForm } from "@/modules/onboarding/components/OnboardingForm";

export default function OnboardingPage() {
  return (
    <PassoShell numero={0} titulo={PASSOS[0].titulo}>
      <OnboardingForm />
    </PassoShell>
  );
}
