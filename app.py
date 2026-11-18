import streamlit as st
from groq import Groq

st.set_page_config(page_title="Meu App de IA", page_icon="🤖")

st.title("🤖 Meu Assistente de IA")
st.write("App atualizado e funcionando!")

# Campo para inserir a chave na barra lateral
api_key_input = st.sidebar.text_input("Insira sua API Key do Groq", type="password")

if not api_key_input:
    st.info("👉 Insira sua chave do Groq (começa com gsk_) na barra lateral para começar.")
    st.stop()

try:
    client = Groq(api_key=api_key_input)
except Exception as e:
    st.error(f"Erro ao inicializar o cliente Groq: {e}")
    st.stop()

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
                    model="llama-3.3-70b-versatile",
                    messages=[{"role": m["role"], "content": m["content"]} for m in st.session_state.messages],
                )
                response = chat_completion.choices[0].message.content
                st.markdown(response)
                st.session_state.messages.append({"role": "assistant", "content": response})
            except Exception as e:
                st.error(f"Erro na API do Groq: {e}")
