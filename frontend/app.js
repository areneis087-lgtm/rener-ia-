const API_BASE = "https://rener-ia-backend.onrender.com";

const elChat = document.getElementById("chat-container");
const elForm = document.getElementById("chat-form");
const elInput = document.getElementById("message-input");
const elSendBtn = document.getElementById("send-btn");
const elMicBtn = document.getElementById("mic-btn");
const elPlusBtn = document.getElementById("plus-btn");
const elAttachMenu = document.getElementById("attach-menu");
const elGalleryInput = document.getElementById("gallery-input");
const elCameraInput = document.getElementById("camera-input");
const elFileInput = document.getElementById("file-input");
const elAttachmentBar = document.getElementById("attachment-preview-bar");
const elAttachmentThumb = document.getElementById("attachment-thumb");
const elAttachmentName = document.getElementById("attachment-name");
const elClearAttachmentBtn = document.getElementById("clear-attachment-btn");
const elNewChatBtn = document.getElementById("new-chat-btn");
const elStyleSelect = document.getElementById("style-select");
const elDrawer = document.getElementById("side-drawer");
const elDrawerBackdrop = document.getElementById("drawer-backdrop");
const elMenuBtn = document.getElementById("menu-btn");
const elCloseDrawerBtn = document.getElementById("close-drawer-btn");
const elCreatorBadge = document.getElementById("creator-badge");
const elCreatorKeyInput = document.getElementById("creator-key-input");
const elSaveCreatorKeyBtn = document.getElementById("save-creator-key-btn");
const elProCodeInput = document.getElementById("pro-code-input");
const elSaveProCodeBtn = document.getElementById("save-pro-code-btn");

const STORAGE_KEY_CHAT = "rener_chat_history_v1";
const STORAGE_KEY_USER = "rener_user_id_v1";
const STORAGE_KEY_STYLE = "rener_style_v1";
const STORAGE_KEY_CREATOR = "rener_creator_key_v1";
const STORAGE_KEY_PRO = "rener_pro_code_v1";

let messages = [];
let pendingFile = null;
let selectedGalleryImageBase64 = "";
let isSending = false;
let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;
let touchStartX = 0;
let touchCurrentX = 0;

function getOrCreateUserId() {
  let id = localStorage.getItem(STORAGE_KEY_USER);
  if (!id) {
    id = "user_" + Math.random().toString(36).slice(2, 10) + "_" + Date.now().toString(36);
    localStorage.setItem(STORAGE_KEY_USER, id);
  }
  return id;
}

const userId = getOrCreateUserId();

function getCreatorKey() {
  return (localStorage.getItem(STORAGE_KEY_CREATOR) || "").trim();
}

function getProCode() {
  return (localStorage.getItem(STORAGE_KEY_PRO) || "").trim();
}

function atualizarBadgeStatus() {
  if (!elCreatorBadge) return;
  if (getCreatorKey()) {
    elCreatorBadge.textContent = "Criador • Online";
    elCreatorBadge.classList.add("active");
  } else if (getProCode()) {
    elCreatorBadge.textContent = "Pro • Ativo";
    elCreatorBadge.classList.add("active");
  } else {
    elCreatorBadge.textContent = "Rener • Online";
    elCreatorBadge.classList.remove("active");
  }
}

function openDrawer() {
  if (elDrawer) elDrawer.classList.add("open");
  if (elDrawerBackdrop) elDrawerBackdrop.classList.add("visible");
}

function closeDrawer() {
  if (elDrawer) elDrawer.classList.remove("open");
  if (elDrawerBackdrop) elDrawerBackdrop.classList.remove("visible");
}

function toggleAttachMenu() {
  if (!elAttachMenu) return;
  elAttachMenu.classList.toggle("open");
}

function closeAttachMenu() {
  if (!elAttachMenu) return;
  elAttachMenu.classList.remove("open");
}

function saveMessages() {
  try {
    const compact = messages.slice(-24).map((m) => ({
      role: m.role,
      content: m.content || "",
      has_image: Boolean(m.imageBase64),
      has_video: Boolean(m.videoBase64),
      imageBase64: m.imageBase64 && m.imageBase64.length < 1800000 ? m.imageBase64 : "",
      videoBase64: "",
      type: m.type || "text",
    }));
    localStorage.setItem(STORAGE_KEY_CHAT, JSON.stringify(compact));
  } catch (_) {}
}

function loadMessages() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY_CHAT);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch (_) {
    return [];
  }
}

function scrollToBottom() {
  if (!elChat) return;
  requestAnimationFrame(() => {
    elChat.scrollTop = elChat.scrollHeight;
  });
}

function renderMessage(msg) {
  if (!elChat) return;
  const row = document.createElement("div");
  row.className = `msg-row ${msg.role === "user" ? "user" : "assistant"}`;

  const bubble = document.createElement("div");
  bubble.className = "msg-bubble";

  if (msg.content) {
    const textEl = document.createElement("div");
    textEl.className = "msg-text";
    textEl.textContent = msg.content;
    bubble.appendChild(textEl);
  }

  if (msg.imageBase64) {
    const imgEl = document.createElement("img");
    imgEl.className = "msg-image";
    imgEl.src = msg.imageBase64.startsWith("data:")
      ? msg.imageBase64
      : `data:image/png;base64,${msg.imageBase64}`;
    imgEl.alt = "Imagem gerada pelo Rener";
    bubble.appendChild(imgEl);

    const saveBtn = document.createElement("a");
    saveBtn.className = "save-media-btn";
    saveBtn.href = imgEl.src;
    saveBtn.download = `rener_${Date.now()}.png`;
    saveBtn.textContent = "Guardar imagem";
    bubble.appendChild(saveBtn);
  }

  if (msg.videoBase64) {
    const vidEl = document.createElement("video");
    vidEl.className = "msg-video";
    vidEl.controls = true;
    vidEl.playsInline = true;
    vidEl.src = msg.videoBase64.startsWith("data:")
      ? msg.videoBase64
      : `data:video/mp4;base64,${msg.videoBase64}`;
    bubble.appendChild(vidEl);
  }

  row.appendChild(bubble);
  elChat.appendChild(row);
  scrollToBottom();
}

function renderAllMessages() {
  if (!elChat) return;
  elChat.innerHTML = "";
  if (!messages.length) {
    const welcome = {
      role: "assistant",
      type: "text",
      content: "Olá! Sou o Rener. Como posso ajudar hoje? Pode pedir texto, imagem ou vídeo, ou escolher uma foto direto da galeria.",
    };
    messages.push(welcome);
  }
  messages.forEach(renderMessage);
}

function clearAttachment() {
  pendingFile = null;
  selectedGalleryImageBase64 = "";
  if (elGalleryInput) elGalleryInput.value = "";
  if (elCameraInput) elCameraInput.value = "";
  if (elFileInput) elFileInput.value = "";
  if (elAttachmentBar) elAttachmentBar.classList.remove("visible");
  if (elAttachmentThumb) {
    elAttachmentThumb.src = "";
    elAttachmentThumb.style.display = "none";
  }
  if (elAttachmentName) elAttachmentName.textContent = "";
}

function setAttachment(file, fromGallery = false) {
  if (!file) return;
  pendingFile = file;
  if (elAttachmentBar) elAttachmentBar.classList.add("visible");

  if (file.type && file.type.startsWith("image/")) {
    const reader = new FileReader();
    reader.onload = (ev) => {
      const dataUrl = String(ev.target?.result || "");
      if (elAttachmentThumb) {
        elAttachmentThumb.src = dataUrl;
        elAttachmentThumb.style.display = "block";
      }
      if (fromGallery) {
        selectedGalleryImageBase64 = dataUrl;
        if (elAttachmentName) {
          elAttachmentName.textContent = `Galeria: ${file.name} (pronta p/ chat e análise)`;
        }
      } else {
        selectedGalleryImageBase64 = "";
        if (elAttachmentName) {
          elAttachmentName.textContent = file.name;
        }
      }
    };
    reader.readAsDataURL(file);
  } else {
    selectedGalleryImageBase64 = "";
    if (elAttachmentThumb) elAttachmentThumb.style.display = "none";
    if (elAttachmentName) elAttachmentName.textContent = file.name;
  }
}

async function analisarArquivoNoBackend(file, promptText) {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("prompt", promptText || "Analise este arquivo e me dê um resumo claro e útil.");
  formData.append("style", elStyleSelect?.value || "Amigável e direto");

  const resp = await fetch(`${API_BASE}/analyze`, {
    method: "POST",
    body: formData,
  });

  if (!resp.ok) {
    const errText = await resp.text();
    throw new Error(errText || `Erro HTTP ${resp.status}`);
  }
  return await resp.json();
}

async function enviarMensagemChat(text) {
  const historyPayload = messages.slice(-12).map((m) => ({
    role: m.role,
    content: m.content || "",
    has_image: Boolean(m.imageBase64),
    has_video: Boolean(m.videoBase64),
  }));

  const payload = {
    message: text,
    history: historyPayload,
    style: elStyleSelect?.value || "Amigável e direto",
    user_id: userId,
    pro_code: getProCode(),
    creator_key: getCreatorKey(),
    gallery_image_base64: selectedGalleryImageBase64 || "",
  };

  const resp = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!resp.ok) {
    const errText = await resp.text();
    throw new Error(errText || `Erro HTTP ${resp.status}`);
  }
  return await resp.json();
}

async function handleFormSubmit(e) {
  e.preventDefault();
  if (isSending) return;

  const text = (elInput?.value || "").trim();
  if (!text && !pendingFile) return;

  isSending = true;
  if (elSendBtn) elSendBtn.disabled = true;

  const userMsg = {
    role: "user",
    type: "text",
    content: text || (pendingFile ? `Arquivo: ${pendingFile.name}` : ""),
  };
  messages.push(userMsg);
  renderMessage(userMsg);
  saveMessages();

  if (elInput) elInput.value = "";

  const loadingMsg = {
    role: "assistant",
    type: "text",
    content: "Pensando...",
  };
  renderMessage(loadingMsg);
  const lastRow = elChat?.lastElementChild;

  try {
    let data;
    if (pendingFile) {
      data = await analisarArquivoNoBackend(pendingFile, text);
    } else {
      data = await enviarMensagemChat(text);
    }

    if (lastRow) lastRow.remove();

    const botMsg = {
      role: "assistant",
      type: data.type || "text",
      content: data.reply || "",
      imageBase64: data.image_base64 || "",
      videoBase64: data.video_base64 || "",
    };
    messages.push(botMsg);
    renderMessage(botMsg);
    saveMessages();
  } catch (err) {
    if (lastRow) lastRow.remove();
    const errMsg = {
      role: "assistant",
      type: "text",
      content: `Não consegui concluir agora: ${err?.message || "erro de conexão"}.`,
    };
    messages.push(errMsg);
    renderMessage(errMsg);
  } finally {
    isSending = false;
    if (elSendBtn) elSendBtn.disabled = false;
  }
}

async function toggleAudioRecording() {
  if (isRecording && mediaRecorder) {
    mediaRecorder.stop();
    isRecording = false;
    if (elMicBtn) elMicBtn.classList.remove("recording");
    return;
  }

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    audioChunks = [];
    mediaRecorder = new MediaRecorder(stream);
    mediaRecorder.ondataavailable = (ev) => {
      if (ev.data && ev.data.size > 0) audioChunks.push(ev.data);
    };
    mediaRecorder.onstop = async () => {
      stream.getTracks().forEach((t) => t.stop());
      const blob = new Blob(audioChunks, { type: "audio/webm" });
      if (!blob.size) return;

      const formData = new FormData();
      formData.append("file", blob, "ditado.webm");
      try {
        const resp = await fetch(`${API_BASE}/transcribe`, {
          method: "POST",
          body: formData,
        });
        if (resp.ok) {
          const data = await resp.json();
          if (data.text && elInput) {
            elInput.value = `${elInput.value ? elInput.value + " " : ""}${data.text}`.trim();
            elInput.focus();
          }
        }
      } catch (_) {}
    };

    mediaRecorder.start();
    isRecording = true;
    if (elMicBtn) elMicBtn.classList.add("recording");
  } catch (_) {}
}

// Eventos de UI
if (elPlusBtn) {
  elPlusBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    toggleAttachMenu();
  });
}

document.addEventListener("click", (e) => {
  if (elAttachMenu && !elAttachMenu.contains(e.target) && e.target !== elPlusBtn) {
    closeAttachMenu();
  }
});

if (elAttachMenu) {
  elAttachMenu.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-action]");
    if (!btn) return;
    const action = btn.getAttribute("data-action");
    closeAttachMenu();

    if (action === "gallery" && elGalleryInput) {
      elGalleryInput.removeAttribute("capture");
      elGalleryInput.setAttribute("accept", "image/*");
      elGalleryInput.click();
    } else if (action === "camera" && elCameraInput) {
      elCameraInput.setAttribute("accept", "image/*");
      elCameraInput.setAttribute("capture", "environment");
      elCameraInput.click();
    } else if (action === "file" && elFileInput) {
      elFileInput.click();
    }
  });
}

if (elGalleryInput) {
  elGalleryInput.addEventListener("change", (e) => {
    const file = e.target.files?.[0];
    if (file) setAttachment(file, true);
  });
}

if (elCameraInput) {
  elCameraInput.addEventListener("change", (e) => {
    const file = e.target.files?.[0];
    if (file) setAttachment(file, false);
  });
}

if (elFileInput) {
  elFileInput.addEventListener("change", (e) => {
    const file = e.target.files?.[0];
    if (file) setAttachment(file, false);
  });
}

if (elClearAttachmentBtn) {
  elClearAttachmentBtn.addEventListener("click", clearAttachment);
}

if (elForm) {
  elForm.addEventListener("submit", handleFormSubmit);
}

if (elMicBtn) {
  elMicBtn.addEventListener("click", toggleAudioRecording);
}

if (elNewChatBtn) {
  elNewChatBtn.addEventListener("click", () => {
    messages = [];
    localStorage.removeItem(STORAGE_KEY_CHAT);
    clearAttachment();
    renderAllMessages();
  });
}

if (elStyleSelect) {
  const savedStyle = localStorage.getItem(STORAGE_KEY_STYLE);
  if (savedStyle) elStyleSelect.value = savedStyle;
  elStyleSelect.addEventListener("change", () => {
    localStorage.setItem(STORAGE_KEY_STYLE, elStyleSelect.value);
  });
}

if (elMenuBtn) elMenuBtn.addEventListener("click", openDrawer);
if (elCloseDrawerBtn) elCloseDrawerBtn.addEventListener("click", closeDrawer);
if (elDrawerBackdrop) elDrawerBackdrop.addEventListener("click", closeDrawer);

// Swipe lateral para abrir/fechar drawer no celular
document.addEventListener("touchstart", (e) => {
  touchStartX = e.touches[0]?.clientX || 0;
  touchCurrentX = touchStartX;
}, { passive: true });

document.addEventListener("touchmove", (e) => {
  touchCurrentX = e.touches[0]?.clientX || touchStartX;
}, { passive: true });

document.addEventListener("touchend", () => {
  const deltaX = touchCurrentX - touchStartX;
  if (touchStartX < 32 && deltaX > 70) {
    openDrawer();
  } else if (elDrawer?.classList.contains("open") && deltaX < -70) {
    closeDrawer();
  }
}, { passive: true });

if (elCreatorKeyInput) {
  elCreatorKeyInput.value = getCreatorKey();
}
if (elSaveCreatorKeyBtn) {
  elSaveCreatorKeyBtn.addEventListener("click", () => {
    localStorage.setItem(STORAGE_KEY_CREATOR, (elCreatorKeyInput?.value || "").trim());
    atualizarBadgeStatus();
    closeDrawer();
  });
}

if (elProCodeInput) {
  elProCodeInput.value = getProCode();
}
if (elSaveProCodeBtn) {
  elSaveProCodeBtn.addEventListener("click", () => {
    localStorage.setItem(STORAGE_KEY_PRO, (elProCodeInput?.value || "").trim());
    atualizarBadgeStatus();
    closeDrawer();
  });
}

atualizarBadgeStatus();
messages = loadMessages();
renderAllMessages();
