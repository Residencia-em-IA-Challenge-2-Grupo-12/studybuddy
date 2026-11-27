import type { Metadata } from "next";

import { FluxoProvider } from "@/modules/fluxo/FluxoProvider";

import "./globals.css";

export const metadata: Metadata = {
  title: "StudyBuddy",
  description: "Assistente de estudos que responde a partir de artigos científicos, com as fontes à vista.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR">
      <body>
        <FluxoProvider>{children}</FluxoProvider>
      </body>
    </html>
  );
}
