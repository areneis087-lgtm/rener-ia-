import base64
from datetime import datetime, timedelta
from io import BytesIO
import json
import os
from pathlib import Path
import random
import re
import tempfile
from urllib.parse import quote, quote_plus
import xml.etree.ElementTree as ET

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from groq import Groq
import imageio.v2 as imageio
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
from pydantic import BaseModel
import requests

try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None

app = FastAPI(title="Rener API", version="2.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TEXT_EXTENSIONS = {
    ".txt", ".md", ".csv", ".json", ".xml", ".yaml", ".yml",
    ".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css", ".sql", ".log",
}

IMAGE_MIME_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}

USO_DIARIO_IMAGENS: dict[str, dict] = {}


class HistoryItem(BaseModel):
    role: str
    content: str = ""
    has_image: bool = False
    has_video: bool = False


class ChatRequest(BaseModel):
    message: str
    history: list[HistoryItem] = []
    style: str = "Amigável e direto"
    user_id: str = "anonimo"
    pro_code: str = ""
    creator_key: str = ""


def get_groq_client() -> Groq:
    api_key = (os.getenv("GROQ_API_KEY") or "").strip().strip('"').strip("'")
    if not api_key:
        raise HTTPException(status_code=500, detail="GROQ_API_KEY não configurada no servidor.")
    return Groq(api_key=api_key)


def get_tavily_key() -> str:
    return (os.getenv("TAVILY_API_KEY") or "").strip().strip('"').strip("'")


def get_pollinations_key() -> str:
    val = (os.getenv("POLLINATIONS_API_KEY") or "").strip().strip('"').strip("'")
    return "" if val == "SUA_CHAVE_POLLINATIONS" else val


def get_limite_gratis_imagens() -> int:
    bruto = (os.getenv("LIMITE_GRATIS_IMAGENS") or "5").strip()
    try:
        return max(1, int(bruto))
    except Exception:
        return 5


def usuario_eh_criador(creator_key: str) -> bool:
    chave_mestra = (os.getenv("RENER_CREATOR_KEY") or "").strip()
    if not chave_mestra:
        return False
    return (creator_key or "").strip() == chave_mestra


def usuario_eh_pro(pro_code: str, creator_key: str = "") -> bool:
    if usuario_eh_criador(creator_key):
        return True
    codigo_servidor = (os.getenv("RENER_PRO_CODE") or "").strip()
    if not codigo_servidor:
        return False
    return (pro_code or "").strip() == codigo_servidor


def verificar_e_consumir_cota_imagem(
    user_id: str, pro_code: str, creator_key: str = ""
) -> tuple[bool, int, int, str]:
    if usuario_eh_criador(creator_key):
        return True, 999999, 999999, "Criador Ilimitado"

    limite = get_limite_gratis_imagens()
    if usuario_eh_pro(pro_code, creator_key):
        return True, 999, 999, "Pro Ilimitado"

    hoje_str = datetime.now().strftime("%Y-%m-%d")
    chave = (user_id or "anonimo").strip()[:80] or "anonimo"
    registro = USO_DIARIO_IMAGENS.get(chave)

    if not registro or registro.get("data") != hoje_str:
        registro = {"data": hoje_str, "usadas": 0}
        USO_DIARIO_IMAGENS[chave] = registro

    if registro["usadas"] >= limite:
        return False, 0, limite, "Limite Atingido"

    registro["usadas"] += 1
    restantes = max(0, limite - registro["usadas"])
    return True, restantes, limite, f"{restantes}/{limite} grátis hoje"


def montar_system_prompt(style: str = "Amigável e direto", is_creator: bool = False) -> str:
    agora_dt = datetime.now()
    regalia_txt = (
        "O usuário atual é o Rener, seu criador. Trate-o com prioridade máxima, respostas diretas e sem restrições de cota. "
        if is_creator
        else ""
    )
    return (
        f"Você se chama Rener. Data de hoje: {agora_dt.strftime('%d/%m/%Y')}. "
        "Seu criador também se chama Rener, e ele montou este aplicativo junto com o Gemini. "
        "Quando perguntarem quem te criou ou sobre a origem do seu nome, responda exatamente: "
        "'Fui criado pelo Rener em parceria com o Gemini — por isso que meu nome é Rener, homenagem ao meu criador.' "
        f"{regalia_txt}"
        "Você gera imagens em alta definição e vídeos curtos quando solicitado no chat. Nunca diga que não consegue gerar imagens quando uma imagem já foi exibida no chat. "
        "Quando o usuário perguntar sobre a resolução ou se a imagem gerada é 4K, responda com base na resolução real informada no histórico ou na mensagem (4K real exige pelo menos 3840 pixels de largura ou 2160 de altura). "
        "Atenção ao contexto: 'Flamengo' em pedidos esportivos, de futebol, time, torcida, escudo ou estádio refere-se ao "
        "Clube de Regatas do Flamengo (cores vermelho e preto, sem azul no escudo oficial), nunca confunda com a ave flamingo "
        "a menos que o usuário peça explicitamente a ave. "
        "Responda sempre em português natural, claro e direto. NUNCA use asteriscos duplos (`**`) ou markdown para negrito. "
        f"Estilo de resposta atual: {style}."
    )


def eh_pedido_escudo_ou_emblema(texto: str) -> bool:
    t = (texto or "").lower()
    return any(p in t for p in ("escudo", "emblema", "brasão", "brasao", "símbolo", "simbolo", "logo"))


def cortar_selo_canto(img: Image.Image) -> Image.Image:
    largura, altura = img.size
    if largura < 200 or altura < 200:
        return img
    return img.crop((0, 0, largura, int(altura * 0.91)))


def refinar_fotografia_pro(img: Image.Image) -> Image.Image:
    base = cortar_selo_canto(img).convert("RGB")
    equilibrada = ImageOps.autocontrast(base, cutoff=0.5)
    nitida = equilibrada.filter(ImageFilter.UnsharpMask(radius=1.6, percent=145, threshold=3))
    contraste = ImageEnhance.Contrast(nitida).enhance(1.08)
    cor = ImageEnhance.Color(contraste).enhance(1.07)
    return ImageEnhance.Sharpness(cor).enhance(1.15)


def detectar_dimensoes_pedido(pedido_usuario: str) -> tuple[int, int]:
    t = (pedido_usuario or "").lower()
    pede_paisagem = any(
        p in t for p in ("paisagem", "widescreen", "horizontal", "banner", "cinematográfico", "cinematografico", "landscape")
    )
    pede_vertical = any(p in t for p in ("vertical", "stories", "story", "celular", "portrait"))
    if pede_vertical:
        return (2160, 3840)
    if pede_paisagem:
        return (3840, 2160)
    return (2160, 2160)


def upscale_4k_profissional(raw_img_bytes: bytes, alvo_dims: tuple[int, int]) -> bytes:
    img = Image.open(BytesIO(raw_img_bytes)).convert("RGB")
    img = refinar_fotografia_pro(img)
    alvo_w, alvo_h = alvo_dims
    if img.size != (alvo_w, alvo_h):
        img = img.resize((alvo_w, alvo_h), Image.Resampling.LANCZOS)
        img = img.filter(ImageFilter.UnsharpMask(radius=1.2, percent=110, threshold=2))
    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def obter_dimensoes_bytes(img_bytes: bytes | None) -> tuple[int, int] | None:
    if not img_bytes:
        return None
    try:
        img = Image.open(BytesIO(img_bytes))
        return img.size
    except Exception:
        return None


def rotulo_resolucao(dims: tuple[int, int] | None) -> str:
    if not dims:
        return "alta definição"
    w, h = dims
    eh_4k = w >= 3840 or h >= 2160
    rotulo = "4K UHD" if eh_4k else "HD"
    return f"{w}x{h} px • {rotulo}"


def formatar_historico_curto(historico: list[HistoryItem], limite: int = 8) -> str:
    trechos = []
    for m in historico[-limite:]:
        papel = "Usuário" if m.role == "user" else "Rener"
        conteudo = (m.content or "").strip()
        anexos = []
        if m.has_image:
            anexos.append("[imagem exibida no chat]")
        if m.has_video:
            anexos.append("[vídeo exibido no chat]")
        texto_final = f"{conteudo} {' '.join(anexos)}".strip()
        if texto_final:
            trechos.append(f"{papel}: {texto_final}")
    return "\n".join(trechos)


def decidir_acao_com_ia(client: Groq, mensagem_atual: str, historico: list[HistoryItem]) -> dict:
    contexto = formatar_historico_curto(historico, limite=6)
    texto_low = (mensagem_atual or "").lower()

    gatilhos_midia = (
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
        "emblema do",
        "mostre o escudo",
        "mostre o emblema",
    )
    if any(p in texto_low for p in gatilhos_midia):
        acao_forçada = "video" if ("vídeo" in texto_low or "video" in texto_low) else "image"
        return {"acao": acao_forçada, "consulta_web": mensagem_atual, "prompt_midia": mensagem_atual}

    padrao = {"acao": "chat", "consulta_web": mensagem_atual, "prompt_midia": mensagem_atual}
    try:
        resp = client.chat.completions.create(
            model="openai/gpt-oss-20b",
            tool_choice="none",
            temperature=0.1,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Você é o roteador inteligente de intenções do assistente Rener. "
                        "Escolha UMA ação: 'image', 'video', 'web' ou 'chat'. "
                        "Use 'web' quando o usuário pedir notícias, placares, resultados, preços, clima, eventos recentes ou informações atuais. "
                        "Use 'image' quando pedir para criar/gerar/desenhar uma imagem, foto ou escudo. "
                        "Use 'video' quando pedir para criar/gerar um vídeo. "
                        "Responda APENAS com JSON válido: "
                        '{"acao": "chat|image|video|web", "consulta_web": "...", "prompt_midia": "..."}'
                    ),
                },
                {"role": "user", "content": f"Contexto:\n{contexto or '(vazio)'}\n\nMensagem atual: {mensagem_atual}"},
            ],
        )
        texto = (resp.choices[0].message.content or "").strip()
        match = re.search(r"\{.*\}", texto, re.DOTALL)
        if match:
            dados = json.loads(match.group(0))
            acao = str(dados.get("acao") or "chat").lower().strip()
            if acao not in {"chat", "image", "video", "web"}:
                acao = "chat"
            return {
                "acao": acao,
                "consulta_web": str(dados.get("consulta_web") or mensagem_atual).strip(),
                "prompt_midia": str(dados.get("prompt_midia") or mensagem_atual).strip(),
            }
    except Exception:
        pass
    return padrao


def planejar_cena_com_ia(client: Groq, pedido_usuario: str, tipo_midia: str, historico: list[HistoryItem]) -> dict:
    eh_escudo = eh_pedido_escudo_ou_emblema(pedido_usuario)
    direcoes_camera = [
        "shot on Sony A7R V, 35mm f/2.8 lens, crisp natural daylight, rich environmental storytelling, ultra-sharp textures",
        "shot on Canon EOS R5, 50mm f/2.0 lens, golden hour directional sunlight, vivid authentic colors, razor-sharp focus",
        "shot on Nikon Z9, 24mm wide editorial angle, dynamic perspective, high dynamic range, lifelike surface detail",
    ]
    assinatura_lente = random.choice(direcoes_camera)
    fallback = {
        "prompt_visual": (
            f"flat clean graphic emblem crest design inspired by {pedido_usuario}, "
            "sharp geometric shapes, bold red and black football palette if Flamengo, clean dark background, no stone texture, no watermark"
            if eh_escudo
            else f"authentic raw documentary photograph of {pedido_usuario}, {assinatura_lente}, "
            "fine individual hair and fabric texture, crisp focus, no soft fog, no haze, no plastic skin, no 3d render look, no watermark"
        )
    }
    contexto_str = formatar_historico_curto(historico)
    try:
        resp = client.chat.completions.create(
            model="openai/gpt-oss-20b",
            tool_choice="none",
            temperature=0.75,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Você é um diretor de fotografia e design visual. Retorne APENAS JSON válido com a chave 'prompt_visual' em inglês. "
                        "Se for escudo ou emblema esportivo, descreva um emblema gráfico nítido, simétrico e bem definido (nunca escultura em pedra/areia suja). "
                        "Se for fotografia, transforme o pedido em uma cena real, viva, criativa e específica com iluminação natural e foco nítido. "
                        "Se o pedido mencionar Flamengo no contexto de futebol/time, use vermelho e preto sem azul, nunca a ave flamingo."
                    ),
                },
                {"role": "user", "content": f"Contexto:\n{contexto_str or '(início)'}\nTipo: {tipo_midia}\nPedido: {pedido_usuario}"},
            ],
        )
        conteudo = (resp.choices[0].message.content or "").strip()
        match = re.search(r"\{.*\}", conteudo, re.DOTALL)
        if match:
            dados = json.loads(match.group(0))
            pv = str(dados.get("prompt_visual") or fallback["prompt_visual"]).strip()
            if eh_escudo:
                return {"prompt_visual": f"{pv}, crisp graphic crest emblem, clean contrast, no stone carving, no watermark"}
            return {"prompt_visual": f"{pv}, {assinatura_lente}"}
    except Exception:
        pass
    return fallback


def gerar_imagem_bytes(info_cena: dict, pollinations_key: str = "", pedido_original: str = "") -> bytes | None:
    alvo_dims = detectar_dimensoes_pedido(pedido_original)
    eh_escudo = eh_pedido_escudo_ou_emblema(pedido_original)
    prompt_visual = info_cena.get("prompt_visual", "authentic raw DSLR photograph, natural daylight, razor sharp focus")
    prompt_limpo = (
        f"{prompt_visual}, sharp graphic crest emblem, clean edges, vivid colors, no watermark"
        if eh_escudo
        else f"{prompt_visual}, 8k raw photography, crisp focus across entire subject, natural contrast, realistic textures, no blurry haze, no fog, no cartoon, no watermark"
    )

    seed = random.randint(100000, 999999999)
    param_chave = f"&key={quote(pollinations_key)}" if pollinations_key else ""
    headers = {"User-Agent": "Mozilla/5.0"}
    if pollinations_key:
        headers["Authorization"] = f"Bearer {pollinations_key}"

    t_low = (pedido_original or "").lower()
    if any(p in t_low for p in ("vertical", "stories", "story", "celular", "portrait")):
        gen_w, gen_h = 1024, 1536
    elif any(p in t_low for p in ("paisagem", "widescreen", "horizontal", "banner", "cinematográfico", "cinematografico", "landscape")):
        gen_w, gen_h = 1536, 1024
    else:
        gen_w, gen_h = 1280, 1280

    tentativas = [
        (
            f"https://image.pollinations.ai/prompt/{quote(prompt_limpo)}"
            f"?width={gen_w}&height={gen_h}&seed={seed}&model=flux&nologo=true{param_chave}",
            35,
        ),
        (
            f"https://image.pollinations.ai/prompt/{quote(prompt_limpo)}"
            f"?width=1024&height=1024&seed={seed + 1}&model=flux&nologo=true{param_chave}",
            28,
        ),
        (
            f"https://image.pollinations.ai/prompt/{quote(prompt_limpo)}"
            f"?width=1024&height=1024&seed={seed + 2}&model=turbo&nologo=true{param_chave}",
            22,
        ),
    ]

    for url, timeout_seg in tentativas:
        try:
            resp = requests.get(url, timeout=timeout_seg, headers=headers)
            if resp.status_code == 200 and resp.content:
                img = Image.open(BytesIO(resp.content)).convert("RGB")
                if img.size[0] >= 200 and img.size[1] >= 200:
                    buf = BytesIO()
                    img.save(buf, format="PNG")
                    return upscale_4k_profissional(buf.getvalue(), alvo_dims)
        except Exception:
            continue

    return None


def gerar_video_mp4_bytes(info_cena: dict, pollinations_key: str = "", pedido_original: str = "", segundos: int = 4, fps: int = 15) -> bytes | None:
    img_bytes = gerar_imagem_bytes(info_cena, pollinations_key=pollinations_key, pedido_original=pedido_original)
    if not img_bytes:
        return None

    largura, altura = 720, 720
    arte_base = Image.open(BytesIO(img_bytes)).convert("RGB").resize((largura + 120, altura + 120), Image.Resampling.LANCZOS)
    total_frames = max(15, segundos * fps)

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        caminho_mp4 = tmp.name

    try:
        writer = imageio.get_writer(caminho_mp4, fps=fps, codec="libx264", quality=8)
        try:
            for i in range(total_frames):
                progresso = i / max(1, total_frames - 1)
                dx = int(progresso * 120)
                dy = int((1 - abs(2 * progresso - 1)) * 80)
                frame = arte_base.crop((dx, dy, dx + largura, dy + altura)).convert("RGB")
                writer.append_data(np.array(frame))
        finally:
            writer.close()
        return Path(caminho_mp4).read_bytes()
    except Exception:
        return None
    finally:
        try:
            Path(caminho_mp4).unlink(missing_ok=True)
        except Exception:
            pass


def buscar_na_internet(consulta: str, tavily_key: str) -> str:
    agora = datetime.now()
    ontem = agora - timedelta(days=1)
    query_data = consulta.strip()
    if "ontem" in query_data.lower():
        query_data = f"{query_data} {ontem.strftime('%d/%m/%Y')}"
    if "hoje" in query_data.lower():
        query_data = f"{query_data} {agora.strftime('%d/%m/%Y')}"

    if tavily_key:
        try:
            resp = requests.post(
                "https://api.tavily.com/search",
                json={"api_key": tavily_key, "query": query_data, "max_results": 5, "include_answer": True},
                timeout=15,
            )
            if resp.status_code == 200:
                dados = resp.json()
                blocos = []
                if (dados.get("answer") or "").strip():
                    blocos.append(f"[Resumo]\n{dados['answer'].strip()}")
                for idx, item in enumerate(dados.get("results", []), start=1):
                    blocos.append(
                        f"[{idx}] {item.get('title', '').strip()}\n"
                        f"Resumo: {item.get('content', '').strip()}\n"
                        f"Fonte: {item.get('url', '').strip()}"
                    )
                if blocos:
                    return "\n\n".join(blocos)
        except Exception:
            pass

    try:
        url = f"https://news.google.com/rss/search?q={quote_plus(query_data)}&hl=pt-BR&gl=BR&ceid=BR:pt-419"
        resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code == 200 and resp.text:
            root = ET.fromstring(resp.text)
            itens = []
            for idx, item in enumerate(root.findall(".//item")[:6], start=1):
                titulo = (item.findtext("title") or "").strip()
                pub = (item.findtext("pubDate") or "").strip()
                link = (item.findtext("link") or "").strip()
                if titulo:
                    itens.append(f"[Notícia {idx}] {titulo} ({pub})\nFonte: {link}")
            return "\n\n".join(itens)
    except Exception:
        pass
    return ""


def extrair_texto_pdf(raw_bytes: bytes, max_chars: int = 12000) -> str:
    if PdfReader is None:
        return ""
    try:
        reader = PdfReader(BytesIO(raw_bytes))
        partes = []
        total = 0
        for num, pagina in enumerate(reader.pages, start=1):
            txt = (pagina.extract_text() or "").strip()
            if txt:
                bloco = f"--- Página {num} ---\n{txt}"
                partes.append(bloco)
                total += len(bloco)
                if total >= max_chars:
                    break
        return "\n\n".join(partes)[:max_chars]
    except Exception:
        return ""


def preparar_imagem_para_visao(raw_bytes: bytes, ext: str) -> tuple[str, str]:
    mime = IMAGE_MIME_TYPES.get(ext.lower())
    try:
        img = Image.open(BytesIO(raw_bytes))
        img.load()
        largura, altura = img.size
        maior_lado = max(largura, altura)
        if maior_lado > 1280:
            escala = 1280 / maior_lado
            img = img.resize((int(largura * escala), int(altura * escala)), Image.Resampling.LANCZOS)
        if img.mode not in ("RGB",):
            img = img.convert("RGB")
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return "image/jpeg", base64.b64encode(buf.getvalue()).decode("utf-8")
    except Exception:
        if not mime:
            mime = "image/jpeg"
        return mime, base64.b64encode(raw_bytes).decode("utf-8")


@app.get("/health")
def health():
    return {"status": "ok", "service": "Rener API", "version": "2.2.0"}


@app.post("/chat")
def chat_endpoint(req: ChatRequest):
    mensagem = (req.message or "").strip()
    if not mensagem:
        raise HTTPException(status_code=400, detail="Mensagem vazia.")

    client = get_groq_client()
    tavily_key = get_tavily_key()
    pollinations_key = get_pollinations_key()
    is_creator = usuario_eh_criador(req.creator_key)

    decisao = decidir_acao_com_ia(client, mensagem, req.history)
    acao = decisao["acao"]

    if acao == "image":
        permitido, _, limite, info_cota = verificar_e_consumir_cota_imagem(
            req.user_id, req.pro_code, req.creator_key
        )
        if not permitido:
            return {
                "type": "paywall",
                "reply": (
                    f"Você atingiu o limite diário gratuito de {limite} imagens em 4K. "
                    "Ative o Rener Pro tocando no badge superior para gerar imagens ilimitadas."
                ),
            }

        pedido = decisao["prompt_midia"]
        info = planejar_cena_com_ia(client, pedido, "imagem", req.history)
        img_bytes = gerar_imagem_bytes(info, pollinations_key=pollinations_key, pedido_original=pedido)
        if not img_bytes:
            return {"type": "text", "reply": "O serviço de imagens falhou agora. Tenta novamente daqui a pouco."}
        dims = obter_dimensoes_bytes(img_bytes)
        res_txt = rotulo_resolucao(dims)
        return {
            "type": "image",
            "reply": f"Aqui está ({res_txt} • {info_cota}):",
            "image_base64": base64.b64encode(img_bytes).decode("utf-8"),
        }

    if acao == "video":
        permitido, _, limite, _ = verificar_e_consumir_cota_imagem(
            req.user_id, req.pro_code, req.creator_key
        )
        if not permitido:
            return {
                "type": "paywall",
                "reply": (
                    f"Você atingiu o limite diário gratuito de {limite} criações visuais. "
                    "Ative o Rener Pro tocando no badge superior para liberar gerações ilimitadas."
                ),
            }

        pedido = decisao["prompt_midia"]
        info = planejar_cena_com_ia(client, pedido, "vídeo curto", req.history)
        vid_bytes = gerar_video_mp4_bytes(info, pollinations_key=pollinations_key, pedido_original=pedido)
        if not vid_bytes:
            return {"type": "text", "reply": "O serviço de vídeo falhou agora. Tenta novamente daqui a pouco."}
        return {
            "type": "video",
            "reply": "Aqui está:",
            "video_base64": base64.b64encode(vid_bytes).decode("utf-8"),
        }

    system_prompt = {"role": "system", "content": montar_system_prompt(req.style, is_creator=is_creator)}

    mensagens = [system_prompt] + [
        {
            "role": m.role,
            "content": (
                f"{m.content} "
                f"{'[imagem exibida no chat]' if m.has_image else ''} "
                f"{'[vídeo exibido no chat]' if m.has_video else ''}"
            ).strip(),
        }
        for m in req.history
        if m.content or m.has_image or m.has_video
    ]

    if acao == "web":
        dados_web = buscar_na_internet(decisao["consulta_web"] or mensagem, tavily_key)
        if dados_web:
            conteudo_user = (
                f"Mensagem do usuário: {mensagem}\n\n"
                f"Dados obtidos na busca na internet (use apenas fatos compatíveis com estes resultados e cite fontes quando houver):\n{dados_web}"
            )
        else:
            conteudo_user = (
                f"Mensagem do usuário: {mensagem}\n\n"
                "Observação: a busca automática na internet não retornou resultados confiáveis agora. "
                "Não invente placares, notícias ou dados recentes; diga claramente o que não foi possível confirmar."
            )
    else:
        conteudo_user = mensagem

    mensagens.append({"role": "user", "content": conteudo_user})

    try:
        completion = client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=mensagens,
            tool_choice="none",
        )
        reply = completion.choices[0].message.content or ""
        return {"type": "text", "reply": reply}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erro ao processar resposta: {exc}") from exc


@app.post("/analyze")
async def analyze_endpoint(
    file: UploadFile = File(...),
    prompt: str = Form("Analise este arquivo e me dê um resumo claro e útil."),
    style: str = Form("Amigável e direto"),
):
    client = get_groq_client()
    raw_bytes = await file.read()
    if not raw_bytes:
        raise HTTPException(status_code=400, detail="Arquivo vazio.")

    if len(raw_bytes) > 8 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Arquivo muito grande (limite de 8 MB).")

    nome_arq = file.filename or "arquivo"
    ext = Path(nome_arq).suffix.lower()
    ctype = (file.content_type or "").lower()
    pergunta = (prompt or "").strip() or "Analise este arquivo e me dê um resumo claro e útil."

    eh_imagem = ext in IMAGE_MIME_TYPES or ctype.startswith("image/")
    if eh_imagem:
        mime, b64_img = preparar_imagem_para_visao(raw_bytes, ext)
        try:
            completion = client.chat.completions.create(
                model="meta-llama/llama-4-scout-17b-16e-instruct",
                messages=[
                    {"role": "system", "content": montar_system_prompt(style)},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": f"Arquivo: {nome_arq}\nPedido: {pergunta}"},
                            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64_img}"}},
                        ],
                    },
                ],
            )
            reply = completion.choices[0].message.content or "Não consegui analisar a imagem."
            return {"type": "text", "reply": reply}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Erro ao analisar imagem: {exc}") from exc

    texto_extraido = ""
    if ext == ".pdf" or ctype == "application/pdf":
        texto_extraido = extrair_texto_pdf(raw_bytes)
        if not texto_extraido:
            return {
                "type": "text",
                "reply": (
                    f"Não consegui extrair texto do PDF '{nome_arq}' (ele pode ser escaneado/imagem ou exigir `pypdf` instalado no servidor). "
                    "Se quiser, envie um print da página como imagem para eu ler visualmente."
                ),
            }
    elif ext in TEXT_EXTENSIONS or ctype.startswith("text/"):
        texto_extraido = raw_bytes.decode("utf-8", errors="replace")[:12000]
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Formato '{ext or ctype}' ainda não suportado. Envie imagem (JPG, PNG, WEBP), PDF ou arquivo de texto.",
        )

    try:
        completion = client.chat.completions.create(
            model="openai/gpt-oss-20b",
            tool_choice="none",
            messages=[
                {"role": "system", "content": montar_system_prompt(style)},
                {
                    "role": "user",
                    "content": (
                        f"Arquivo anexado: {nome_arq}\n"
                        f"Pedido do usuário: {pergunta}\n\n"
                        f"Conteúdo extraído:\n{texto_extraido}"
                    ),
                },
            ],
        )
        reply = completion.choices[0].message.content or "Não consegui analisar o arquivo."
        return {"type": "text", "reply": reply}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erro ao analisar arquivo: {exc}") from exc


@app.post("/transcribe")
async def transcribe_endpoint(file: UploadFile = File(...)):
    client = get_groq_client()
    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Áudio vazio.")

    nome_arq = file.filename or "ditado.webm"
    ext = Path(nome_arq).suffix.lstrip(".") or "webm"
    with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
        tmp.write(audio_bytes)
        caminho = tmp.name

    try:
        with open(caminho, "rb") as f_audio:
            transcricao = client.audio.transcriptions.create(
                file=(f"ditado.{ext}", f_audio.read()),
                model="whisper-large-v3-turbo",
                language="pt",
                response_format="text",
            )
        texto = transcricao.strip() if isinstance(transcricao, str) else str(getattr(transcricao, "text", "") or "").strip()
        return {"text": texto}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erro na transcrição: {exc}") from exc
    finally:
        try:
            Path(caminho).unlink(missing_ok=True)
        except Exception:
            pass
