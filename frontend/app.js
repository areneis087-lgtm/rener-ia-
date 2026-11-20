const API_BASE_URL = "https://rener-ia.onrender.com";

const chatArea = document.getElementById("chatArea");
const welcomeCard = document.getElementById("welcomeCard");
const composerForm = document.getElementById("composerForm");
const promptInput = document.getElementById("promptInput");
const sendBtn = document.getElementById("sendBtn");

const attachBtn = document.getElementById("attachBtn");
const plusMenu = document.getElementById("plusMenu");
const optPhotos = document.getElementById("optPhotos");
const optCamera = document.getElementById("optCamera");
const optFiles = document.getElementById("optFiles");
const optDrive = document.getElementById("optDrive");
const optCreateImage = document.getElementById("optCreateImage");

const photoInput = document.getElementById("photoInput");
const cameraInput = document.getElementById("cameraInput");
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

function getOrCreateUserId() {
  let uid = localStorage.getItem("rener_user_id");
  if (!uid) {
    uid = `usr_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
    localStorage.setItem("rener_user_id", uid);
  }
  return uid;
}

function getProCode() {
  return localStorage.getItem("rener_pro_code") || "";
}

function setProCode(code) {
  localStorage.setItem("rener_pro_code", (code || "").trim());
}

function getCreatorKey() {
  return localStorage.getItem("rener_creator_key") || "";
}

function setCreatorKey(key) {
  localStorage.setItem("rener_creator_key", (key || "").trim());
}

function abrirModalAcesso() {
  const creatorAtual = getCreatorKey();
  const escolha = window.prompt(
    "Modo Criador (ilimitado): cole sua chave RENER_CREATOR_KEY abaixo (ou deixe vazio para usar modo Pro/Grátis):",
    creatorAtual
  );
  if (escolha !== null) {
    setCreatorKey(escolha);
    checkHealth();
    appendMessage("assistant", {
      text: escolha.trim()
        ? "Modo Criador Ilimitado ativado neste dispositivo, Rener!"
        : "Chave de criador removida deste dispositivo.",
    });
  }
}

function autoResizeTextarea() {
  promptInput.style.height = "auto";
  promptInput.style.height = `${Math.min(promptInput.scrollHeight, 140)}px`;
}

function togglePlusMenu(forceState = null) {
  const shouldOpen = forceState !== null ? forceState : plusMenu.classList.contains("hidden");
  plusMenu.classList.toggle("hidden", !shouldOpen);
}

promptInput.addEventListener("input", autoResizeTextarea);

promptInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    composerForm.requestSubmit();
  }
});

attachBtn.addEventListener("click", (event) => {
  event.stopPropagation();
  togglePlusMenu();
});

document.addEventListener("click", (event) => {
  if (!plusMenu.classList.contains("hidden") && !plusMenu.contains(event.target) && event.target !== attachBtn) {
    togglePlusMenu(false);
  }
});

optPhotos.addEventListener("click", () => {
  togglePlusMenu(false);
  photoInput.click();
});

optCamera.addEventListener("click", () => {
  togglePlusMenu(false);
  cameraInput.click();
});

optFiles.addEventListener("click", () => {
  togglePlusMenu(false);
  fileInput.click();
});

optDrive.addEventListener("click", () => {
  togglePlusMenu(false);
  fileInput.click();
});

optCreateImage.addEventListener("click", () => {
  togglePlusMenu(false);
  if (!promptInput.value.trim()) {
    promptInput.value = "Gere uma imagem de ";
  }
  autoResizeTextarea();
  promptInput.focus();
});

function handleSelectedFile(inputEl) {
  const file = inputEl.files && inputEl.files[0];
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
}

photoInput.addEventListener("change", () => handleSelectedFile(photoInput));
cameraInput.addEventListener("change", () => handleSelectedFile(cameraInput));
fileInput.addEventListener("change", () => handleSelectedFile(fileInput));

function clearAttachment() {
  selectedFile = null;
  photoInput.value = "";
  cameraInput.value = "";
  fileInput.value = "";
  attachmentThumb.src = "";
  attachmentThumb.classList.add("hidden");
  attachmentName.textContent = "";
  attachmentBar.classList.add("hidden");
}

removeAttachmentBtn.addEventListener("click", clearAttachment);

function triggerImageDownload(base64Data) {
  const link = document.createElement("a");
  link.href = `data:image/png;base64,${base64Data}`;
  link.download = `imagem_rener_4k_${Date.now()}.png`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

function appendMessage(role, { text = "", imageBase64 = "", videoBase64 = "", isPaywall = false } = {}) {
  if (welcomeCard) {
    welcomeCard.classList.add("hidden");
  }

  const bubble = document.createElement("div");
  bubble.className = `message ${role}`;

  if (text) {
    const p = document.createElement("div");
    p.textContent = text.replace(/\*\*/g, "");
    bubble.appendChild(p);
  }

  if (isPaywall) {
    const proBtn = document.createElement("button");
    proBtn.type = "button";
    proBtn.className = "download-img-btn";
    proBtn.textContent = "Configurar chave de acesso";
    proBtn.addEventListener("click", abrirModalAcesso);
    bubble.appendChild(proBtn);
  }

  if (imageBase64) {
    const img = document.createElement("img");
    img.src = `data:image/png;base64,${imageBase64}`;
    img.alt = "Imagem gerada pelo Rener";
    bubble.appendChild(img);

    const downloadBtn = document.createElement("button");
    downloadBtn.type = "button";
    downloadBtn.className = "download-img-btn";
    downloadBtn.textContent = "Baixar imagem";
    downloadBtn.addEventListener("click", () => triggerImageDownload(imageBase64));
    bubble.appendChild(downloadBtn);
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

newChatBtn.addEventListener("click", () => {
  history = [];
  clearAttachment();
  togglePlusMenu(false);
  chatArea.innerHTML = "";
  if (welcomeCard) {
    welcomeCard.classList.remove("hidden");
    chatArea.appendChild(welcomeCard);
  }
});

if (statusBadge) {
  statusBadge.style.cursor = "pointer";
  statusBadge.title = "Toque para configurar acesso de Criador ou Pro";
  statusBadge.addEventListener("click", abrirModalAcesso);
}

async function checkHealth() {
  try {
    const res = await fetch(`${API_BASE_URL}/health`);
    if (res.ok) {
      if (getCreatorKey()) {
        statusBadge.textContent = "Criador";
      } else if (getProCode()) {
        statusBadge.textContent = "Pro Online";
      } else {
        statusBadge.textContent = "Online";
      }
      statusBadge.style.color = "#4ade80";
      return;
    }
  } catch (_) {}
  statusBadge.textContent = "A iniciar";
  statusBadge.style.color = "#facc15";
}

composerForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  togglePlusMenu(false);

  const messageText = promptInput.value.trim();
  const fileToSend = selectedFile;

  if (!messageText && !fileToSend) return;

  const comandoCriadorMatch = messageText.match(/^\/?criador\s+(.+)$/i);
  if (comandoCriadorMatch && !fileToSend) {
    const chaveDigitada = comandoCriadorMatch[1].trim();
    setCreatorKey(chaveDigitada);
    promptInput.value = "";
    autoResizeTextarea();
    checkHealth();
    appendMessage("user", { text: "/criador ********" });
    appendMessage("assistant", {
      text: "Chave de criador salva neste dispositivo! Agora você tem acesso ilimitado.",
    });
    return;
  }

  const userSummary = fileToSend
    ? `${messageText || "Analise este ficheiro."} [Anexo: ${fileToSend.name}]`
    : messageText;

  appendMessage("user", { text: userSummary });

  promptInput.value = "";
  autoResizeTextarea();
  clearAttachment();
  sendBtn.disabled = true;

  const loadingBubble = appendMessage("assistant", {
    text: fileToSend ? "A analisar o ficheiro..." : "A criar...",
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
          user_id: getOrCreateUserId(),
          pro_code: getProCode(),
          creator_key: getCreatorKey(),
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
    const isPaywall = data.type === "paywall";

    appendMessage("assistant", {
      text: replyText,
      imageBase64,
      videoBase64,
      isPaywall,
    });

    if (!isPaywall) {
      history.push({ role: "user", content: userSummary });
      history.push({
        role: "assistant",
        content: replyText,
        has_image: Boolean(imageBase64),
        has_video: Boolean(videoBase64),
      });
    }
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
