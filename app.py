import base64
from pathlib import Path
from ddgs import DDGS
from groq import Groq
import streamlit as st

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


def pesquisar_na_internet(consulta: str, max_resultados: int = 5) -> str:
    try:
        resultados_texto = []
        with DDGS() as ddgs:
            resultados = list(ddgs.text(consulta, region="br-pt", max_results=max_resultados))
            for idx, r in enumerate(resultados, start=1):
                titulo = r.get("title", "").strip()
                trecho = r.get("body", "").strip()
                link = r.get("href", "").strip()
                resultados_texto.append(f"[{idx}] {titulo}\nResumo: {trecho}\nFonte: {link}")
        return "\n\n".join(resultados_texto) if resultados_texto else ""
    except Exception:
        return ""


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
    api_key = st.secrets["GROQ_API_KEY"]
except Exception:
    st.error("⚠️ Chave de API não configurada! Adicione a GROQ_API_KEY em Settings > Secrets.")
    st.stop()

client = Groq(api_key=api_key)

system_prompt = {
    "role": "system",
    "content": (
        "Você se chama Rener. "
        "Seu criador também se chama Rener, e ele montou este aplicativo junto com o Gemini. "
        "Quando perguntarem quem te criou ou sobre a origem do seu nome, responda exatamente: "
        "'Fui criado pelo Rener em parceria com o Gemini — por isso que meu nome é Rener, homenagem ao meu criador.' "
        "Quando forem fornecidos resultados de pesquisa na internet, use esses dados para responder com precisão, clareza e rapidez, "
        "indicando o que está atualizado ou ao vivo conforme os resultados. Se os resultados não trouxerem um placar em tempo real, avise isso com transparência. "
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
    st.write("Geração e edição de imagens com IA:")
    st.link_button("Abrir Leonardo.ai", "https://app.leonardo.ai", use_container_width=True)
    if st.button("Voltar para o chat"):
        st.session_state.menu_aba = "Chat"
        st.rerun()

elif st.session_state.menu_aba == "Vídeos":
    st.subheader("🎬 Vídeos")
    st.write("Criação de vídeos com IA:")
    st.link_button("Abrir Runway", "https://runwayml.com", use_container_width=True)
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
            st.markdown(message["content"])

    if prompt := st.chat_input("Peça ao Rener"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Pesquisando e respondendo..."):
                try:
                    resultados_web = pesquisar_na_internet(prompt)
                    mensagens_enviadas = [system_prompt] + [
                        {"role": m["role"], "content": m["content"]} for m in st.session_state.messages[:-1]
                    ]

                    if resultados_web:
                        mensagem_com_busca = (
                            f"Pergunta do usuário: {prompt}\n\n"
                            f"Resultados rápidos encontrados na internet:\n{resultados_web}\n\n"
                            "Responda de forma direta e útil com base nesses resultados."
                        )
                    else:
                        mensagem_com_busca = prompt

                    mensagens_enviadas.append({"role": "user", "content": mensagem_com_busca})

                    chat_completion = client.chat.completions.create(
                        model="openai/gpt-oss-20b",
                        messages=mensagens_enviadas,
                    )
                    response = chat_completion.choices[0].message.content
                    st.markdown(response)
                    st.session_state.messages.append({"role": "assistant", "content": response})
                except Exception as e:
                    st.error(f"Erro: {e}")
