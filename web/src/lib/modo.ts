/** `NEXT_PUBLIC_API_MODE` escolhe o transporte da camada de API.
 *  O padrão é `mock`: o fluxo é navegável sem backend, que é o critério de aceite da issue. */
export type Modo = "mock" | "real";

export const MODO: Modo = process.env.NEXT_PUBLIC_API_MODE === "real" ? "real" : "mock";
