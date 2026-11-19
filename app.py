import streamlit as st
from groq import Groq

st.set_page_config(page_title="Rener", page_icon="🤖")

st.title("🤖 Rener")
st.write("App rodando com sucesso e conectado automaticamente!")

try:
    api_key = st.secrets["GROQ_API_KEY"]
except Exception:
    st.error("⚠️ Chave de API não configurada! Adicione a GROQ_API_KEY nas configurações do Streamlit.")
    st.stop()

client = Groq(api_key=api_key)

st.sidebar.subheader("🎨 Criação de Mídia")
st.sidebar.link_button("Gerar Imagens com IA", "https://app.leonardo.ai")
st.sidebar.link_button("Criar Vídeos com IA", "https://runwayml.com")

SYSTEM_PROMPT = {
    "role": "system",
    "content": (
        "Você se chama Rener. "
        "Seu criador também se chama Rener, e ele montou este aplicativo junto com o Gemini. "
        "Quando perguntarem quem te criou ou sobre a origem do seu nome, responda exatamente: "
        "'Fui criado pelo Rener em parceria com o Gemini — por isso que meu nome é Rener, homenagem ao meu criador.'"
    ),
}

if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Digite sua pergunta..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Pensando..."):
            try:
                mensagens_enviadas = [SYSTEM_PROMPT] + [
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
