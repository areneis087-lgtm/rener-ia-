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
from PIL import Image, ImageDraw, ImageFilter, ImageFont
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
    eh_futebol = any(k in t_lower for k in ("flamengo", "futebol", "time", "gol", "estádio", "estadio", "bola", "campeão", "campeao"))
    assunto_limpo = re.sub(
        r"\b(me|gere|gerar|crie|criar|faz|fazer|faça|pra|para|mim|uma|um|imagem|foto|vídeo|video|curto|de|do|da|o|a)\b",
        " ",
        t_lower,
        flags=re.IGNORECASE,
    )
    assunto_limpo = re.sub(r"\s+", " ", assunto_limpo).strip(" .,!?")
    if not assunto_limpo:
        assunto_limpo = pedido_usuario.strip()

    fallback = {
        "assunto": assunto_limpo,
        "cena": "futebol" if eh_futebol else "paisagem",
        "cor_primaria": (196, 28, 36) if "flamengo" in t_lower else (26, 92, 184),
        "cor_secundaria": (14, 16, 24) if "flamengo" in t_lower else (8, 18, 38),
        "destaque": (250, 204, 21),
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
                        "com as chaves: assunto (string curta e clara do tema pedido, sem palavras soltas como 'pra mim'), "
                        "cena ('futebol', 'paisagem', 'espaco' ou 'abstrato'), "
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
            cena_raw = str(dados.get("cena") or fallback["cena"]).strip().lower()
            if cena_raw not in {"futebol", "paisagem", "espaco", "abstrato"}:
                cena_raw = fallback["cena"]
            return {
                "assunto": str(dados.get("assunto") or fallback["assunto"]).strip(),
                "cena": cena_raw,
                "cor_primaria": tuple(int(x) for x in (dados.get("cor_primaria") or fallback["cor_primaria"])[:3]),
                "cor_secundaria": tuple(int(x) for x in (dados.get("cor_secundaria") or fallback["cor_secundaria"])[:3]),
                "destaque": tuple(int(x) for x in (dados.get("destaque") or fallback["destaque"])[:3]),
            }
    except Exception:
        pass
    return fallback


def carregar_fonte(tamanho: int, negrito: bool = True):
    caminhos = (
        [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        ]
        if negrito
        else [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        ]
    )
    for c in caminhos:
        if Path(c).exists():
            try:
                return ImageFont.truetype(c, tamanho)
            except Exception:
                pass
    try:
        return ImageFont.load_default(size=tamanho)
    except TypeError:
        return ImageFont.load_default()


def desenhar_bola_futebol(draw: ImageDraw.ImageDraw, cx: int, cy: int, raio: int, cor_borda=(250, 204, 21)):
    draw.ellipse([cx - raio, cy - raio, cx + raio, cy + raio], fill=(248, 250, 252), outline=cor_borda, width=5)
    # Pentágono central estilizado
    pentagono = []
    raio_p = int(raio * 0.36)
    for i in range(5):
        ang = math.radians(-90 + i * 72)
        pentagono.append((cx + int(raio_p * math.cos(ang)), cy + int(raio_p * math.sin(ang))))
    draw.polygon(pentagono, fill=(15, 23, 42))
    # Linhas conectando aos gomos
    for i in range(5):
        ang = math.radians(-90 + i * 72)
        px, py = cx + int(raio_p * math.cos(ang)), cy + int(raio_p * math.sin(ang))
        bx, by = cx + int(raio * 0.92 * math.cos(ang)), cy + int(raio * 0.92 * math.sin(ang))
        draw.line([(px, py), (bx, by)], fill=(15, 23, 42), width=4)


def gerar_arte_rener(info_midia: dict, largura: int = 1024, altura: int = 1024) -> bytes:
    assunto = info_midia["assunto"]
    cena = info_midia.get("cena", "abstrato")
    c1 = info_midia["cor_primaria"]
    c2 = info_midia["cor_secundaria"]
    dest = info_midia["destaque"]

    img = Image.new("RGB", (largura, altura), c2)
    draw = ImageDraw.Draw(img)

    # Céu / gradiente base
    for y in range(altura):
        fator = y / max(1, altura - 1)
        r = int(c2[0] * (1 - fator) + c1[0] * fator * 0.72)
        g = int(c2[1] * (1 - fator) + c1[1] * fator * 0.72)
        b = int(c2[2] * (1 - fator) + c1[2] * fator * 0.72)
        draw.line([(0, y), (largura, y)], fill=(min(255, r), min(255, g), min(255, b)))

    # Raios de luz saindo do centro superior
    origem_x, origem_y = largura // 2, int(altura * 0.34)
    for ang_deg in range(-160, 15, 20):
        rad = math.radians(ang_deg)
        ex = origem_x + int(largura * 1.1 * math.cos(rad))
        ey = origem_y + int(altura * 1.1 * math.sin(rad))
        draw.line([(origem_x, origem_y), (ex, ey)], fill=(dest[0], dest[1], dest[2]), width=2)

    if cena == "futebol":
        # Faixas verticais características no fundo superior
        larg_faixa = 96
        for x in range(0, largura + larg_faixa, larg_faixa * 2):
            draw.rectangle([x, 0, x + larg_faixa, int(altura * 0.64)], fill=(c1[0], c1[1], c1[2]))

        # Arquibancada e refletores
        draw.rectangle([0, int(altura * 0.46), largura, int(altura * 0.64)], fill=(18, 22, 34))
        for rx in range(110, largura - 60, 180):
            draw.rounded_rectangle([rx - 26, 110, rx + 26, 145], radius=8, fill=(248, 250, 252))

        # Gramado estilizado na metade inferior
        horizonte = int(altura * 0.62)
        draw.rectangle([0, horizonte, largura, altura], fill=(20, 92, 46))
        for i in range(6):
            y1 = horizonte + int((altura - horizonte) * (i / 6))
            y2 = horizonte + int((altura - horizonte) * ((i + 1) / 6))
            tom = (24, 108, 54) if i % 2 == 0 else (18, 82, 40)
            draw.rectangle([0, y1, largura, y2], fill=tom)

        # Linhas do campo
        draw.ellipse([largura // 2 - 170, horizonte + 35, largura // 2 + 170, horizonte + 155], outline=(236, 253, 245), width=4)
        draw.line([(largura // 2, horizonte), (largura // 2, altura)], fill=(236, 253, 245), width=4)

        # Bola centralizada em destaque
        desenhar_bola_futebol(draw, largura // 2, int(altura * 0.43), 92, cor_borda=dest)

    elif cena == "paisagem":
        horizonte = int(altura * 0.60)
        # Sol brilhante
        sol_r = 95
        draw.ellipse([origem_x - sol_r, origem_y - sol_r, origem_x + sol_r, origem_y + sol_r], fill=dest)
        # Montanhas ao fundo
        draw.polygon([(0, horizonte), (240, horizonte - 170), (520, horizonte)], fill=(30, 41, 68))
        draw.polygon([(430, horizonte), (740, horizonte - 210), (largura, horizonte)], fill=(22, 33, 56))
        # Água / terreno na base
        draw.rectangle([0, horizonte, largura, altura], fill=(15, 58, 92))
        for ry in range(horizonte + 24, altura - 140, 34):
            larg_onda = int(120 + (ry - horizonte) * 0.8)
            draw.rounded_rectangle([largura // 2 - larg_onda, ry, largura // 2 + larg_onda, ry + 8], radius=4, fill=dest)
    else:
        # Composição espacial / abstrata com órbitas e estrelas
        rng = np.random.default_rng(42)
        for _ in range(70):
            sx = int(rng.integers(40, largura - 40))
            sy = int(rng.integers(40, int(altura * 0.72)))
            sr = int(rng.integers(2, 6))
            draw.ellipse([sx - sr, sy - sr, sx + sr, sy + sr], fill=(255, 255, 255))
        draw.ellipse([origem_x - 160, origem_y - 160, origem_x + 160, origem_y + 160], outline=dest, width=5)
        draw.ellipse([origem_x - 110, origem_y - 110, origem_x + 110, origem_y + 110], fill=c1, outline=(255, 255, 255), width=3)

    # Painel inferior escuro semitransparente para título sempre legível
    camada = Image.new("RGBA", (largura, altura), (0, 0, 0, 0))
    d_ov = ImageDraw.Draw(camada)
    d_ov.rounded_rectangle([48, altura - 255, largura - 48, altura - 48], radius=34, fill=(8, 12, 24, 215))
    img = Image.alpha_composite(img.convert("RGBA"), camada).convert("RGB")
    draw = ImageDraw.Draw(img)

    # Moldura externa
    draw.rounded_rectangle([28, 28, largura - 28, altura - 28], radius=40, outline=dest, width=4)

    fonte_badge = carregar_fonte(28, negrito=True)
    fonte_titulo = carregar_fonte(52, negrito=True)
    fonte_sub = carregar_fonte(26, negrito=False)

    # Selo superior RENER
    draw.rounded_rectangle([64, 56, 230, 108], radius=24, fill=(8, 12, 24), outline=dest, width=3)
    draw.text((147, 82), "RENER", fill=dest, font=fonte_badge, anchor="mm")

    # Título em destaque na base
    palavras = assunto.split()
    linhas = []
    atual = ""
    for p in palavras:
        teste = f"{atual} {p}".strip()
        if len(teste) <= 20:
            atual = teste
        else:
            if atual:
                linhas.append(atual)
            atual = p
    if atual:
        linhas.append(atual)

    y_texto = altura - 205
    for linha in linhas[:2]:
        draw.text((largura // 2, y_texto), linha.upper(), fill=(255, 255, 255), font=fonte_titulo, anchor="mm")
        y_texto += 62

    draw.text((largura // 2, altura - 82), "Arte criada direto no Rener", fill=dest, font=fonte_sub, anchor="mm")

    img_final = img.filter(ImageFilter.SMOOTH)
    buf = BytesIO()
    img_final.save(buf, format="PNG")
    return buf.getvalue()


def gerar_video_curto_rener(info_midia: dict, segundos: int = 4, fps: int = 15) -> bytes:
    largura, altura = 720, 720
    arte_base = Image.open(BytesIO(gerar_arte_rener(info_midia, largura + 140, altura + 140))).convert("RGB")
    total_frames = max(15, segundos * fps)
    assunto = info_midia["assunto"]
    dest = info_midia["destaque"]

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        caminho_mp4 = tmp.name

    try:
        writer = imageio.get_writer(caminho_mp4, fps=fps, codec="libx264", quality=7)
        try:
            fonte_rodape = carregar_fonte(26, negrito=True)
            for i in range(total_frames):
                progresso = i / max(1, total_frames - 1)
                dx = int(progresso * 140)
                dy = int((1 - abs(2 * progresso - 1)) * 90)
                frame = arte_base.crop((dx, dy, dx + largura, dy + altura)).convert("RGBA")

                barra = Image.new("RGBA", (largura, altura), (0, 0, 0, 0))
                d = ImageDraw.Draw(barra)
                largura_barra = int((largura - 80) * progresso)
                d.rounded_rectangle([40, altura - 54, largura - 40, altura - 40], radius=7, fill=(255, 255, 255, 70))
                if largura_barra > 8:
                    d.rounded_rectangle([40, altura - 54, 40 + largura_barra, altura - 40], radius=7, fill=(dest[0], dest[1], dest[2], 240))
                d.text((largura // 2, altura - 84), f"Rener • {assunto[:38]}", fill=(255, 255, 255, 245), font=fonte_rodape, anchor="mm")

                final_frame = Image.alpha_composite(frame, barra).convert("RGB")
                writer.append_data(np.array(final_frame))
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
