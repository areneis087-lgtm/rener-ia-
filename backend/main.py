import base64
import json
import os
import random
import re
import tempfile
import unicodedata
import xml.etree.ElementTree as ET

from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from urllib.parse import quote, quote_plus

import imageio.v2 as imageio
import numpy as np
import requests

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from groq import Groq
from PIL import (
    Image,
    ImageDraw,
    ImageEnhance,
    ImageFilter,
    ImageOps,
)
from pydantic import BaseModel, Field

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None


# ============================================================
# CONFIGURAÇÃO GERAL
# ============================================================

APP_VERSION = "3.3.0"

app = FastAPI(
    title="Rener API",
    version=APP_VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

MODELO_CHAT_RAPIDO = os.getenv(
    "CHAT_MODEL",
    "openai/gpt-oss-120b",
)

MODELO_AUX_RAPIDO = os.getenv(
    "AUX_MODEL",
    MODELO_CHAT_RAPIDO,
)

MODELO_VISAO = os.getenv(
    "VISION_MODEL",
    "qwen/qwen3.8-27b",
)

MODELO_TRANSCRICAO = os.getenv(
    "TRANSCRIPTION_MODEL",
    "whisper-large-v3-turbo",
)

LIMITE_ARQUIVO = 8 * 1024 * 1024

TEXT_EXTENSIONS = {
    ".txt", ".md", ".csv", ".json", ".xml", ".yaml", ".yml",
    ".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css",
    ".sql", ".log", ".ini", ".cfg", ".toml",
}

IMAGE_MIME_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".gif": "image/gif",
}

# Observação: esta cota é mantida na memória do processo.
# Para persistência real entre reinicializações, use um banco de dados.
USO_DIARIO_IMAGENS: dict[str, dict] = {}


# ============================================================
# CLUBES DE FUTEBOL
# ============================================================

ALIASES_CLUBES = {
    "flamengo": "flamengo",
    "mengao": "flamengo",
    "mengão": "flamengo",
    "clube de regatas do flamengo": "flamengo",
    "palmeiras": "palmeiras",
    "sociedade esportiva palmeiras": "palmeiras",
    "corinthians": "corinthians",
    "sport club corinthians paulista": "corinthians",
    "sao paulo": "sao_paulo",
    "são paulo": "sao_paulo",
    "spfc": "sao_paulo",
    "santos": "santos",
    "gremio": "gremio",
    "grêmio": "gremio",
    "internacional": "internacional",
    "vasco": "vasco",
    "botafogo": "botafogo",
    "fluminense": "fluminense",
    "cruzeiro": "cruzeiro",
    "atletico mineiro": "atletico_mineiro",
    "atlético mineiro": "atletico_mineiro",
    "galo": "atletico_mineiro",
    "bahia": "bahia",
    "fortaleza": "fortaleza",
    "real madrid": "real_madrid",
    "barcelona": "barcelona",
}


# ============================================================
# MODELOS DE DADOS
# ============================================================

class HistoryItem(BaseModel):
    role: str
    content: str = ""
    has_image: bool = False
    has_video: bool = False


class ChatRequest(BaseModel):
    message: str
    history: list[HistoryItem] = Field(default_factory=list)
    style: str = "Amigável e direto"
    user_id: str = "anonimo"
    pro_code: str = ""
    creator_key: str = ""
    gallery_image_base64: str = ""


# ============================================================
# CHAVES E CONFIGURAÇÕES
# ============================================================

def ler_variavel(nome: str, padrao: str = "") -> str:
    return (
        os.getenv(nome, padrao)
        .strip()
        .strip('"')
        .strip("'")
    )


def get_groq_client() -> Groq:
    api_key = ler_variavel("GROQ_API_KEY")

    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="GROQ_API_KEY não configurada no servidor.",
        )

    return Groq(api_key=api_key)


def get_pollinations_key() -> str:
    valor = ler_variavel("POLLINATIONS_API_KEY")

    if valor in {"", "SUA_CHAVE_POLLINATIONS"}:
        return ""

    return valor


def get_hf_token() -> str:
    return (
        ler_variavel("HF_TOKEN")
        or ler_variavel("HUGGINGFACE_API_KEY")
    )


def get_tavily_key() -> str:
    return ler_variavel("TAVILY_API_KEY")


def get_limite_gratis_imagens() -> int:
    try:
        return max(
            1,
            int(ler_variavel("LIMITE_GRATIS_IMAGENS", "5")),
        )
    except ValueError:
        return 5


# ============================================================
# PLANOS PRO E CRIADOR
# ============================================================

def usuario_eh_criador(creator_key: str) -> bool:
    chave_mestra = ler_variavel("RENER_CREATOR_KEY")

    if not chave_mestra:
        return False

    return bool(
        creator_key
        and creator_key.strip() == chave_mestra
    )


def usuario_eh_pro(
    pro_code: str,
    creator_key: str = "",
) -> bool:
    if usuario_eh_criador(creator_key):
        return True

    codigo_servidor = ler_variavel("RENER_PRO_CODE")

    if not codigo_servidor:
        return False

    return bool(
        pro_code
        and pro_code.strip() == codigo_servidor
    )


def verificar_e_consumir_cota_imagem(
    user_id: str,
    pro_code: str,
    creator_key: str = "",
) -> tuple[bool, int, int, str]:

    if usuario_eh_criador(creator_key):
        return True, 999999, 999999, "Criador Ilimitado"

    limite = get_limite_gratis_imagens()

    if usuario_eh_pro(pro_code, creator_key):
        return True, 999, 999, "Pro Ilimitado"

    hoje = datetime.now().strftime("%Y-%m-%d")
    chave = (user_id or "anonimo").strip()[:80] or "anonimo"

    registro = USO_DIARIO_IMAGENS.get(chave)

    if not registro or registro.get("data") != hoje:
        registro = {
            "data": hoje,
            "usadas": 0,
        }
        USO_DIARIO_IMAGENS[chave] = registro

    if registro["usadas"] >= limite:
        return False, 0, limite, "Limite Atingido"

    registro["usadas"] += 1

    restantes = max(
        0,
        limite - registro["usadas"],
    )

    return (
        True,
        restantes,
        limite,
        f"{restantes}/{limite} grátis hoje",
    )


# ============================================================
# PERSONALIDADE DA RENER
# ============================================================

def montar_system_prompt(
    style: str = "Amigável e direto",
    is_creator: bool = False,
) -> str:

    agora = datetime.now()

    regalia = (
        "O usuário atual é Rener, seu criador. "
        "Trate-o com prioridade e respostas diretas. "
        if is_creator
        else ""
    )

    return (
        f"Você se chama Rener. Data de hoje: {agora.strftime('%d/%m/%Y')}. "
        "Seu criador também se chama Rener, e ele montou este aplicativo "
        "junto com o Gemini. Quando perguntarem quem te criou ou sobre "
        "a origem do seu nome, responda: "
        "'Fui criado pelo Rener em parceria com o Gemini — "
        "por isso que meu nome é Rener, homenagem ao meu criador.' "

        f"{regalia}"

        "Siga as instruções do usuário de forma objetiva, colaborativa "
        "e sem rodeios. "

        "Você tem conhecimento amplo em Língua Portuguesa, História, "
        "Geografia, Biologia, Ciências e Inglês. "

        "Você tem especialidade na história de Sergipe e de suas cidades, "
        "incluindo colonização, capitania, independência, emancipação "
        "política, formação dos municípios, figuras históricas, cultura "
        "e patrimônio. "

        "Quando responder sobre Sergipe, seja preciso e não invente datas "
        "ou fatos quando não tiver certeza. "

        "Quando houver dados de pesquisa na internet, utilize-os com "
        "cuidado e indique as fontes disponíveis. "

        "Quando não tiver certeza de uma informação, deixe isso claro. "
        "Não invente notícias, placares, resultados ou informações atuais. "

        "Atenção: Flamengo em contexto de futebol, time, torcida, escudo "
        "ou estádio significa Clube de Regatas do Flamengo. "
        "Use vermelho e preto, sem azul no escudo oficial. "
        "Não confunda com a ave flamingo, exceto quando o usuário pedir "
        "explicitamente a ave. "

        "Responda em português natural, claro e direto. "
        "Evite usar markdown para negrito. "

        f"Estilo de resposta atual: {style}."
    )


# ============================================================
# IDENTIFICAÇÃO DE PEDIDOS
# ============================================================

def eh_pedido_escudo_ou_emblema(texto: str) -> bool:
    texto = (texto or "").lower()

    return any(
        palavra in texto
        for palavra in (
            "escudo",
            "emblema",
            "brasão",
            "brasao",
            "símbolo",
            "simbolo",
            "logo",
        )
    )


def normalizar_texto(texto: str) -> str:
    sem_acento = unicodedata.normalize(
        "NFKD",
        texto or "",
    )

    sem_acento = "".join(
        caractere
        for caractere in sem_acento
        if not unicodedata.combining(caractere)
    )

    texto_limpo = re.sub(
        r"[^\w\s-]",
        " ",
        sem_acento.lower(),
    )

    return re.sub(
        r"\s+",
        " ",
        texto_limpo,
    ).strip()


def identificar_clube_futebol(texto: str) -> str | None:
    texto = normalizar_texto(texto)

    for apelido in sorted(
        ALIASES_CLUBES,
        key=len,
        reverse=True,
    ):
        apelido_norm = normalizar_texto(apelido)

        if re.search(
            rf"(?<!\w){re.escape(apelido_norm)}(?!\w)",
            texto,
        ):
            return ALIASES_CLUBES[apelido]

    return None


def decidir_acao_rapida(mensagem_atual: str) -> dict:
    texto = (mensagem_atual or "").lower().strip()

    palavras_gerar = (
        "gere", "gerar", "crie", "criar",
        "faça", "faca", "mostre", "quero",
    )

    palavras_video = (
        "vídeo", "video", "curta metragem",
        "animação", "animacao",
    )

    if any(p in texto for p in palavras_video):
        if any(p in texto for p in palavras_gerar):
            return {
                "acao": "video",
                "consulta_web": mensagem_atual,
                "prompt_midia": mensagem_atual,
            }

    gatilhos_imagem = (
        "gere uma imagem",
        "gerar uma imagem",
        "crie uma imagem",
        "criar uma imagem",
        "faça uma imagem",
        "faca uma imagem",
        "faça a imagem",
        "faca a imagem",
        "gera uma imagem",
        "cria uma imagem",
        "crie foto",
        "cria foto",
        "gerar foto",
        "gere uma foto",
        "crie ela",
        "crie ele",
        "imagem de ",
        "imagem do ",
        "imagem da ",
        "foto de ",
        "foto do ",
        "foto da ",
        "desenhe ",
        "escudo do",
        "escudo de",
        "emblema do",
        "emblema de",
        "mostre o escudo",
        "mostre o emblema",
    )

    if any(p in texto for p in gatilhos_imagem):
        return {
            "acao": "image",
            "consulta_web": mensagem_atual,
            "prompt_midia": mensagem_atual,
        }

    gatilhos_web = (
        "notícia",
        "noticias",
        "notícias",
        "placar",
        "resultado do jogo",
        "quanto foi o jogo",
        "previsão do tempo",
        "clima em",
        "cotação",
        "dólar hoje",
        "dolar hoje",
        "hoje em ",
        "últimas notícias",
        "ultimas noticias",
    )

    if any(p in texto for p in gatilhos_web):
        return {
            "acao": "web",
            "consulta_web": mensagem_atual,
            "prompt_midia": mensagem_atual,
        }

    return {
        "acao": "chat",
        "consulta_web": mensagem_atual,
        "prompt_midia": mensagem_atual,
    }


# ============================================================
# IMAGENS ENVIADAS PELA GALERIA
# ============================================================

def _decodificar_imagem_galeria(
    gallery_image_base64: str,
) -> Image.Image | None:

    b64 = (gallery_image_base64 or "").strip()

    if not b64:
        return None

    if b64.startswith("data:") and "," in b64:
        b64 = b64.split(",", 1)[1]

    try:
        raw = base64.b64decode(
            b64,
            validate=True,
        )

        imagem = Image.open(
            BytesIO(raw),
        ).convert("RGBA")

        imagem.load()

        if imagem.width < 16 or imagem.height < 16:
            return None

        return imagem

    except Exception:
        return None


def aplicar_imagem_da_galeria(
    imagem_bytes: bytes,
    pedido_original: str,
    gallery_image_base64: str = "",
    tipo_escudo: bool = False,
) -> tuple[bytes, bool]:

    escudo = _decodificar_imagem_galeria(
        gallery_image_base64,
    )

    if escudo is None:
        return imagem_bytes, False

    try:
        base = Image.open(
            BytesIO(imagem_bytes),
        ).convert("RGBA")

        extrema = escudo.getextrema()
        tem_transparencia = (
            len(extrema) >= 4
            and extrema[3][0] < 250
        )

        if not tem_transparencia:
            pixels = escudo.getdata()

            novos_pixels = [
                (r, g, b, 0)
                if r > 244 and g > 244 and b > 244
                else (r, g, b, a)
                for r, g, b, a in pixels
            ]

            escudo.putdata(novos_pixels)

        largura, altura = base.size

        if tipo_escudo:
            tamanho = int(min(largura, altura) * 0.56)

            escudo.thumbnail(
                (tamanho, tamanho),
                Image.Resampling.LANCZOS,
            )

            x = (largura - escudo.width) // 2
            y = (altura - escudo.height) // 2

        else:
            tamanho = int(min(largura, altura) * 0.16)

            escudo.thumbnail(
                (tamanho, tamanho),
                Image.Resampling.LANCZOS,
            )

            margem = max(
                20,
                int(min(largura, altura) * 0.035),
            )

            x = largura - escudo.width - margem
            y = margem

        base.alpha_composite(
            escudo,
            (x, y),
        )

        buffer = BytesIO()

        base.convert("RGB").save(
            buffer,
            format="PNG",
            optimize=True,
        )

        return buffer.getvalue(), True

    except Exception:
        return imagem_bytes, False


# ============================================================
# TRATAMENTO E RESOLUÇÃO DE IMAGENS
# ============================================================

def cortar_selo_canto(img: Image.Image) -> Image.Image:
    largura, altura = img.size

    if largura < 200 or altura < 200:
        return img

    return img.crop(
        (0, 0, largura, int(altura * 0.91)),
    )


def refinar_fotografia_pro(img: Image.Image) -> Image.Image:
    base = cortar_selo_canto(img).convert("RGB")

    equilibrada = ImageOps.autocontrast(
        base,
        cutoff=0.5,
    )

    nitida = equilibrada.filter(
        ImageFilter.UnsharpMask(
            radius=1.6,
            percent=145,
            threshold=3,
        ),
    )

    contraste = ImageEnhance.Contrast(
        nitida,
    ).enhance(1.08)

    cor = ImageEnhance.Color(
        contraste,
    ).enhance(1.07)

    return ImageEnhance.Sharpness(
        cor,
    ).enhance(1.15)


def detectar_dimensoes_pedido(
    pedido_usuario: str,
) -> tuple[int, int]:

    texto = (pedido_usuario or "").lower()

    pede_paisagem = any(
        p in texto
        for p in (
            "paisagem",
            "widescreen",
            "horizontal",
            "banner",
            "cinematográfico",
            "cinematografico",
            "landscape",
        )
    )

    pede_vertical = any(
        p in texto
        for p in (
            "vertical",
            "stories",
            "story",
            "celular",
            "portrait",
        )
    )

    if pede_vertical:
        return 1080, 1920

    if pede_paisagem:
        return 1920, 1080

    return 1280, 1280


def upscale_profissional(
    raw_img_bytes: bytes,
    alvo_dims: tuple[int, int],
) -> bytes:

    img = Image.open(
        BytesIO(raw_img_bytes),
    ).convert("RGB")

    img = refinar_fotografia_pro(img)

    alvo_w, alvo_h = alvo_dims

    if img.size != (alvo_w, alvo_h):
        img = ImageOps.fit(
            img,
            (alvo_w, alvo_h),
            method=Image.Resampling.LANCZOS,
        )

    img = img.filter(
        ImageFilter.UnsharpMask(
            radius=1.2,
            percent=110,
            threshold=2,
        ),
    )

    buffer = BytesIO()

    img.save(
        buffer,
        format="PNG",
        optimize=True,
    )

    return buffer.getvalue()


def gerar_imagem_fallback_local(
    pedido_original: str,
    alvo_dims: tuple[int, int],
) -> bytes:

    largura, altura = alvo_dims
    texto = (pedido_original or "Criação visual Rener").lower()

    if "flamengo" in texto:
        cor_topo = (35, 10, 14)
        cor_fundo = (15, 15, 20)
    else:
        cor_topo = (15, 29, 58)
        cor_fundo = (6, 11, 22)

    imagem = Image.new(
        "RGB",
        (largura, altura),
        cor_fundo,
    )

    desenho = ImageDraw.Draw(imagem)

    for y in range(altura):
        proporcao = y / max(1, altura - 1)

        r = int(
            cor_topo[0] * (1 - proporcao)
            + cor_fundo[0] * proporcao
        )

        g = int(
            cor_topo[1] * (1 - proporcao)
            + cor_fundo[1] * proporcao
        )

        b = int(
            cor_topo[2] * (1 - proporcao)
            + cor_fundo[2] * proporcao
        )

        desenho.line(
            [(0, y), (largura, y)],
            fill=(r, g, b),
        )

    resumo = (pedido_original or "Rener").strip()[:60]

    desenho.text(
        (max(28, largura // 14), max(28, altura // 2 - 12)),
        "RENER",
        fill=(147, 197, 253),
    )

    desenho.text(
        (max(28, largura // 14), max(56, altura // 2 + 12)),
        resumo,
        fill=(248, 250, 252),
    )

    buffer = BytesIO()

    imagem.save(
        buffer,
        format="PNG",
        optimize=True,
    )

    return buffer.getvalue()


def obter_dimensoes_bytes(
    img_bytes: bytes | None,
) -> tuple[int, int] | None:

    if not img_bytes:
        return None

    try:
        imagem = Image.open(
            BytesIO(img_bytes),
        )

        return imagem.size

    except Exception:
        return None


def rotulo_resolucao(
    dims: tuple[int, int] | None,
) -> str:

    if not dims:
        return "alta definição"

    largura, altura = dims

    eh_4k = largura >= 3840 or altura >= 2160

    rotulo = (
        "4K UHD"
        if eh_4k
        else (
            "FHD"
            if max(largura, altura) >= 1920
            else "HD"
        )
    )

    return f"{largura}x{altura} px • {rotulo}"


# ============================================================
# HISTÓRICO DA CONVERSA
# ============================================================

def formatar_historico_curto(
    historico: list[HistoryItem],
    limite: int = 6,
) -> str:

    trechos = []

    for item in historico[-limite:]:
        papel = (
            "Usuário"
            if item.role == "user"
            else "Rener"
        )

        conteudo = (item.content or "").strip()
        anexos = []

        if item.has_image:
            anexos.append("[imagem exibida no chat]")

        if item.has_video:
            anexos.append("[vídeo exibido no chat]")

        texto_final = (
            f"{conteudo} {' '.join(anexos)}"
        ).strip()

        if texto_final:
            trechos.append(
                f"{papel}: {texto_final}",
            )

    return "\n".join(trechos)


# ============================================================
# PLANEJAMENTO DE CENA COM IA
# ============================================================

def planejar_cena_com_ia(
    client: Groq,
    pedido_usuario: str,
    tipo_midia: str,
    historico: list[HistoryItem],
) -> dict:

    eh_escudo = eh_pedido_escudo_ou_emblema(
        pedido_usuario,
    )

    clube = identificar_clube_futebol(
        pedido_usuario,
    )

    if eh_escudo:
        prompt_fallback = (
            f"crisp vector football crest emblem for "
            f"{clube or pedido_usuario}, clean sharp lines, "
            "centered composition, plain background, no watermark"
        )
    else:
        prompt_fallback = (
            f"realistic candid photograph of {pedido_usuario}, "
            "natural lighting, sharp focus, real camera detail, "
            "authentic environment"
        )

    fallback = {
        "prompt_visual": prompt_fallback,
    }

    contexto = formatar_historico_curto(historico)

    try:
        resposta = client.chat.completions.create(
            model=MODELO_AUX_RAPIDO,
            temperature=0.5,
            max_tokens=220,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Retorne APENAS JSON válido com a chave "
                        "'prompt_visual'. Escreva o prompt em inglês. "
                        "Descreva a cena visual solicitada. "
                        "Não inclua explicações fora do JSON. "
                        "Se mencionar Flamengo no contexto de futebol, "
                        "use vermelho e preto, sem azul, e nunca a ave."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Contexto:\n{contexto or '(início)'}\n"
                        f"Tipo: {tipo_midia}\n"
                        f"Pedido: {pedido_usuario}"
                    ),
                },
            ],
        )

        conteudo = (
            resposta.choices[0].message.content or ""
        ).strip()

        correspondencia = re.search(
            r"\{.*\}",
            conteudo,
            re.DOTALL,
        )

        if correspondencia:
            dados = json.loads(
                correspondencia.group(0),
            )

            prompt_visual = str(
                dados.get("prompt_visual")
                or fallback["prompt_visual"]
            ).strip()

            return {
                "prompt_visual": prompt_visual[:1500],
            }

    except Exception:
        pass

    return fallback


# ============================================================
# GERAÇÃO DE IMAGENS
# ============================================================

def _tentar_hf_sem_token(
    prompt_curto: str,
    hf_token: str,
) -> bytes | None:

    modelos = [
        "black-forest-labs/FLUX.1-schnell",
        "stabilityai/stable-diffusion-xl-base-1.0",
    ]

    headers = {
        "Accept": "image/png",
    }

    if hf_token:
        headers["Authorization"] = (
            f"Bearer {hf_token}"
        )

    for modelo in modelos:
        try:
            resposta = requests.post(
                f"https://router.huggingface.co/hf-inference/models/{modelo}",
                headers=headers,
                json={"inputs": prompt_curto},
                timeout=45,
            )

            content_type = (
                resposta.headers.get("Content-Type") or ""
            ).lower()

            if (
                resposta.status_code == 200
                and resposta.content
                and "json" not in content_type
                and "html" not in content_type
            ):
                imagem = Image.open(
                    BytesIO(resposta.content),
                ).convert("RGB")

                if imagem.width >= 128 and imagem.height >= 128:
                    buffer = BytesIO()

                    imagem.save(
                        buffer,
                        format="PNG",
                    )

                    return buffer.getvalue()

        except Exception:
            continue

    return None


def gerar_imagem_bytes(
    info_cena: dict,
    pollinations_key: str = "",
    pedido_original: str = "",
    gallery_image_base64: str = "",
) -> tuple[bytes, bool, bool]:

    chave = (
        pollinations_key
        or get_pollinations_key()
    ).strip()

    hf_token = get_hf_token()

    alvo_dims = detectar_dimensoes_pedido(
        pedido_original,
    )

    prompt_visual = (
        info_cena.get("prompt_visual")
        or pedido_original
        or "realistic photo"
    ).strip()

    prompt_curto = prompt_visual[:500]
    seed = random.randint(100000, 999999999)

    param_chave = (
        f"&key={quote(chave)}"
        if chave
        else ""
    )

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "image/png,image/webp,image/*,*/*",
    }

    if chave:
        headers["Authorization"] = (
            f"Bearer {chave}"
        )

    tentativas = [
        (
            "https://image.pollinations.ai/prompt/"
            f"{quote(prompt_curto)}"
            f"?width=1024&height=1024&seed={seed}"
            f"&model=flux&nologo=true{param_chave}"
        ),
        (
            "https://gen.pollinations.ai/image/"
            f"{quote(prompt_curto)}"
            f"?width=1024&height=1024&seed={seed + 1}"
            f"&model=flux&nologo=true{param_chave}"
        ),
        (
            "https://image.pollinations.ai/prompt/"
            f"{quote((pedido_original or prompt_curto)[:250])}"
            f"?width=512&height=512&seed={seed + 2}"
        ),
    ]

    for url in tentativas:
        try:
            resposta = requests.get(
                url,
                timeout=45,
                headers=headers,
            )

            content_type = (
                resposta.headers.get("Content-Type") or ""
            ).lower()

            if (
                resposta.status_code == 200
                and resposta.content
                and "html" not in content_type
                and "text" not in content_type
            ):
                imagem = Image.open(
                    BytesIO(resposta.content),
                ).convert("RGB")

                if imagem.width >= 128 and imagem.height >= 128:
                    buffer = BytesIO()

                    imagem.save(
                        buffer,
                        format="PNG",
                    )

                    imagem_final = upscale_profissional(
                        buffer.getvalue(),
                        alvo_dims,
                    )

                    composta, aplicou_galeria = (
                        aplicar_imagem_da_galeria(
                            imagem_final,
                            pedido_original,
                            gallery_image_base64,
                            eh_pedido_escudo_ou_emblema(
                                pedido_original,
                            ),
                        )
                    )

                    return composta, aplicou_galeria, False

        except Exception:
            continue

    imagem_hf = _tentar_hf_sem_token(
        prompt_curto,
        hf_token,
    )

    if imagem_hf:
        imagem_final = upscale_profissional(
            imagem_hf,
            alvo_dims,
        )

        composta, aplicou_galeria = (
            aplicar_imagem_da_galeria(
                imagem_final,
                pedido_original,
                gallery_image_base64,
                eh_pedido_escudo_ou_emblema(
                    pedido_original,
                ),
            )
        )

        return composta, aplicou_galeria, False

    imagem_fallback = gerar_imagem_fallback_local(
        pedido_original,
        alvo_dims,
    )

    composta, aplicou_galeria = (
        aplicar_imagem_da_galeria(
            imagem_fallback,
            pedido_original,
            gallery_image_base64,
            eh_pedido_escudo_ou_emblema(
                pedido_original,
            ),
        )
    )

    return composta, aplicou_galeria, True


# ============================================================
# GERAÇÃO DE VÍDEO CURTO
# ============================================================

def gerar_video_mp4_bytes(
    info_cena: dict,
    pollinations_key: str = "",
    pedido_original: str = "",
    gallery_image_base64: str = "",
    segundos: int = 3,
    fps: int = 12,
) -> bytes | None:

    imagem_bytes, _, _ = gerar_imagem_bytes(
        info_cena,
        pollinations_key=pollinations_key,
        pedido_original=pedido_original,
        gallery_image_base64=gallery_image_base64,
    )

    if not imagem_bytes:
        return None

    largura = 640
    altura = 640

    arte_base = (
        Image.open(BytesIO(imagem_bytes))
        .convert("RGB")
        .resize(
            (largura + 96, altura + 96),
            Image.Resampling.LANCZOS,
        )
    )

    total_frames = max(
        12,
        min(120, segundos * fps),
    )

    caminho_mp4 = None

    try:
        with tempfile.NamedTemporaryFile(
            suffix=".mp4",
            delete=False,
        ) as tmp:
            caminho_mp4 = tmp.name

        writer = imageio.get_writer(
            caminho_mp4,
            fps=fps,
            codec="libx264",
            quality=7,
            macro_block_size=16,
        )

        try:
            for i in range(total_frames):
                progresso = i / max(
                    1,
                    total_frames - 1,
                )

                dx = int(progresso * 96)

                dy = int(
                    (1 - abs(2 * progresso - 1)) * 64
                )

                frame = arte_base.crop(
                    (
                        dx,
                        dy,
                        dx + largura,
                        dy + altura,
                    )
                ).convert("RGB")

                writer.append_data(
                    np.array(frame),
                )

        finally:
            writer.close()

        return Path(caminho_mp4).read_bytes()

    except Exception:
        return None

    finally:
        if caminho_mp4:
            try:
                Path(caminho_mp4).unlink(
                    missing_ok=True,
                )
            except Exception:
                pass


# ============================================================
# PESQUISA NA INTERNET
# ============================================================

def buscar_na_internet(
    consulta: str,
    tavily_key: str,
) -> str:

    agora = datetime.now()
    ontem = agora - timedelta(days=1)

    query_data = (consulta or "").strip()

    if "ontem" in query_data.lower():
        query_data += f" {ontem.strftime('%d/%m/%Y')}"

    if "hoje" in query_data.lower():
        query_data += f" {agora.strftime('%d/%m/%Y')}"

    if tavily_key:
        try:
            resposta = requests.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": tavily_key,
                    "query": query_data,
                    "max_results": 5,
                    "include_answer": True,
                },
                timeout=12,
            )

            if resposta.status_code == 200:
                dados = resposta.json()
                blocos = []

                resumo = (
                    dados.get("answer") or ""
                ).strip()

                if resumo:
                    blocos.append(
                        f"[Resumo]\n{resumo}",
                    )

                for indice, item in enumerate(
                    dados.get("results", []),
                    start=1,
                ):
                    blocos.append(
                        f"[{indice}] "
                        f"{item.get('title', '').strip()}\n"
                        f"Resumo: "
                        f"{item.get('content', '').strip()}\n"
                        f"Fonte: "
                        f"{item.get('url', '').strip()}"
                    )

                if blocos:
                    return "\n\n".join(blocos)

        except Exception:
            pass

    try:
        url = (
            "https://news.google.com/rss/search?"
            f"q={quote_plus(query_data)}"
            "&hl=pt-BR&gl=BR&ceid=BR:pt-419"
        )

        resposta = requests.get(
            url,
            timeout=10,
            headers={
                "User-Agent": "Mozilla/5.0",
            },
        )

        if resposta.status_code == 200:
            raiz = ET.fromstring(
                resposta.text,
            )

            itens = []

            for indice, item in enumerate(
                raiz.findall(".//item")[:5],
                start=1,
            ):
                titulo = (
                    item.findtext("title") or ""
                ).strip()

                publicacao = (
                    item.findtext("pubDate") or ""
                ).strip()

                link = (
                    item.findtext("link") or ""
                ).strip()

                if titulo:
                    itens.append(
                        f"[Notícia {indice}] {titulo} "
                        f"({publicacao})\nFonte: {link}"
                    )

            return "\n\n".join(itens)

    except Exception:
        pass

    return ""


# ============================================================
# LEITURA DE ARQUIVOS E PDF
# ============================================================

def extrair_texto_pdf(
    raw_bytes: bytes,
    max_chars: int = 12000,
) -> str:

    if PdfReader is None:
        return ""

    try:
        leitor = PdfReader(
            BytesIO(raw_bytes),
        )

        partes = []
        total = 0

        for numero, pagina in enumerate(
            leitor.pages,
            start=1,
        ):
            texto = (
                pagina.extract_text() or ""
            ).strip()

            if texto:
                bloco = (
                    f"--- Página {numero} ---\n{texto}"
                )

                partes.append(bloco)
                total += len(bloco)

            if total >= max_chars:
                break

        return "\n\n".join(partes)[:max_chars]

    except Exception:
        return ""


def preparar_imagem_para_visao(
    raw_bytes: bytes,
    ext: str,
) -> tuple[str, str]:

    mime = IMAGE_MIME_TYPES.get(
        ext.lower(),
        "image/jpeg",
    )

    try:
        imagem = Image.open(
            BytesIO(raw_bytes),
        )

        imagem.load()

        largura, altura = imagem.size
        maior_lado = max(largura, altura)

        if maior_lado > 1280:
            escala = 1280 / maior_lado

            imagem = imagem.resize(
                (
                    max(1, int(largura * escala)),
                    max(1, int(altura * escala)),
                ),
                Image.Resampling.LANCZOS,
            )

        if imagem.mode != "RGB":
            imagem = imagem.convert("RGB")

        buffer = BytesIO()

        imagem.save(
            buffer,
            format="JPEG",
            quality=85,
            optimize=True,
        )

        return (
            "image/jpeg",
            base64.b64encode(
                buffer.getvalue(),
            ).decode("utf-8"),
        )

    except Exception:
        return (
            mime,
            base64.b64encode(
                raw_bytes,
            ).decode("utf-8"),
        )


# ============================================================
# ROTAS DE SAÚDE
# ============================================================

@app.get("/")
@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "Rener API",
        "version": APP_VERSION,
    }


# ============================================================
# ROTA PRINCIPAL DO CHAT
# ============================================================

@app.post("/chat")
def chat_endpoint(req: ChatRequest):

    mensagem = (req.message or "").strip()

    if not mensagem:
        raise HTTPException(
            status_code=400,
            detail="Mensagem vazia.",
        )

    if len(mensagem) > 20000:
        raise HTTPException(
            status_code=400,
            detail="Mensagem muito grande.",
        )

    client = get_groq_client()

    tavily_key = get_tavily_key()
    pollinations_key = get_pollinations_key()

    is_creator = usuario_eh_criador(
        req.creator_key,
    )

    decisao = decidir_acao_rapida(
        mensagem,
    )

    acao = decisao["acao"]

    # --------------------------------------------------------
    # GERAÇÃO DE IMAGEM
    # --------------------------------------------------------

    if acao == "image":

        permitido, _, limite, info_cota = (
            verificar_e_consumir_cota_imagem(
                req.user_id,
                req.pro_code,
                req.creator_key,
            )
        )

        if not permitido:
            return {
                "type": "paywall",
                "reply": (
                    f"Você atingiu o limite diário gratuito "
                    f"de {limite} imagens. "
                    "Ative o Rener Pro para gerar imagens ilimitadas."
                ),
            }

        pedido = decisao["prompt_midia"]

        info = planejar_cena_com_ia(
            client,
            pedido,
            "imagem",
            req.history,
        )

        imagem_bytes, aplicou_galeria, usou_fallback = (
            gerar_imagem_bytes(
                info,
                pollinations_key=pollinations_key,
                pedido_original=pedido,
                gallery_image_base64=req.gallery_image_base64,
            )
        )

        dimensoes = obter_dimensoes_bytes(
            imagem_bytes,
        )

        resolucao = rotulo_resolucao(
            dimensoes,
        )

        clube = identificar_clube_futebol(
            pedido,
        )

        aviso_galeria = ""

        if clube and not aplicou_galeria:
            aviso_galeria = (
                " Nenhuma imagem da galeria foi aplicada."
            )

        aviso_fallback = (
            " Foi utilizada uma arte de contingência "
            "porque o serviço externo de imagem não respondeu."
            if usou_fallback
            else ""
        )

        return {
            "type": "image",
            "reply": (
                f"Aqui está ({resolucao} • {info_cota})."
                f"{aviso_galeria}{aviso_fallback}"
            ),
            "image_base64": base64.b64encode(
                imagem_bytes,
            ).decode("utf-8"),
        }

    # --------------------------------------------------------
    # GERAÇÃO DE VÍDEO CURTO
    # --------------------------------------------------------

    if acao == "video":

        permitido, _, limite, _ = (
            verificar_e_consumir_cota_imagem(
                req.user_id,
                req.pro_code,
                req.creator_key,
            )
        )

        if not permitido:
            return {
                "type": "paywall",
                "reply": (
                    f"Você atingiu o limite diário gratuito "
                    f"de {limite} criações visuais. "
                    "Ative o Rener Pro para liberar "
                    "mais criações."
                ),
            }

        pedido = decisao["prompt_midia"]

        info = planejar_cena_com_ia(
            client,
            pedido,
            "vídeo curto",
            req.history,
        )

        video_bytes = gerar_video_mp4_bytes(
            info,
            pollinations_key=pollinations_key,
            pedido_original=pedido,
            gallery_image_base64=req.gallery_image_base64,
        )

        if not video_bytes:
            return {
                "type": "text",
                "reply": (
                    "Não consegui criar o vídeo agora. "
                    "Tente novamente daqui a pouco."
                ),
            }

        return {
            "type": "video",
            "reply": "Aqui está o seu vídeo curto:",
            "video_base64": base64.b64encode(
                video_bytes,
            ).decode("utf-8"),
        }

    # --------------------------------------------------------
    # HISTÓRICO
    # --------------------------------------------------------

    mensagens = [
        {
            "role": "system",
            "content": montar_system_prompt(
                req.style,
                is_creator=is_creator,
            ),
        }
    ]

    for item in req.history[-10:]:

        papel = item.role

        if papel not in {"user", "assistant"}:
            continue

        conteudo = (item.content or "").strip()

        if item.has_image:
            conteudo += " [imagem exibida no chat]"

        if item.has_video:
            conteudo += " [vídeo exibido no chat]"

        if conteudo:
            mensagens.append({
                "role": papel,
                "content": conteudo[:12000],
            })

    # --------------------------------------------------------
    # PESQUISA NA INTERNET
    # --------------------------------------------------------

    if acao == "web":

        dados_web = buscar_na_internet(
            decisao["consulta_web"] or mensagem,
            tavily_key,
        )

        if dados_web:
            conteudo_usuario = (
                f"Mensagem do usuário: {mensagem}\n\n"
                "Dados obtidos na busca na internet. "
                "Use os resultados com cuidado, não invente "
                "informações e apresente as fontes disponíveis:\n\n"
                f"{dados_web}"
            )
        else:
            conteudo_usuario = (
                f"Mensagem do usuário: {mensagem}\n\n"
                "A busca automática não retornou resultados "
                "confiáveis neste momento. Não invente notícias, "
                "placares ou dados recentes. Informe que não "
                "foi possível confirmar a informação."
            )

    else:
        conteudo_usuario = mensagem

    mensagens.append({
        "role": "user",
        "content": conteudo_usuario,
    })

    # --------------------------------------------------------
    # RESPOSTA DA IA
    # --------------------------------------------------------

    try:
        completion = client.chat.completions.create(
            model=MODELO_CHAT_RAPIDO,
            messages=mensagens,
            temperature=0.6,
            max_tokens=2048,
        )

        resposta = (
            completion.choices[0].message.content
            or ""
        ).strip()

        if not resposta:
            resposta = (
                "Não consegui formular uma resposta agora. "
                "Pode tentar novamente?"
            )

        return {
            "type": "text",
            "reply": resposta,
        }

    except Exception as exc:
        print(
            "Erro no chat:",
            repr(exc),
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "Erro ao processar a resposta. "
                "Verifique a chave e o modelo configurado no Groq."
            ),
        ) from exc


# ============================================================
# ROTA DE ANÁLISE DE ARQUIVOS
# ============================================================

@app.post("/analyze")
async def analyze_endpoint(
    file: UploadFile = File(...),
    prompt: str = Form(
        "Analise este arquivo e me dê um resumo claro e útil."
    ),
    style: str = Form("Amigável e direto"),
):

    client = get_groq_client()

    raw_bytes = await file.read()

    if not raw_bytes:
        raise HTTPException(
            status_code=400,
            detail="Arquivo vazio.",
        )

    if len(raw_bytes) > LIMITE_ARQUIVO:
        raise HTTPException(
            status_code=400,
            detail="Arquivo muito grande. Limite de 8 MB.",
        )

    nome_arq = (
        Path(file.filename or "arquivo").name
    )

    ext = Path(nome_arq).suffix.lower()

    content_type = (
        file.content_type or ""
    ).lower()

    pergunta = (
        prompt or ""
    ).strip() or (
        "Analise este arquivo e me dê um resumo claro e útil."
    )

    eh_imagem = (
        ext in IMAGE_MIME_TYPES
        or content_type.startswith("image/")
    )

    # --------------------------------------------------------
    # ANÁLISE DE IMAGEM
    # --------------------------------------------------------

    if eh_imagem:

        mime, imagem_b64 = preparar_imagem_para_visao(
            raw_bytes,
            ext,
        )

        try:
            completion = client.chat.completions.create(
                model=MODELO_VISAO,
                messages=[
                    {
                        "role": "system",
                        "content": montar_system_prompt(style),
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    f"Arquivo: {nome_arq}\n"
                                    f"Pedido: {pergunta}"
                                ),
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": (
                                        f"data:{mime};base64,{imagem_b64}"
                                    ),
                                },
                            },
                        ],
                    },
                ],
                temperature=0.4,
                max_tokens=2048,
            )

            resposta = (
                completion.choices[0].message.content
                or "Não consegui analisar a imagem."
            )

            return {
                "type": "text",
                "reply": resposta,
            }

        except Exception as exc:
            print(
                "Erro ao analisar imagem:",
                repr(exc),
            )

            raise HTTPException(
                status_code=500,
                detail=(
                    "Erro ao analisar imagem. "
                    "Verifique se o modelo de visão configurado "
                    "está disponível na sua conta Groq."
                ),
            ) from exc

    # --------------------------------------------------------
    # ANÁLISE DE PDF
    # --------------------------------------------------------

    texto_extraido = ""

    if ext == ".pdf" or content_type == "application/pdf":

        texto_extraido = extrair_texto_pdf(
            raw_bytes,
        )

        if not texto_extraido:
            return {
                "type": "text",
                "reply": (
                    f"Não consegui extrair texto do PDF '{nome_arq}'. "
                    "Ele pode ser escaneado ou conter apenas imagens. "
                    "Envie uma captura da página como imagem para "
                    "que eu possa analisá-la visualmente."
                ),
            }

    # --------------------------------------------------------
    # ANÁLISE DE ARQUIVOS DE TEXTO E CÓDIGO
    # --------------------------------------------------------

    elif ext in TEXT_EXTENSIONS or content_type.startswith("text/"):

        texto_extraido = raw_bytes.decode(
            "utf-8",
            errors="replace",
        )[:12000]

    else:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Formato '{ext or content_type}' não suportado. "
                "Envie JPG, PNG, WEBP, PDF ou arquivo de texto."
            ),
        )

    # --------------------------------------------------------
    # RESPOSTA DA ANÁLISE
    # --------------------------------------------------------

    try:
        completion = client.chat.completions.create(
            model=MODELO_CHAT_RAPIDO,
            messages=[
                {
                    "role": "system",
                    "content": montar_system_prompt(style),
                },
                {
                    "role": "user",
                    "content": (
                        f"Arquivo anexado: {nome_arq}\n"
                        f"Pedido do usuário: {pergunta}\n\n"
                        "Analise o conteúdo abaixo com atenção. "
                        "Explique de forma clara e organizada. "
                        "Se for código, identifique erros e melhorias.\n\n"
                        f"Conteúdo extraído:\n{texto_extraido}"
                    ),
                },
            ],
            temperature=0.4,
            max_tokens=2048,
        )

        resposta = (
            completion.choices[0].message.content
            or "Não consegui analisar o arquivo."
        )

        return {
            "type": "text",
            "reply": resposta,
        }

    except Exception as exc:
        print(
            "Erro na análise de arquivo:",
            repr(exc),
        )

        raise HTTPException(
            status_code=500,
            detail="Erro ao analisar o arquivo.",
        ) from exc


# ============================================================
# ROTA DE TRANSCRIÇÃO DE ÁUDIO
# ============================================================

@app.post("/transcribe")
async def transcribe_endpoint(
    file: UploadFile = File(...),
):

    client = get_groq_client()

    audio_bytes = await file.read()

    if not audio_bytes:
        raise HTTPException(
            status_code=400,
            detail="Áudio vazio.",
        )

    if len(audio_bytes) > 25 * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail="Áudio muito grande. Limite de 25 MB.",
        )

    nome_arq = file.filename or "ditado.webm"

    ext = (
        Path(nome_arq).suffix.lstrip(".")
        or "webm"
    )

    caminho = None

    try:
        with tempfile.NamedTemporaryFile(
            suffix=f".{ext}",
            delete=False,
        ) as tmp:

            tmp.write(audio_bytes)
            caminho = tmp.name

        with open(caminho, "rb") as arquivo_audio:

            transcricao = client.audio.transcriptions.create(
                file=(
                    f"ditado.{ext}",
                    arquivo_audio.read(),
                ),
                model=MODELO_TRANSCRICAO,
                language="pt",
                response_format="text",
            )

        if isinstance(transcricao, str):
            texto = transcricao.strip()
        else:
            texto = str(
                getattr(transcricao, "text", "") or ""
            ).strip()

        return {
            "text": texto,
        }

    except Exception as exc:
        print(
            "Erro na transcrição:",
            repr(exc),
        )

        raise HTTPException(
            status_code=500,
            detail="Erro ao transcrever o áudio.",
        ) from exc

    finally:
        if caminho:
            try:
                Path(caminho).unlink(
                    missing_ok=True,
                )
            except Exception:
                pass
