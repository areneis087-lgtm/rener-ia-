import base64
from datetime import datetime, timedelta
from io import BytesIO
import json
from pathlib import Path
import re
import tempfile
from urllib.parse import quote, quote_plus
import xml.etree.ElementTree as ET
from ddgs import DDGS
from groq import Groq
import imageio.v2 as imageio
import numpy as np
from PIL import Image
import requests
import streamlit as st
from streamlit_mic_recorder import mic_recorder
from tavily import TavilyClient

st.set_page_config(page_title="Rener", page_icon="✨", layout="centered")


def carregar_chaves_secrets() -> dict[str, str]:
    chaves = {
        "GROQ_API_KEY": "",
        "TAVILY_API_KEY": "",
        "POLLINATIONS_API_KEY": "",
    }
    try:
        for nome in chaves:
            if nome in st.secrets:
                valor = str(st.secrets[nome] or "").strip().strip('"').strip("'")
                if valor and valor != "SUA_CHAVE_POLLINATIONS":
                    chaves[nome] = valor
    except Exception:
        pass
    return chaves


def encontrar_e_carregar_fundo() -> str:
    candidatos = [
        Path("fundo.png"),
        Path("fundo.jpg"),
        Path("fundo.jpeg"),
        Path("fundo.webp"),
        Path("1000426462_2.png"),
        Path("1000426462.png"),
    ]
    for arq in Path(".").iterdir():
        if arq.is_file() and arq.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
            if arq.stem.lower().startswith("fundo") or "1000426462" in arq.stem.lower():
                candidatos.insert(0, arq)

    for caminho in candidatos:
        if caminho.exists() and caminho.is_file():
            dados = caminho.read_bytes()
            b64 = base64.b64encode(dados).decode("utf-8")
            ext = caminho.suffix.lower().lstrip(".")
            mime = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"
            return f"data:{mime};base64,{b64}"

    return ""


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


def transcrever_audio_com_groq(client: Groq, audio_bytes: bytes, formato: str = "wav") -> str:
    if not audio_bytes:
        return ""
    ext = formato.lstrip(".").lower() or "wav"
    with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
        tmp.write(audio_bytes)
        caminho_audio = tmp.name

    try:
        with open(caminho_audio, "rb") as f_audio:
            transcricao = client.audio.transcriptions.create(
                file=(f"ditado.{ext}", f_audio.read()),
                model="whisper-large-v3-turbo",
                language="pt",
                response_format="text",
            )
        if isinstance(transcricao, str):
            return transcricao.strip()
        return str(getattr(transcricao, "text", "") or "").strip()
    except Exception:
        return ""
    finally:
        try:
            Path(caminho_audio).unlink(missing_ok=True)
        except Exception:
            pass


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


def formatar_historico_curto(mensagens: list[dict], limite: int = 8) -> str:
    trechos = []
    for m in mensagens[-limite:]:
        papel = "Usuário" if m.get("role") == "user" else "Rener"
        conteudo = str(m.get("content") or "").strip()
        anexos = []
        if m.get("image"):
            anexos.append("[imagem exibida no chat]")
        if m.get("video"):
            anexos.append("[vídeo exibido no chat]")
        texto_final = f"{conteudo} {' '.join(anexos)}".strip()
        if texto_final:
            trechos.append(f"{papel}: {texto_final}")
    return "\n".join(trechos)


def decidir_acao_com_ia(client: Groq, mensagem_atual: str, historico: list[dict]) -> dict:
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
    historico_mensagens: list[dict] | None = None,
) -> dict:
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
    info_cena: dict,
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
    info_cena: dict,
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

        kwargs_busca = {
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


def processar_turno_usuario(
    prompt_texto: str,
    client: Groq,
    tavily_key: str,
    pollinations_key: str,
    system_prompt: dict,
) -> None:
    st.session_state.messages.append({"role": "user", "content": prompt_texto})
    with st.chat_message("user"):
        st.markdown(prompt_texto)

    with st.chat_message("assistant"):
        historico_anterior = st.session_state.messages[:-1]
        decisao = decidir_acao_com_ia(client, prompt_texto, historico_anterior)
        acao = decisao["acao"]

        if acao == "image":
            pedido_midia = decisao["prompt_midia"]
            with st.spinner("Criando imagem..."):
                info = planejar_cena_com_ia(client, pedido_midia, "imagem", historico_anterior)
                img_bytes = gerar_imagem_alta_qualidade(
                    info,
                    pollinations_key=pollinations_key,
                    pedido_original=pedido_midia,
                )
                if img_bytes:
                    st.session_state.ultima_imagem_gerada = img_bytes
                    texto_resp = "Aqui está:"
                    st.markdown(texto_resp)
                    st.image(img_bytes, use_container_width=True)
                    st.session_state.messages.append({"role": "assistant", "content": texto_resp, "image": img_bytes})
                else:
                    texto_resp = "Não consegui gerar a imagem agora. Tente novamente em instantes."
                    st.markdown(texto_resp)
                    st.session_state.messages.append({"role": "assistant", "content": texto_resp})

        elif acao == "video":
            pedido_midia = decisao["prompt_midia"]
            with st.spinner("Criando vídeo curto..."):
                info = planejar_cena_com_ia(client, pedido_midia, "vídeo curto", historico_anterior)
                mp4_bytes = gerar_video_curto_rener(
                    info,
                    pollinations_key=pollinations_key,
                    pedido_original=pedido_midia,
                    segundos=4,
                )
                if mp4_bytes:
                    st.session_state.ultimo_video_gerado = mp4_bytes
                    texto_resp = "Aqui está:"
                    st.markdown(texto_resp)
                    st.video(mp4_bytes)
                    st.session_state.messages.append({"role": "assistant", "content": texto_resp, "video": mp4_bytes})
                else:
                    texto_resp = "Não consegui gerar o vídeo curto agora. Tente novamente em instantes."
                    st.markdown(texto_resp)
                    st.session_state.messages.append({"role": "assistant", "content": texto_resp})

        else:
            with st.spinner("Pensando..."):
                try:
                    mensagens_enviadas = [system_prompt] + [
                        {
                            "role": m["role"],
                            "content": (
                                f"{m.get('content', '')} "
                                f"{'[imagem exibida no chat]' if m.get('image') else ''} "
                                f"{'[vídeo exibido no chat]' if m.get('video') else ''}"
                            ).strip(),
                        }
                        for m in historico_anterior
                        if m.get("content") or m.get("image") or m.get("video")
                    ]

                    if acao == "web":
                        consulta_busca = decisao["consulta_web"] or prompt_texto
                        resultados_web = pesquisar_na_internet(consulta_busca, tavily_key)
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

                    chat_completion = client.chat.completions.create(
                        model="openai/gpt-oss-20b",
                        messages=mensagens_enviadas,
                        tool_choice="none",
                    )
                    response = chat_completion.choices[0].message.content
                    st.markdown(response)
                    st.session_state.messages.append({"role": "assistant", "content": response})
                except Exception as e:
                    st.error(f"Erro: {e}")


bg_data_uri = encontrar_e_carregar_fundo()

if bg_data_uri:
    fundo_css = f"""
        .stApp {{
            background:
                linear-gradient(rgba(5, 8, 17, 0.42), rgba(5, 8, 17, 0.56)),
                url("{bg_data_uri}") center center / cover no-repeat fixed !important;
            color: #f3f4f6;
        }}
    """
else:
    fundo_css = """
        .stApp {
            background: radial-gradient(circle at 50% 20%, #0d1d42 0%, #050507 62%);
            color: #f3f4f6;
        }
    """

st.markdown(
    f"""
    <style>
        html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {{
            scroll-behavior: smooth !important;
            -webkit-overflow-scrolling: touch !important;
            overflow-anchor: auto !important;
        }}

        [data-testid="stMainBlockContainer"] {{
            padding-bottom: 145px !important;
        }}

        {fundo_css}

        [data-testid="stSidebar"] {{
            background-color: #090a0d;
            border-right: 1px solid rgba(255, 255, 255, 0.08);
        }}
        .hero-box {{
            text-align: center;
            padding: 36px 16px 24px 16px;
            background: rgba(5, 8, 17, 0.78);
            border: 1px solid rgba(255, 255, 255, 0.12);
            border-radius: 24px;
            backdrop-filter: blur(6px);
        }}
        .hero-sparkle {{
            font-size: 36px;
            margin-bottom: 10px;
        }}
        .hero-title {{
            font-size: 28px;
            font-weight: 600;
            color: #ffffff;
            margin: 0;
            text-shadow: 0 2px 10px rgba(0, 0, 0, 0.85);
        }}
        .hero-sub {{
            font-size: 14px;
            color: #e2e8f0;
            margin-top: 6px;
            text-shadow: 0 1px 8px rgba(0, 0, 0, 0.85);
        }}

        [data-testid="stChatMessageAvatarUser"],
        [data-testid="stChatMessageAvatarAssistant"],
        [data-testid="stChatMessage"] > div:first-child {{
            display: none !important;
        }}

        [data-testid="stChatMessage"] {{
            background: transparent !important;
            border: none !important;
            box-shadow: none !important;
            padding: 4px 0 !important;
            margin-bottom: 10px !important;
            display: flex !important;
            width: 100% !important;
        }}

        [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]),
        [data-testid="stChatMessage"]:has([aria-label="Chat message from user"]) {{
            justify-content: flex-end !important;
        }}

        [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stChatMessageContent"],
        [data-testid="stChatMessage"]:has([aria-label="Chat message from user"]) [data-testid="stChatMessageContent"] {{
            background: rgba(148, 163, 184, 0.22) !important;
            color: #f8fafc !important;
            border: 1px solid rgba(255, 255, 255, 0.16) !important;
            border-radius: 24px 24px 6px 24px !important;
            padding: 10px 16px !important;
            max-width: 82% !important;
            backdrop-filter: blur(6px);
            box-shadow: 0 4px 14px rgba(0, 0, 0, 0.28) !important;
        }}

        [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]),
        [data-testid="stChatMessage"]:has([aria-label="Chat message from assistant"]) {{
            justify-content: flex-start !important;
        }}

        [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) [data-testid="stChatMessageContent"],
        [data-testid="stChatMessage"]:has([aria-label="Chat message from assistant"]) [data-testid="stChatMessageContent"] {{
            background: rgba(9, 13, 24, 0.82) !important;
            color: #f8fafc !important;
            border: 1px solid rgba(255, 255, 255, 0.14) !important;
            border-radius: 8px 22px 22px 22px !important;
            padding: 10px 16px !important;
            max-width: 88% !important;
            backdrop-filter: blur(6px);
        }}

        [data-testid="stBottom"],
        [data-testid="stBottom"] > div,
        [data-testid="stBottom"] > div > div {{
            background: transparent !important;
            background-color: transparent !important;
            border: none !important;
            box-shadow: none !important;
        }}

        [data-testid="stChatInput"] {{
            background-color: rgba(14, 19, 32, 0.92) !important;
            border: 2px solid #ffffff !important;
            border-radius: 999px !important;
            padding: 4px 10px 4px 16px !important;
            box-shadow: 0 0 14px rgba(255, 255, 255, 0.28) !important;
        }}

        [data-testid="stChatInput"] > div,
        [data-testid="stChatInput"] > div > div,
        [data-testid="stChatInput"] [data-baseweb="textarea"],
        [data-testid="stChatInput"] [data-baseweb="base-input"] {{
            background: transparent !important;
            background-color: transparent !important;
            border: none !important;
            box-shadow: none !important;
        }}

        [data-testid="stChatInput"] textarea {{
            background: transparent !important;
            background-color: transparent !important;
            color: #ffffff !important;
            caret-color: #ffffff !important;
            font-size: 15px !important;
            border: none !important;
            box-shadow: none !important;
        }}

        [data-testid="stChatInput"] textarea::placeholder {{
            color: #e2e8f0 !important;
            opacity: 1 !important;
        }}

        [data-testid="stChatInput"] button {{
            background-color: rgba(148, 163, 184, 0.28) !important;
            color: #ffffff !important;
            border-radius: 999px !important;
            border: 1.5px solid #ffffff !important;
            min-width: 38px !important;
            height: 38px !important;
        }}

        [data-testid="stChatInput"] button:hover {{
            background-color: rgba(148, 163, 184, 0.45) !important;
        }}
    </style>
    """,
    unsafe_allow_html=True,
)

if "messages" not in st.session_state:
    st.session_state.messages = []
if "menu_aba" not in st.session_state:
    st.session_state.menu_aba = "Chat"
if "notebooks" not in st.session_state:
    st.session_state.notebooks = ["Criação de Aplicativo de IA"]
if "programados" not in st.session_state:
    st.session_state.programados = []
if "estilo_rener" not in st.session_state:
    st.session_state.estilo_rener = "Amigável e direto"
if "ultima_imagem_gerada" not in st.session_state:
    st.session_state.ultima_imagem_gerada = None
if "ultimo_video_gerado" not in st.session_state:
    st.session_state.ultimo_video_gerado = None
if "ultimo_hash_audio" not in st.session_state:
    st.session_state.ultimo_hash_audio = ""
if "texto_ditado_pendente" not in st.session_state:
    st.session_state.texto_ditado_pendente = ""

chaves_secretas = carregar_chaves_secrets()
groq_key = chaves_secretas["GROQ_API_KEY"]
tavily_key = chaves_secretas["TAVILY_API_KEY"]
pollinations_key = chaves_secretas["POLLINATIONS_API_KEY"]

with st.sidebar:
    st.markdown("### Rener")

    if st.button("✏️ Nova conversa", use_container_width=True):
        st.session_state.messages = []
        st.session_state.menu_aba = "Chat"
        st.session_state.texto_ditado_pendente = ""
        st.rerun()

    st.divider()

    if st.button("🗂️ Biblioteca", use_container_width=True):
        st.session_state.menu_aba = "Biblioteca"
    if st.button("🖼️ Imagens", use_container_width=True):
        st.session_state.menu_aba = "Imagens"
    if st.button("⏰ Programado", use_container_width=True):
        st.session_state.menu_aba = "Programado"
    if st.button("⚙️ Personalizar", use_container_width=True):
        st.session_state.menu_aba = "Personalizar"
    if st.button("🎬 Vídeos", use_container_width=True):
        st.session_state.menu_aba = "Vídeos"

    st.divider()
    st.markdown("**Notebooks**")
    novo_nb = st.text_input("Nome do notebook", placeholder="Ex: Ideias do App", label_visibility="collapsed")
    if st.button("➕ Novo notebook", use_container_width=True):
        if novo_nb.strip():
            st.session_state.notebooks.append(novo_nb.strip())
            st.rerun()

    for nb in st.session_state.notebooks:
        st.caption(f"• {nb}")

    st.divider()
    st.caption("Criador: Rener")

if not groq_key:
    st.error("⚠️ Chave de API não configurada! Adicione a GROQ_API_KEY em Settings > Secrets.")
    st.stop()

client = Groq(api_key=groq_key)

agora_dt = datetime.now()
data_atual = agora_dt.strftime("%d/%m/%Y")
ontem_data = (agora_dt - timedelta(days=1)).strftime("%d/%m/%Y")

system_prompt = {
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
        f"Estilo de resposta atual: {st.session_state.estilo_rener}."
    ),
}

if st.session_state.menu_aba == "Biblioteca":
    st.subheader("🗂️ Biblioteca")
    if st.session_state.messages:
        for m in st.session_state.messages:
            st.markdown(f"**{m['role'].title()}:** {m['content']}")
    else:
        st.info("Nenhuma mensagem salva na conversa atual ainda.")
    if st.button("Voltar para o chat"):
        st.session_state.menu_aba = "Chat"
        st.rerun()

elif st.session_state.menu_aba == "Imagens":
    st.subheader("🖼️ Imagens")
    prompt_img = st.text_input("O que você quer criar?", placeholder="Ex: Coelho real, escudo do Flamengo, carro...")
    if st.button("✨ Criar imagem", use_container_width=True):
        if prompt_img.strip():
            with st.spinner("Criando imagem..."):
                info = planejar_cena_com_ia(client, prompt_img.strip(), "imagem", st.session_state.messages)
                img_bytes = gerar_imagem_alta_qualidade(
                    info,
                    pollinations_key=pollinations_key,
                    pedido_original=prompt_img.strip(),
                )
                if img_bytes:
                    st.session_state.ultima_imagem_gerada = img_bytes
                    st.session_state.messages.append(
                        {
                            "role": "assistant",
                            "content": "Aqui está:",
                            "image": img_bytes,
                        }
                    )
                else:
                    st.warning("Não consegui gerar a imagem agora. Tente novamente em instantes.")
    if st.session_state.ultima_imagem_gerada:
        img_b = st.session_state.ultima_imagem_gerada
        st.image(img_b, use_container_width=True)
        st.download_button("Baixar imagem (PNG)", data=img_b, file_name="imagem.png", mime="image/png", use_container_width=True)
    if st.button("Voltar para o chat"):
        st.session_state.menu_aba = "Chat"
        st.rerun()

elif st.session_state.menu_aba == "Vídeos":
    st.subheader("🎬 Vídeos")
    prompt_vid = st.text_input("O que você quer no vídeo curto?", placeholder="Ex: Lobo na neve, praia ao pôr do sol...")
    duracao_vid = st.slider("Duração (segundos)", min_value=2, max_value=6, value=4)
    if st.button("🎥 Criar vídeo curto", use_container_width=True):
        if prompt_vid.strip():
            with st.spinner("Criando vídeo curto..."):
                info = planejar_cena_com_ia(client, prompt_vid.strip(), "vídeo curto", st.session_state.messages)
                mp4_bytes = gerar_video_curto_rener(
                    info,
                    pollinations_key=pollinations_key,
                    pedido_original=prompt_vid.strip(),
                    segundos=duracao_vid,
                )
                if mp4_bytes:
                    st.session_state.ultimo_video_gerado = mp4_bytes
                    st.session_state.messages.append(
                        {
                            "role": "assistant",
                            "content": "Aqui está:",
                            "video": mp4_bytes,
                        }
                    )
                else:
                    st.warning("Não consegui gerar o vídeo agora. Tente novamente em instantes.")
    if st.session_state.ultimo_video_gerado:
        vid_b = st.session_state.ultimo_video_gerado
        st.video(vid_b)
        st.download_button("Baixar vídeo (MP4)", data=vid_b, file_name="video_curto.mp4", mime="video/mp4", use_container_width=True)
    if st.button("Voltar para o chat"):
        st.session_state.menu_aba = "Chat"
        st.rerun()

elif st.session_state.menu_aba == "Programado":
    st.subheader("⏰ Programado")
    tarefa = st.text_input("Adicionar lembrete ou tarefa programada")
    if st.button("Salvar item"):
        if tarefa.strip():
            st.session_state.programados.append(tarefa.strip())
    for item in st.session_state.programados:
        st.write(f"• {item}")
    if st.button("Voltar para o chat"):
        st.session_state.menu_aba = "Chat"
        st.rerun()

elif st.session_state.menu_aba == "Personalizar":
    st.subheader("⚙️ Personalizar")
    estilo = st.selectbox(
        "Como o Rener deve responder?",
        ["Amigável e direto", "Detalhado e técnico", "Criativo e descontraído"],
        index=["Amigável e direto", "Detalhado e técnico", "Criativo e descontraído"].index(
            st.session_state.estilo_rener
        ),
    )
    if st.button("Salvar preferência"):
        st.session_state.estilo_rener = estilo
        st.success("Preferência salva!")
    if st.button("Voltar para o chat"):
        st.session_state.menu_aba = "Chat"
        st.rerun()

else:
    if not st.session_state.messages:
        st.markdown(
            """
            <div class="hero-box">
                <div class="hero-sparkle">✦</div>
                <p class="hero-title">Olá, Rener, vamos começar</p>
                <p class="hero-sub">Rener • Assistente de IA</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            if message.get("content"):
                st.markdown(message["content"])
            if message.get("image"):
                st.image(message["image"], use_container_width=True)
            if message.get("video"):
                st.video(message["video"])

    col_mic, col_vazio = st.columns([1, 3])
    with col_mic:
        gravacao = mic_recorder(
            start_prompt="🎤 Ditar",
            stop_prompt="⏹ Parar",
            just_once=False,
            use_container_width=True,
            key="microfone_ditado_rener",
        )

    if gravacao and isinstance(gravacao, dict) and gravacao.get("bytes"):
        audio_bytes = gravacao["bytes"]
        audio_hash = base64.b64encode(audio_bytes[:1024]).decode("utf-8") + f"_{len(audio_bytes)}"
        if audio_hash != st.session_state.ultimo_hash_audio:
            st.session_state.ultimo_hash_audio = audio_hash
            with st.spinner("Transcrevendo sua voz..."):
                texto_transcrito = transcrever_audio_com_groq(client, audio_bytes, formato="wav")
                if texto_transcrito:
                    st.session_state.texto_ditado_pendente = texto_transcrito

    if st.session_state.texto_ditado_pendente:
        st.info(f"🎙️ Ditado: **{st.session_state.texto_ditado_pendente}**")
        col_env, col_limp = st.columns([3, 1])
        with col_env:
            if st.button("Enviar ditado", use_container_width=True):
                texto_para_enviar = st.session_state.texto_ditado_pendente
                st.session_state.texto_ditado_pendente = ""
                processar_turno_usuario(texto_para_enviar, client, tavily_key, pollinations_key, system_prompt)
                st.rerun()
        with col_limp:
            if st.button("Limpar", use_container_width=True):
                st.session_state.texto_ditado_pendente = ""
                st.rerun()

    if prompt := st.chat_input("Peça ao Rener"):
        processar_turno_usuario(prompt, client, tavily_key, pollinations_key, system_prompt)
