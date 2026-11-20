
import base64
from datetime import datetime, timedelta
from io import BytesIO
import json
import os
from pathlib import Path
import random
import re
import tempfile
from urllib.parse import quote_plus, unquote
import xml.etree.ElementTree as ET

import imageio.v2 as imageio
import numpy as np
import requests
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from groq import Groq
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
from pydantic import BaseModel, Field

try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None


# =========================================================
# CONFIGURAÇÃO PRINCIPAL
# =========================================================

app = FastAPI(title="Rener API", version="2.4.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

WEB_HEADERS = {
    "User-Agent": "Mozilla/5.0 Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml,*/*",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8",
}

IMAGE_MIME_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}

TEXT_EXTENSIONS = {
    ".txt", ".md", ".csv", ".json", ".xml", ".yaml", ".yml",
    ".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css",
    ".sql", ".log",
}

USO_DIARIO_IMAGENS = {}


# =========================================================
# MODELOS DE DADOS
# =========================================================

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


# =========================================================
# CHAVES E CONFIGURAÇÕES
# =========================================================

def get_groq_client():
    api_key = (os.getenv("GROQ_API_KEY") or "").strip().strip('"').strip("'")

    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="GROQ_API_KEY não configurada no servidor."
        )

    return Groq(api_key=api_key)


def get_tavily_key():
    return (
        (os.getenv("TAVILY_API_KEY") or "")
        .strip()
        .strip('"')
        .strip("'")
    )


def get_pollinations_key():
    return (
        (os.getenv("POLLINATIONS_API_KEY") or "")
        .strip()
        .strip('"')
        .strip("'")
    )


def get_limite_gratis_imagens():
    try:
        return max(1, int(os.getenv("LIMITE_GRATIS_IMAGENS", "5")))
    except Exception:
        return 5


def usuario_eh_criador(creator_key):
    chave = (os.getenv("RENER_CREATOR_KEY") or "").strip()

    return bool(chave) and (creator_key or "").strip() == chave


def usuario_eh_pro(pro_code, creator_key=""):
    if usuario_eh_criador(creator_key):
        return True

    codigo = (os.getenv("RENER_PRO_CODE") or "").strip()

    return bool(codigo) and (pro_code or "").strip() == codigo


# =========================================================
# SISTEMA DE COTAS
# =========================================================

def verificar_e_consumir_cota_imagem(
    user_id,
    pro_code,
    creator_key="",
    consumir=False
):
    if usuario_eh_criador(creator_key):
        return True, 999999, 999999, "Criador Ilimitado"

    if usuario_eh_pro(pro_code, creator_key):
        return True, 999, 999, "Pro Ilimitado"

    limite = get_limite_gratis_imagens()

    hoje = datetime.now().strftime("%Y-%m-%d")
    usuario = (user_id or "anonimo").strip()[:80] or "anonimo"

    registro = USO_DIARIO_IMAGENS.get(usuario)

    if not registro or registro.get("data") != hoje:
        registro = {"data": hoje, "usadas": 0}
        USO_DIARIO_IMAGENS[usuario] = registro

    usadas = registro["usadas"]

    if usadas >= limite:
        return False, 0, limite, "Limite Atingido"

    if consumir:
        registro["usadas"] += 1
        usadas += 1

    restantes = max(0, limite - usadas)

    return True, restantes, limite, f"{restantes}/{limite} grátis hoje"


# =========================================================
# PROMPT DO ASSISTENTE
# =========================================================

def montar_system_prompt(style="Amigável e direto", is_creator=False):
    agora = datetime.now()

    regalia = (
        "O usuário atual é o criador do Rener. "
        if is_creator else ""
    )

    return (
        f"Você se chama Rener. Data de hoje: {agora.strftime('%d/%m/%Y')}. "
        "Seu criador se chama Rener e montou este aplicativo em parceria com o Gemini. "
        "Quando perguntarem quem te criou, responda: "
        "'Fui criado pelo Rener em parceria com o Gemini — por isso que meu nome é Rener, homenagem ao meu criador.' "
        f"{regalia}"
        "Responda sempre em português natural, claro e direto. "
        "Não invente resultados de pesquisas ou informações recentes. "
        "Quando falar de imagens, informe a resolução real quando ela estiver disponível. "
        "Flamengo em contexto de futebol significa Clube de Regatas do Flamengo, "
        "com suas cores tradicionais vermelho e preto. "
        f"Estilo de resposta: {style}."
    )


# =========================================================
# FUNÇÕES DE IMAGEM
# =========================================================

def eh_pedido_escudo_ou_emblema(texto):
    t = (texto or "").lower()

    return any(
        p in t for p in (
            "escudo", "emblema", "brasão", "brasao",
            "símbolo", "simbolo", "logo"
        )
    )


def cortar_selo_canto(img):
    largura, altura = img.size

    if largura < 200 or altura < 200:
        return img

    return img.crop((0, 0, largura, int(altura * 0.91)))


def refinar_fotografia_pro(img):
    base = cortar_selo_canto(img).convert("RGB")

    equilibrada = ImageOps.autocontrast(base, cutoff=0.5)

    nitida = equilibrada.filter(
        ImageFilter.UnsharpMask(
            radius=1.6,
            percent=145,
            threshold=3
        )
    )

    contraste = ImageEnhance.Contrast(nitida).enhance(1.08)
    cor = ImageEnhance.Color(contraste).enhance(1.07)

    return ImageEnhance.Sharpness(cor).enhance(1.15)


def detectar_dimensoes_pedido(pedido_usuario):
    t = (pedido_usuario or "").lower()

    paisagem = any(
        p in t for p in (
            "paisagem", "widescreen", "horizontal",
            "banner", "cinematográfico", "cinematografico",
            "landscape"
        )
    )

    vertical = any(
        p in t for p in (
            "vertical", "stories", "story",
            "celular", "portrait"
        )
    )

    if vertical:
        return 2160, 3840

    if paisagem:
        return 3840, 2160

    return 2160, 2160


def upscale_4k_profissional(raw_img_bytes, alvo_dims):
    img = Image.open(BytesIO(raw_img_bytes)).convert("RGB")

    img = refinar_fotografia_pro(img)

    alvo_w, alvo_h = alvo_dims

    if img.size != (alvo_w, alvo_h):
        img = img.resize(
            (alvo_w, alvo_h),
            Image.Resampling.LANCZOS
        )

        img = img.filter(
            ImageFilter.UnsharpMask(
                radius=1.2,
                percent=110,
                threshold=2
            )
        )

    buffer = BytesIO()

    img.save(
        buffer,
        format="PNG",
        optimize=True
    )

    return buffer.getvalue()


def obter_dimensoes_bytes(img_bytes):
    if not img_bytes:
        return None

    try:
        img = Image.open(BytesIO(img_bytes))
        return img.size
    except Exception:
        return None


def rotulo_resolucao(dims):
    if not dims:
        return "alta definição"

    largura, altura = dims

    eh_4k = largura >= 3840 or altura >= 2160

    rotulo = "4K UHD" if eh_4k else "HD"

    return f"{largura}x{altura} px • {rotulo}"


def normalizar_imagem_baixada(raw_bytes, alvo_dims):
    try:
        img = Image.open(BytesIO(raw_bytes))
        img.load()

        if img.width < 150 or img.height < 150:
            return None

        if img.mode in ("RGBA", "LA") or "transparency" in img.info:
            rgba = img.convert("RGBA")

            fundo = Image.new(
                "RGBA",
                rgba.size,
                (14, 18, 30, 255)
            )

            combinada = Image.alpha_composite(
                fundo,
                rgba
            ).convert("RGB")

        else:
            combinada = img.convert("RGB")

        buffer = BytesIO()
        combinada.save(buffer, format="PNG")

        return upscale_4k_profissional(
            buffer.getvalue(),
            alvo_dims
        )

    except Exception as erro:
        print(f"ERRO AO NORMALIZAR IMAGEM: {erro}")
        return None


# =========================================================
# BUSCA DE ESCUDOS
# =========================================================

def buscar_escudo_na_web(consulta, alvo_dims):
    termo = (consulta or "").strip()

    if not termo:
        return None

    if "flamengo" in termo.lower():
        termo_busca = "Clube de Regatas do Flamengo official crest PNG"
    else:
        termo_busca = f"{termo} escudo oficial PNG"

    candidatas = []

    # Wikimedia Commons
    try:
        url = (
            "https://commons.wikimedia.org/w/api.php"
            "?action=query&generator=search"
            "&gsrnamespace=6&gsrlimit=6"
            "&prop=imageinfo&iiprop=url&format=json"
            f"&gsrsearch={quote_plus(termo_busca)}"
        )

        resposta = requests.get(
            url,
            timeout=12,
            headers=WEB_HEADERS
        )

        if resposta.status_code == 200:
            paginas = (
                resposta.json().get("query", {}).get("pages", {})
            )

            for pagina in paginas.values():
                for info in pagina.get("imageinfo", []):
                    endereco = info.get("url", "")

                    if re.search(
                        r"\.(png|jpg|jpeg|webp)$",
                        endereco,
                        re.I
                    ):
                        if endereco not in candidatas:
                            candidatas.append(endereco)

    except Exception as erro:
        print(f"ERRO WIKIMEDIA: {erro}")

    # DuckDuckGo
    for consulta_busca in (
        termo_busca,
        f"{termo} emblem logo PNG"
    ):
        try:
            resposta = requests.get(
                "https://html.duckduckgo.com/html/",
                params={"q": consulta_busca},
                timeout=12,
                headers=WEB_HEADERS
            )

            if resposta.status_code == 200:
                encontrados = re.findall(
                    r'uddg=([^&"]+)',
                    resposta.text
                )

                for endereco in encontrados:
                    endereco = unquote(endereco)

                    if re.search(
                        r"\.(png|jpg|jpeg|webp)(\?|$)",
                        endereco,
                        re.I
                    ):
                        if endereco not in candidatas:
                            candidatas.append(endereco)

        except Exception as erro:
            print(f"ERRO DUCKDUCKGO: {erro}")

    # Baixa e valida os resultados
    for endereco in candidatas[:8]:
        try:
            resposta = requests.get(
                endereco,
                timeout=12,
                headers=WEB_HEADERS
            )

            tipo = resposta.headers.get(
                "Content-Type", ""
            ).lower()

            if (
                resposta.status_code != 200
                or not resposta.content
                or "image" not in tipo
            ):
                continue

            imagem = normalizar_imagem_baixada(
                resposta.content,
                alvo_dims
            )

            if imagem:
                return imagem

        except Exception as erro:
            print(f"ERRO AO BAIXAR ESCUDO: {erro}")

    return None


# =========================================================
# HISTÓRICO DO CHAT
# =========================================================

def formatar_historico_curto(historico, limite=8):
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

        texto = f"{conteudo} {' '.join(anexos)}".strip()

        if texto:
            trechos.append(f"{papel}: {texto}")

    return "\n".join(trechos)


# =========================================================
# IDENTIFICAÇÃO DA INTENÇÃO
# =========================================================

def decidir_acao_com_ia(client, mensagem_atual, historico):
    contexto = formatar_historico_curto(
        historico,
        limite=6
    )

    texto = (mensagem_atual or "").lower()

    gatilhos_imagem = (
        "gere uma imagem",
        "gerar uma imagem",
        "crie uma imagem",
        "criar uma imagem",
        "faça uma imagem",
        "faca uma imagem",
        "imagem de ",
        "foto de ",
        "desenhe ",
        "escudo do",
        "escudo de",
        "emblema do",
        "emblema de",
        "mostre o escudo",
        "mostre o emblema",
    )

    if any(p in texto for p in gatilhos_imagem):
        acao = (
            "video"
            if "vídeo" in texto or "video" in texto
            else "image"
        )

        return {
            "acao": acao,
            "consulta_web": mensagem_atual,
            "prompt_midia": mensagem_atual
        }

    padrao = {
        "acao": "chat",
        "consulta_web": mensagem_atual,
        "prompt_midia": mensagem_atual
    }

    try:
        resposta = client.chat.completions.create(
            model="openai/gpt-oss-20b",
            tool_choice="none",
            temperature=0.1,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Você é o roteador de intenções do assistente Rener. "
                        "Escolha uma ação: image, video, web ou chat. "
                        "Use image para pedidos de imagens e fotos. "
                        "Use video para criação de vídeos. "
                        "Use web para informações atuais, notícias, "
                        "resultados e preços. "
                        "Responda apenas JSON válido com as chaves "
                        "acao, consulta_web e prompt_midia."
                    )
                },
                {
                    "role": "user",
                    "content": (
                        f"Contexto:\n{contexto}\n\n"
                        f"Mensagem atual: {mensagem_atual}"
                    )
                }
            ]
        )

        texto_resposta = (
            resposta.choices[0].message.content or ""
        ).strip()

        correspondencia = re.search(
            r"\{.*\}",
            texto_resposta,
            re.DOTALL
        )

        if correspondencia:
            dados = json.loads(correspondencia.group(0))

            acao = str(
                dados.get("acao", "chat")
            ).lower().strip()

            if acao not in ("chat", "image", "video", "web"):
                acao = "chat"

            return {
                "acao": acao,
                "consulta_web": str(
                    dados.get("consulta_web") or mensagem_atual
                ).strip(),
                "prompt_midia": str(
                    dados.get("prompt_midia") or mensagem_atual
                ).strip()
            }

    except Exception as erro:
        print(f"ERRO NO ROTEADOR: {erro}")

    return padrao


# =========================================================
# PLANEJAMENTO VISUAL COM GROQ
# =========================================================

def planejar_cena_com_ia(
    client,
    pedido_usuario,
    tipo_midia,
    historico
):
    eh_escudo = eh_pedido_escudo_ou_emblema(
        pedido_usuario
    )

    fallback = {
        "prompt_visual": (
            f"professional clean football crest emblem inspired by {pedido_usuario}, "
            "symmetrical design, precise geometric lines, "
            "clean edges, vivid traditional colors, "
            "no stone texture, no watermark"
            if eh_escudo
            else
            f"highly realistic professional photograph of {pedido_usuario}, "
            "natural daylight, detailed textures, "
            "sharp focus, realistic colors, "
            "documentary photography, no watermark"
        )
    }

    contexto = formatar_historico_curto(historico)

    try:
        resposta = client.chat.completions.create(
            model="openai/gpt-oss-20b",
            tool_choice="none",
            temperature=0.7,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Você é um diretor de fotografia e designer visual. "
                        "Transforme o pedido em um prompt visual detalhado "
                        "em inglês. Retorne somente JSON válido com a chave "
                        "prompt_visual. Para escudos, use design gráfico "
                        "limpo, simétrico e nítido. Para fotografias, "
                        "use aparência realista e iluminação natural. "
                        "Flamengo no futebol usa vermelho e preto."
                    )
                },
                {
                    "role": "user",
                    "content": (
                        f"Contexto:\n{contexto}\n"
                        f"Tipo: {tipo_midia}\n"
                        f"Pedido: {pedido_usuario}"
                    )
                }
            ]
        )

        conteudo = (
            resposta.choices[0].message.content or ""
        ).strip()

        correspondencia = re.search(
            r"\{.*\}",
            conteudo,
            re.DOTALL
        )

        if correspondencia:
            dados = json.loads(correspondencia.group(0))

            prompt = str(
                dados.get("prompt_visual") or ""
            ).strip()

            if prompt:
                return {
                    "prompt_visual": prompt
                }

    except Exception as erro:
        print(f"ERRO AO PLANEJAR CENA: {erro}")

    return fallback


# =========================================================
# GERAÇÃO DE IMAGENS POLLINATIONS
# =========================================================

def gerar_imagem_bytes(
    info_cena,
    pollinations_key="",
    pedido_original=""
):
    alvo_dims = detectar_dimensoes_pedido(
        pedido_original
    )

    eh_escudo = eh_pedido_escudo_ou_emblema(
        pedido_original
    )

    # Primeiro tenta localizar o escudo solicitado.
    if eh_escudo:
        imagem_real = buscar_escudo_na_web(
            pedido_original,
            alvo_dims
        )

        if imagem_real:
            return imagem_real

    if not pollinations_key:
        print("ERRO: POLLINATIONS_API_KEY não configurada.")
        return None

    if not pollinations_key.startswith("sk_"):
        print(
            "AVISO: a chave não começa com sk_. "
            "Confira se é uma chave secreta válida."
        )

    prompt = info_cena.get(
        "prompt_visual",
        "realistic professional photography"
    )

    if eh_escudo:
        prompt += (
            ", clean football crest, symmetrical graphic design, "
            "precise edges, vivid colors, no watermark"
        )
    else:
        prompt += (
            ", ultra realistic photography, detailed textures, "
            "natural light, sharp focus, realistic colors, "
            "no cartoon, no watermark"
        )

    texto = (pedido_original or "").lower()

    if any(
        p in texto for p in (
            "vertical", "stories", "story",
            "celular", "portrait"
        )
    ):
        largura, altura = 1024, 1536

    elif any(
        p in texto for p in (
            "paisagem", "widescreen", "horizontal",
            "banner", "cinematográfico",
            "cinematografico", "landscape"
        )
    ):
        largura, altura = 1536, 1024

    else:
        largura, altura = 1024, 1024

    headers = {
        "Authorization": f"Bearer {pollinations_key}",
        "User-Agent": "Rener-IA/2.4",
        "Accept": "image/*"
    }

    modelos = [
        "black-forest-labs/flux.1-schnell",
        "tongyi-mai/z-image-turbo"
    ]

    for modelo in modelos:
        try:
            endereco = (
                "https://gen.pollinations.ai/image/"
                + quote_plus(prompt)
            )

            parametros = {
                "model": modelo,
                "width": largura,
                "height": altura,
                "seed": random.randint(100000, 999999999),
                "nologo": "true"
            }

            resposta = requests.get(
                endereco,
                params=parametros,
                headers=headers,
                timeout=(15, 120)
            )

            if resposta.status_code != 200:
                print(
                    f"POLLINATIONS HTTP {resposta.status_code}: "
                    f"{resposta.text[:500]}"
                )
                continue

            if not resposta.content:
                print("POLLINATIONS retornou conteúdo vazio.")
                continue

            try:
                imagem = Image.open(
                    BytesIO(resposta.content)
                )

                imagem.load()

                if imagem.width < 200 or imagem.height < 200:
                    print("Imagem retornada com tamanho inválido.")
                    continue

                buffer = BytesIO()

                imagem.convert("RGB").save(
                    buffer,
                    format="PNG"
                )

                resultado = upscale_4k_profissional(
                    buffer.getvalue(),
                    alvo_dims
                )

                print(
                    f"IMAGEM GERADA COM SUCESSO: {modelo}"
                )

                return resultado

            except Exception as erro:
                print(f"ERRO AO PROCESSAR IMAGEM: {erro}")
                continue

        except requests.exceptions.Timeout:
            print(f"TEMPO ESGOTADO NO MODELO: {modelo}")

        except requests.exceptions.RequestException as erro:
            print(f"ERRO DE CONEXÃO POLLINATIONS: {erro}")

        except Exception as erro:
            print(f"ERRO INESPERADO: {erro}")

    print("TODOS OS MODELOS DE IMAGEM FALHARAM.")

    return None


# =========================================================
# GERAÇÃO DE VÍDEOS CURTOS
# =========================================================

def gerar_video_mp4_bytes(
    info_cena,
    pollinations_key="",
    pedido_original="",
    segundos=4,
    fps=15
):
    imagem_bytes = gerar_imagem_bytes(
        info_cena,
        pollinations_key=pollinations_key,
        pedido_original=pedido_original
    )

    if not imagem_bytes:
        return None

    largura = 720
    altura = 720

    try:
        arte = Image.open(
            BytesIO(imagem_bytes)
        ).convert("RGB")

        arte = arte.resize(
            (largura + 120, altura + 120),
            Image.Resampling.LANCZOS
        )

        total_frames = max(15, segundos * fps)

        with tempfile.NamedTemporaryFile(
            suffix=".mp4",
            delete=False
        ) as tmp:
            caminho = tmp.name

        try:
            writer = imageio.get_writer(
                caminho,
                fps=fps,
                codec="libx264",
                quality=8
            )

            try:
                for i in range(total_frames):
                    progresso = i / max(
                        1,
                        total_frames - 1
                    )

                    dx = int(progresso * 120)

                    dy = int(
                        (1 - abs(2 * progresso - 1)) * 80
                    )

                    frame = arte.crop(
                        (
                            dx,
                            dy,
                            dx + largura,
                            dy + altura
                        )
                    )

                    writer.append_data(
                        np.array(frame)
                    )

            finally:
                writer.close()

            return Path(caminho).read_bytes()

        finally:
            try:
                Path(caminho).unlink(missing_ok=True)
            except Exception:
                pass

    except Exception as erro:
        print(f"ERRO AO CRIAR VÍDEO: {erro}")
        return None


# =========================================================
# PESQUISA NA INTERNET
# =========================================================

def buscar_na_internet(consulta, tavily_key):
    agora = datetime.now()
    ontem = agora - timedelta(days=1)

    query = (consulta or "").strip()

    if "ontem" in query.lower():
        query += f" {ontem.strftime('%d/%m/%Y')}"

    if "hoje" in query.lower():
        query += f" {agora.strftime('%d/%m/%Y')}"

    if tavily_key:
        try:
            resposta = requests.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": tavily_key,
                    "query": query,
                    "max_results": 5,
                    "include_answer": True
                },
                timeout=20
            )

            if resposta.status_code == 200:
                dados = resposta.json()
                blocos = []

                if dados.get("answer"):
                    blocos.append(
                        "[Resumo]\n" + dados["answer"]
                    )

                for i, item in enumerate(
                    dados.get("results", []),
                    start=1
                ):
                    blocos.append(
                        f"[{i}] {item.get('title', '')}\n"
                        f"Resumo: {item.get('content', '')}\n"
                        f"Fonte: {item.get('url', '')}"
                    )

                if blocos:
                    return "\n\n".join(blocos)

        except Exception as erro:
            print(f"ERRO TAVILY: {erro}")

    # Alternativa: Google News RSS
    try:
        url = (
            "https://news.google.com/rss/search?"
            f"q={quote_plus(query)}&hl=pt-BR&gl=BR&ceid=BR:pt-419"
        )

        resposta = requests.get(
            url,
            timeout=15,
            headers=WEB_HEADERS
        )

        if resposta.status_code == 200:
            raiz = ET.fromstring(resposta.text)
            itens = []

            for i, item in enumerate(
                raiz.findall(".//item")[:6],
                start=1
            ):
                titulo = (
                    item.findtext("title") or ""
                ).strip()

                data = (
                    item.findtext("pubDate") or ""
                ).strip()

                link = (
                    item.findtext("link") or ""
                ).strip()

                if titulo:
                    itens.append(
                        f"[Notícia {i}] {titulo} ({data})\n"
                        f"Fonte: {link}"
                    )

            return "\n\n".join(itens)

    except Exception as erro:
        print(f"ERRO GOOGLE NEWS: {erro}")

    return ""


# =========================================================
# ANÁLISE DE PDF
# =========================================================

def extrair_texto_pdf(raw_bytes, max_chars=12000):
    if PdfReader is None:
        return ""

    try:
        leitor = PdfReader(BytesIO(raw_bytes))

        partes = []
        total = 0

        for numero, pagina in enumerate(
            leitor.pages,
            start=1
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

    except Exception as erro:
        print(f"ERRO PDF: {erro}")
        return ""


# =========================================================
# PREPARAÇÃO DE IMAGENS PARA ANÁLISE
# =========================================================

def preparar_imagem_para_visao(raw_bytes, ext):
    mime = IMAGE_MIME_TYPES.get(
        ext.lower(),
        "image/jpeg"
    )

    try:
        img = Image.open(BytesIO(raw_bytes))
        img.load()

        largura, altura = img.size

        maior_lado = max(largura, altura)

        if maior_lado > 1280:
            escala = 1280 / maior_lado

            img = img.resize(
                (
                    int(largura * escala),
                    int(altura * escala)
                ),
                Image.Resampling.LANCZOS
            )

        img = img.convert("RGB")

        buffer = BytesIO()

        img.save(
            buffer,
            format="JPEG",
            quality=85
        )

        return (
            "image/jpeg",
            base64.b64encode(
                buffer.getvalue()
            ).decode("utf-8")
        )

    except Exception as erro:
        print(f"ERRO AO PREPARAR IMAGEM: {erro}")

        return (
            mime,
            base64.b64encode(raw_bytes).decode("utf-8")
        )


# =========================================================
# ROTA DE SAÚDE DO SERVIDOR
# =========================================================

@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "Rener API",
        "version": "2.4.0"
    }


# =========================================================
# ROTA PRINCIPAL DO CHAT
# =========================================================

@app.post("/chat")
def chat_endpoint(req: ChatRequest):
    mensagem = (req.message or "").strip()

    if not mensagem:
        raise HTTPException(
            status_code=400,
            detail="Mensagem vazia."
        )

    client = get_groq_client()

    tavily_key = get_tavily_key()
    pollinations_key = get_pollinations_key()

    is_creator = usuario_eh_criador(
        req.creator_key
    )

    decisao = decidir_acao_com_ia(
        client,
        mensagem,
        req.history
    )

    acao = decisao["acao"]

    # -----------------------------------------------------
    # GERAÇÃO DE IMAGEM
    # -----------------------------------------------------

    if acao == "image":
        permitido, _, limite, _ = (
            verificar_e_consumir_cota_imagem(
                req.user_id,
                req.pro_code,
                req.creator_key,
                consumir=False
            )
        )

        if not permitido:
            return {
                "type": "paywall",
                "reply": (
                    f"Você atingiu o limite diário gratuito "
                    f"de {limite} imagens. "
                    "Ative o Rener Pro para liberar mais gerações."
                )
            }

        pedido = decisao["prompt_midia"]

        info = planejar_cena_com_ia(
            client,
            pedido,
            "imagem",
            req.history
        )

        imagem_bytes = gerar_imagem_bytes(
            info,
            pollinations_key=pollinations_key,
            pedido_original=pedido
        )

        if not imagem_bytes:
            return {
                "type": "text",
                "reply": (
                    "Não consegui gerar sua imagem agora. "
                    "O serviço de imagens não respondeu corretamente. "
                    "Tente novamente mais tarde."
                )
            }

        _, restantes, _, info_cota = (
            verificar_e_consumir_cota_imagem(
                req.user_id,
                req.pro_code,
                req.creator_key,
                consumir=True
            )
        )

        dimensoes = obter_dimensoes_bytes(
            imagem_bytes
        )

        resolucao = rotulo_resolucao(
            dimensoes
        )

        return {
            "type": "image",
            "reply": (
                f"Aqui está ({resolucao} • {info_cota}):"
            ),
            "image_base64": base64.b64encode(
                imagem_bytes
            ).decode("utf-8")
        }

    # -----------------------------------------------------
    # GERAÇÃO DE VÍDEO
    # -----------------------------------------------------

    if acao == "video":
        permitido, _, limite, _ = (
            verificar_e_consumir_cota_imagem(
                req.user_id,
                req.pro_code,
                req.creator_key,
                consumir=False
            )
        )

        if not permitido:
            return {
                "type": "paywall",
                "reply": (
                    f"Você atingiu o limite diário de "
                    f"{limite} criações visuais. "
                    "Ative o Rener Pro para liberar mais gerações."
                )
            }

        pedido = decisao["prompt_midia"]

        info = planejar_cena_com_ia(
            client,
            pedido,
            "vídeo curto",
            req.history
        )

        video_bytes = gerar_video_mp4_bytes(
            info,
            pollinations_key=pollinations_key,
            pedido_original=pedido
        )

        if not video_bytes:
            return {
                "type": "text",
                "reply": (
                    "Não consegui criar o vídeo agora. "
                    "O serviço de imagens falhou."
                )
            }

        verificar_e_consumir_cota_imagem(
            req.user_id,
            req.pro_code,
            req.creator_key,
            consumir=True
        )

        return {
            "type": "video",
            "reply": "Aqui está seu vídeo:",
            "video_base64": base64.b64encode(
                video_bytes
            ).decode("utf-8")
        }

    # -----------------------------------------------------
    # CHAT E PESQUISA
    # -----------------------------------------------------

    mensagens = [
        {
            "role": "system",
            "content": montar_system_prompt(
                req.style,
                is_creator=is_creator
            )
        }
    ]

    for item in req.history:
        if item.role not in ("user", "assistant"):
            continue

        if not (
            item.content
            or item.has_image
            or item.has_video
        ):
            continue

        conteudo = item.content or ""

        if item.has_image:
            conteudo += " [imagem exibida no chat]"

        if item.has_video:
            conteudo += " [vídeo exibido no chat]"

        mensagens.append({
            "role": item.role,
            "content": conteudo
        })

    if acao == "web":
        dados_web = buscar_na_internet(
            decisao["consulta_web"] or mensagem,
            tavily_key
        )

        if dados_web:
            conteudo_user = (
                f"Mensagem do usuário: {mensagem}\n\n"
                "Dados encontrados na internet:\n"
                f"{dados_web}\n\n"
                "Use os dados com cuidado e informe as fontes."
            )

        else:
            conteudo_user = (
                f"Mensagem do usuário: {mensagem}\n\n"
                "A busca na internet não retornou resultados "
                "confiáveis. Não invente informações recentes."
            )

    else:
        conteudo_user = mensagem

    mensagens.append({
        "role": "user",
        "content": conteudo_user
    })

    try:
        resposta = client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=mensagens,
            tool_choice="none"
        )

        texto = (
            resposta.choices[0].message.content or ""
        )

        return {
            "type": "text",
            "reply": texto
        }

    except Exception as erro:
        print(f"ERRO CHAT GROQ: {erro}")

        raise HTTPException(
            status_code=500,
            detail="Erro ao processar resposta do Rener."
        )


# =========================================================
# ROTA DE ANÁLISE DE ARQUIVOS
# =========================================================

@app.post("/analyze")
async def analyze_endpoint(
    file: UploadFile = File(...),
    prompt: str = Form(
        "Analise este arquivo e me dê um resumo claro e útil."
    ),
    style: str = Form("Amigável e direto")
):
    client = get_groq_client()

    raw_bytes = await file.read()

    if not raw_bytes:
        raise HTTPException(
            status_code=400,
            detail="Arquivo vazio."
        )

    if len(raw_bytes) > 8 * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail="Arquivo muito grande. Limite de 8 MB."
        )

    nome = file.filename or "arquivo"
    ext = Path(nome).suffix.lower()
    tipo = (file.content_type or "").lower()

    pergunta = (
        prompt or
        "Analise este arquivo e me dê um resumo claro e útil."
    ).strip()

    eh_imagem = (
        ext in IMAGE_MIME_TYPES
        or tipo.startswith("image/")
    )

    # -----------------------------------------------------
    # ANÁLISE DE IMAGENS
    # -----------------------------------------------------

    if eh_imagem:
        mime, imagem_b64 = preparar_imagem_para_visao(
            raw_bytes,
            ext
        )

        try:
            resposta = client.chat.completions.create(
                model="meta-llama/llama-4-scout-17b-16e-instruct",
                messages=[
                    {
                        "role": "system",
                        "content": montar_system_prompt(style)
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    f"Arquivo: {nome}\n"
                                    f"Pedido: {pergunta}"
                                )
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": (
                                        f"data:{mime};base64,"
                                        f"{imagem_b64}"
                                    )
                                }
                            }
                        ]
                    }
                ]
            )

            texto = (
                resposta.choices[0].message.content
                or "Não consegui analisar a imagem."
            )

            return {
                "type": "text",
                "reply": texto
            }

        except Exception as erro:
            print(f"ERRO NA ANÁLISE DA IMAGEM: {erro}")

            raise HTTPException(
                status_code=500,
                detail="Erro ao analisar imagem."
            )

    # -----------------------------------------------------
    # ANÁLISE DE PDF E DOCUMENTOS
    # -----------------------------------------------------

    texto_extraido = ""

    if ext == ".pdf" or tipo == "application/pdf":
        texto_extraido = extrair_texto_pdf(
            raw_bytes
        )

        if not texto_extraido:
            return {
                "type": "text",
                "reply": (
                    f"Não consegui extrair o texto do PDF '{nome}'. "
                    "Ele pode ser escaneado ou exigir uma ferramenta "
                    "de leitura de imagens."
                )
            }

    elif ext in TEXT_EXTENSIONS or tipo.startswith("text/"):
        texto_extraido = raw_bytes.decode(
            "utf-8",
            errors="replace"
        )[:12000]

    else:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Formato '{ext or tipo}' não suportado. "
                "Envie JPG, PNG, WEBP, PDF ou texto."
            )
        )

    try:
        resposta = client.chat.completions.create(
            model="openai/gpt-oss-20b",
            tool_choice="none",
            messages=[
                {
                    "role": "system",
                    "content": montar_system_prompt(style)
                },
                {
                    "role": "user",
                    "content": (
                        f"Arquivo: {nome}\n"
                        f"Pedido: {pergunta}\n\n"
                        f"Conteúdo extraído:\n{texto_extraido}"
                    )
                }
            ]
        )

        texto = (
            resposta.choices[0].message.content
            or "Não consegui analisar o arquivo."
        )

        return {
            "type": "text",
            "reply": texto
        }

    except Exception as erro:
        print(f"ERRO NA ANÁLISE DO ARQUIVO: {erro}")

        raise HTTPException(
            status_code=500,
            detail="Erro ao analisar arquivo."
        )


# =========================================================
# ROTA DE TRANSCRIÇÃO DE ÁUDIO
# =========================================================

@app.post("/transcribe")
async def transcribe_endpoint(
    file: UploadFile = File(...)
):
    client = get_groq_client()

    audio_bytes = await file.read()

    if not audio_bytes:
        raise HTTPException(
            status_code=400,
            detail="Áudio vazio."
        )

    if len(audio_bytes) > 25 * 1024 * 1024:
        raise HTTPException(
            status_code=400,
            detail="Áudio muito grande."
        )

    nome = file.filename or "ditado.webm"

    ext = (
        Path(nome).suffix.lstrip(".")
        or "webm"
    )

    with tempfile.NamedTemporaryFile(
        suffix=f".{ext}",
        delete=False
    ) as tmp:
        tmp.write(audio_bytes)
        caminho = tmp.name

    try:
        with open(caminho, "rb") as arquivo:
            resposta = client.audio.transcriptions.create(
                file=(
                    f"ditado.{ext}",
                    arquivo.read()
                ),
                model="whisper-large-v3-turbo",
                language="pt",
                response_format="text"
            )

        if isinstance(resposta, str):
            texto = resposta.strip()
        else:
            texto = str(
                getattr(resposta, "text", "") or ""
            ).strip()

        return {
            "text": texto
        }

    except Exception as erro:
        print(f"ERRO NA TRANSCRIÇÃO: {erro}")

        raise HTTPException(
            status_code=500,
            detail="Erro ao transcrever áudio."
        )

    finally:
        try:
            Path(caminho).unlink(missing_ok=True)
        except Exception:
            pass


# =========================================================
# FINAL
# =========================================================

@app.get("/")
def inicio():
    return {
        "service": "Rener API",
        "version": "2.4.0",
        "status": "online",
        "message": "Servidor Rener funcionando."
    }
