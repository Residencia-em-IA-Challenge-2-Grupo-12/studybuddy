import type { CargaCognitiva, Material } from "@/modules/fluxo/types";

/** O que o formulário coleta. `prazo` vazio significa "sem prazo" — vira `null` no contrato. */
export type CamposMaterial = {
  disciplina: string;
  titulo: string;
  carga: CargaCognitiva;
  horas: number;
  dificuldade: number;
  prazo: string; // "2026-12-04" ou ""
};

/** Monta o `Material` do contrato. Separado do componente para poder ser testado contra o pydantic. */
export function montarMaterial(campos: CamposMaterial, id: string): Material {
  return {
    id,
    disciplina: campos.disciplina.trim(),
    titulo: campos.titulo.trim(),
    carga: campos.carga,
    horas_estimadas: campos.horas,
    dificuldade: campos.dificuldade,
    prazo: campos.prazo.trim() === "" ? null : campos.prazo,
  };
}

/** "2026-12-04" -> "04/12", para a lista. */
export function prazoCurto(prazo: string | null): string {
  if (!prazo) return "";
  const [ano, mes, dia] = prazo.split("-");
  return ano && mes && dia ? `${dia}/${mes}` : prazo;
}
