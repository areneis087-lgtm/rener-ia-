import streamlit as st
from groq import Groq

st.set_page_config(page_title="Meu App de IA", page_icon="🤖")

st.title("🤖 Meu Assistente de IA")
st.write("App rodando com sucesso e conectado automaticamente!")

# Puxa a chave de forma segura direto das configurações do Streamlit
try:
    api_key = st.secrets["GROQ_API_KEY"]
except Exception:
    st.error("⚠️ Chave de API não configurada! Adicione a GROQ_API_KEY nas configurações do Streamlit.")
    st.stop()

client = Groq(api_key=api_key)

# Barra lateral com os atalhos de mídia que criamos antes
st.sidebar.subheader("🎨 Criação de Mídia")
st.sidebar.link_button("Gerar Imagens com IA", "https://app.leonardo.ai")
st.sidebar.link_button("Criar Vídeos com IA", "https://runwayml.com")

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
                chat_completion = client.chat.completions.create(
                    model="openai/gpt-oss-20b",
                    messages=[{"role": m["role"], "content": m["content"]} for m in st.session_state.messages],
                )
                response = chat_completion.choices[0].message.content
                st.markdown(response)
                st.session_state.messages.append({"role": "assistant", "content": response})
            except Exception as e:
                st.error(f"Erro: {e}")
