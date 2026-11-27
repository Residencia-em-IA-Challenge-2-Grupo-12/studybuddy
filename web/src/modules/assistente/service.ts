import { api } from "@/lib/api";

import type { Info, Pipeline, Resposta } from "./types";

/** Qual pipeline e quais modelos este servidor usa. */
export function obterInfo(signal?: AbortSignal): Promise<Info> {
  return api<Info>("/assistente/info", { signal });
}

/** Uma pergunta ao assistente. O `pipeline` vai sempre explícito no corpo, então a mesma tela
 *  funciona contra um servidor só e contra os dois containers do docker-compose. */
export function perguntar(pergunta: string, pipeline: Pipeline, signal?: AbortSignal): Promise<Resposta> {
  return api<Resposta>("/assistente/perguntar", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ pergunta, pipeline }),
    signal,
  });
}
