import { api } from "@/lib/api";

import type {
  CheckIn,
  ContextoEstudante,
  EntradaOnboarding,
  Material,
  PlanoResposta,
} from "./types";

/** Superfície provisória do fluxo. Ainda **não existe rota** no backend: hoje só o mock responde,
 *  e estes caminhos serão reconciliados com as rotas reais quando o Maestro expuser as dele.
 */

const corpo = (dados: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(dados),
});

export async function carregarContexto(entrada: EntradaOnboarding): Promise<ContextoEstudante> {
  return api<ContextoEstudante>("/fluxo/contexto", corpo(entrada));
}

export async function enviarCheckin(checkin: CheckIn): Promise<CheckIn> {
  return api<CheckIn>("/fluxo/checkin", corpo(checkin));
}

export async function enviarMateriais(materiais: Material[]): Promise<Material[]> {
  return api<Material[]>("/fluxo/materiais", corpo({ materiais }));
}

export async function carregarPlano(): Promise<PlanoResposta> {
  return api<PlanoResposta>("/fluxo/plano", corpo({}));
}

export async function confirmarPlano(): Promise<{ sincronizado: boolean }> {
  return api<{ sincronizado: boolean }>("/fluxo/confirmar", corpo({}));
}
