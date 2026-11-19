import streamlit as st
from groq import Groq

st.set_page_config(page_title="Rener", page_icon="✨", layout="centered")

st.markdown(
    """
    <style>
        .stApp {
            background: radial-gradient(circle at 50% 20%, #0d1d42 0%, #050507 62%);
            color: #f3f4f6;
        }
        [data-testid="stSidebar"] {
            background-color: #090a0d;
            border-right: 1px solid rgba(255, 255, 255, 0.08);
        }
        .hero-box {
            text-align: center;
            padding: 36px 12px 24px 12px;
        }
        .hero-sparkle {
            font-size: 36px;
            margin-bottom: 10px;
        }
        .hero-title {
            font-size: 28px;
            font-weight: 600;
            color: #ffffff;
            margin: 0;
        }
        .hero-sub {
            font-size: 14px;
            color: #9ca3af;
            margin-top: 6px;
        }

        /* Rodapé transparente */
        [data-testid="stBottom"],
        [data-testid="stBottom"] > div,
        [data-testid="stBottom"] > div > div {
            background: transparent !important;
            background-color: transparent !important;
            border: none !important;
            box-shadow: none !important;
        }

        /* Contorno branco bem visível no bloco de entrada */
        [data-testid="stChatInput"] {
            background-color: #141926 !important;
            border: 2px solid #ffffff !important;
            border-radius: 999px !important;
            padding: 4px 10px 4px 16px !important;
            box-shadow: 0 0 12px rgba(255, 255, 255, 0.25) !important;
        }

        [data-testid="stChatInput"] > div,
        [data-testid="stChatInput"] > div > div,
        [data-testid="stChatInput"] [data-baseweb="textarea"],
        [data-testid="stChatInput"] [data-baseweb="base-input"] {
            background: transparent !important;
            background-color: transparent !important;
            border: none !important;
            box-shadow: none !important;
        }

        [data-testid="stChatInput"] textarea {
            background: transparent !important;
            background-color: transparent !important;
            color: #ffffff !important;
            caret-color: #ffffff !important;
            font-size: 15px !important;
            border: none !important;
            box-shadow: none !important;
        }

        [data-testid="stChatInput"] textarea::placeholder {
            color: #e2e8f0 !important;
            opacity: 1 !important;
        }

        [data-testid="stChatInput"] button {
            background-color: #2563eb !important;
            color: #ffffff !important;
            border-radius: 999px !important;
            border: 1.5px solid #ffffff !important;
            min-width: 38px !important;
            height: 38px !important;
        }

        [data-testid="stChatInput"] button:hover {
            background-color: #3b82f6 !important;
        }

        [data-testid="stChatMessage"] {
            background-color: rgba(30, 41, 59, 0.55);
            border: 1px solid rgba(255, 255, 255, 0.22);
            border-radius: 20px;
            padding: 10px 14px;
            margin-bottom: 8px;
        }
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
            with st.spinner("Pensando..."):
                try:
                    mensagens_enviadas = [system_prompt] + [
                        {"role": m["role"], "content": m["content"]} for m in st.session_state.messages
                    ]
                    chat_completion = client.chat.completions.create(
                        model="openai/gpt-oss-20b",
                        messages=mensagens_enviadas,
                    )
                    response = chat_completion.choices[0].message.content
                    st.markdown(response)
                    st.session_state.messages.append({"role": "assistant", "content": response})
                except Exception as e:
                    st.error(f"Erro: {e}")
