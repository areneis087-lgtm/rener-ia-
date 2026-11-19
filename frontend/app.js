// URL pública do backend FastAPI no Render
const API_BASE_URL =
  window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1"
    ? "http://localhost:8000"
    : "https://rener-ia.onrender.com";

const heroEl = document.getElementById("hero");
const messagesEl = document.getElementById("messages");
const chatAreaEl = document.getElementById("chat-area");
const formEl = document.getElementById("chat-form");
const inputEl = document.getElementById("prompt-input");
const micBtn = document.getElementById("mic-btn");
const sendBtn = document.getElementById("send-btn");
const newChatBtn = document.getElementById("btn-new-chat");
const hintEl = document.getElementById("recording-hint");
const statusEl = document.getElementById("api-status");

let history = [];
let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;

function scrollToBottom() {
  chatAreaEl.scrollTop = chatAreaEl.scrollHeight;
}

function appendMessage(role, { content = "", imageBase64 = "", videoBase64 = "" }) {
  heroEl.classList.add("hidden");

  const div = document.createElement("div");
  div.className = `msg ${role}`;

  if (content) {
    const p = document.createElement("div");
    p.textContent = content;
    div.appendChild(p);
  }

  if (imageBase64) {
    const img = document.createElement("img");
    img.src = `data:image/png;base64,${imageBase64}`;
    img.alt = "Imagem gerada pelo Rener";
    div.appendChild(img);
  }

  if (videoBase64) {
    const video = document.createElement("video");
    video.src = `data:video/mp4;base64,${videoBase64}`;
    video.controls = true;
    video.playsInline = true;
    div.appendChild(video);
  }

  messagesEl.appendChild(div);
  scrollToBottom();
  return div;
}

async function enviarMensagem(texto) {
  const limpo = (texto || "").trim();
  if (!limpo) return;

  appendMessage("user", { content: limpo });
  const historicoAtual = [...history];
  history.push({ role: "user", content: limpo, has_image: false, has_video: false });

  inputEl.value = "";
  inputEl.style.height = "auto";
  sendBtn.disabled = true;

  const loadingBubble = appendMessage("assistant", { content: "Pensando..." });

  try {
    const resp = await fetch(`${API_BASE_URL}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: limpo,
        history: historicoAtual,
        style: "Amigável e direto",
      }),
    });

    const data = await resp.json();
    loadingBubble.remove();

    if (!resp.ok) {
      throw new Error(data.detail || "Falha ao falar com o Rener.");
    }

    if (data.type === "image" && data.image_base64) {
      appendMessage("assistant", { content: data.reply || "Aqui está:", imageBase64: data.image_base64 });
      history.push({ role: "assistant", content: data.reply || "Aqui está:", has_image: true, has_video: false });
    } else if (data.type === "video" && data.video_base64) {
      appendMessage("assistant", { content: data.reply || "Aqui está:", videoBase64: data.video_base64 });
      history.push({ role: "assistant", content: data.reply || "Aqui está:", has_image: false, has_video: true });
    } else {
      const replyText = data.reply || "";
      appendMessage("assistant", { content: replyText });
      history.push({ role: "assistant", content: replyText, has_image: false, has_video: false });
    }
  } catch (err) {
    loadingBubble.remove();
    appendMessage("assistant", { content: `Erro: ${err.message}` });
  } finally {
    sendBtn.disabled = false;
  }
}

async function enviarAudioParaTranscricao(blob) {
  hintEl.textContent = "Transcrevendo sua voz...";
  hintEl.classList.remove("hidden");

  try {
    const formData = new FormData();
    formData.append("file", blob, "ditado.webm");

    const resp = await fetch(`${API_BASE_URL}/transcribe`, {
      method: "POST",
      body: formData,
    });

    const data = await resp.json();
    if (!resp.ok) {
      throw new Error(data.detail || "Não foi possível transcrever o áudio.");
    }

    if (data.text) {
      inputEl.value = data.text;
      inputEl.focus();
    }
  } catch (err) {
    appendMessage("assistant", { content: `Erro no microfone: ${err.message}` });
  } finally {
    hintEl.classList.add("hidden");
    hintEl.textContent = "Ouvindo... toque no microfone para enviar.";
  }
}

async function alternarGravacao() {
  if (!isRecording) {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      appendMessage("assistant", { content: "Seu navegador não suporta gravação de áudio neste contexto (use HTTPS ou localhost)." });
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioChunks = [];
      mediaRecorder = new MediaRecorder(stream);

      mediaRecorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          audioChunks.push(event.data);
        }
      };

      mediaRecorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const audioBlob = new Blob(audioChunks, { type: mediaRecorder.mimeType || "audio/webm" });
        if (audioBlob.size > 0) {
          await enviarAudioParaTranscricao(audioBlob);
        }
      };

      mediaRecorder.start();
      isRecording = true;
      micBtn.classList.add("recording");
      hintEl.classList.remove("hidden");
    } catch (err) {
      appendMessage("assistant", { content: `Permissão do microfone negada ou indisponível: ${err.message}` });
    }
  } else if (mediaRecorder && mediaRecorder.state !== "inactive") {
    isRecording = false;
    micBtn.classList.remove("recording");
    mediaRecorder.stop();
  }
}

formEl.addEventListener("submit", (e) => {
  e.preventDefault();
  enviarMensagem(inputEl.value);
});

inputEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    enviarMensagem(inputEl.value);
  }
});

inputEl.addEventListener("input", () => {
  inputEl.style.height = "auto";
  inputEl.style.height = `${Math.min(inputEl.scrollHeight, 110)}px`;
});

micBtn.addEventListener("click", alternarGravacao);

newChatBtn.addEventListener("click", () => {
  history = [];
  messagesEl.innerHTML = "";
  heroEl.classList.remove("hidden");
});

(async function verificarSaudeApi() {
  try {
    const resp = await fetch(`${API_BASE_URL}/health`);
    statusEl.textContent = resp.ok ? "Online" : "Offline";
  } catch {
    statusEl.textContent = "Local / Aguardando API";
  }
})();
