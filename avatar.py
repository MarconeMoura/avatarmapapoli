import json
import os
import random
import re
import ssl
import unicodedata
import urllib.error
import urllib.request
from difflib import SequenceMatcher
from typing import Any

import certifi
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Carrega variáveis de ambiente (prioriza .env no desenvolvimento local)
load_dotenv(override=True)

app = FastAPI(title="Avatar Guia POLI UPE")


def resolver_diretorio_static() -> str:
    candidatos = ["static", "Static"]
    for pasta in candidatos:
        if os.path.isdir(pasta):
            return pasta
    os.makedirs("static", exist_ok=True)
    return "static"


STATIC_DIR = resolver_diretorio_static()
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_TTS_MODEL = os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts")
OPENAI_TTS_VOICE = os.getenv("OPENAI_TTS_VOICE", "nova")
GEMINI_TEXT_MODEL = os.getenv("GEMINI_TEXT_MODEL", "gemini-2.0-flash")
OPENAI_TTS_INSTRUCTIONS = os.getenv(
    "OPENAI_TTS_INSTRUCTIONS",
    "Fale em portugues do Brasil, voz feminina natural, tom acolhedor e claro.",
)

genai_client = None
if GOOGLE_API_KEY:
    try:
        import google.genai as genai_module

        genai_client = genai_module.Client(api_key=GOOGLE_API_KEY)
        print("Google AI (genai) configurado com sucesso!")
    except Exception as e:
        print(f"Aviso: erro ao inicializar Google AI: {e}")
else:
    print("Aviso: GOOGLE_API_KEY não configurada. Respostas em fallback local.")

locais_campus = {
    "entrada": {
        "x": 36.76,
        "y": 70.66,
        "salas": ["Portão Principal", "Acesso Benfica"],
        "dica": "Lembre o calouro de andar sempre com o comprovante de matrícula nos primeiros dias.",
    },
    "estacionamento": {
        "x": 22.67,
        "y": 63.62,
        "salas": ["Vagas de Carros", "Motos"],
        "dica": "As vagas acabam rápido, então quem chega tarde sofre pra estacionar.",
    },
    "lanchonete": {
        "x": 17.22,
        "y": 38.97,
        "salas": ["Lanchonete", "Mesas de Refeição"],
        "dica": "O point do intervalo. Corre pra pegar o salgado antes da fila crescer.",
    },
    "bloco a": {
        "x": 27.33,
        "y": 43.66,
        "salas": ["Térreo: A01, NAPSI, A2, A3, Pós-Graduação", "1º Andar: Auditório"],
        "dica": "No A tem o NAPSI para apoio psicológico e o Auditório para eventos; atrás dele fica uma lanchonete muito elogiada.",
    },
    "bloco h": {
        "x": 44.49,
        "y": 47.65,
        "salas": ["Térreo: LIP-03, Biblioteca"],
        "dica": "No H, o LIP-03 costuma ter Expressão Gráfica, Programação e Estrutura de Dados, e a Biblioteca ajuda muito na rotina.",
    },
    "bloco g": {
        "x": 57.44,
        "y": 44.6,
        "salas": ["Salas de Professores", "Coordenação", "LIP-07", "DTI (Departamento de Tecnologia da Informação)"],
        "dica": "No G tem vários LIPs e o DTI, onde você resolve email institucional e acesso das máquinas.",
    },
    "bloco f": {
        "x": 65.28,
        "y": 44.6,
        "salas": ["Salas de Aula"],
        "dica": "Muitas aulas teóricas passam por aqui, então vale decorar esse caminho cedo.",
    },
    "bloco b": {
        "x": 56.65,
        "y": 58.45,
        "salas": ["Térreo: B01 a B04, DA, Lab. de Química", "1º Andar: Divisão de Estágio, Escolaridade"],
        "dica": "No B ficam muitas aulas dos períodos iniciais e a Escolaridade, onde se resolve matrícula.",
    },
    "da": {
        "x": 71.31,
        "y": 54.23,
        "salas": ["Diretório Acadêmico", "Área de Vivência", "Praça do Dominó (em frente ao D.A)"],
        "dica": "É a base dos alunos. Em frente ao D.A fica a Praça do Dominó, ponto clássico de convivência.",
    },
    "bloco i/k": {
        "x": 52.67,
        "y": 34.74,
        "salas": [
            "Bloco I (1º ao 3º Andar)",
            "Bloco K (Labs de Robótica e Topografia)",
            "DATP",
            "Sala dos Professores",
            "Praça do Dominó (próxima ao bloco I/K)",
        ],
        "dica": "No I/K ficam o DATP e a sala dos professores; perto dali também está a Praça do Dominó.",
    },
    "bloco e": {
        "x": 72.9,
        "y": 39.67,
        "salas": ["Laboratórios de Informática", "Salas de Aula"],
        "dica": "Fica na parte superior do campus e costuma aparecer em aulas práticas.",
    },
    "bloco d": {
        "x": 81.42,
        "y": 42.49,
        "salas": ["Lab. Avançado de Construção Civil", "Sala do Empreendedor"],
        "dica": "Confere direitinho se tua atividade é no D ou no E.",
    },
    "bloco j": {
        "x": 80.06,
        "y": 61.97,
        "salas": ["Labs de Eletrotécnica", "Máquinas Elétricas", "Mecatrônica"],
        "dica": "Paraíso pra quem curte elétrica. Atenção com equipamentos.",
    },
    "bloco c": {
        "x": 89.26,
        "y": 58.69,
        "salas": ["Física Experimental", "Labs de Computação", "LIP-01", "Corisco"],
        "dica": "Esse bloco vai aparecer bastante na tua rotina de computação.",
    },
}

SALAS_IMPORTANTES_POR_LOCAL = {
    "bloco a": ["A01", "NAPSI", "Auditório"],
    "bloco b": ["B01", "Escolaridade", "Lab. de Química"],
    "bloco c": ["LIP-01", "Labs de Computação", "Física Experimental"],
    "bloco d": ["Lab. Avançado de Construção Civil", "Sala do Empreendedor"],
    "bloco e": ["Laboratórios de Informática", "Salas de Aula"],
    "bloco f": ["Salas de Aula"],
    "bloco g": ["LIP-07", "DTI", "Coordenação"],
    "bloco h": ["Biblioteca", "LIP-03"],
    "bloco i/k": ["DATP", "Sala dos Professores", "Labs de Robótica"],
    "bloco j": ["Labs de Eletrotécnica", "Máquinas Elétricas", "Mecatrônica"],
}

CONHECIMENTO_PRATICO_POR_LOCAL = {
    "bloco a": [
        "NAPSI oferece apoio psicológico aos alunos.",
        "O Auditório recebe eventos importantes da POLI.",
        "Atrás do Bloco A fica uma lanchonete com lanches muito elogiados.",
    ],
    "bloco b": [
        "Muitas aulas dos períodos iniciais acontecem no Bloco B.",
        "Na Escolaridade são resolvidas pendências de matrícula.",
        "Na Escolaridade, é importante tratar Diva com respeito e gentileza.",
    ],
    "bloco h": [
        "No LIP-03 costumam ocorrer aulas de Expressão Gráfica.",
        "No LIP-03 também aparecem aulas de Programação e Estrutura de Dados.",
        "A Biblioteca é ponto-chave para estudo e consulta.",
    ],
    "bloco g": [
        "O Bloco G concentra vários LIPs (laboratórios de informática).",
        "No LIP-07 costumam ocorrer aulas de Introdução à Programação.",
        "No DTI é possível resolver email institucional e acesso às máquinas.",
    ],
    "bloco i/k": [
        "No bloco I/K ficam o DATP e a sala dos professores.",
        "A Praça do Dominó fica próxima ao bloco I/K e em frente ao D.A.",
    ],
    "da": [
        "Em frente ao D.A fica a Praça do Dominó, ponto tradicional de convivência.",
    ],
}

ultimas_falas_por_bloco: dict[str, str] = {}
historico_fallback_por_bloco: dict[str, list[str]] = {}
historico_falas_ia_por_bloco: dict[str, list[str]] = {}

POLIA_PERSONA_BASE = [
    "Você é a Polia, avatar guia da POLI UPE.",
    "Fale em português do Brasil, de forma acolhedora, clara e objetiva.",
    "Prefira frases naturais e úteis para calouros.",
]

POLIA_DIRETRIZES_BASE = [
    "Não use aspas nem emojis.",
    "Evite informações inventadas; quando faltar contexto, seja transparente.",
]


def carregar_contexto_global_polia() -> list[str]:
    blocos: list[str] = []
    extra_env = (os.getenv("POLIA_EXTRA_CONTEXT") or "").strip()
    if extra_env:
        blocos.append(extra_env)

    arquivo_contexto = "polia_contexto_extra.txt"
    if os.path.exists(arquivo_contexto):
        try:
            with open(arquivo_contexto, "r", encoding="utf-8") as f:
                texto = f.read().strip()
            if texto:
                blocos.append(texto)
        except Exception as e:
            print(f"Aviso: falha ao ler {arquivo_contexto}: {e}")
    return blocos


def serializar_contexto_extra(contexto_extra: Any) -> str:
    if not contexto_extra:
        return ""
    if isinstance(contexto_extra, str):
        return contexto_extra.strip()
    if isinstance(contexto_extra, (list, tuple, set)):
        partes = [str(x).strip() for x in contexto_extra if str(x).strip()]
        return "\n".join(partes)
    if isinstance(contexto_extra, dict):
        partes = []
        for k, v in contexto_extra.items():
            if v is None:
                continue
            valor = str(v).strip()
            if valor:
                partes.append(f"{k}: {valor}")
        return "\n".join(partes)
    return str(contexto_extra).strip()


CONTEXTO_GLOBAL_POLIA = carregar_contexto_global_polia()


def montar_prompt_polia(
    objetivo: str,
    regras: list[str] | None = None,
    dados: dict[str, Any] | None = None,
    contexto_extra: Any = None,
) -> str:
    linhas: list[str] = []
    linhas.extend(POLIA_PERSONA_BASE)
    linhas.append(f"Objetivo: {objetivo}")

    if CONTEXTO_GLOBAL_POLIA:
        linhas.append("Contexto extra global da Polia:")
        linhas.extend(CONTEXTO_GLOBAL_POLIA)

    extra_req = serializar_contexto_extra(contexto_extra)
    if extra_req:
        linhas.append("Contexto extra desta requisição:")
        linhas.append(extra_req)

    if dados:
        linhas.append("Dados úteis:")
        for chave, valor in dados.items():
            if valor is None:
                continue
            linhas.append(f"- {chave}: {valor}")

    linhas.append("Diretrizes:")
    for regra in POLIA_DIRETRIZES_BASE:
        linhas.append(f"- {regra}")
    for regra in (regras or []):
        linhas.append(f"- {regra}")
    return "\n".join(linhas)


def escolher_fala_fallback(destino_id: str, opcoes: list[str]) -> str:
    usadas = set(historico_fallback_por_bloco.get(destino_id, []))
    disponiveis = [frase for frase in opcoes if frase not in usadas]
    if not disponiveis:
        usadas = set()
        disponiveis = opcoes[:]

    frase = random.choice(disponiveis)
    usadas.add(frase)
    historico_fallback_por_bloco[destino_id] = list(usadas)
    return frase


def normalizar_texto(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto)
    texto = texto.encode("ascii", "ignore").decode("ascii")
    texto = texto.lower()
    texto = re.sub(r"[^a-z0-9\s]", " ", texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto


def remover_zeros_a_esquerda(numero: str) -> str:
    numero_limpo = (numero or "").lstrip("0")
    return numero_limpo or "0"


def gerar_aliases_codigo(prefixo: str, numero: str) -> list[str]:
    prefixo = (prefixo or "").lower()
    numero_original = numero or ""
    numero_sem_zero = remover_zeros_a_esquerda(numero_original)

    if not prefixo or not numero_original:
        return []

    aliases = {
        f"{prefixo}{numero_original}",
        f"{prefixo}-{numero_original}",
        f"{prefixo} {numero_original}",
        f"{prefixo}{numero_sem_zero}",
        f"{prefixo}-{numero_sem_zero}",
        f"{prefixo} {numero_sem_zero}",
    }

    if prefixo == "lip":
        aliases.update(
            {
                f"laboratorio de informatica {numero_original}",
                f"laboratorio de informatica {numero_sem_zero}",
                f"lab de informatica {numero_original}",
                f"lab de informatica {numero_sem_zero}",
                f"lab info {numero_original}",
                f"lab info {numero_sem_zero}",
            }
        )

    return [normalizar_texto(a) for a in aliases if a]


def extrair_codigos_texto(texto: str) -> list[tuple[str, str]]:
    codigos: list[tuple[str, str]] = []
    vistos: set[tuple[str, str]] = set()
    for prefixo, numero in re.findall(r"\b([A-Za-z]{1,4})\s*[- ]?\s*(\d{1,3})\b", texto or ""):
        chave = (prefixo.lower(), numero)
        if chave in vistos:
            continue
        vistos.add(chave)
        codigos.append(chave)
    return codigos


def deduplicar_indice(indice: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    vistos: set[tuple[str, str]] = set()
    unico: list[tuple[str, str, str]] = []
    for termo, destino, label in indice:
        chave = (termo, destino)
        if chave in vistos:
            continue
        vistos.add(chave)
        unico.append((termo, destino, label))
    return unico


def extrair_salas_importantes(destino_id: str, dados_local: dict, limite: int = 3) -> list[str]:
    predefinidas = SALAS_IMPORTANTES_POR_LOCAL.get(destino_id, [])
    if predefinidas:
        return predefinidas[:limite]

    candidatos: list[str] = []
    for item in dados_local.get("salas", []):
        partes = [p.strip() for p in re.split(r"[,;:]", item) if p.strip()]
        for parte in partes:
            parte = re.sub(
                r"^(terreo|1o andar|2o andar|3o andar)\s*",
                "",
                normalizar_texto(parte),
                flags=re.IGNORECASE,
            ).strip()
            if len(parte) >= 3:
                candidatos.append(parte)

    unicos: list[str] = []
    vistos: set[str] = set()
    for candidato in candidatos:
        if candidato in vistos:
            continue
        vistos.add(candidato)
        unicos.append(candidato)
    return unicos[:limite]


def extrair_conhecimento_pratico(destino_id: str, limite: int = 2) -> list[str]:
    return CONHECIMENTO_PRATICO_POR_LOCAL.get(destino_id, [])[:limite]


def construir_indice_salas() -> list[tuple[str, str, str]]:
    indice: list[tuple[str, str, str]] = []
    for destino, dados in locais_campus.items():
        indice.append((normalizar_texto(destino), destino, destino.upper()))

        for item in dados["salas"]:
            item_norm = normalizar_texto(item)
            if item_norm:
                indice.append((item_norm, destino, item))

            for pref1, num1, pref2, num2 in re.findall(
                r"\b([A-Za-z]{1,4})\s*[- ]?\s*(\d{1,3})\s*a\s*([A-Za-z]{0,4})\s*[- ]?\s*(\d{1,3})\b",
                item,
                flags=re.IGNORECASE,
            ):
                prefixo_inicio = pref1.lower()
                prefixo_fim = (pref2 or pref1).lower()
                if prefixo_inicio != prefixo_fim:
                    continue

                inicio = int(num1)
                fim = int(num2)
                if inicio > fim:
                    inicio, fim = fim, inicio
                if (fim - inicio) > 50:
                    continue

                for n in range(inicio, fim + 1):
                    numero_txt = str(n).zfill(max(len(num1), len(num2), 2))
                    label_codigo = f"{prefixo_inicio.upper()}-{numero_txt}"
                    for alias in gerar_aliases_codigo(prefixo_inicio, numero_txt):
                        indice.append((alias, destino, label_codigo))

            for parte in re.split(r"[,;:]", item):
                parte_limpa = parte.strip()
                parte_norm = normalizar_texto(parte_limpa)
                if len(parte_norm) >= 3:
                    indice.append((parte_norm, destino, parte_limpa))

            for prefixo, numero in extrair_codigos_texto(item):
                label_codigo = f"{prefixo.upper()}-{numero.zfill(2)}"
                for alias in gerar_aliases_codigo(prefixo, numero):
                    indice.append((alias, destino, label_codigo))

    return deduplicar_indice(indice)


indice_salas = construir_indice_salas()


def adicionar_sinonimos() -> None:
    sinonimos = {
        "biblioteca": ["bib", "livros", "estudo", "estudar", "acervo"],
        "lanchonete": ["lanche", "comida", "restaurante", "cafe", "lanchar"],
        "laboratorio": ["lab", "oficina", "pratica", "equipamento"],
        "eletrotecnica": ["eletro", "eletrica", "elet"],
        "robotica": ["robo"],
        "topografia": ["topo"],
        "computacao": ["computador", "programacao", "codigo"],
        "informatica": ["info", "computador", "pc"],
        "salas": ["sala", "classe", "room", "ambiente", "dependencia"],
        "salas de aula": ["aula", "aulas", "classe", "sala de aula", "room"],
        "laboratorios de informatica": [
            "lip",
            "laboratorio de informatica",
            "lab de informatica",
            "lab info",
            "informatica",
        ],
    }
    global indice_salas

    for termo_orig, sinonimos_list in sinonimos.items():
        termo_orig_norm = normalizar_texto(termo_orig)
        for destino, dados in locais_campus.items():
            salas_norm = normalizar_texto(" ".join(dados["salas"]))
            if termo_orig_norm in salas_norm:
                for sin in sinonimos_list:
                    indice_salas.append((normalizar_texto(sin), destino, f"{sin.capitalize()} (alias)"))

    indice_salas = deduplicar_indice(indice_salas)


adicionar_sinonimos()


def construir_aliases_blocos() -> dict[str, str]:
    aliases: dict[str, str] = {}
    for destino in locais_campus.keys():
        destino_lower = destino.lower().strip()
        if not destino_lower.startswith("bloco"):
            continue

        sufixo = destino_lower.replace("bloco", "", 1)
        for parte in re.findall(r"[a-z]+", sufixo):
            letra = parte[:1]
            if letra and letra.isalpha():
                aliases[letra] = destino
    return aliases


aliases_blocos = construir_aliases_blocos()


def inferir_destino_por_codigo(codigo: str) -> str | None:
    letra = (codigo or "")[:1].lower()
    return aliases_blocos.get(letra)


def buscar_destino_por_sala(pergunta: str) -> dict[str, str] | None:
    pergunta_norm = normalizar_texto(pergunta)

    codigos = extrair_codigos_texto(pergunta)
    for prefixo, numero in codigos:
        for alias in gerar_aliases_codigo(prefixo, numero):
            for termo, destino, label in indice_salas:
                if termo == alias:
                    return {"destino": destino, "sala": label}

        destino_inferido = inferir_destino_por_codigo(prefixo)
        if destino_inferido:
            return {"destino": destino_inferido, "sala": f"{prefixo.upper()}-{numero.zfill(2)}"}

    melhor: tuple[int, str, str] | None = None
    for termo, destino, label in indice_salas:
        if termo and termo in pergunta_norm:
            score = len(termo)
            if not melhor or score > melhor[0]:
                melhor = (score, destino, label)

    if melhor:
        return {"destino": melhor[1], "sala": melhor[2]}

    tokens = [t for t in pergunta_norm.split() if len(t) >= 3]
    melhor_fuzzy: tuple[float, str, str] | None = None
    for termo, destino, label in indice_salas:
        if not termo or len(termo) < 3:
            continue

        score = 0.0
        sim_frase = SequenceMatcher(None, pergunta_norm, termo).ratio()
        score = max(score, sim_frase * 0.7)

        for tk in tokens:
            sim = SequenceMatcher(None, tk, termo).ratio()
            if tk in termo or termo in tk:
                sim = max(sim, 0.9)
            score = max(score, sim)

        if score >= 0.84 and (not melhor_fuzzy or score > melhor_fuzzy[0]):
            melhor_fuzzy = (score, destino, label)

    if melhor_fuzzy:
        return {"destino": melhor_fuzzy[1], "sala": melhor_fuzzy[2]}
    return None


def extrair_json(texto: str) -> dict | None:
    if not texto:
        return None

    texto = texto.strip()
    try:
        return json.loads(texto)
    except Exception:
        pass

    inicio = texto.find("{")
    fim = texto.rfind("}")
    if inicio >= 0 and fim > inicio:
        trecho = texto[inicio : fim + 1]
        try:
            return json.loads(trecho)
        except Exception:
            return None
    return None


async def inferir_destino_com_ia(pergunta: str, contexto_extra: Any = None) -> dict[str, str] | None:
    if not genai_client:
        return None

    destinos_validos = list(locais_campus.keys())
    prompt = montar_prompt_polia(
        objetivo="Classificar a intenção da pergunta e inferir destino do campus.",
        dados={
            "destinos_validos": ", ".join(destinos_validos),
            "pergunta": pergunta,
            "saida_esperada": '{"destino": "<id_do_destino_ou_null>", "motivo": "<resumo_curto>"}',
        },
        regras=[
            "Responda SOMENTE com JSON válido, sem texto fora do JSON.",
            "Use apenas um ID presente em destinos_validos.",
            "Se não houver destino claro, use destino=null.",
            "Considere equivalências como sala, classe, laboratório, LIP, bloco, abreviações e pequenos erros de digitação.",
        ],
        contexto_extra=contexto_extra,
    )

    try:
        response = genai_client.models.generate_content(model=GEMINI_TEXT_MODEL, contents=prompt)
        bruto = (response.text or "").strip()
        data = extrair_json(bruto)
        if not isinstance(data, dict):
            return None

        destino = data.get("destino")
        if isinstance(destino, str):
            destino = destino.lower().strip()
        else:
            destino = None

        if destino in locais_campus:
            return {"destino": destino, "motivo": str(data.get("motivo") or "")}
        return None
    except Exception as e:
        print(f"Erro inferindo destino com IA: {e}")
        return None


async def gerar_fala_com_ia(destino_id: str, dados_local: dict, contexto_extra: Any = None) -> str:
    local = destino_id.upper()
    salas = ", ".join(dados_local["salas"])
    salas_importantes = extrair_salas_importantes(destino_id, dados_local)
    salas_importantes_txt = ", ".join(salas_importantes) if salas_importantes else "nao especificadas"
    conhecimento_pratico = extrair_conhecimento_pratico(destino_id)
    conhecimento_pratico_txt = " | ".join(conhecimento_pratico) if conhecimento_pratico else ""
    dica = dados_local.get("dica", "Aproveite a POLI!")
    fala_anterior = ultimas_falas_por_bloco.get(destino_id, "")
    historico = historico_falas_ia_por_bloco.get(destino_id, [])[-5:]

    estilo = random.choice([
        "acolhedor e engracado",
        "empolgado e camarada",
        "direto e motivador",
        "leve e descontraido",
    ])

    prompt = montar_prompt_polia(
        objetivo="Recepcionar o calouro com contexto real do bloco, de forma breve e útil.",
        dados={
            "estilo": estilo,
            "local": local,
            "salas": salas,
            "salas_importantes": salas_importantes_txt,
            "conhecimento_pratico": conhecimento_pratico_txt,
            "dica": dica,
        },
        regras=[
            "Crie 1 frase (ou 2 frases curtas) entre 12 e 24 palavras.",
            f"Cite explicitamente o nome do local: {local}.",
            "Cada interação deve soar nova; evite repetir estrutura e palavras.",
            "Mencione 1 destaque real do bloco.",
            "Se houver conhecimento_pratico, inclua 1 dica útil ao calouro.",
            "Não invente informações.",
        ],
        contexto_extra=contexto_extra,
    )

    if fala_anterior:
        prompt += f" A última fala usada nesse bloco foi: '{fala_anterior}'. Não repita essa fala."
    if historico:
        prompt += " Evite semelhança com estas últimas falas do bloco: " + " | ".join(historico)

    if not genai_client:
        destaque_curto = salas_importantes[0] if salas_importantes else local
        extra_util = conhecimento_pratico[0] if conhecimento_pratico else ""
        fallback = [
            f"Você chegou ao {local}. O destaque daqui é {destaque_curto}. {extra_util or dica}",
            f"No {local}, vale passar em {destaque_curto}. {extra_util or dica}",
            f"Bem-vindo ao {local}: referência rápida é {destaque_curto}. {extra_util or dica}",
        ]
        frase = escolher_fala_fallback(destino_id, fallback)
        ultimas_falas_por_bloco[destino_id] = frase
        return frase

    def frase_valida(texto: str) -> bool:
        t = (texto or "").strip()
        if not t:
            return False
        palavras = [p for p in re.split(r"\s+", t) if p]
        if len(palavras) < 8:
            return False
        return local.lower() in t.lower()

    try:
        response = genai_client.models.generate_content(model=GEMINI_TEXT_MODEL, contents=prompt)
        frase = (response.text or "").strip()

        repetida = any(frase.lower() == h.lower() for h in historico) or (
            fala_anterior and frase.lower() == fala_anterior.lower()
        )
        if repetida or not frase_valida(frase):
            response2 = genai_client.models.generate_content(
                model=GEMINI_TEXT_MODEL,
                contents=prompt + " Gere outra versão mais contextual, citando o bloco e um destaque real.",
            )
            frase2 = (response2.text or "").strip()
            if frase2:
                frase = frase2

        if not frase_valida(frase):
            destaque_curto = salas_importantes[0] if salas_importantes else local
            extra_util = conhecimento_pratico[0] if conhecimento_pratico else dica
            frase = f"Você chegou ao {local}. O destaque daqui é {destaque_curto}. {extra_util}"

        ultimas_falas_por_bloco[destino_id] = frase
        historico_falas_ia_por_bloco.setdefault(destino_id, []).append(frase)
        return frase
    except Exception as e:
        print(f"Erro na IA: {e}")
        destaque_curto = salas_importantes[0] if salas_importantes else local
        extra_util = conhecimento_pratico[0] if conhecimento_pratico else ""
        fallback = [
            f"Você chegou ao {local}. O destaque daqui é {destaque_curto}. {extra_util or dica}",
            f"No {local}, vale passar em {destaque_curto}. {extra_util or dica}",
            f"Bem-vindo ao {local}: referência rápida é {destaque_curto}. {extra_util or dica}",
        ]
        frase = escolher_fala_fallback(destino_id, fallback)
        ultimas_falas_por_bloco[destino_id] = frase
        return frase


class RequisicaoLocal(BaseModel):
    destino: str
    contexto_extra: dict[str, Any] | str | list[str] | None = None


class RequisicaoChat(BaseModel):
    pergunta: str
    contexto_extra: dict[str, Any] | str | list[str] | None = None


class RequisicaoTTS(BaseModel):
    texto: str


@app.get("/", response_class=HTMLResponse)
async def ler_index() -> str:
    candidatos = [
        os.path.join(STATIC_DIR, "index.html"),
        os.path.join(STATIC_DIR, "index"),
        "index.html",
        "index",
    ]
    for caminho in candidatos:
        if os.path.exists(caminho):
            with open(caminho, "r", encoding="utf-8") as f:
                return f.read()
    return "<h1>Arquivo de interface nao encontrado.</h1>"


@app.get("/api/locais")
async def listar_locais() -> dict[str, Any]:
    return locais_campus


@app.post("/api/guiar")
async def guiar_usuario(req: RequisicaoLocal) -> dict[str, Any]:
    destino_id = req.destino.lower().strip()
    if destino_id in locais_campus:
        dados = locais_campus[destino_id]
        texto_avatar = await gerar_fala_com_ia(destino_id, dados, contexto_extra=req.contexto_extra)
        return {
            "status": "sucesso",
            "coordenadas": {"x": dados["x"], "y": dados["y"]},
            "salas": dados["salas"],
            "dica": dados["dica"],
            "texto": texto_avatar,
        }
    return {"status": "erro", "mensagem": "Local não encontrado."}


@app.post("/api/chat")
async def chat_veterano(req: RequisicaoChat) -> dict[str, Any]:
    busca = buscar_destino_por_sala(req.pergunta)
    if busca:
        destino = busca["destino"]
        sala = busca["sala"]
        nome_destino = destino.upper()
        return {
            "status": "sucesso",
            "tipo": "sala",
            "destino": destino,
            "texto": f"Achei {sala}. Fica no {nome_destino}. Bora te guiar pra la!",
        }

    inferencia_ia = await inferir_destino_com_ia(req.pergunta, contexto_extra=req.contexto_extra)
    if inferencia_ia:
        destino = inferencia_ia["destino"]
        nome_destino = destino.upper()
        return {
            "status": "sucesso",
            "tipo": "sala",
            "destino": destino,
            "texto": f"Entendi tua busca e localizei no {nome_destino}. Vou te guiar ate la!",
        }

    prompt = montar_prompt_polia(
        objetivo="Responder dúvida geral do calouro de forma útil e natural.",
        dados={"pergunta": req.pergunta},
        regras=["Responda com no máximo 3 frases.", "Seja direto e natural."],
        contexto_extra=req.contexto_extra,
    )

    if not genai_client:
        return {
            "status": "sucesso",
            "texto": "Tenta me perguntar por bloco ou sala, tipo B01, K06 ou Biblioteca, que eu te guio rapidinho.",
        }

    try:
        response = genai_client.models.generate_content(model=GEMINI_TEXT_MODEL, contents=prompt)
        texto = (response.text or "").strip()
        if not texto:
            texto = "Posso te ajudar com rotas por bloco e sala. Manda um local que eu te levo."
        return {"status": "sucesso", "texto": texto}
    except Exception as e:
        print(f"Erro no chat IA: {e}")
        return {
            "status": "sucesso",
            "texto": "Deu ruim na IA agora, mas ainda consigo te guiar se tu disser uma sala ou bloco.",
        }


def gerar_audio_openai(texto: str) -> bytes | None:
    if not OPENAI_API_KEY:
        return None

    texto_limpo = (texto or "").strip()
    if not texto_limpo:
        return None

    payload = {
        "model": OPENAI_TTS_MODEL,
        "voice": OPENAI_TTS_VOICE,
        "input": texto_limpo,
        "response_format": "mp3",
        "instructions": OPENAI_TTS_INSTRUCTIONS,
    }

    request = urllib.request.Request(
        url="https://api.openai.com/v1/audio/speech",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {OPENAI_API_KEY}",
        },
    )

    try:
        ssl_ctx = ssl.create_default_context(cafile=certifi.where())
        with urllib.request.urlopen(request, timeout=30, context=ssl_ctx) as response:
            audio = response.read()
        return audio or None
    except urllib.error.HTTPError as e:
        erro = e.read().decode("utf-8", errors="ignore")
        print(f"Erro OpenAI TTS HTTP {e.code}: {erro}")
        return None
    except Exception as e:
        print(f"Erro OpenAI TTS: {e}")
        return None


@app.post("/api/tts")
async def gerar_tts(req: RequisicaoTTS):
    audio = gerar_audio_openai(req.texto)
    if not audio:
        return {"status": "erro", "mensagem": "TTS indisponível"}
    return Response(content=audio, media_type="audio/mpeg")


if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "9000"))
    uvicorn.run(app, host=host, port=port, reload=False)
