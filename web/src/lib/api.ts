import { respostaMock } from "./mock";
import { MODO } from "./modo";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const TETO_DO_CORPO = 300;

/** Erro da API com o status preservado. O corpo vem em três formatos (ver §1.2 do plano):
 *  503/504 -> {detail: string}; 422 -> {detail: [{loc, msg}]}; 500 -> text/plain. */
export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;
  readonly body: string;

  constructor(status: number, detail: string, body = "") {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.body = body;
  }
}

type DetalheDeValidacao = { loc?: unknown[]; msg?: string };

/** Normaliza os três formatos de erro do FastAPI em uma frase legível. */
function normalizarDetalhe(detalhe: unknown, corpo: string, status: number): string {
  if (typeof detalhe === "string" && detalhe.trim()) return detalhe.trim();

  if (Array.isArray(detalhe) && detalhe.length > 0) {
    const partes = (detalhe as DetalheDeValidacao[]).map((item) => {
      const msg = typeof item?.msg === "string" ? item.msg : JSON.stringify(item);
      const campo = Array.isArray(item?.loc)
        ? item.loc.filter((parte) => parte !== "body").join(".")
        : "";
      return campo ? `${campo}: ${msg}` : msg;
    });
    return partes.join("; ");
  }

  const texto = corpo.trim();
  if (!texto) return `A API respondeu ${status} sem corpo.`;
  return texto.length > TETO_DO_CORPO ? `${texto.slice(0, TETO_DO_CORPO)}…` : texto;
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  // No modo mock, o caminho registrado responde local; o que não está registrado segue para a rede,
  // para que a tela do assistente continue funcionando contra a API real no mesmo servidor.
  if (MODO === "mock") {
    const mock = respostaMock(init?.method ?? "GET", path, init?.body);
    if (mock.encontrada) return mock.corpo as T;
  }

  const res = await fetch(`${API_URL}${path}`, { cache: "no-store", ...init });

  // Sempre texto primeiro: o 500 do FastAPI é text/plain e não tem JSON para ler.
  const corpo = await res.text();
  let dados: unknown;
  try {
    dados = corpo ? JSON.parse(corpo) : undefined;
  } catch {
    dados = undefined;
  }

  if (!res.ok) {
    const detalhe = (dados as { detail?: unknown } | undefined)?.detail;
    throw new ApiError(res.status, normalizarDetalhe(detalhe, corpo, res.status), corpo);
  }

  if (dados === undefined) {
    throw new ApiError(res.status, normalizarDetalhe(undefined, corpo, res.status), corpo);
  }

  return dados as T;
}
