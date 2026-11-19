
import base64
import json
import re
import tempfile
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from urllib.parse import quote, quote_plus

import imageio.v2 as imageio
import numpy as np
import requests
import streamlit as st

from PIL import Image, ImageDraw, ImageFilter
from groq import Groq
from tavily import TavilyClient
from ddgs import DDGS


# =========================================================
# CONFIGURAÇÃO
# =========================================================

st.set_page_config(
    page_title="Rener AI",
    page_icon="✨",
    layout="centered"
)

MODELOS_IMAGEM = {
    "Flux 2 Pro": "black-forest-labs/flux.2-pro",
    "Flux 2 Max": "black-forest-labs/flux.2-max",
    "GPT Image 2": "openai/gpt-image-2",
    "Gemini 3 Pro Image": "google/gemini-3-pro-image",
    "Seedream 5 Pro": "bytedance/seedream-5.0-pro",
    "Ideogram Quality": "ideogram-ai/ideogram-v4-quality",
    "Flux Schnell": "black-forest-labs/flux.1-schnell",
}


# =========================================================
# CHAVES
# =========================================================

def obter_secret(nome):
    try:
        return str(st.secrets.get(nome, "")).strip()
    except Exception:
        return ""


GROQ_API_KEY = obter_secret("GROQ_API_KEY")
TAVILY_API_KEY = obter_secret("TAVILY_API_KEY")
POLLINATIONS_API_KEY = obter_secret("POLLINATIONS_API_KEY")


# =========================================================
# ESTADO DO APLICATIVO
# =========================================================

PADROES = {
    "messages": [],
    "menu_aba": "Chat",
    "notebooks": ["Criação de Aplicativo de IA"],
    "programados": [],
    "estilo_rener": "Amigável e direto",
    "ultima_imagem_gerada": None,
    "ultimo_video_gerado": None,
    "modelo_imagem": "black-forest-labs/flux.2-pro",
}

for chave, valor in PADROES.items():
    if chave not in st.session_state:
        st.session_state[chave] = valor


# =========================================================
# FUNDO PERSONALIZADO
# =========================================================

def encontrar_e_carregar_fundo():

    candidatos = [
        Path("fundo.png"),
        Path("fundo.jpg"),
        Path("fundo.jpeg"),
        Path("fundo.webp"),
        Path("1000426462_2.png"),
        Path("1000426462.png"),
    ]

    for caminho in candidatos:
        if caminho.exists() and caminho.is_file():
            dados = caminho.read_bytes()
            b64 = base64.b64encode(dados).decode()
            ext = caminho.suffix.lower().lstrip(".")

            mime = (
                "image/jpeg"
                if ext in ("jpg", "jpeg")
                else f"image/{ext}"
            )

            return f"data:{mime};base64,{b64}"

    return ""


bg_data_uri = encontrar_e_carregar_fundo()

if bg_data_uri:
    fundo_css = f"""
    .stApp {{
        background:
        linear-gradient(
            rgba(5,8,17,0.42),
            rgba(5,8,17,0.56)
        ),
        url("{bg_data_uri}") center/cover fixed;
    }}
    """
else:
    fundo_css = """
    .stApp {
        background:
        radial-gradient(
            circle at 50% 20%,
            #0d1d42 0%,
            #050507 62%
        );
    }
"""


st.markdown(
    f"""
    <style>
    {fundo_css}

    html, body {{
        scroll-behavior: smooth;
    }}

    [data-testid="stMainBlockContainer"] {{
        padding-bottom: 110px;
    }}

    [data-testid="stSidebar"] {{
        background-color: #090a0d;
        border-right: 1px solid #252525;
    }}

    .hero-box {{
        text-align: center;
        padding: 36px 16px 24px;
        background: rgba(5,8,17,.82);
        border: 1px solid rgba(255,255,255,.12);
        border-radius: 24px;
        backdrop-filter: blur(8px);
    }}

    .hero-sparkle {{
        font-size: 36px;
    }}

    .hero-title {{
        font-size: 28px;
        font-weight: 700;
        color: white;
        margin: 0;
    }}

    .hero-sub {{
        color: #cbd5e1;
        font-size: 14px;
    }}

    [data-testid="stChatMessage"] {{
        background: transparent !important;
        border: none !important;
    }}

    [data-testid="stChatInput"] {{
        background: rgba(14,19,32,.95) !important;
        border: 2px solid white !important;
        border-radius: 999px !important;
        box-shadow: 0 0 14px rgba(255,255,255,.2);
    }}

    [data-testid="stChatInput"] textarea {{
        color: white !important;
        background: transparent !important;
    }}

    [data-testid="stChatInput"] textarea::placeholder {{
        color: #e2e8f0 !important;
    }}

    </style>
    """,
    unsafe_allow_html=True
)


# =========================================================
# CLIENTE GROQ
# =========================================================

if not GROQ_API_KEY:
    st.error(
        "Configure GROQ_API_KEY nos Secrets do Streamlit."
    )
    st.stop()

client = Groq(api_key=GROQ_API_KEY)


# =========================================================
# DETECÇÃO DE IMAGENS E VÍDEOS
# =========================================================

def detectar_pedido_midia(texto):

    t = texto.lower().strip()

    palavras_video = (
        "vídeo", "video", "clipe",
        "animação", "animacao",
        "faz um vídeo", "cria um vídeo",
        "gere um vídeo", "crie um vídeo",
    )

    if any(p in t for p in palavras_video):
        return "video"

    palavras_imagem = (
        "imagem", "foto", "ilustração",
        "ilustracao", "desenho", "arte",
        "gere uma", "gera uma",
        "crie uma", "cria uma",
        "faça uma", "faz uma",
        "gere um", "gera um",
        "crie um", "cria um",
        "faça um", "faz um",
    )

    if any(p in t for p in palavras_imagem):
        return "image"

    return ""


# =========================================================
# DIRETOR ARTÍSTICO DO RENER
# =========================================================

def planejar_cena_com_ia(
    client,
    pedido_usuario,
    tipo_midia
):

    pedido = pedido_usuario.lower()

    fallback = {
        "prompt_visual": (
            f"{pedido_usuario}, professional cinematic artwork, "
            "photorealistic, ultra detailed, sharp focus, "
            "professional lighting, realistic materials, "
            "beautiful composition, high quality"
        ),
        "cor_a": (25, 35, 55),
        "cor_b": (15, 20, 32),
        "cor_c": (220, 38, 38),
    }

    # Direção especial para o Flamengo
    if any(
        palavra in pedido
        for palavra in [
            "flamengo",
            "mengão",
            "mengao",
            "rubro-negro",
        ]
    ):

        fallback["prompt_visual"] = (
            "Epic photorealistic Flamengo football club artwork. "
            "A luxurious red and black horizontal striped satin flag "
            "waving dramatically, realistic fabric folds, "
            "embroidered white CRF monogram inspired by Clube de "
            "Regatas do Flamengo, golden five-pointed star above "
            "the emblem, dramatic cinematic lighting, deep black "
            "shadows, vivid red highlights, premium sports poster, "
            "extremely detailed fabric texture, professional "
            "composition, sharp focus, realistic materials. "
            "No random lettering, no unwanted watermark."
        )

        return fallback

    try:

        resposta = client.chat.completions.create(
            model="openai/gpt-oss-20b",
            tool_choice="none",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Você é o diretor artístico profissional "
                        "do Rener AI. Transforme pedidos simples "
                        "em prompts de imagem extremamente "
                        "detalhados em inglês. "
                        "Priorize qualidade visual, realismo, "
                        "iluminação cinematográfica, texturas, "
                        "profundidade e composição profissional. "
                        "Preserve escudos, logotipos, símbolos, "
                        "emblemas e textos quando solicitados. "
                        "Não proíba logos quando forem pedidos. "
                        "Retorne somente JSON válido com as chaves "
                        "prompt_visual, cor_a, cor_b e cor_c."
                    )
                },
                {
                    "role": "user",
                    "content": (
                        f"Tipo: {tipo_midia}. "
                        f"Pedido: {pedido_usuario}"
                    )
                }
            ]
        )

        conteudo = (
            resposta.choices[0].message.content or ""
        ).strip()

        match = re.search(
            r"\{.*\}",
            conteudo,
            re.DOTALL
        )

        if match:

            dados = json.loads(match.group(0))

            def cor_valida(valor, padrao):
                try:
                    cor = tuple(
                        max(0, min(255, int(x)))
                        for x in valor[:3]
                    )
                    return cor if len(cor) == 3 else padrao
                except Exception:
                    return padrao

            return {
                "prompt_visual": str(
                    dados.get("prompt_visual")
                    or fallback["prompt_visual"]
                ),
                "cor_a": cor_valida(
                    dados.get("cor_a", []),
                    fallback["cor_a"]
                ),
                "cor_b": cor_valida(
                    dados.get("cor_b", []),
                    fallback["cor_b"]
                ),
                "cor_c": cor_valida(
                    dados.get("cor_c", []),
                    fallback["cor_c"]
                ),
            }

    except Exception:
        pass

    return fallback


# =========================================================
# GERADOR DE IMAGENS DE ALTA QUALIDADE
# =========================================================

def gerar_imagem_alta_qualidade(
    info_cena,
    largura=1024,
    altura=1024
):

    if not POLLINATIONS_API_KEY:
        raise RuntimeError(
            "POLLINATIONS_API_KEY não configurada. "
            "Adicione a chave nos Secrets do Streamlit."
        )

    prompt = info_cena.get(
        "prompt_visual",
        "Professional photorealistic artwork"
    )

    modelo = st.session_state.modelo_imagem

    url = (
        "https://gen.pollinations.ai/image/"
        + quote(prompt, safe="")
    )

    parametros = {
        "model": modelo,
        "width": largura,
        "height": altura,
        "enhance": "true",
        "nologo": "true",
        "private": "true",
    }

    headers = {
        "Authorization": (
            f"Bearer {POLLINATIONS_API_KEY}"
        ),
        "User-Agent": "Rener-AI/2.0",
    }

    try:

        resposta = requests.get(
            url,
            params=parametros,
            headers=headers,
            timeout=(20, 240)
        )

        if resposta.status_code == 401:
            raise RuntimeError(
                "Chave Pollinations inválida ou sem autorização."
            )

        if resposta.status_code == 402:
            raise RuntimeError(
                "Saldo ou orçamento da API insuficiente."
            )

        resposta.raise_for_status()

        imagem = Image.open(
            BytesIO(resposta.content)
        )

        imagem.verify()

        imagem = Image.open(
            BytesIO(resposta.content)
        ).convert("RGB")

        if imagem.width < 256 or imagem.height < 256:
            raise RuntimeError(
                "A API retornou uma imagem com resolução insuficiente."
            )

        buffer = BytesIO()

        imagem.save(
            buffer,
            format="PNG",
            optimize=True
        )

        return buffer.getvalue()

    except requests.exceptions.Timeout:
        raise RuntimeError(
            "A geração demorou demais. Tente novamente."
        )

    except requests.exceptions.RequestException as erro:
        raise RuntimeError(
            f"Erro na API de imagens: {erro}"
        )

    except Exception as erro:
        if isinstance(erro, RuntimeError):
            raise

        raise RuntimeError(
            f"Não foi possível processar a imagem: {erro}"
        )


# =========================================================
# GERADOR DE VÍDEO CURTO
# =========================================================

def gerar_video_curto_rener(
    info_cena,
    segundos=4,
    fps=15
):

    largura = 720
    altura = 720

    imagem_bytes = gerar_imagem_alta_qualidade(
        info_cena,
        largura + 140,
        altura + 140
    )

    arte = Image.open(
        BytesIO(imagem_bytes)
    ).convert("RGB")

    arte = arte.resize(
        (largura + 140, altura + 140)
    )

    total_frames = max(
        15,
        segundos * fps
    )

    with tempfile.NamedTemporaryFile(
        suffix=".mp4",
        delete=False
    ) as tmp:

        caminho = Path(tmp.name)

    try:

        writer = imageio.get_writer(
            str(caminho),
            fps=fps,
            codec="libx264",
            quality=7
        )

        try:

            for i in range(total_frames):

                progresso = (
                    i / max(1, total_frames - 1)
                )

                dx = int(progresso * 140)

                dy = int(
                    (
                        1 - abs(2 * progresso - 1)
                    ) * 90
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

        return caminho.read_bytes()

    finally:

        try:
            caminho.unlink(missing_ok=True)
        except Exception:
            pass


# =========================================================
# PESQUISA NA INTERNET
# =========================================================

def precisa_pesquisar_na_web(consulta):

    texto = consulta.strip().lower()

    gatilhos = (
        "jogo", "placar", "resultado",
        "gol", "gols", "ao vivo",
        "partida", "notícia", "noticia",
        "hoje", "ontem", "amanhã", "amanha",
        "agora", "últimas", "ultimas",
        "preço", "preco", "cotação",
        "cotacao", "clima", "tempo",
        "quem ganhou", "quem venceu",
        "campeonato", "tabela",
        "pesquise", "pesquisa",
        "procure", "na internet",
        "no google",
    )

    return any(p in texto for p in gatilhos)


def eh_consulta_esportiva(consulta):

    gatilhos = (
        "jogo", "placar", "resultado",
        "gol", "gols", "ontem",
        "hoje", "ao vivo", "partida",
        "notícia", "noticia",
    )

    return any(
        p in consulta.lower()
        for p in gatilhos
    )


def montar_query_com_datas(consulta):

    agora = datetime.now()

    ontem = agora - timedelta(days=1)

    texto = consulta.strip()

    if "ontem" in texto.lower():
        texto += " " + ontem.strftime("%d/%m/%Y")

    if "hoje" in texto.lower():
        texto += " " + agora.strftime("%d/%m/%Y")

    if eh_consulta_esportiva(texto):
        texto += " placar resultado gols"

    return texto


def buscar_com_tavily(consulta):

    if not TAVILY_API_KEY:
        return ""

    try:

        tavily = TavilyClient(
            api_key=TAVILY_API_KEY
        )

        tempo_real = eh_consulta_esportiva(
            consulta
        )

        kwargs = {
            "query": montar_query_com_datas(consulta),
            "topic": "news" if tempo_real else "general",
            "search_depth": (
                "advanced" if tempo_real else "basic"
            ),
            "max_results": 5,
            "include_answer": True,
            "include_raw_content": tempo_real,
        }

        if tempo_real:
            kwargs["days"] = 3

        resposta = tavily.search(**kwargs)

        blocos = []

        resumo = (
            resposta.get("answer") or ""
        ).strip()

        if resumo:
            blocos.append(
                "[Resumo da pesquisa]\n" + resumo
            )

        for item in resposta.get("results", []):

            titulo = item.get("title", "")
            conteudo = item.get("content", "")
            link = item.get("url", "")

            blocos.append(
                f"Título: {titulo}\n"
                f"Resumo: {conteudo}\n"
                f"Fonte: {link}"
            )

        return "\n\n".join(blocos)

    except Exception:
        return ""


def buscar_ddgs(consulta):

    resultados = []

    try:

        with DDGS() as ddgs:

            itens = list(
                ddgs.text(
                    consulta,
                    region="br-pt",
                    max_results=5
                )
            )

            for item in itens:

                resultados.append(
                    f"Título: {item.get('title', '')}\n"
                    f"Resumo: {item.get('body', '')}\n"
                    f"Fonte: {item.get('href', '')}"
                )

    except Exception:
        pass

    return resultados


def buscar_google_noticias(consulta):

    resultados = []

    try:

        url = (
            "https://news.google.com/rss/search?q="
            + quote_plus(consulta)
            + "&hl=pt-BR&gl=BR&ceid=BR:pt-419"
        )

        resposta = requests.get(
            url,
            timeout=10,
            headers={
                "User-Agent": "Mozilla/5.0"
            }
        )

        if resposta.status_code == 200:

            import xml.etree.ElementTree as ET

            root = ET.fromstring(resposta.text)

            for item in root.findall(".//item")[:5]:

                titulo = (
                    item.findtext("title") or ""
                ).strip()

                link = (
                    item.findtext("link") or ""
                ).strip()

                data = (
                    item.findtext("pubDate") or ""
                ).strip()

                if titulo:

                    resultados.append(
                        f"Notícia: {titulo}\n"
                        f"Data: {data}\n"
                        f"Fonte: {link}"
                    )

    except Exception:
        pass

    return resultados


def pesquisar_na_internet(consulta):

    tavily = buscar_com_tavily(consulta)

    if tavily:
        return tavily

    consulta = montar_query_com_datas(
        consulta
    )

    resultados = []

    resultados.extend(
        buscar_google_noticias(consulta)
    )

    resultados.extend(
        buscar_ddgs(consulta)
    )

    return "\n\n".join(resultados[:8])


# =========================================================
# PROMPT PRINCIPAL DA IA
# =========================================================

agora = datetime.now()

data_atual = agora.strftime("%d/%m/%Y")

ontem_data = (
    agora - timedelta(days=1)
).strftime("%d/%m/%Y")


def criar_system_prompt():

    return {
        "role": "system",
        "content": (
            f"Você se chama Rener. "
            f"Data de hoje: {data_atual}. "
            f"Data de ontem: {ontem_data}. "

            "Seu criador também se chama Rener, "
            "e ele montou este aplicativo junto com o Gemini. "

            "Quando perguntarem quem te criou, responda: "
            "'Fui criado pelo Rener em parceria com o Gemini.' "

            "Converse com naturalidade, autonomia e espontaneidade. "

            "Entenda o contexto da conversa. "
            "Não invente informações, notícias ou resultados. "

            "Quando o usuário enviar uma notícia ou comentar "
            "um acontecimento, acompanhe a conversa naturalmente. "

            "Quando receber dados de pesquisa, utilize-os "
            "com responsabilidade. "

            "Seu objetivo é ajudar com criatividade, "
            "clareza e inteligência. "

            f"Estilo atual: {st.session_state.estilo_rener}."
        )
    }


# =========================================================
# BARRA LATERAL
# =========================================================

with st.sidebar:

    st.markdown("### ✨ Rener AI")

    if st.button(
        "✏️ Nova conversa",
        use_container_width=True
    ):

        st.session_state.messages = []
        st.session_state.menu_aba = "Chat"

        st.rerun()

    st.divider()

    opcoes_menu = [
        ("💬 Chat", "Chat"),
        ("🗂️ Biblioteca", "Biblioteca"),
        ("🖼️ Imagens", "Imagens"),
        ("⏰ Programado", "Programado"),
        ("⚙️ Personalizar", "Personalizar"),
        ("🎬 Vídeos", "Vídeos"),
    ]

    for titulo, aba in opcoes_menu:

        if st.button(
            titulo,
            use_container_width=True
        ):

            st.session_state.menu_aba = aba
            st.rerun()

    st.divider()

    st.markdown("**Notebooks**")

    novo_nb = st.text_input(
        "Nome do notebook",
        placeholder="Ex: Ideias do aplicativo",
        label_visibility="collapsed"
    )

    if st.button(
        "➕ Novo notebook",
        use_container_width=True
    ):

        if novo_nb.strip():

            st.session_state.notebooks.append(
                novo_nb.strip()
            )

            st.rerun()

    for notebook in st.session_state.notebooks:
        st.caption("• " + notebook)

    st.divider()

    st.caption("Criado por Rener")


# =========================================================
# ABA BIBLIOTECA
# =========================================================

if st.session_state.menu_aba == "Biblioteca":

    st.subheader("🗂️ Biblioteca")

    if st.session_state.messages:

        for mensagem in st.session_state.messages:

            with st.container():

                st.markdown(
                    f"**{mensagem['role'].title()}:**"
                )

                if mensagem.get("content"):
                    st.markdown(mensagem["content"])

                if mensagem.get("image"):
                    st.image(
                        mensagem["image"],
                        use_container_width=True
                    )

                if mensagem.get("video"):
                    st.video(mensagem["video"])

    else:

        st.info(
            "Nenhuma mensagem salva na conversa atual."
        )

    if st.button("Voltar para o chat"):
        st.session_state.menu_aba = "Chat"
        st.rerun()


# =========================================================
# ABA IMAGENS
# =========================================================

elif st.session_state.menu_aba == "Imagens":

    st.subheader("🖼️ Gerador de imagens Rener")

    st.write(
        "Crie imagens realistas, artísticas, "
        "esportivas e cinematográficas."
    )

    prompt_img = st.text_area(
        "O que você quer criar?",
        placeholder=(
            "Ex: Uma bandeira do Flamengo "
            "com o escudo CRF e uma estrela dourada."
        )
    )

    modelo_nome = st.selectbox(
        "Modelo de geração",
        list(MODELOS_IMAGEM.keys()),
        index=0
    )

    resolucao = st.selectbox(
        "Resolução",
        [
            "1024 x 1024",
            "1536 x 1024",
            "1024 x 1536",
        ]
    )

    if st.button(
        "✨ Criar imagem",
        use_container_width=True
    ):

        if not prompt_img.strip():

            st.warning(
                "Digite o que você deseja criar."
            )

        else:

            try:

                with st.spinner(
                    "O Rener está criando sua imagem..."
                ):

                    st.session_state.modelo_imagem = (
                        MODELOS_IMAGEM[modelo_nome]
                    )

                    largura, altura = map(
                        int,
                        resolucao.split(" x ")
                    )

                    info = planejar_cena_com_ia(
                        client,
                        prompt_img,
                        "imagem"
                    )

                    imagem = gerar_imagem_alta_qualidade(
                        info,
                        largura,
                        altura
                    )

                    st.session_state.ultima_imagem_gerada = imagem

                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": "Imagem criada pelo Rener.",
                        "image": imagem,
                    })

                st.success("Imagem criada!")

            except Exception as erro:

                st.error(str(erro))

    if st.session_state.ultima_imagem_gerada:

        imagem = st.session_state.ultima_imagem_gerada

        st.image(
            imagem,
            use_container_width=True
        )

        st.download_button(
            "⬇️ Baixar imagem PNG",
            data=imagem,
            file_name="rener_imagem.png",
            mime="image/png",
            use_container_width=True
        )


# =========================================================
# ABA VÍDEOS
# =========================================================

elif st.session_state.menu_aba == "Vídeos":

    st.subheader("🎬 Vídeos do Rener")

    st.info(
        "Esta versão cria um vídeo MP4 com movimento "
        "de câmera a partir de uma imagem gerada. "
        "Não é animação completa de personagens."
    )

    prompt_vid = st.text_input(
        "O que você quer no vídeo?",
        placeholder="Ex: Uma bandeira do Flamengo"
    )

    duracao = st.slider(
        "Duração em segundos",
        2,
        6,
        4
    )

    if st.button(
        "🎥 Criar vídeo",
        use_container_width=True
    ):

        if prompt_vid.strip():

            try:

                with st.spinner(
                    "Criando vídeo..."
                ):

                    info = planejar_cena_com_ia(
                        client,
                        prompt_vid,
                        "vídeo curto"
                    )

                    video = gerar_video_curto_rener(
                        info,
                        segundos=duracao
                    )

                    st.session_state.ultimo_video_gerado = video

                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": "Vídeo criado pelo Rener.",
                        "video": video,
                    })

                st.success("Vídeo criado!")

            except Exception as erro:

                st.error(str(erro))

    if st.session_state.ultimo_video_gerado:

        video = st.session_state.ultimo_video_gerado

        st.video(video)

        st.download_button(
            "⬇️ Baixar vídeo MP4",
            data=video,
            file_name="rener_video.mp4",
            mime="video/mp4",
            use_container_width=True
        )


# =========================================================
# ABA PROGRAMADO
# =========================================================

elif st.session_state.menu_aba == "Programado":

    st.subheader("⏰ Programado")

    tarefa = st.text_input(
        "Adicionar lembrete ou tarefa"
    )

    if st.button("Salvar tarefa"):

        if tarefa.strip():

            st.session_state.programados.append(
                tarefa.strip()
            )

            st.success("Tarefa salva!")

    for item in st.session_state.programados:

        st.write("• " + item)


# =========================================================
# ABA PERSONALIZAR
# =========================================================

elif st.session_state.menu_aba == "Personalizar":

    st.subheader("⚙️ Personalizar Rener")

    estilos = [
        "Amigável e direto",
        "Detalhado e técnico",
        "Criativo e descontraído",
    ]

    estilo = st.selectbox(
        "Como o Rener deve responder?",
        estilos,
        index=estilos.index(
            st.session_state.estilo_rener
        )
    )

    if st.button("Salvar preferência"):

        st.session_state.estilo_rener = estilo

        st.success("Preferência salva!")


# =========================================================
# ABA CHAT
# =========================================================

else:

    if not st.session_state.messages:

        st.markdown(
            """
            <div class="hero-box">
                <div class="hero-sparkle">✦</div>
                <p class="hero-title">
                    Olá! Vamos começar?
                </p>
                <p class="hero-sub">
                    Rener AI • Seu assistente inteligente
                </p>
            </div>
            """,
            unsafe_allow_html=True
        )

    # Histórico
    for mensagem in st.session_state.messages:

        with st.chat_message(mensagem["role"]):

            if mensagem.get("content"):
                st.markdown(mensagem["content"])

            if mensagem.get("image"):
                st.image(
                    mensagem["image"],
                    use_container_width=True
                )

            if mensagem.get("video"):
                st.video(mensagem["video"])

    # Entrada do usuário
    if prompt := st.chat_input("Peça ao Rener..."):

        st.session_state.messages.append({
            "role": "user",
            "content": prompt
        })

        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):

            tipo_midia = detectar_pedido_midia(
                prompt
            )

            # GERAÇÃO DE IMAGEM
            if tipo_midia == "image":

                try:

                    with st.spinner(
                        "Criando imagem em alta qualidade..."
                    ):

                        info = planejar_cena_com_ia(
                            client,
                            prompt,
                            "imagem"
                        )

                        imagem = gerar_imagem_alta_qualidade(
                            info
                        )

                        st.session_state.ultima_imagem_gerada = imagem

                    st.markdown("Aqui está sua imagem:")

                    st.image(
                        imagem,
                        use_container_width=True
                    )

                    st.download_button(
                        "⬇️ Baixar imagem",
                        data=imagem,
                        file_name="rener_imagem.png",
                        mime="image/png"
                    )

                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": "Aqui está sua imagem:",
                        "image": imagem
                    })

                except Exception as erro:

                    st.error(str(erro))

            # GERAÇÃO DE VÍDEO
            elif tipo_midia == "video":

                try:

                    with st.spinner(
                        "Criando vídeo curto..."
                    ):

                        info = planejar_cena_com_ia(
                            client,
                            prompt,
                            "vídeo curto"
                        )

                        video = gerar_video_curto_rener(
                            info,
                            segundos=4
                        )

                        st.session_state.ultimo_video_gerado = video

                    st.markdown("Aqui está seu vídeo:")

                    st.video(video)

                    st.download_button(
                        "⬇️ Baixar vídeo",
                        data=video,
                        file_name="rener_video.mp4",
                        mime="video/mp4"
                    )

                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": "Aqui está seu vídeo:",
                        "video": video
                    })

                except Exception as erro:

                    st.error(str(erro))

            # CONVERSA NORMAL
            else:

                try:

                    with st.spinner("Rener está pensando..."):

                        mensagens = [
                            criar_system_prompt()
                        ]

                        for mensagem in (
                            st.session_state.messages[:-1]
                        ):

                            if mensagem.get("content"):

                                mensagens.append({
                                    "role": mensagem["role"],
                                    "content": mensagem["content"]
                                })

                        mensagem_usuario = prompt

                        if precisa_pesquisar_na_web(prompt):

                            resultado = pesquisar_na_internet(
                                prompt
                            )

                            if resultado:

                                mensagem_usuario = (
                                    f"Mensagem do usuário:\n{prompt}\n\n"
                                    f"Informações encontradas na internet:\n"
                                    f"{resultado}\n\n"
                                    "Responda naturalmente. "
                                    "Não invente informações. "
                                    "Diferencie fatos confirmados "
                                    "de informações não verificadas."
                                )

                        mensagens.append({
                            "role": "user",
                            "content": mensagem_usuario
                        })

                        resposta = client.chat.completions.create(
                            model="openai/gpt-oss-20b",
                            messages=mensagens,
                            tool_choice="none"
                        )

                        texto = (
                            resposta.choices[0].message.content
                            or "Não consegui gerar uma resposta."
                        )

                    st.markdown(texto)

                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": texto
                    })

                except Exception as erro:

                    st.error(
                        f"Erro ao responder: {erro}"
                    )
