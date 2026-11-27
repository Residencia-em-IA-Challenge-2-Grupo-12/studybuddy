#!/usr/bin/env node
// Copia as fixtures de referência para web/src/mocks/, onde o Next consegue importá-las.
// O Next não importa JSON de fora da raiz do projeto, então a cópia é o caminho; o --check
// garante que ela não se separe da origem.
//
//   node scripts/sincronizar-mocks.mjs           copia e gera o índice
//   node scripts/sincronizar-mocks.mjs --check   não copia; sai com 1 se houver divergência
//
// As fixtures da [0.2] vivem em api/tests/fixtures. As de pesquisa/fixtures/communication são de
// outra família (saída do agente Communication), copiadas à parte e não validadas contra os
// contratos do Maestro — ver scripts/validar-mocks.py.

import { existsSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const AQUI = dirname(fileURLToPath(import.meta.url)); // web/scripts
const WEB = dirname(AQUI); // web
const REPO = dirname(WEB); // raiz do repositório
// MOCKS_DESTINO existe para testar a própria checagem numa cópia, sem tocar no repositório.
const DESTINO = process.env.MOCKS_DESTINO ? resolve(process.env.MOCKS_DESTINO) : join(WEB, "src", "mocks");

const FONTES = [
  { de: join(REPO, "api", "tests", "fixtures", "contexto"), para: "contexto", exporta: "CONTEXTO", tipo: "ContextoEstudante" },
  { de: join(REPO, "api", "tests", "fixtures", "proposta"), para: "proposta", exporta: "PROPOSTA", tipo: "PropostaGrade" },
  { de: join(REPO, "api", "tests", "fixtures", "resultado"), para: "resultado", exporta: "RESULTADO", tipo: "ResultadoValidacao" },
  // communication é outra família: não tem tipo de contrato para afirmar.
  { de: join(REPO, "pesquisa", "fixtures", "communication"), para: "communication", exporta: "COMMUNICATION", tipo: null },
];

const CONFERIR = process.argv.includes("--check");

/** Caminho para exibir: relativo quando está dentro de web/, absoluto quando é override em /tmp. */
const bonito = (alvo) => {
  const rel = relative(WEB, alvo);
  return rel.startsWith("..") ? alvo : rel;
};

const listar = (dir) =>
  existsSync(dir)
    ? readdirSync(dir)
        .filter((nome) => nome.endsWith(".json"))
        .sort()
    : [];

const problemas = [];
const copiados = [];
const removidos = [];

for (const fonte of FONTES) {
  if (!existsSync(fonte.de)) {
    console.error(`fonte ausente: ${fonte.de}`);
    process.exit(1);
  }

  const destino = join(DESTINO, fonte.para);
  const origens = listar(fonte.de);

  if (!CONFERIR) mkdirSync(destino, { recursive: true });

  for (const nome of origens) {
    const esperado = readFileSync(join(fonte.de, nome), "utf8");
    const alvo = join(destino, nome);
    const atual = existsSync(alvo) ? readFileSync(alvo, "utf8") : null;
    if (atual === esperado) continue;

    if (CONFERIR) problemas.push(`divergente: ${bonito(alvo)}`);
    else {
      writeFileSync(alvo, esperado);
      copiados.push(bonito(alvo));
    }
  }

  // Arquivo que sumiu da origem não pode continuar no destino: o diretório é gerado.
  for (const nome of listar(destino)) {
    if (origens.includes(nome)) continue;
    const alvo = join(destino, nome);
    if (CONFERIR) problemas.push(`sobrando: ${bonito(alvo)}`);
    else {
      rmSync(alvo);
      removidos.push(bonito(alvo));
    }
  }
}

/** Índice tipado, gerado a partir das pastas — não editar à mão. */
function gerarIndice() {
  const grupos = FONTES.map((fonte) => ({
    pasta: fonte.para,
    exporta: fonte.exporta,
    tipo: fonte.tipo,
    itens: listar(join(DESTINO, fonte.para)).map((nome) => ({
      nome,
      id: nome
        .replace(/\.json$/, "")
        .replace(/[^A-Za-z0-9_]/g, "_")
        .replace(/^(\d)/, "_$1"),
    })),
  }));

  // Nome repetido entre pastas geraria um import duplicado: melhor falhar aqui do que emitir TS quebrado.
  const vistos = new Set();
  for (const grupo of grupos) {
    for (const item of grupo.itens) {
      if (vistos.has(item.id)) {
        console.error(`fixture com nome repetido entre pastas: ${item.id}.json`);
        process.exit(1);
      }
      vistos.add(item.id);
    }
  }

  const tipos = [...new Set(grupos.map((grupo) => grupo.tipo).filter(Boolean))];
  const linhas = [
    "// GERADO por scripts/sincronizar-mocks.mjs — não editar à mão.",
    "// Fonte: api/tests/fixtures (contratos da [0.2]) e pesquisa/fixtures/communication.",
    "//",
    "// O `as Tipo` é ponte, não check: o TypeScript infere JSON como `string` e perde as uniões",
    '// (`modo: "normal" | "reducao_danos"`, `status: "APROVADO" | "REPROVADO"`). Quem confere o mock',
    "// contra o contrato é scripts/validar-mocks.py, que roda o pydantic de verdade.",
    "",
  ];

  if (tipos.length > 0) {
    linhas.push(`import type { ${tipos.join(", ")} } from "@/modules/fluxo/types";`);
    linhas.push("");
  }

  for (const grupo of grupos) {
    for (const item of grupo.itens) {
      linhas.push(`import ${item.id} from "./${grupo.pasta}/${item.nome}";`);
    }
  }
  linhas.push("");

  for (const grupo of grupos) {
    linhas.push(`export const ${grupo.exporta} = {`);
    for (const item of grupo.itens) {
      linhas.push(grupo.tipo ? `  ${item.id}: ${item.id} as ${grupo.tipo},` : `  ${item.id},`);
    }
    linhas.push("} as const;");
    linhas.push("");
  }

  return linhas.join("\n");
}

const indice = join(DESTINO, "index.ts");
const conteudoIndice = gerarIndice();
const indiceAtual = existsSync(indice) ? readFileSync(indice, "utf8") : null;

if (indiceAtual !== conteudoIndice) {
  if (CONFERIR) problemas.push("divergente: src/mocks/index.ts");
  else {
    mkdirSync(DESTINO, { recursive: true });
    writeFileSync(indice, conteudoIndice);
    copiados.push("src/mocks/index.ts");
  }
}

const total = FONTES.reduce((soma, fonte) => soma + listar(join(DESTINO, fonte.para)).length, 0);

if (CONFERIR) {
  if (problemas.length > 0) {
    console.error(`mocks fora de sincronia com as fixtures (${problemas.length}):`);
    for (const problema of problemas) console.error(`  ${problema}`);
    console.error("rode: node scripts/sincronizar-mocks.mjs");
    process.exit(1);
  }
  console.log(`ok   ${total} mocks em sincronia com as fixtures`);
} else {
  console.log(`${total} mocks sincronizados`);
  for (const caminho of copiados) console.log(`  copiado    ${caminho}`);
  for (const caminho of removidos) console.log(`  removido   ${caminho}`);
}
