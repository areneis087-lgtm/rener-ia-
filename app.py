import base64
from datetime import datetime, timedelta
from io import BytesIO
import json
import math
from pathlib import Path
import re
import tempfile
from urllib.parse import quote_plus
import xml.etree.ElementTree as ET
from ddgs import DDGS
from groq import Groq
import imageio.v2 as imageio
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
import requests
import streamlit as st
from tavily import TavilyClient

st.set_page_config(page_title="Rener", page_icon="✨", layout="centered")


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


def detectar_pedido_midia(texto: str) -> str:
    t = texto.lower()
    palavras_video = ("vídeo", "video", "vídeo curto", "video curto", "clipe", "animação", "animacao")
    palavras_imagem = ("imagem", "foto", "ilustração", "ilustracao", "desenho", "arte")
    if any(p in t for p in palavras_video):
        return "video"
    if any(p in t for p in palavras_imagem):
        return "image"
    return ""


def interpretar_assunto_com_ia(client: Groq, pedido_usuario: str, tipo_midia: str) -> dict:
    t_lower = pedido_usuario.lower()
    eh_flamengo = "flamengo" in t_lower or "crf" in t_lower
    eh_futebol = eh_flamengo or any(
        k in t_lower for k in ("futebol", "time", "gol", "estádio", "estadio", "bola", "campeão", "campeao")
    )

    fallback = {
        "assunto": "Flamengo" if eh_flamengo else pedido_usuario.strip(),
        "estilo_visual": "flamengo" if eh_flamengo else ("futebol" if eh_futebol else "paisagem"),
        "cor_primaria": (198, 24, 32) if eh_flamengo else (26, 92, 184),
        "cor_secundaria": (14, 15, 20) if eh_flamengo else (8, 18, 38),
        "destaque": (245, 196, 48),
    }
    try:
        resp = client.chat.completions.create(
            model="openai/gpt-oss-20b",
            tool_choice="none",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Você interpreta pedidos de imagem ou vídeo curto em português e devolve APENAS um objeto JSON válido "
                        "com as chaves: assunto (string curta do tema), "
                        "estilo_visual ('flamengo', 'futebol', 'paisagem' ou 'espaco'), "
                        "cor_primaria (lista de 3 inteiros RGB), cor_secundaria (lista de 3 inteiros RGB), destaque (lista de 3 inteiros RGB). "
                        "Não escreva texto fora do JSON."
                    ),
                },
                {"role": "user", "content": f"Tipo: {tipo_midia} | Pedido: {pedido_usuario}"},
            ],
        )
        conteudo = (resp.choices[0].message.content or "").strip()
        match = re.search(r"\{.*\}", conteudo, re.DOTALL)
        if match:
            dados = json.loads(match.group(0))
            estilo_raw = str(dados.get("estilo_visual") or fallback["estilo_visual"]).strip().lower()
            if eh_flamengo:
                estilo_raw = "flamengo"
            elif estilo_raw not in {"flamengo", "futebol", "paisagem", "espaco"}:
                estilo_raw = fallback["estilo_visual"]
            return {
                "assunto": str(dados.get("assunto") or fallback["assunto"]).strip(),
                "estilo_visual": estilo_raw,
                "cor_primaria": (198, 24, 32) if estilo_raw == "flamengo" else tuple(int(x) for x in (dados.get("cor_primaria") or fallback["cor_primaria"])[:3]),
                "cor_secundaria": (14, 15, 20) if estilo_raw == "flamengo" else tuple(int(x) for x in (dados.get("cor_secundaria") or fallback["cor_secundaria"])[:3]),
                "destaque": tuple(int(x) for x in (dados.get("destaque") or fallback["destaque"])[:3]),
            }
    except Exception:
        pass
    return fallback


def desenhar_estrela(draw: ImageDraw.ImageDraw, cx: int, cy: int, raio_ext: int, raio_int: int, preenchimento, contorno=None, largura_borda: int = 2):
    pontos = []
    for i in range(10):
        ang = math.radians(-90 + i * 36)
        r = raio_ext if i % 2 == 0 else raio_int
        pontos.append((cx + int(r * math.cos(ang)), cy + int(r * math.sin(ang))))
    draw.polygon(pontos, fill=preenchimento, outline=contorno, width=largura_borda if contorno else 1)


def desenhar_monograma_crf(draw: ImageDraw.ImageDraw, cx: int, cy: int, escala: float = 1.0):
    s = escala
    cor_branco = (244, 246, 249)
    cor_sombra = (24, 26, 32)
    borda = max(5, int(9 * s))

    # Letra C à esquerda
    c_box = [int(cx - 210 * s), int(cy - 135 * s), int(cx + 35 * s), int(cy + 135 * s)]
    draw.arc(c_box, start=42, end=318, fill=cor_sombra, width=int(56 * s) + borda * 2)
    draw.arc(c_box, start=42, end=318, fill=cor_branco, width=int(56 * s))

    # Haste vertical do F/R ao centro
    h_x1 = int(cx - 35 * s)
    h_x2 = int(cx + 22 * s)
    h_y1 = int(cy - 155 * s)
    h_y2 = int(cy + 155 * s)
    draw.rounded_rectangle([h_x1 - borda, h_y1 - borda, h_x2 + borda, h_y2 + borda], radius=int(18 * s), fill=cor_sombra)
    draw.rounded_rectangle([h_x1, h_y1, h_x2, h_y2], radius=int(14 * s), fill=cor_branco)

    # Topo e meio do F à direita
    f_box_top = [int(cx - 10 * s), int(cy - 155 * s), int(cx + 205 * s), int(cy + 30 * s)]
    draw.arc(f_box_top, start=250, end=65, fill=cor_sombra, width=int(48 * s) + borda * 2)
    draw.arc(f_box_top, start=250, end=65, fill=cor_branco, width=int(48 * s))

    # Perna diagonal do R
    perna_sombra = [
        (int(cx + 15 * s) - borda, int(cy + 8 * s)),
        (int(cx + 75 * s) + borda, int(cy + 8 * s)),
        (int(cx + 195 * s) + borda, int(cy + 155 * s) + borda),
        (int(cx + 125 * s) - borda, int(cy + 155 * s) + borda),
    ]
    perna_branca = [
        (int(cx + 20 * s), int(cy + 14 * s)),
        (int(cx + 70 * s), int(cy + 14 * s)),
        (int(cx + 185 * s), int(cy + 152 * s)),
        (int(cx + 132 * s), int(cy + 152 * s)),
    ]
    draw.polygon(perna_sombra, fill=cor_sombra)
    draw.polygon(perna_branca, fill=cor_branco)


def desenhar_bola_futebol(draw: ImageDraw.ImageDraw, cx: int, cy: int, raio: int):
    draw.ellipse([cx - raio, cy - raio, cx + raio, cy + raio], fill=(248, 250, 252), outline=(15, 23, 42), width=5)
    pentagono = []
    raio_p = int(raio * 0.36)
    for i in range(5):
        ang = math.radians(-90 + i * 72)
        pentagono.append((cx + int(raio_p * math.cos(ang)), cy + int(raio_p * math.sin(ang))))
    draw.polygon(pentagono, fill=(15, 23, 42))
    for i in range(5):
        ang = math.radians(-90 + i * 72)
        px, py = cx + int(raio_p * math.cos(ang)), cy + int(raio_p * math.sin(ang))
        bx, by = cx + int(raio * 0.92 * math.cos(ang)), cy + int(raio * 0.92 * math.sin(ang))
        draw.line([(px, py), (bx, by)], fill=(15, 23, 42), width=4)


def gerar_arte_rener(info_midia: dict, largura: int = 1024, altura: int = 1024) -> bytes:
    estilo = info_midia.get("estilo_visual", "paisagem")
    c1 = info_midia["cor_primaria"]
    c2 = info_midia["cor_secundaria"]
    dest = info_midia["destaque"]

    img = Image.new("RGB", (largura, altura), c2)
    draw = ImageDraw.Draw(img)

    if estilo == "flamengo":
        num_faixas = 8
        alt_faixa = altura / num_faixas
        for idx in range(num_faixas):
            y0 = int(idx * alt_faixa)
            y1 = int((idx + 1) * alt_faixa) + 1
            cor_base = c2 if idx % 2 == 0 else c1
            draw.rectangle([0, y0, largura, y1], fill=cor_base)

        # Ondulação suave simulando tecido
        yy, xx = np.mgrid[0:altura, 0:largura].astype(np.float32)
        onda = (
            np.sin(xx / largura * math.pi * 2.2 + yy / altura * math.pi * 1.4) * 0.14
            + np.cos(yy / altura * math.pi * 5.0 - xx / largura * math.pi * 1.1) * 0.08
        )
        arr = np.array(img, dtype=np.float32)
        for c in range(3):
            arr[:, :, c] = np.clip(arr[:, :, c] * (1.0 + onda), 0, 255)
        img = Image.fromarray(arr.astype(np.uint8))
        draw = ImageDraw.Draw(img)

        desenhar_estrela(
            draw,
            cx=largura // 2,
            cy=int(altura * 0.20),
            raio_ext=int(largura * 0.068),
            raio_int=int(largura * 0.028),
            preenchimento=dest,
            contorno=(120, 82, 10),
            largura_borda=3,
        )
        desenhar_monograma_crf(draw, cx=largura // 2, cy=int(altura * 0.54), escala=largura / 1024.0)

    elif estilo == "futebol":
        horizonte = int(altura * 0.62)
        for y in range(horizonte):
            fator = y / max(1, horizonte - 1)
            r = int(c2[0] * (1 - fator) + c1[0] * fator * 0.65)
            g = int(c2[1] * (1 - fator) + c1[1] * fator * 0.65)
            b = int(c2[2] * (1 - fator) + c1[2] * fator * 0.65)
            draw.line([(0, y), (largura, y)], fill=(min(255, r), min(255, g), min(255, b)))

        draw.rectangle([0, horizonte, largura, altura], fill=(22, 96, 48))
        for i in range(6):
            y1 = horizonte + int((altura - horizonte) * (i / 6))
            y2 = horizonte + int((altura - horizonte) * ((i + 1) / 6))
            tom = (26, 112, 56) if i % 2 == 0 else (18, 84, 42)
            draw.rectangle([0, y1, largura, y2], fill=tom)

        draw.ellipse([largura // 2 - 190, horizonte + 40, largura // 2 + 190, horizonte + 170], outline=(236, 253, 245), width=4)
        draw.line([(largura // 2, horizonte), (largura // 2, altura)], fill=(236, 253, 245), width=4)
        desenhar_bola_futebol(draw, largura // 2, int(altura * 0.45), 96)

    elif estilo == "paisagem":
        horizonte = int(altura * 0.60)
        for y in range(horizonte):
            fator = y / max(1, horizonte - 1)
            r = int(c2[0] * (1 - fator) + c1[0] * fator * 0.8)
            g = int(c2[1] * (1 - fator) + c1[1] * fator * 0.8)
            b = int(c2[2] * (1 - fator) + c1[2] * fator * 0.8)
            draw.line([(0, y), (largura, y)], fill=(min(255, r), min(255, g), min(255, b)))

        sol_r = 105
        sx, sy = largura // 2, int(altura * 0.35)
        draw.ellipse([sx - sol_r, sy - sol_r, sx + sol_r, sy + sol_r], fill=dest)
        draw.polygon([(0, horizonte), (260, horizonte - 180), (550, horizonte)], fill=(28, 39, 64))
        draw.polygon([(450, horizonte), (770, horizonte - 220), (largura, horizonte)], fill=(20, 30, 52))
        draw.rectangle([0, horizonte, largura, altura], fill=(14, 56, 90))
        for ry in range(horizonte + 26, altura - 20, 36):
            larg_onda = int(130 + (ry - horizonte) * 0.85)
            draw.rounded_rectangle([largura // 2 - larg_onda, ry, largura // 2 + larg_onda, ry + 8], radius=4, fill=dest)

    else:
        for y in range(altura):
            fator = y / max(1, altura - 1)
            r = int(c2[0] * (1 - fator) + c1[0] * fator * 0.5)
            g = int(c2[1] * (1 - fator) + c1[1] * fator * 0.5)
            b = int(c2[2] * (1 - fator) + c1[2] * fator * 0.5)
            draw.line([(0, y), (largura, y)], fill=(min(255, r), min(255, g), min(255, b)))

        rng = np.random.default_rng(42)
        for _ in range(90):
            px = int(rng.integers(30, largura - 30))
            py = int(rng.integers(30, altura - 30))
            pr = int(rng.integers(2, 6))
            draw.ellipse([px - pr, py - pr, px + pr, py + pr], fill=(255, 255, 255))
        cx, cy = largura // 2, altura // 2
        draw.ellipse([cx - 180, cy - 180, cx + 180, cy + 180], outline=dest, width=5)
        draw.ellipse([cx - 120, cy - 120, cx + 120, cy + 120], fill=c1, outline=(255, 255, 255), width=3)

    img_final = img.filter(ImageFilter.SMOOTH)
    buf = BytesIO()
    img_final.save(buf, format="PNG")
    return buf.getvalue()


def gerar_video_curto_rener(info_midia: dict, segundos: int = 4, fps: int = 15) -> bytes:
    largura, altura = 720, 720
    arte_base = Image.open(BytesIO(gerar_arte_rener(info_midia, largura + 140, altura + 140))).convert("RGB")
    total_frames = max(15, segundos * fps)

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        caminho_mp4 = tmp.name

    try:
        writer = imageio.get_writer(caminho_mp4, fps=fps, codec="libx264", quality=7)
        try:
            for i in range(total_frames):
                progresso = i / max(1, total_frames - 1)
                dx = int(progresso * 140)
                dy = int((1 - abs(2 * progresso - 1)) * 90)
                frame = arte_base.crop((dx, dy, dx + largura, dy + altura)).convert("RGB")
                writer.append_data(np.array(frame))
        finally:
            writer.close()

        return Path(caminho_mp4).read_bytes()
    finally:
        try:
            Path(caminho_mp4).unlink(missing_ok=True)
        except Exception:
            pass


def precisa_pesquisar_na_web(consulta: str) -> bool:
    texto = consulta.strip().lower()
    if len(texto) <= 24 and texto in {
        "oi",
        "olá",
        "ola",
        "bom dia",
        "boa tarde",
        "boa noite",
        "tudo bem",
        "muito bem",
        "valeu",
        "obrigado",
        "obrigada",
        "top",
        "show",
        "beleza",
        "ok",
        "flamengo time",
        "cadê imagem?",
        "cade imagem?",
    }:
        return False

    gatilhos_web = (
        "jogo",
        "placar",
        "resultado",
        "gol",
        "gols",
        "ao vivo",
        "partida",
        "notícia",
        "noticia",
        "notícias",
        "noticias",
        "hoje",
        "ontem",
        "amanhã",
        "amanha",
        "agora",
        "últimas",
        "ultimas",
        "preço",
        "preco",
        "cotação",
        "cotacao",
        "clima",
        "tempo",
        "quem ganhou",
        "quem venceu",
        "campeonato",
        "tabela",
        "pesquise",
        "pesquisa",
        "procure",
        "na internet",
        "no google",
    )
    return any(p in texto for p in gatilhos_web)


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


def buscar_com_tavily(consulta: str) -> str:
    tavily_key = str(st.secrets.get("TAVILY_API_KEY", "")).strip()
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


def pesquisar_na_internet(consulta: str) -> str:
    resultado_tavily = buscar_com_tavily(consulta)
    if resultado_tavily:
        return resultado_tavily

    coletados = []
    coletados.extend(buscar_google_noticias_rss(montar_query_com_datas(consulta), max_itens=5))
    coletados.extend(buscar_ddgs(montar_query_com_datas(consulta), max_resultados=4))
    return "\n\n".join(coletados[:8]) if coletados else ""


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
            padding-bottom: 120px !important;
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

        /* Esconde avatares/ícones padrão de usuário e robô no chat */
        [data-testid="stChatMessageAvatarUser"],
        [data-testid="stChatMessageAvatarAssistant"],
        [data-testid="stChatMessage"] > div:first-child {{
            display: none !important;
        }}

        /* Container base de cada mensagem */
        [data-testid="stChatMessage"] {{
            background: transparent !important;
            border: none !important;
            box-shadow: none !important;
            padding: 4px 0 !important;
            margin-bottom: 10px !important;
            display: flex !important;
            width: 100% !important;
        }}

        /* Mensagem do usuário à direita em cinza fraco arredondado */
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

        /* Resposta da IA à esquerda */
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

        /* Rodapé transparente */
        [data-testid="stBottom"],
        [data-testid="stBottom"] > div,
        [data-testid="stBottom"] > div > div {{
            background: transparent !important;
            background-color: transparent !important;
            border: none !important;
            box-shadow: none !important;
        }}

        /* Contorno branco bem visível no bloco de entrada */
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

with st.sidebar:
    st.markdown("### Rener")

    if st.button("✏️ Nova conversa", use_container_width=True):
        st.session_state.messages = []
        st.session_state.menu_aba = "Chat"
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

try:
    api_key = str(st.secrets["GROQ_API_KEY"]).strip()
except Exception:
    st.error("⚠️ Chave de API não configurada! Adicione a GROQ_API_KEY em Settings > Secrets.")
    st.stop()

client = Groq(api_key=api_key)

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
        "Converse com naturalidade, autonomia e espontaneidade, como uma pessoa real que está batendo papo com o Rener. "
        "Entenda bem o contexto da conversa para não responder de forma confusa ou fora do assunto. "
        "Quando o usuário te elogiar ou pedir para agradecer elogios, agradeça de forma simpática e direta na própria conversa. "
        "Quando o usuário comentar um placar ou algo que aconteceu, acompanhe o papo naturalmente; só quando ele pedir para você buscar ou confirmar um resultado/notícia na internet, use os dados da pesquisa sem inventar placar que não exista nas fontes. "
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
    prompt_img = st.text_input("Descreva o que você quer ver", placeholder="Ex: Flamengo")
    if st.button("✨ Criar imagem", use_container_width=True):
        if prompt_img.strip():
            with st.spinner("Criando imagem..."):
                info = interpretar_assunto_com_ia(client, prompt_img.strip(), "imagem")
                img_bytes = gerar_arte_rener(info)
                st.session_state.ultima_imagem_gerada = img_bytes
                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "content": "Aqui está:",
                        "image": img_bytes,
                    }
                )
    if st.session_state.ultima_imagem_gerada:
        img_b = st.session_state.ultima_imagem_gerada
        st.image(img_b, use_container_width=True)
        st.download_button("Baixar imagem (PNG)", data=img_b, file_name="imagem.png", mime="image/png", use_container_width=True)
    if st.button("Voltar para o chat"):
        st.session_state.menu_aba = "Chat"
        st.rerun()

elif st.session_state.menu_aba == "Vídeos":
    st.subheader("🎬 Vídeos")
    prompt_vid = st.text_input("Descreva o que você quer no vídeo curto", placeholder="Ex: Flamengo")
    duracao_vid = st.slider("Duração (segundos)", min_value=2, max_value=6, value=4)
    if st.button("🎥 Criar vídeo curto", use_container_width=True):
        if prompt_vid.strip():
            with st.spinner("Criando vídeo curto..."):
                info = interpretar_assunto_com_ia(client, prompt_vid.strip(), "vídeo curto")
                mp4_bytes = gerar_video_curto_rener(info, segundos=duracao_vid)
                st.session_state.ultimo_video_gerado = mp4_bytes
                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "content": "Aqui está:",
                        "video": mp4_bytes,
                    }
                )
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

    if prompt := st.chat_input("Peça ao Rener"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            tipo_midia = detectar_pedido_midia(prompt)

            if tipo_midia == "image":
                with st.spinner("Criando imagem..."):
                    info = interpretar_assunto_com_ia(client, prompt, "imagem")
                    img_bytes = gerar_arte_rener(info)
                    st.session_state.ultima_imagem_gerada = img_bytes
                    texto_resp = "Aqui está:"
                    st.markdown(texto_resp)
                    st.image(img_bytes, use_container_width=True)
                    st.session_state.messages.append({"role": "assistant", "content": texto_resp, "image": img_bytes})

            elif tipo_midia == "video":
                with st.spinner("Criando vídeo curto..."):
                    info = interpretar_assunto_com_ia(client, prompt, "vídeo curto")
                    mp4_bytes = gerar_video_curto_rener(info, segundos=4)
                    st.session_state.ultimo_video_gerado = mp4_bytes
                    texto_resp = "Aqui está:"
                    st.markdown(texto_resp)
                    st.video(mp4_bytes)
                    st.session_state.messages.append({"role": "assistant", "content": texto_resp, "video": mp4_bytes})

            else:
                with st.spinner("Pensando..."):
                    try:
                        mensagens_enviadas = [system_prompt] + [
                            {"role": m["role"], "content": m["content"]}
                            for m in st.session_state.messages[:-1]
                            if m.get("content")
                        ]

                        if precisa_pesquisar_na_web(prompt):
                            resultados_web = pesquisar_na_internet(prompt)
                            if resultados_web:
                                mensagem_envio = (
                                    f"Mensagem do usuário: {prompt}\n\n"
                                    f"Dados da busca na internet:\n{resultados_web}\n\n"
                                    "Responda de forma natural e humana, usando os dados quando ajudarem."
                                )
                            else:
                                mensagem_envio = prompt
                        else:
                            mensagem_envio = prompt

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
