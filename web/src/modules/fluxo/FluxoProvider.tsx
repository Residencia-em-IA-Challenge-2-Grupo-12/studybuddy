"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import type { CheckIn, ContextoEstudante, EscalasCheckIn, Material } from "./types";

const CHAVE = "studybuddy.fluxo.v1";

export type EstadoFluxo = {
  contexto: ContextoEstudante | null;
  checkin: CheckIn | null;
  /** As quatro escalas da issue. `checkin` carrega os três campos do contrato; estas sobram
   *  e ficam guardadas para não descartar o que o estudante respondeu. */
  escalas: EscalasCheckIn | null;
  materiais: Material[] | null;
};

const VAZIO: EstadoFluxo = { contexto: null, checkin: null, escalas: null, materiais: null };

type Fluxo = EstadoFluxo & {
  hidratado: boolean;
  definir: (parcial: Partial<EstadoFluxo>) => void;
  limpar: () => void;
};

const Contexto = createContext<Fluxo | null>(null);

export function FluxoProvider({ children }: { children: React.ReactNode }) {
  const [estado, setEstado] = useState<EstadoFluxo>(VAZIO);
  const [hidratado, setHidratado] = useState(false);

  // O servidor renderiza vazio e o estado vem do localStorage depois da montagem: assim a
  // hidratação não diverge e os passos não piscam com dado de outra sessão.
  useEffect(() => {
    try {
      const bruto = window.localStorage.getItem(CHAVE);
      if (bruto) {
        const salvo = JSON.parse(bruto) as Partial<EstadoFluxo>;
        setEstado({ ...VAZIO, ...salvo });
      }
    } catch {
      // localStorage bloqueado ou conteúdo inválido: começa do zero
    }
    setHidratado(true);
  }, []);

  useEffect(() => {
    if (!hidratado) return;
    try {
      window.localStorage.setItem(CHAVE, JSON.stringify(estado));
    } catch {
      // sem persistência, o fluxo continua funcionando nesta aba
    }
  }, [estado, hidratado]);

  const definir = useCallback((parcial: Partial<EstadoFluxo>) => {
    setEstado((atual) => ({ ...atual, ...parcial }));
  }, []);

  const limpar = useCallback(() => setEstado(VAZIO), []);

  const valor = useMemo<Fluxo>(
    () => ({ ...estado, hidratado, definir, limpar }),
    [estado, hidratado, definir, limpar],
  );

  return <Contexto.Provider value={valor}>{children}</Contexto.Provider>;
}

export function useFluxo(): Fluxo {
  const valor = useContext(Contexto);
  if (!valor) throw new Error("useFluxo precisa estar dentro de <FluxoProvider>");
  return valor;
}
