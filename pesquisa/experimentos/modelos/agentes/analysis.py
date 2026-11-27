"""Plugin do Analysis Agent na harness ([3.0]).

Onde o Analysis usa modelo: escolher a técnica e escrever a justificativa de cada material, citando a base.
Os casos saem das fixtures da [0.2]: cada contexto -> PropostaGrade (heurística, sem LLM) -> um caso por
material, com o MESMO prompt e os MESMOS trechos que a API usaria (justificativa.montar_prompt). A busca roda
uma vez e fica igual para todos os modelos, então a comparação só muda o modelo.

Métricas do agente (além do JSON válido, da fidelidade e da latência, que são da harness):
- citacao_valida: sobrou ao menos uma citação de artigo recebido depois do verificador (senão a API cai
  na técnica padrão);
- citacoes_mantidas: das citações de artigo, a fração que o verificador manteve (inventadas saem);
- tecnica_adequada: a técnica combina com a carga (alta: active recall, intercalada, Feynman, Pomodoro,
  deep work; baixa: flashcards, repetição espaçada, leitura, resumo) e alta carga não recebe flashcards.
"""

import re
import unicodedata

from langchain_core.documents import Document

from ..rodar import API_DIR, Caso, Config  # primeiro: põe api/ no sys.path

from app.modules.agentes.analysis import AgenteAnalysis
from app.modules.agentes.analysis import justificativa as j
from app.modules.agentes.contratos import ContextoEstudante, DiretivaMaestro
from app.modules.rag.fontes import formatar_trechos
from app.modules.rag.verificador import verificar


FIXTURES = API_DIR / "tests" / "fixtures" / "contexto"
_ARTIGO = re.compile(r"artigo_\d{2}")

ADEQUADAS = {
    "alta": ("recall", "recupera", "intercal", "interleav", "feynman", "pomodoro", "deep work", "foco profundo",
             "resolu", "pratica deliberada"),
    "baixa": ("flashcard", "espacad", "spaced", "leitura", "resumo", "revis"),
}


def _sem_acento(t: str) -> str:
    return unicodedata.normalize("NFKD", t.lower()).encode("ascii", "ignore").decode()


def tecnica_adequada(tecnica: str, carga: str) -> bool:
    t = _sem_acento(tecnica)
    if carga == "alta" and "flashcard" in t:
        return False
    return any(k in t for k in ADEQUADAS[carga])


def contexto_do_juiz(prompt: str, trechos: list[Document]) -> str:
    """Tudo o que o modelo recebeu como fato: os dados da grade (material, carga, horários, ritmo) e os trechos.
    Só com os trechos, o juiz reprovava afirmações certas tiradas da grade ("a carga cognitiva é alta")."""
    inicio, fim = prompt.index("MATERIAL:"), prompt.index("FRAGMENTOS DA BASE:")
    return f"DADOS DA GRADE:\n{prompt[inicio:fim].strip()}\n\nFRAGMENTOS DA BASE:\n{formatar_trechos(trechos)}"


class AgenteAnalysisExperimento:
    nome = "analysis"
    contrato = j.JustificativaLLM
    configs_padrao = [
        Config("qwen3:8b"),                          # referência: o modelo atual da API
        Config("qwen3.5:9b"),                        # Qwen mais novo na mesma classe de tamanho
        Config("gemma3:12b"),
        Config("gemma4:12b"),                        # Gemma mais novo, mesmo tamanho do gemma3:12b
        Config("gemma4:e4b"),                        # outro candidato a alternativa leve
        Config("llama3.1:8b"),                       # Meta (o llama4 não cabe em 24 GB)
        Config("ministral-3:8b"),                    # Mistral
        Config("qwen3.5:4b"),                        # candidato a alternativa leve
        Config("qwen3.5:9b-q8_0"),                   # quantização: q8_0 vs o q4 padrão do qwen3.5:9b
        Config("qwen3.5:9b", reasoning=True),        # modo <think> ligado
        Config("qwen3.5:9b", temperature=0.7),
        Config("qwen3.5:9b", formato=False),         # JSON só pedido no prompt, sem o JSON Schema
    ]

    def __init__(self):
        self._casos: list[Caso] | None = None

    def casos(self) -> list[Caso]:
        if self._casos is None:
            self._casos = self._montar()
        return self._casos

    def _montar(self) -> list[Caso]:
        agente = AgenteAnalysis()
        cenarios = [(p.stem, ContextoEstudante.model_validate_json(p.read_text(encoding="utf-8")), None)
                    for p in sorted(FIXTURES.glob("*.json"))]
        fadiga = next(c for n, c, _ in cenarios if n == "fadiga")
        cenarios.append(("fadiga_reducao", fadiga, DiretivaMaestro(intencao="dia leve", rota="reducao_danos")))
        cache: dict[str, list[Document]] = {}
        casos = []
        for nome, ctx, diretiva in cenarios:
            proposta = agente.propor(ctx, diretiva)
            estado = j.estado_da_proposta(proposta, ctx)
            materiais = {m.id: m for m in ctx.materiais}
            for mid in dict.fromkeys(b.material_id for b in proposta.blocos):
                m = materiais[mid]
                blocos = [b for b in proposta.blocos if b.material_id == mid]
                consulta = j.consulta(m)
                trechos = cache.setdefault(consulta, j._buscar_padrao(consulta))
                prompt = j.montar_prompt(m, blocos, ctx, trechos, estado)
                casos.append(Caso(
                    id=f"{nome}/{mid}", prompt=prompt, contexto=contexto_do_juiz(prompt, trechos),
                    dados={"carga": m.carga, "trechos": [{"source": d.metadata.get("source", ""), "texto": d.page_content}
                                                         for d in trechos]},
                ))
        return casos

    def avaliar(self, caso: Caso, objeto) -> dict:
        if objeto is None:
            return {"citacao_valida": 0.0, "citacoes_mantidas": None, "tecnica_adequada": 0.0}
        trechos = [Document(page_content=t["texto"], metadata={"source": t["source"]}) for t in caso.dados["trechos"]]
        _, v = verificar(objeto.justificativa, trechos)
        total = len(v.citadas) + len(v.fora_do_contexto)
        return {
            "citacao_valida": float(bool(v.citadas)),
            "citacoes_mantidas": (len(v.citadas) / total) if total else None,
            "tecnica_adequada": float(tecnica_adequada(objeto.tecnica, caso.dados["carga"])),
        }

    def resposta(self, objeto) -> str:
        return objeto.justificativa

    def metricas(self) -> list[str]:
        return ["citacao_valida", "citacoes_mantidas", "tecnica_adequada"]
