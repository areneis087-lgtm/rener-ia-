const BACKEND_URL = "https://rener-ia.onrender.com";

const chatEl = document.getElementById("chat") || document.getElementById("messages") || document.querySelector(".chat-messages");
const formEl = document.getElementById("chat-form") || document.querySelector("form");
const inputEl = document.getElementById("message-input") || document.getElementById("prompt-input") || document.querySelector("textarea, input[type='text']");
const galleryInputEl = document.getElementById("gallery-input") || document.querySelector("input[type='file'][accept*='image']");
const styleSelectEl = document.getElementById("style-select");
const newChatBtnEl = document.getElementById("new-chat-btn");

let conversationHistory = [];
let selectedGalleryBase64 = "";
let selectedGalleryDataUrl = "";

function getOrCreateUserId() {
  let id = localStorage.getItem("rener_user_id");
  if (!id) {
    id = "user_" + Math.random().toString(36).slice(2, 12);
    localStorage.setItem("rener_user_id", id);
  }
  return id;
}

const USER_ID = getOrCreateUserId();

function ensureGalleryPreviewUI() {
  let box = document.getElementById("gallery-preview-box");
  if (!box && formEl) {
    box = document.createElement("div");
    box.id = "gallery-preview-box";
    box.className = "gallery-preview-box";
    box.style.display = "none";

    const img = document.createElement("img");
    img.id = "gallery-preview-img";
    img.alt = "Pré-visualização da imagem";

    const btn = document.createElement("button");
    btn.type = "button";
    btn.id = "clear-gallery-btn";
    btn.setAttribute("aria-label", "Remover imagem");
    btn.textContent = "×";
    btn.addEventListener("click", clearGalleryAttachment);

    box.appendChild(img);
    box.appendChild(btn);
    formEl.prepend(box);
  }
  return box;
}

function setGalleryAttachment(dataUrl, base64) {
  selectedGalleryDataUrl = dataUrl || "";
  selectedGalleryBase64 = base64 || "";
  const box = ensureGalleryPreviewUI();
  const img = document.getElementById("gallery-preview-img");
  if (box && img && selectedGalleryDataUrl) {
    img.src = selectedGalleryDataUrl;
    box.style.display = "inline-flex";
  }
}

function clearGalleryAttachment() {
  selectedGalleryDataUrl = "";
  selectedGalleryBase64 = "";
  if (galleryInputEl) {
    galleryInputEl.value = "";
  }
  const box = document.getElementById("gallery-preview-box");
  const img = document.getElementById("gallery-preview-img");
  if (img) img.src = "";
  if (box) box.style.display = "none";
}

function appendMessage({ role, text = "", imageSrc = "", videoSrc = "" }) {
  if (!chatEl) return null;

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

if (galleryInputEl) {
  galleryInputEl.addEventListener("change", (event) => {
    const file = event.target.files && event.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result || "");
      const parts = result.split(",");
      const b64 = parts.length > 1 ? parts[1] : result;
      setGalleryAttachment(result, b64);
    };
    reader.readAsDataURL(file);
  });
}

if (newChatBtnEl) {
  newChatBtnEl.addEventListener("click", () => {
    conversationHistory = [];
    clearGalleryAttachment();
    if (chatEl) chatEl.innerHTML = "";
    appendMessage({
      role: "assistant",
      text: "Olá! Sou o Rener. Como posso ajudar hoje?",
    });
  });
}

async function sendMessage(event) {
  if (event) event.preventDefault();
  if (!inputEl) return;

  const message = (inputEl.value || "").trim();
  const attachedDataUrl = selectedGalleryDataUrl;
  const attachedBase64 = selectedGalleryBase64;

  if (!message && !attachedBase64) return;

  const promptText = message || "Analise esta imagem.";

  appendMessage({
    role: "user",
    text: message,
    imageSrc: attachedDataUrl,
  });

  inputEl.value = "";
  clearGalleryAttachment();

  const loadingRow = appendMessage({
    role: "assistant",
    text: "A pensar...",
  });

  const payload = {
    message: promptText,
    history: conversationHistory.slice(-10),
    style: styleSelectEl ? styleSelectEl.value : "Amigável e direto",
    user_id: USER_ID,
    pro_code: localStorage.getItem("rener_pro_code") || "",
    creator_key: localStorage.getItem("rener_creator_key") || "",
    gallery_image_base64: attachedBase64,
  };

  try {
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
