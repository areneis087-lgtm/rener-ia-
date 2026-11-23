const BACKEND_URL = "https://rener-ia.onrender.com";

const chatEl = document.getElementById("chat") || document.getElementById("messages") || document.querySelector(".chat-messages");
const welcomeScreenEl = document.getElementById("welcome-screen");
const formEl = document.getElementById("chat-form") || document.querySelector("form");
const inputEl = document.getElementById("message-input") || document.getElementById("prompt-input") || document.querySelector("textarea, input[type='text']");

const sidebarEl = document.getElementById("sidebar");
const sidebarBackdropEl = document.getElementById("sidebar-backdrop");
const openSidebarBtnEl = document.getElementById("open-sidebar-btn");
const closeSidebarBtnEl = document.getElementById("close-sidebar-btn");

const attachToggleBtnEl = document.getElementById("attach-toggle-btn");
const attachMenuEl = document.getElementById("attach-menu");
const pickCameraBtnEl = document.getElementById("pick-camera-btn");
const pickGalleryBtnEl = document.getElementById("pick-gallery-btn");
const pickFilesBtnEl = document.getElementById("pick-files-btn");
const quickImageBtnEl = document.getElementById("quick-image-btn");
const quickVideoBtnEl = document.getElementById("quick-video-btn");
const creatorProBtnEl = document.getElementById("creator-pro-btn");

const cameraInputEl = document.getElementById("camera-input");
const galleryInputEl = document.getElementById("gallery-input");
const filesInputEl = document.getElementById("files-input");

const micBtnEl = document.getElementById("mic-btn");
const styleSelectEl = document.getElementById("style-select");
const newChatBtnEl = document.getElementById("new-chat-btn");
const topbarNewChatBtnEl = document.getElementById("topbar-new-chat-btn");
const clearHistoryBtnEl = document.getElementById("clear-history-btn");
const conversationListEl = document.getElementById("conversation-list");

const shortcutLibraryBtnEl = document.getElementById("shortcut-library-btn");
const shortcutImagesBtnEl = document.getElementById("shortcut-images-btn");
const shortcutScheduledBtnEl = document.getElementById("shortcut-scheduled-btn");
const shortcutCustomizeBtnEl = document.getElementById("shortcut-customize-btn");
const shortcutVideosBtnEl = document.getElementById("shortcut-videos-btn");

let conversationHistory = [];
let selectedGalleryBase64 = "";
let selectedGalleryDataUrl = "";
let selectedFileObj = null;
let mediaRecorder = null;
let audioChunks = [];

function getOrCreateUserId() {
  let id = localStorage.getItem("rener_user_id");
  if (!id) {
    id = "user_" + Math.random().toString(36).slice(2, 12);
    localStorage.setItem("rener_user_id", id);
  }
  return id;
}

const USER_ID = getOrCreateUserId();

function setSidebarOpen(open) {
  if (!sidebarEl) return;
  sidebarEl.classList.toggle("open", open);
  if (sidebarBackdropEl) {
    sidebarBackdropEl.hidden = !open;
  }
}

function setAttachMenuOpen(open) {
  if (!attachMenuEl) return;
  attachMenuEl.hidden = !open;
}

function hideWelcomeIfNeeded() {
  if (welcomeScreenEl) {
    welcomeScreenEl.style.display = "none";
  }
}

function showWelcomeScreen() {
  if (welcomeScreenEl) {
    welcomeScreenEl.style.display = "";
  }
}

function ensureGalleryPreviewUI() {
  let box = document.getElementById("gallery-preview-box");
  if (!box && formEl && formEl.parentNode) {
    box = document.createElement("div");
    box.id = "gallery-preview-box";
    box.className = "gallery-preview-box";
    box.style.display = "none";

    const label = document.createElement("span");
    label.className = "preview-label";
    label.textContent = "Pré-visualização";

    const img = document.createElement("img");
    img.id = "gallery-preview-img";
    img.alt = "Pré-visualização da imagem";

    const btn = document.createElement("button");
    btn.type = "button";
    btn.id = "clear-gallery-btn";
    btn.setAttribute("aria-label", "Remover imagem");
    btn.textContent = "×";
    btn.addEventListener("click", clearGalleryAttachment);

    box.appendChild(label);
    box.appendChild(img);
    box.appendChild(btn);
    formEl.parentNode.insertBefore(box, formEl);
  }
  return box;
}

function setGalleryAttachment(dataUrl, base64, labelText = "Pré-visualização") {
  selectedGalleryDataUrl = dataUrl || "";
  selectedGalleryBase64 = base64 || "";
  const box = ensureGalleryPreviewUI();
  const img = document.getElementById("gallery-preview-img");
  if (box && img && selectedGalleryDataUrl) {
    const label = box.querySelector(".preview-label");
    if (label) label.textContent = labelText;
    img.src = selectedGalleryDataUrl;
    box.style.display = "inline-flex";
  }
}

function clearGalleryAttachment() {
  selectedGalleryDataUrl = "";
  selectedGalleryBase64 = "";
  selectedFileObj = null;
  if (galleryInputEl) galleryInputEl.value = "";
  if (cameraInputEl) cameraInputEl.value = "";
  if (filesInputEl) filesInputEl.value = "";
  const box = document.getElementById("gallery-preview-box");
  const img = document.getElementById("gallery-preview-img");
  if (img) img.src = "";
  if (box) box.style.display = "none";
}

function registerConversationSummary(firstText) {
  if (!conversationListEl || !firstText) return;
  const item = document.createElement("button");
  item.type = "button";
  item.className = "sidebar-action-btn";
  item.textContent = firstText.slice(0, 32);
  item.addEventListener("click", () => setSidebarOpen(false));
  conversationListEl.prepend(item);
}

function appendMessage({ role, text = "", imageSrc = "", videoSrc = "" }) {
  if (!chatEl) return null;
  hideWelcomeIfNeeded();

  const row = document.createElement("div");
  row.className = `msg-row ${role === "user" ? "msg-user" : "msg-assistant"}`;

  const bubble = document.createElement("div");
  bubble.className = "msg-bubble";

  if (imageSrc) {
    const imgEl = document.createElement("img");
    imgEl.src = imageSrc;
    imgEl.alt = "Imagem na conversa";
    imgEl.className = "chat-msg-image";
    bubble.appendChild(imgEl);
  }

  if (videoSrc) {
    const vidEl = document.createElement("video");
    vidEl.src = videoSrc;
    vidEl.controls = true;
    vidEl.playsInline = true;
    vidEl.className = "chat-msg-video";
    bubble.appendChild(vidEl);
  }

  if (text) {
    const textEl = document.createElement("div");
    textEl.className = "msg-text";
    textEl.textContent = text;
    bubble.appendChild(textEl);
  }

  row.appendChild(bubble);
  chatEl.appendChild(row);
  chatEl.scrollTop = chatEl.scrollHeight;
  return row;
}

function handleImageFileSelected(file) {
  if (!file) return;
  selectedFileObj = file;
  const reader = new FileReader();
  reader.onload = () => {
    const result = String(reader.result || "");
    const parts = result.split(",");
    const b64 = parts.length > 1 ? parts[1] : result;
    setGalleryAttachment(result, b64, file.name || "Imagem");
  };
  reader.readAsDataURL(file);
}

function handleAnyFileSelected(file) {
  if (!file) return;
  selectedFileObj = file;
  if (file.type && file.type.startsWith("image/")) {
    handleImageFileSelected(file);
    return;
  }
  selectedGalleryBase64 = "";
  selectedGalleryDataUrl = "";
  const box = ensureGalleryPreviewUI();
  const img = document.getElementById("gallery-preview-img");
  if (box) {
    const label = box.querySelector(".preview-label");
    if (label) label.textContent = `Ficheiro: ${file.name}`;
    if (img) {
      img.removeAttribute("src");
      img.style.display = "none";
    }
    box.style.display = "inline-flex";
  }
}

if (openSidebarBtnEl) {
  openSidebarBtnEl.addEventListener("click", () => {
    setAttachMenuOpen(false);
    setSidebarOpen(true);
  });
}

if (closeSidebarBtnEl) {
  closeSidebarBtnEl.addEventListener("click", () => setSidebarOpen(false));
}

if (sidebarBackdropEl) {
  sidebarBackdropEl.addEventListener("click", () => setSidebarOpen(false));
}

if (attachToggleBtnEl) {
  attachToggleBtnEl.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (!attachMenuEl) return;
    setAttachMenuOpen(attachMenuEl.hidden);
  });
}

document.addEventListener("click", (e) => {
  if (
    attachMenuEl &&
    !attachMenuEl.hidden &&
    !attachMenuEl.contains(e.target) &&
    e.target !== attachToggleBtnEl
  ) {
    setAttachMenuOpen(false);
  }
});

if (pickCameraBtnEl && cameraInputEl) {
  pickCameraBtnEl.addEventListener("click", () => {
    setAttachMenuOpen(false);
    cameraInputEl.click();
  });
  cameraInputEl.addEventListener("change", (event) => {
    handleImageFileSelected(event.target.files && event.target.files[0]);
  });
}

if (pickGalleryBtnEl && galleryInputEl) {
  pickGalleryBtnEl.addEventListener("click", () => {
    setAttachMenuOpen(false);
    galleryInputEl.click();
  });
  galleryInputEl.addEventListener("change", (event) => {
    handleImageFileSelected(event.target.files && event.target.files[0]);
  });
}

if (pickFilesBtnEl && filesInputEl) {
  pickFilesBtnEl.addEventListener("click", () => {
    setAttachMenuOpen(false);
    filesInputEl.click();
  });
  filesInputEl.addEventListener("change", (event) => {
    handleAnyFileSelected(event.target.files && event.target.files[0]);
  });
}

if (quickImageBtnEl && inputEl) {
  quickImageBtnEl.addEventListener("click", () => {
    setAttachMenuOpen(false);
    inputEl.value = "Gere uma imagem de ";
    inputEl.focus();
  });
}

if (quickVideoBtnEl && inputEl) {
  quickVideoBtnEl.addEventListener("click", () => {
    setAttachMenuOpen(false);
    inputEl.value = "Gere um vídeo curto de ";
    inputEl.focus();
  });
}

if (creatorProBtnEl) {
  creatorProBtnEl.addEventListener("click", () => {
    setAttachMenuOpen(false);
    const atualCreator = localStorage.getItem("rener_creator_key") || "";
    const atualPro = localStorage.getItem("rener_pro_code") || "";
    const novaChave = window.prompt("Chave Criador (deixe em branco para manter/limpar):", atualCreator);
    if (novaChave !== null) {
      localStorage.setItem("rener_creator_key", novaChave.trim());
    }
    const novoPro = window.prompt("Código Pro (deixe em branco para manter/limpar):", atualPro);
    if (novoPro !== null) {
      localStorage.setItem("rener_pro_code", novoPro.trim());
    }
  });
}

if (shortcutLibraryBtnEl) {
  shortcutLibraryBtnEl.addEventListener("click", () => {
    setSidebarOpen(false);
    appendMessage({ role: "assistant", text: "Biblioteca: envie um PDF, imagem ou ficheiro de texto pelo botão + > Arquivos para analisar." });
  });
}

if (shortcutImagesBtnEl && inputEl) {
  shortcutImagesBtnEl.addEventListener("click", () => {
    setSidebarOpen(false);
    inputEl.value = "Gere uma imagem de ";
    inputEl.focus();
  });
}

if (shortcutScheduledBtnEl) {
  shortcutScheduledBtnEl.addEventListener("click", () => {
    setSidebarOpen(false);
    appendMessage({ role: "assistant", text: "Programado: use o campo de mensagem para pedir resumos, planos ou tarefas rápidas." });
  });
}

if (shortcutCustomizeBtnEl) {
  shortcutCustomizeBtnEl.addEventListener("click", () => {
    setSidebarOpen(false);
    if (styleSelectEl) styleSelectEl.focus();
  });
}

if (shortcutVideosBtnEl && inputEl) {
  shortcutVideosBtnEl.addEventListener("click", () => {
    setSidebarOpen(false);
    inputEl.value = "Gere um vídeo curto de ";
    inputEl.focus();
  });
}

function resetConversation() {
  conversationHistory = [];
  clearGalleryAttachment();
  if (chatEl) {
    Array.from(chatEl.querySelectorAll(".msg-row")).forEach((el) => el.remove());
  }
  showWelcomeScreen();
  setSidebarOpen(false);
}

if (newChatBtnEl) {
  newChatBtnEl.addEventListener("click", resetConversation);
}

if (topbarNewChatBtnEl) {
  topbarNewChatBtnEl.addEventListener("click", resetConversation);
}

if (clearHistoryBtnEl) {
  clearHistoryBtnEl.addEventListener("click", () => {
    if (conversationListEl) conversationListEl.innerHTML = "";
    resetConversation();
  });
}

if (micBtnEl) {
  micBtnEl.addEventListener("click", async () => {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      appendMessage({ role: "assistant", text: "Gravação de áudio não suportada neste navegador." });
      return;
    }

    if (mediaRecorder && mediaRecorder.state === "recording") {
      mediaRecorder.stop();
      micBtnEl.textContent = "🎤";
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioChunks = [];
      mediaRecorder = new MediaRecorder(stream);
      mediaRecorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) audioChunks.push(e.data);
      };
      mediaRecorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(audioChunks, { type: "audio/webm" });
        const formData = new FormData();
        formData.append("file", blob, "ditado.webm");
        try {
          const resp = await fetch(`${BACKEND_URL}/transcribe`, { method: "POST", body: formData });
          const data = await resp.json();
          if (resp.ok && data.text && inputEl) {
            inputEl.value = `${inputEl.value} ${data.text}`.trim();
            inputEl.focus();
          }
        } catch (_) {}
      };
      mediaRecorder.start();
      micBtnEl.textContent = "⏹";
    } catch (_) {
      appendMessage({ role: "assistant", text: "Permissão do microfone negada ou indisponível." });
    }
  });
}

async function sendMessage(event) {
  if (event) event.preventDefault();
  if (!inputEl) return;

  setAttachMenuOpen(false);
  const message = (inputEl.value || "").trim();
  const attachedDataUrl = selectedGalleryDataUrl;
  const attachedBase64 = selectedGalleryBase64;
  const fileToAnalyze = selectedFileObj;

  if (!message && !attachedBase64 && !fileToAnalyze) return;

  if (conversationHistory.length === 0) {
    registerConversationSummary(message || (fileToAnalyze ? fileToAnalyze.name : "Imagem"));
  }

  appendMessage({
    role: "user",
    text: message || (fileToAnalyze ? `Analisar ${fileToAnalyze.name}` : ""),
    imageSrc: attachedDataUrl,
  });

  inputEl.value = "";
  clearGalleryAttachment();

  const loadingRow = appendMessage({
    role: "assistant",
    text: "A pensar...",
  });

  try {
    if (fileToAnalyze && !attachedBase64) {
      const formData = new FormData();
      formData.append("file", fileToAnalyze);
      formData.append("prompt", message || "Analise este arquivo e me dê um resumo claro e útil.");
      formData.append("style", styleSelectEl ? styleSelectEl.value : "Amigável e direto");

      const resp = await fetch(`${BACKEND_URL}/analyze`, {
        method: "POST",
        body: formData,
      });
      const data = await resp.json();
      if (loadingRow && loadingRow.parentNode) loadingRow.parentNode.removeChild(loadingRow);

      if (!resp.ok) {
        appendMessage({ role: "assistant", text: `Erro: ${data.detail || "falha na análise"}` });
        return;
      }

      const replyText = data.reply || "";
      appendMessage({ role: "assistant", text: replyText });
      conversationHistory.push({ role: "user", content: message || fileToAnalyze.name, has_image: false, has_video: false });
      conversationHistory.push({ role: "assistant", content: replyText, has_image: false, has_video: false });
      return;
    }

    const promptText = message || "Analise esta imagem.";
    const payload = {
      message: promptText,
      history: conversationHistory.slice(-10),
      style: styleSelectEl ? styleSelectEl.value : "Amigável e direto",
      user_id: USER_ID,
      pro_code: localStorage.getItem("rener_pro_code") || "",
      creator_key: localStorage.getItem("rener_creator_key") || "",
      gallery_image_base64: attachedBase64,
    };

    const resp = await fetch(`${BACKEND_URL}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const data = await resp.json();
    if (loadingRow && loadingRow.parentNode) {
      loadingRow.parentNode.removeChild(loadingRow);
    }

    if (!resp.ok) {
      const errMsg = data && data.detail ? data.detail : "Erro ao comunicar com o servidor.";
      appendMessage({ role: "assistant", text: `Erro: ${errMsg}` });
      return;
    }

    const replyText = data.reply || "";
    const outImgSrc = data.image_base64 ? `data:image/png;base64,${data.image_base64}` : "";
    const outVidSrc = data.video_base64 ? `data:video/mp4;base64,${data.video_base64}` : "";

    appendMessage({
      role: "assistant",
      text: replyText,
      imageSrc: outImgSrc,
      videoSrc: outVidSrc,
    });

    conversationHistory.push({
      role: "user",
      content: promptText,
      has_image: Boolean(attachedBase64),
      has_video: false,
    });

    conversationHistory.push({
      role: "assistant",
      content: replyText,
      has_image: Boolean(outImgSrc),
      has_video: Boolean(outVidSrc),
    });
  } catch (err) {
    if (loadingRow && loadingRow.parentNode) {
      loadingRow.parentNode.removeChild(loadingRow);
    }
    appendMessage({
      role: "assistant",
      text: `Erro de ligação: ${err && err.message ? err.message : "verifique o backend"}`,
    });
  }
}

if (formEl) {
  formEl.addEventListener("submit", sendMessage);
}

if (inputEl) {
  inputEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage(e);
    }
  });
}

ensureGalleryPreviewUI();
