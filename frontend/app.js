const API_BASE_URL = "https://rener-ia.onrender.com";

const chatArea = document.getElementById("chatArea");
const welcomeCard = document.getElementById("welcomeCard");
const composerForm = document.getElementById("composerForm");
const promptInput = document.getElementById("promptInput");
const sendBtn = document.getElementById("sendBtn");
const attachBtn = document.getElementById("attachBtn");
const fileInput = document.getElementById("fileInput");
const attachmentBar = document.getElementById("attachmentBar");
const attachmentThumb = document.getElementById("attachmentThumb");
const attachmentName = document.getElementById("attachmentName");
const removeAttachmentBtn = document.getElementById("removeAttachmentBtn");
const micBtn = document.getElementById("micBtn");
const newChatBtn = document.getElementById("newChatBtn");
const statusBadge = document.getElementById("statusBadge");

let history = [];
let selectedFile = null;
let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;

function autoResizeTextarea() {
  promptInput.style.height = "auto";
  promptInput.style.height = `${Math.min(promptInput.scrollHeight, 140)}px`;
}

promptInput.addEventListener("input", autoResizeTextarea);

promptInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    composerForm.requestSubmit();
  }
});

function appendMessage(role, { text = "", imageBase64 = "", videoBase64 = "" } = {}) {
  if (welcomeCard) {
    welcomeCard.classList.add("hidden");
  }

  const bubble = document.createElement("div");
  bubble.className = `message ${role}`;

  if (text) {
    const p = document.createElement("div");
    p.textContent = text;
    bubble.appendChild(p);
  }

  if (imageBase64) {
    const img = document.createElement("img");
    img.src = `data:image/png;base64,${imageBase64}`;
    img.alt = "Imagem gerada pelo Rener";
    bubble.appendChild(img);
  }

  if (videoBase64) {
    const video = document.createElement("video");
    video.src = `data:video/mp4;base64,${videoBase64}`;
    video.controls = true;
    video.autoplay = true;
    video.loop = true;
    video.playsInline = true;
    bubble.appendChild(video);
  }

  chatArea.appendChild(bubble);
  chatArea.scrollTop = chatArea.scrollHeight;
  return bubble;
}

function clearAttachment() {
  selectedFile = null;
  fileInput.value = "";
  attachmentThumb.src = "";
  attachmentThumb.classList.add("hidden");
  attachmentName.textContent = "";
  attachmentBar.classList.add("hidden");
}

attachBtn.addEventListener("click", () => {
  fileInput.click();
});

fileInput.addEventListener("change", () => {
  const file = fileInput.files && fileInput.files[0];
  if (!file) return;

  selectedFile = file;
  attachmentName.textContent = file.name;
  attachmentBar.classList.remove("hidden");

  if (file.type.startsWith("image/")) {
    const reader = new FileReader();
    reader.onload = (e) => {
      attachmentThumb.src = e.target.result;
      attachmentThumb.classList.remove("hidden");
    };
    reader.readAsDataURL(file);
  } else {
    attachmentThumb.src = "";
    attachmentThumb.classList.add("hidden");
  }
});

removeAttachmentBtn.addEventListener("click", clearAttachment);

newChatBtn.addEventListener("click", () => {
  history = [];
  clearAttachment();
  chatArea.innerHTML = "";
  if (welcomeCard) {
    welcomeCard.classList.remove("hidden");
    chatArea.appendChild(welcomeCard);
  }
});

async function checkHealth() {
  try {
    const res = await fetch(`${API_BASE_URL}/health`);
    if (res.ok) {
      statusBadge.textContent = "Online";
      statusBadge.style.color = "#4ade80";
      return;
    }
  } catch (_) {}
  statusBadge.textContent = "A iniciar";
  statusBadge.style.color = "#facc15";
}

composerForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const messageText = promptInput.value.trim();
  const fileToSend = selectedFile;

  if (!messageText && !fileToSend) return;

  const userSummary = fileToSend
    ? `${messageText || "Analise este ficheiro."} [Anexo: ${fileToSend.name}]`
    : messageText;

  appendMessage("user", { text: userSummary });

  promptInput.value = "";
  autoResizeTextarea();
  clearAttachment();
  sendBtn.disabled = true;

  const loadingBubble = appendMessage("assistant", {
    text: fileToSend ? "A analisar o ficheiro..." : "A pensar...",
  });

  try {
    let data;

    if (fileToSend) {
      const formData = new FormData();
      formData.append("file", fileToSend);
      formData.append("prompt", messageText || "Analise este ficheiro e dê um resumo claro e útil.");
      formData.append("style", "Amigável e direto");

      const res = await fetch(`${API_BASE_URL}/analyze`, {
        method: "POST",
        body: formData,
      });
      data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Falha ao analisar o ficheiro.");
      }
    } else {
      const res = await fetch(`${API_BASE_URL}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: messageText,
          history: history.slice(-12),
          style: "Amigável e direto",
        }),
      });
      data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Falha ao obter resposta.");
      }
    }

    loadingBubble.remove();

    const replyText = data.reply || "";
    const imageBase64 = data.image_base64 || "";
    const videoBase64 = data.video_base64 || "";

    appendMessage("assistant", {
      text: replyText,
      imageBase64,
      videoBase64,
    });

    history.push({ role: "user", content: userSummary });
    history.push({
      role: "assistant",
      content: replyText,
      has_image: Boolean(imageBase64),
      has_video: Boolean(videoBase64),
    });
  } catch (err) {
    loadingBubble.remove();
    appendMessage("assistant", {
      text: `Não foi possível concluir agora: ${err.message}`,
    });
  } finally {
    sendBtn.disabled = false;
    promptInput.focus();
  }
});

micBtn.addEventListener("click", async () => {
  if (!isRecording) {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      appendMessage("assistant", { text: "O teu navegador não suporta gravação de áudio." });
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioChunks = [];
      mediaRecorder = new MediaRecorder(stream);
      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunks.push(e.data);
      };
      mediaRecorder.onstop = async () => {
        stream.getTracks().forEach((track) => track.stop());
        const audioBlob = new Blob(audioChunks, { type: "audio/webm" });
        const formData = new FormData();
        formData.append("file", audioBlob, "ditado.webm");

        try {
          const res = await fetch(`${API_BASE_URL}/transcribe`, {
            method: "POST",
            body: formData,
          });
          const data = await res.json();
          if (res.ok && data.text) {
            promptInput.value = promptInput.value ? `${promptInput.value} ${data.text}` : data.text;
            autoResizeTextarea();
            promptInput.focus();
          }
        } catch (_) {}
      };

      mediaRecorder.start();
      isRecording = true;
      micBtn.classList.add("recording");
    } catch (_) {
      appendMessage("assistant", { text: "Permissão de microfone recusada ou indisponível." });
    }
  } else {
    mediaRecorder.stop();
    isRecording = false;
    micBtn.classList.remove("recording");
  }
});

checkHealth();
