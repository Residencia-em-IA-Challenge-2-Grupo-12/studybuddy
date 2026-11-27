"use client";

import Link from "next/link";

import { useFluxo } from "../FluxoProvider";

export const PASSOS = [
  { href: "/onboarding", rotulo: "onboarding", titulo: "Onboarding" },
  { href: "/check-in", rotulo: "check-in", titulo: "Check-in de hoje" },
  { href: "/materiais", rotulo: "materiais", titulo: "Materiais" },
  { href: "/plano", rotulo: "plano", titulo: "Plano da semana" },
] as const;

export type PassoFaltando = { rotulo: string; href: string } | null;

type Props = {
  numero: number;
  titulo: string;
  faltando?: PassoFaltando;
  /** `larga` para telas cujo conteúdo não cabe na coluna de leitura — a grade da semana, por exemplo. */
  largura?: "normal" | "larga";
  children?: React.ReactNode;
};

/** Casca comum dos quatro passos: navegação, título e o bloqueio de pré-requisito.
 *  Passo sem o dado anterior mostra o que falta, em vez de uma tela quebrada. */
export function PassoShell({ numero, titulo, faltando = null, largura = "normal", children }: Props) {
  const { hidratado } = useFluxo();

  if (!hidratado) {
    return (
      <main className="pagina">
        <p className="secundario" role="status">
          Carregando o seu fluxo.
        </p>
      </main>
    );
  }

  return (
    <main className={largura === "larga" ? "pagina pagina--larga" : "pagina"}>
      <nav className="fluxo__nav" aria-label="Passos do fluxo">
        {PASSOS.map((passo, indice) => (
          <Link
            key={passo.href}
            href={passo.href}
            className="fluxo__link"
            aria-current={indice === numero ? "step" : undefined}
          >
            {passo.rotulo}
          </Link>
        ))}
      </nav>

      {faltando ? (
        <div className="fluxo__vazio">
          <h1 className="fluxo__titulo">Falta o {faltando.rotulo}</h1>
          <p className="secundario">Este passo depende do anterior. Preencha-o para continuar.</p>
          <Link className="botao botao--secundario" href={faltando.href}>
            Ir para o {faltando.rotulo}
          </Link>
        </div>
      ) : (
        <>
          <h1 className="fluxo__titulo">{titulo}</h1>
          {children}
        </>
      )}
    </main>
  );
}
