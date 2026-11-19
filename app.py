import base64
from datetime import datetime, timedelta
from io import BytesIO
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any
from urllib.parse import quote, quote_plus
import xml.etree.ElementTree as ET

from ddgs import DDGS
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from groq import Groq
import imageio.v2 as imageio
import numpy as np
from PIL import Image
from pydantic import BaseModel
import requests
from tavily import TavilyClient


app = FastAPI(title="Rener API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def obter_chaves() -> dict[str, str]:
    return {
        "GROQ_API_KEY": os.getenv("GROQ_API_KEY", "").strip(),
        "TAVILY_API_KEY": os.getenv("TAVILY_API_KEY", "").strip(),
        "POLLINATIONS_API_KEY": os.getenv("POLLINATIONS_API_KEY", "").strip(),
    }


def obter_groq_client() -> Groq:
    chaves = obter_chaves()
    if not chaves["GROQ_API_KEY"]:
        raise HTTPException(status_code=500, detail="GROQ_API_KEY não configurada no ambiente.")
    return Groq(api_key=chaves["GROQ_API_KEY"])


def montar_system_prompt(estilo: str = "Amigável e direto") -> dict[str, str]:
    agora_dt = datetime.now()
    data_atual = agora_dt.strftime("%d/%m/%Y")
    ontem_data = (agora_dt - timedelta(days=1)).strftime("%d/%m/%Y")
    return {
        "role": "system",
        "content": (
            f"Você se chama Rener. Data de hoje: {data_atual}; data de ontem: {ontem_data}. "
            "Seu criador também se chama Rener, e ele montou este aplicativo junto com o Gemini. "
            "Quando perguntarem quem te criou ou sobre a origem do seu nome, responda exatamente: "
            "'Fui criado pelo Rener em parceria com o Gemini — por isso que meu nome é Rener, homenagem ao meu criador.' "
            "Você tem funções integradas no aplicativo para gerar imagens, buscar imagens reais, gerar vídeos "
            "curtos em MP4 e pesquisar na internet. Quando uma mensagem anterior do histórico contiver "
            "[imagem exibida no chat] ou [vídeo exibido no chat] e o usuário perguntar sobre essa mídia, "
            "responda diretamente sobre a mídia já exibida (por exemplo, informando se ela foi gerada por IA ou "
            "buscada na web) e NUNCA diga que o serviço falhou quando a mídia já foi entregue na conversa. "
            "Se uma nova geração de imagem, vídeo ou busca na web realmente falhar no momento atual, explique que "
            "o serviço externo falhou, bloqueou ou demorou a responder temporariamente. "
            "Você entende perfeitamente qualquer assunto e qualquer pedido do usuário, conectando sempre o que está "
            "sendo dito agora ao histórico da conversa. "
            "Converse com naturalidade, autonomia e espontaneidade, como uma pessoa real que está batendo papo com o Rener. "
            "Quando o usuário te elogiar ou pedir para agradecer elogios, agradeça de forma simpática e direta na própria conversa. "
            "Quando o usuário pedir para buscar ou confirmar um resultado, fato recente ou notícia na internet, use os dados "
            "da pesquisa com exatidão sem inventar informações que não estejam nas fontes. "
            "Nunca chame ferramentas internas como browser.search; responda sempre em texto direto. "
            f"Estilo de resposta atual: {estilo}."
        ),
    }


def eh_pedido_escudo_ou_emblema(texto: str) -> bool:
    t = (texto or "").lower()
    return any(p in t for p in ("escudo", "emblema", "brasão", "brasao", "símbolo", "simbolo", "logo"))


def eh_pedido_imagem_real(texto: str) -> bool:
    t = (texto or "").lower()
    return any(
        p in t
        for p in (
            "imagem real",
            "foto real",
            "fotografia real",
            "de verdade",
            "foto de verdade",
            "imagem de verdade",
            "real mesmo",
        )
    )


def buscar_imagem_real_na_web(consulta: str, max_tentativas: int = 8) -> bytes | None:
    termo = consulta.strip()
    if not termo:
        return None

    queries = [
        f"{termo} foto real",
        f"{termo} png transparente",
        f"{termo} oficial",
        termo,
    ]
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Linux; Android 13; Mobile) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
        ),
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    }

    for q in queries:
        try:
            with DDGS() as ddgs:
                resultados = list(ddgs.images(q, region="br-pt", safesearch="moderate", max_results=max_tentativas))
        except Exception:
            resultados = []

        for item in resultados:
            url_img = str(item.get("image") or item.get("thumbnail") or "").strip()
            if not url_img.startswith(("http://", "https://")):
                continue
            try:
                resp = requests.get(url_img, timeout=12, headers=headers, allow_redirects=True)
                content_type = (resp.headers.get("Content-Type") or "").lower()
                if resp.status_code != 200 or not resp.content:
                    continue
                if "html" in content_type or "text" in content_type:
                    continue

                img = Image.open(BytesIO(resp.content))
                img.load()
                largura, altura = img.size
                if largura < 120 or altura < 120:
                    continue

                if img.mode in ("RGBA", "LA") or "transparency" in img.info:
                    rgba = img.convert("RGBA")
                    fundo_escuro = Image.new("RGBA", rgba.size, (12, 16, 28, 255))
                    combinada = Image.alpha_composite(fundo_escuro, rgba).convert("RGB")
                else:
                    combinada = img.convert("RGB")

                buf = BytesIO()
                combinada.save(buf, format="PNG")
                return buf.getvalue()
            except Exception:
                continue

    return None


def cortar_selo_canto(img: Image.Image) -> Image.Image:
    largura, altura = img.size
    if largura < 200 or altura < 200:
        return img
    return img.crop((0, 0, largura, int(altura * 0.91)))


def detectar_dimensoes_pedido(pedido_usuario: str) -> tuple[int, int]:
    t = pedido_usuario.lower()
    pede_paisagem = any(
        p in t for p in ("paisagem", "widescreen", "horizontal", "banner", "cinematográfico", "cinematografico", "landscape")
    )
    pede_vertical = any(p in t for p in ("vertical", "stories", "story", "celular", "portrait"))

    if pede_vertical:
        return (768, 1280)
    if pede_paisagem:
        return (1280, 720)
    return (1024, 1024)


def formatar_historico_curto(mensagens: list[dict[str, Any]], limite: int = 8) -> str:
    trechos = []
    for m in mensagens[-limite:]:
        papel = "Usuário" if m.get("role") == "user" else "Rener"
        conteudo = str(m.get("content") or "").strip()
        anexos = []
        if m.get("has_image"):
            anexos.append("[imagem exibida no chat]")
        if m.get("has_video"):
            anexos.append("[vídeo exibido no chat]")
        texto_final = f"{conteudo} {' '.join(anexos)}".strip()
        if texto_final:
            trechos.append(f"{papel}: {texto_final}")
    return "\n".join(trechos)


def decidir_acao_com_ia(client: Groq, mensagem_atual: str, historico: list[dict[str, Any]]) -> dict[str, str]:
    contexto = formatar_historico_curto(historico, limite=6)
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
                        "Analise a mensagem atual e o contexto recente da conversa e escolha UMA ação:\n"
                        "- 'image': o usuário quer ver, criar ou gerar uma imagem, foto real, escudo, brasão, emblema ou logo "
                        "(incluindo pedidos que continuam um pedido visual anterior, como 'em 4k', 'de frente', 'imagem real').\n"
                        "- 'video': o usuário quer ver, criar ou gerar um vídeo, animação ou clipe curto.\n"
                        "- 'web': a resposta exige fato recente, notícia, placar, resultado, cotação, clima, "
                        "estreia ou informação atual da internet.\n"
                        "- 'chat': conversa geral, explicação, dúvida, opinião, programação, estudo ou papo do dia a dia "
                        "(incluindo perguntas sobre uma imagem ou resposta já exibida no chat).\n"
                        "Preencha 'consulta_web' com uma busca clara quando for 'web', e 'prompt_midia' com o pedido "
                        "visual completo (combinando o contexto se houver referência implícita) quando for 'image' ou 'video'.\n"
                        "Responda APENAS com JSON válido no formato:\n"
                        '{"acao": "chat|image|video|web", "consulta_web": "...", "prompt_midia": "..."}'
                    ),
                },
                {
                    "role": "user",
                    "content": f"Contexto:\n{contexto or '(vazio)'}\n\nMensagem atual: {mensagem_atual}",
                },
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


def planejar_cena_com_ia(
    client: Groq,
    pedido_usuario: str,
    tipo_midia: str,
    historico_mensagens: list[dict[str, Any]] | None = None,
) -> dict[str, str]:
    eh_escudo = eh_pedido_escudo_ou_emblema(pedido_usuario)
    if eh_escudo:
        fallback = {
            "prompt_visual": (
                f"clean flat vector football crest emblem inspired by {pedido_usuario}, "
                "sharp crisp geometric shapes, centered on clean dark background, "
                "no distorted faces, no extra text, no watermark"
            ),
        }
    else:
        fallback = {
            "prompt_visual": (
                f"candid real-life photograph of {pedido_usuario}, shot on professional camera, "
                "natural lighting, sharp focus, authentic real-world textures, true-to-life details, "
                "no cartoon, no illustration, no 3d render, no text, no watermark"
            ),
        }

    contexto_str = formatar_historico_curto(historico_mensagens or [])
    try:
        resp = client.chat.completions.create(
            model="openai/gpt-oss-20b",
            tool_choice="none",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Você é o diretor visual inteligente do Rener. Sua função é compreender perfeitamente o "
                        "que o usuário pediu em qualquer assunto e associar ao contexto recente da conversa.\n"
                        "Regras:\n"
                        "1. Foque exatamente no assunto pedido pelo usuário, sem trocar o tema.\n"
                        "2. Se o pedido envolver escudo, brasão, emblema ou logo, descreva um emblema gráfico "
                        "limpo, simétrico, nítido e centralizado em fundo simples.\n"
                        "3. Para cenas, animais, pessoas, veículos ou lugares reais, priorize fotografia realista "
                        "com iluminação natural, foco nítido e texturas autênticas.\n"
                        "4. Nunca inclua palavras soltas aleatórias ou marcas d'água.\n"
                        "Retorne APENAS um JSON válido com a chave:\n"
                        "prompt_visual (descrição detalhada em inglês)."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Contexto recente:\n{contexto_str or '(início da conversa)'}\n\n"
                        f"Tipo de mídia: {tipo_midia}\n"
                        f"Pedido do usuário: {pedido_usuario}"
                    ),
                },
            ],
        )
        conteudo = (resp.choices[0].message.content or "").strip()
        match = re.search(r"\{.*\}", conteudo, re.DOTALL)
        if match:
            dados = json.loads(match.group(0))
            pv = str(dados.get("prompt_visual") or fallback["prompt_visual"]).strip()
            return {"prompt_visual": pv}
    except Exception:
        pass
    return fallback


def gerar_imagem_alta_qualidade(
    info_cena: dict[str, str],
    pollinations_key: str = "",
    pedido_original: str = "",
) -> bytes | None:
    if eh_pedido_escudo_ou_emblema(pedido_original) or eh_pedido_imagem_real(pedido_original):
        imagem_real = buscar_imagem_real_na_web(pedido_original)
        if imagem_real:
            return imagem_real

    largura, altura = detectar_dimensoes_pedido(pedido_original)
    prompt_visual = info_cena.get("prompt_visual", "realistic photograph, sharp focus, high detail")
    if eh_pedido_escudo_ou_emblema(pedido_original):
        prompt_limpo = f"{prompt_visual}, crisp edges, clean emblem design, no watermark, no logo text"
    else:
        prompt_limpo = (
            f"{prompt_visual}, sharp focus, high clarity, natural lighting, "
            "no cartoon, no blur, no text, no watermark, no logo"
        )

    param_chave = f"&key={quote(pollinations_key)}" if pollinations_key else ""
    headers = {"User-Agent": "Mozilla/5.0"}
    if pollinations_key:
        headers["Authorization"] = f"Bearer {pollinations_key}"

    tentativas_url = [
        (
            f"https://image.pollinations.ai/prompt/{quote(prompt_limpo)}"
            f"?width={largura}&height={altura}&model=flux&nologo=true&enhance=true{param_chave}",
            30,
        ),
        (
            f"https://image.pollinations.ai/prompt/{quote(prompt_limpo)}"
            f"?width=1024&height=1024&nologo=true{param_chave}",
            25,
        ),
    ]

    for url, timeout_seg in tentativas_url:
        try:
            resp = requests.get(url, timeout=timeout_seg, headers=headers)
            if resp.status_code == 200 and resp.content:
                img = Image.open(BytesIO(resp.content)).convert("RGB")
                if img.size[0] >= 120 and img.size[1] >= 120:
                    img = cortar_selo_canto(img)
                    buf = BytesIO()
                    img.save(buf, format="PNG")
                    return buf.getvalue()
        except Exception:
            continue

    return None


def gerar_video_curto_rener(
    info_cena: dict[str, str],
    pollinations_key: str = "",
    pedido_original: str = "",
    segundos: int = 4,
    fps: int = 15,
) -> bytes | None:
    img_bytes = gerar_imagem_alta_qualidade(
        info_cena,
        pollinations_key=pollinations_key,
        pedido_original=pedido_original,
    )
    if not img_bytes:
        return None

    largura, altura = 720, 720
    arte_base = Image.open(BytesIO(img_bytes)).convert("RGB").resize(
        (largura + 120, altura + 120), Image.Resampling.LANCZOS
    )
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


def eh_consulta_esportiva_ou_tempo_real(consulta: str) -> bool:
    gatilhos = ("jogo", "placar", "resultado", "gol", "gols", "ontem", "hoje", "ao vivo", "partida", "notícia", "noticia")
    return any(p in consulta.lower() for p in gatilhos)


def montar_query_com_datas(consulta: str) -> str:
    agora = datetime.now()
    ontem = agora - timedelta(days=1)
    hoje_str = agora.strftime("%d/%m/%Y")
    ontem_str = ontem.strftime("%d/%m/%Y")

    texto = consulta.strip()
    texto_ajustado = texto
    if "ontem" in texto.lower():
        texto_ajustado = f"{texto_ajustado} {ontem_str}"
    if "hoje" in texto.lower():
        texto_ajustado = f"{texto_ajustado} {hoje_str}"

    if eh_consulta_esportiva_ou_tempo_real(texto):
        return f"{texto_ajustado} placar resultado gols"
    return texto_ajustado


def buscar_com_tavily(consulta: str, tavily_key: str) -> str:
    if not tavily_key:
        return ""
    try:
        tavily = TavilyClient(api_key=tavily_key)
        tempo_real = eh_consulta_esportiva_ou_tempo_real(consulta)
        categoria = "news" if tempo_real else "general"
        profundidade = "advanced" if tempo_real else "basic"
        query_busca = montar_query_com_datas(consulta)

        kwargs_busca: dict[str, Any] = {
            "query": query_busca,
            "topic": categoria,
            "search_depth": profundidade,
            "max_results": 5,
            "include_answer": True,
            "include_raw_content": tempo_real,
        }
        if categoria == "news":
            kwargs_busca["days"] = 3

        resposta = tavily.search(**kwargs_busca)

        blocos = []
        resumo_direto = (resposta.get("answer") or "").strip()
        if resumo_direto:
            blocos.append(f"[Resumo direto da pesquisa]\n{resumo_direto}")

        for idx, item in enumerate(resposta.get("results", []), start=1):
            titulo = (item.get("title") or "").strip()
            conteudo = (item.get("content") or "").strip()
            raw = (item.get("raw_content") or "").strip()
            texto_extra = raw[:1400] if raw else conteudo
            url = (item.get("url") or "").strip()
            data_pub = (item.get("published_date") or "").strip()
            cabecalho = f"[{idx}] {titulo}"
            if data_pub:
                cabecalho += f" ({data_pub})"
            blocos.append(f"{cabecalho}\nResumo: {conteudo}\nDetalhes: {texto_extra}\nFonte: {url}")

        return "\n\n".join(blocos)
    except Exception:
        return ""


def buscar_google_noticias_rss(consulta: str, max_itens: int = 6) -> list[str]:
    itens = []
    try:
        url = f"https://news.google.com/rss/search?q={quote_plus(consulta)}&hl=pt-BR&gl=BR&ceid=BR:pt-419"
        resp = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code == 200 and resp.text:
            root = ET.fromstring(resp.text)
            for idx, item in enumerate(root.findall(".//item")[:max_itens], start=1):
                titulo = (item.findtext("title") or "").strip()
                pub_date = (item.findtext("pubDate") or "").strip()
                link = (item.findtext("link") or "").strip()
                if titulo:
                    linha = f"[Notícia {idx}] {titulo}"
                    if pub_date:
                        linha += f" | Data: {pub_date}"
                    if link:
                        linha += f"\nFonte: {link}"
                    itens.append(linha)
    except Exception:
        pass
    return itens


def buscar_ddgs(consulta: str, max_resultados: int = 4) -> list[str]:
    itens = []
    try:
        with DDGS() as ddgs:
            resultados = list(ddgs.text(consulta, region="br-pt", max_results=max_resultados))
            for idx, r in enumerate(resultados, start=1):
                titulo = r.get("title", "").strip()
                trecho = r.get("body", "").strip()
                link = r.get("href", "").strip()
                if titulo or trecho:
                    itens.append(f"[Web {idx}] {titulo}\nResumo: {trecho}\nFonte: {link}")
    except Exception:
        pass
    return itens


def pesquisar_na_internet(consulta: str, tavily_key: str) -> str:
    resultado_tavily = buscar_com_tavily(consulta, tavily_key)
    if resultado_tavily:
        return resultado_tavily

    coletados = []
    coletados.extend(buscar_google_noticias_rss(montar_query_com_datas(consulta), max_itens=5))
    coletados.extend(buscar_ddgs(montar_query_com_datas(consulta), max_resultados=4))
    return "\n\n".join(coletados[:8]) if coletados else ""


class MensagemItem(BaseModel):
    role: str
    content: str = ""
    has_image: bool = False
    has_video: bool = False


class ChatRequest(BaseModel):
    message: str
    history: list[MensagemItem] = []
    style: str = "Amigável e direto"


class MediaRequest(BaseModel):
    prompt: str
    history: list[MensagemItem] = []
    seconds: int = 4


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "assistant": "Rener"}


@app.post("/chat")
def chat_endpoint(req: ChatRequest) -> dict[str, Any]:
    prompt_texto = (req.message or "").strip()
    if not prompt_texto:
        raise HTTPException(status_code=400, detail="Mensagem vazia.")

    client = obter_groq_client()
    chaves = obter_chaves()
    historico_dict = [m.model_dump() for m in req.history]
    decisao = decidir_acao_com_ia(client, prompt_texto, historico_dict)
    acao = decisao["acao"]

    if acao == "image":
        pedido_midia = decisao["prompt_midia"]
        info = planejar_cena_com_ia(client, pedido_midia, "imagem", historico_dict)
        img_bytes = gerar_imagem_alta_qualidade(
            info,
            pollinations_key=chaves["POLLINATIONS_API_KEY"],
            pedido_original=pedido_midia,
        )
        if img_bytes:
            return {
                "type": "image",
                "reply": "Aqui está:",
                "image_base64": base64.b64encode(img_bytes).decode("utf-8"),
                "mime_type": "image/png",
            }
        return {"type": "text", "reply": "Não consegui gerar a imagem agora. Tente novamente em instantes."}

    if acao == "video":
        pedido_midia = decisao["prompt_midia"]
        info = planejar_cena_com_ia(client, pedido_midia, "vídeo curto", historico_dict)
        mp4_bytes = gerar_video_curto_rener(
            info,
            pollinations_key=chaves["POLLINATIONS_API_KEY"],
            pedido_original=pedido_midia,
            segundos=4,
        )
        if mp4_bytes:
            return {
                "type": "video",
                "reply": "Aqui está:",
                "video_base64": base64.b64encode(mp4_bytes).decode("utf-8"),
                "mime_type": "video/mp4",
            }
        return {"type": "text", "reply": "Não consegui gerar o vídeo curto agora. Tente novamente em instantes."}

    system_prompt = montar_system_prompt(req.style)
    mensagens_enviadas = [system_prompt] + [
        {
            "role": m["role"],
            "content": (
                f"{m.get('content', '')} "
                f"{'[imagem exibida no chat]' if m.get('has_image') else ''} "
                f"{'[vídeo exibido no chat]' if m.get('has_video') else ''}"
            ).strip(),
        }
        for m in historico_dict
        if m.get("content") or m.get("has_image") or m.get("has_video")
    ]

    if acao == "web":
        consulta_busca = decisao["consulta_web"] or prompt_texto
        resultados_web = pesquisar_na_internet(consulta_busca, chaves["TAVILY_API_KEY"])
        if resultados_web:
            mensagem_envio = (
                f"Mensagem do usuário: {prompt_texto}\n\n"
                f"Dados da busca na internet:\n{resultados_web}\n\n"
                "Responda de forma natural e humana, usando os dados quando ajudarem."
            )
        else:
            mensagem_envio = prompt_texto
    else:
        mensagem_envio = prompt_texto

    mensagens_enviadas.append({"role": "user", "content": mensagem_envio})

    try:
        chat_completion = client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=mensagens_enviadas,
            tool_choice="none",
        )
        resposta = chat_completion.choices[0].message.content or ""
        return {"type": "text", "reply": resposta}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erro no modelo: {exc}") from exc


@app.post("/image")
def image_endpoint(req: MediaRequest) -> dict[str, Any]:
    pedido = (req.prompt or "").strip()
    if not pedido:
        raise HTTPException(status_code=400, detail="Prompt vazio.")

    client = obter_groq_client()
    chaves = obter_chaves()
    historico_dict = [m.model_dump() for m in req.history]
    info = planejar_cena_com_ia(client, pedido, "imagem", historico_dict)
    img_bytes = gerar_imagem_alta_qualidade(
        info,
        pollinations_key=chaves["POLLINATIONS_API_KEY"],
        pedido_original=pedido,
    )
    if not img_bytes:
        raise HTTPException(status_code=502, detail="Não foi possível gerar a imagem.")

    return {
        "reply": "Aqui está:",
        "image_base64": base64.b64encode(img_bytes).decode("utf-8"),
        "mime_type": "image/png",
    }


@app.post("/video")
def video_endpoint(req: MediaRequest) -> dict[str, Any]:
    pedido = (req.prompt or "").strip()
    if not pedido:
        raise HTTPException(status_code=400, detail="Prompt vazio.")

    client = obter_groq_client()
    chaves = obter_chaves()
    historico_dict = [m.model_dump() for m in req.history]
    info = planejar_cena_com_ia(client, pedido, "vídeo curto", historico_dict)
    mp4_bytes = gerar_video_curto_rener(
        info,
        pollinations_key=chaves["POLLINATIONS_API_KEY"],
        pedido_original=pedido,
        segundos=max(2, min(6, req.seconds)),
    )
    if not mp4_bytes:
        raise HTTPException(status_code=502, detail="Não foi possível gerar o vídeo.")

    return {
        "reply": "Aqui está:",
        "video_base64": base64.b64encode(mp4_bytes).decode("utf-8"),
        "mime_type": "video/mp4",
    }


@app.post("/transcribe")
async def transcribe_endpoint(file: UploadFile = File(...)) -> dict[str, str]:
    conteudo = await file.read()
    if not conteudo:
        raise HTTPException(status_code=400, detail="Arquivo de áudio vazio.")

    client = obter_groq_client()
    nome_arq = file.filename or "ditado.wav"
    ext = Path(nome_arq).suffix.lstrip(".").lower() or "wav"

    with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
        tmp.write(conteudo)
        caminho_audio = tmp.name

    try:
        with open(caminho_audio, "rb") as f_audio:
            transcricao = client.audio.transcriptions.create(
                file=(f"ditado.{ext}", f_audio.read()),
                model="whisper-large-v3-turbo",
                language="pt",
                response_format="text",
            )
        texto = transcricao.strip() if isinstance(transcricao, str) else str(getattr(transcricao, "text", "") or "").strip()
        return {"text": texto}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Falha na transcrição: {exc}") from exc
    finally:
        try:
            Path(caminho_audio).unlink(missing_ok=True)
        except Exception:
            pass
