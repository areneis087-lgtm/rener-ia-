const API_BASE = "https://rener-ia.onrender.com";

const STORAGE_CHAT = "rener_chat_v2";
const STORAGE_USER = "rener_user_id_v1";
const STORAGE_STYLE = "rener_style_v1";
const STORAGE_CREATOR = "rener_creator_key_v1";
const STORAGE_PRO = "rener_pro_code_v1";

const el = {
  drawerBackdrop: document.getElementById("drawerBackdrop"),
  sideDrawer: document.getElementById("sideDrawer"),
  openDrawerBtn: document.getElementById("openDrawerBtn"),
  drawerCloseBtn: document.getElementById("drawerCloseBtn"),
  navNewChatBtn: document.getElementById("navNewChatBtn"),
  navLibraryBtn: document.getElementById("navLibraryBtn"),
  navImagesBtn: document.getElementById("navImagesBtn"),
  navScheduledBtn: document.getElementById("navScheduledBtn"),
  navCustomizeBtn: document.getElementById("navCustomizeBtn"),
  navVideosBtn: document.getElementById("navVideosBtn"),
  drawerList: document.getElementById("drawerList"),
  drawerModeText: document.getElementById("drawerModeText"),
  drawerClearHistoryBtn: document.getElementById("drawerClearHistoryBtn"),
  statusBadge: document.getElementById("statusBadge"),
  clearBtn: document.getElementById("clearBtn"),
  chatArea: document.getElementById("chatArea"),
  welcomeCard: document.getElementById("welcomeCard"),
  attachmentBar: document.getElementById("attachmentBar"),
  attachmentThumb: document.getElementById("attachmentThumb"),
  attachmentName: document.getElementById("attachmentName"),
  removeAttachmentBtn: document.getElementById("removeAttachmentBtn"),
  plusMenu: document.getElementById("plusMenu"),
  plusBtn: document.getElementById("plusBtn"),
  cameraTileBtn: document.getElementById("cameraTileBtn"),
  galleryTileBtn: document.getElementById("galleryTileBtn"),
  filesTileBtn: document.getElementById("filesTileBtn"),
  imagePromptTileBtn: document.getElementById("imagePromptTileBtn"),
  videoPromptRowBtn: document.getElementById("videoPromptRowBtn"),
  creatorKeyRowBtn: document.getElementById("creatorKeyRowBtn"),
  composerForm: document.getElementById("composerForm"),
  promptInput: document.getElementById("promptInput"),
  micBtn: document.getElementById("micBtn"),
  sendBtn: document.getElementById("sendBtn"),
  cameraInput: document.getElementById("cameraInput"),
  galleryInput: document.getElementById("galleryInput"),
  fileInput: document.getElementById("fileInput"),
};

let messages = [];
let pendingFile = null;
let selectedGalleryImageBase64 = "";
let isSending = false;
let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;
let touchStartX = 0;
let touchCurrentX = 0;

function getUserId() {
  let id = localStorage.getItem(STORAGE_USER);
  if (!id) {
    id = "rener_" + Math.random().toString(36).slice(2, 10) + "_" + Date.now().toString(36);
    localStorage.setItem(STORAGE_USER, id);
  }
  return id;
}

const userId = getUserId();

function getStyle() {
  return localStorage.getItem(STORAGE_STYLE) || "Amigável e direto";
}

function getCreatorKey() {
  return (localStorage.getItem(STORAGE_CREATOR) || "").trim();
}

function getProCode() {
  return (localStorage.getItem(STORAGE_PRO) || "").trim();
}

function atualizarStatus() {
  const creator = getCreatorKey();
  const pro = getProCode();
  if (el.statusBadge) {
    if (creator) el.statusBadge.textContent = "Criador • Online";
    else if (pro) el.statusBadge.textContent = "Pro • Online";
    else el.statusBadge.textContent = "Online";
  }
  if (el.drawerModeText) {
    el.drawerModeText.textContent = creator
      ? "Modo Criador"
      : pro
      ? "Modo Pro"
      : `Estilo: ${getStyle()}`;
  }
}

function openDrawer() {
  el.sideDrawer?.classList.add("open");
  el.drawerBackdrop?.classList.add("open");
  renderDrawerList("history");
}

function closeDrawer() {
  el.sideDrawer?.classList.remove("open");
  el.drawerBackdrop?.classList.remove("open");
}

function openPlusMenu() {
  el.plusMenu?.classList.remove("hidden");
}

function closePlusMenu() {
  el.plusMenu?.classList.add("hidden");
}

function togglePlusMenu() {
  if (!el.plusMenu) return;
  if (el.plusMenu.classList.contains("hidden")) openPlusMenu();
  else closePlusMenu();
}

function salvarMensagens() {
  try {
    const compact = messages.slice(-24).map((m) => ({
      role: m.role,
      content: m.content || "",
      type: m.type || "text",
      imageBase64: m.imageBase64 && m.imageBase64.length < 1800000 ? m.imageBase64 : "",
      videoBase64: "",
    }));
    localStorage.setItem(STORAGE_CHAT, JSON.stringify(compact));
  } catch (_) {}
}

function carregarMensagens() {
  try {
    const raw = localStorage.getItem(STORAGE_CHAT);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch (_) {
    return [];
  }
}

function scrollChatBottom() {
  if (!el.chatArea) return;
  requestAnimationFrame(() => {
    el.chatArea.scrollTop = el.chatArea.scrollHeight;
  });
}

function atualizarWelcome() {
  if (!el.welcomeCard) return;
  if (messages.length > 0) el.welcomeCard.classList.add("hidden");
  else el.welcomeCard.classList.remove("hidden");
}

function renderMessage(msg) {
  if (!el.chatArea) return;
  atualizarWelcome();

  const div = document.createElement("div");
  div.className = `message ${msg.role === "user" ? "user" : "assistant"}`;

  if (msg.content) {
    const p = document.createElement("div");
    p.textContent = msg.content;
    div.appendChild(p);
  }

  if (msg.imageBase64) {
    const src = msg.imageBase64.startsWith("data:")
      ? msg.imageBase64
      : `data:image/png;base64,${msg.imageBase64}`;

    const img = document.createElement("img");
    img.src = src;
    img.alt = "Imagem gerada pelo Rener";
    div.appendChild(img);

    const dlBtn = document.createElement("button");
    dlBtn.type = "button";
    dlBtn.className = "download-img-btn";
    dlBtn.textContent = "Baixar imagem";
    dlBtn.addEventListener("click", () => {
      const a = document.createElement("a");
      a.href = src;
      a.download = `rener_${Date.now()}.png`;
      a.click();
    });
    div.appendChild(dlBtn);
  }

  if (msg.videoBase64) {
    const vid = document.createElement("video");
    vid.controls = true;
    vid.playsInline = true;
    vid.src = msg.videoBase64.startsWith("data:")
      ? msg.videoBase64
      : `data:video/mp4;base64,${msg.videoBase64}`;
    div.appendChild(vid);
  }

  el.chatArea.appendChild(div);
  scrollChatBottom();
  return div;
}

function renderAllMessages() {
  if (!el.chatArea) return;
  Array.from(el.chatArea.querySelectorAll(".message")).forEach((n) => n.remove());
  atualizarWelcome();
  messages.forEach(renderMessage);
}

function renderDrawerList(tab = "history") {
  if (!el.drawerList) return;
  el.drawerList.innerHTML = "";

  if (tab === "images") {
    const imgs = messages.filter((m) => m.imageBase64);
    if (!imgs.length) {
      el.drawerList.innerHTML = `<div class="drawer-item-card"><strong>Nenhuma imagem ainda</strong><small>Peça uma imagem no chat para ver aqui.</small></div>`;
      return;
    }
    imgs.forEach((m, idx) => {
      const card = document.createElement("button");
      card.type = "button";
      card.className = "drawer-item-card";
      card.innerHTML = `<strong>Imagem ${idx + 1}</strong><small>${(m.content || "Gerada pelo Rener").slice(0, 60)}</small>`;
      card.addEventListener("click", () => {
        closeDrawer();
        renderMessage(m);
      });
      el.drawerList.appendChild(card);
    });
    return;
  }

  const userMsgs = messages.filter((m) => m.role === "user");
  if (!userMsgs.length) {
    el.drawerList.innerHTML = `<div class="drawer-item-card"><strong>Sem histórico ainda</strong><small>Envie uma mensagem para começar.</small></div>`;
    return;
  }

  userMsgs.slice(-10).reverse().forEach((m) => {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "drawer-item-card";
    card.innerHTML = `<strong>${(m.content || "Mensagem").slice(0, 42)}</strong><small>Toque para rolar até o chat</small>`;
    card.addEventListener("click", () => {
      closeDrawer();
      scrollChatBottom();
    });
    el.drawerList.appendChild(card);
  });
}

function clearAttachment() {
  pendingFile = null;
  selectedGalleryImageBase64 = "";
  if (el.cameraInput) el.cameraInput.value = "";
  if (el.galleryInput) el.galleryInput.value = "";
  if (el.fileInput) el.fileInput.value = "";
  el.attachmentBar?.classList.add("hidden");
  if (el.attachmentThumb) {
    el.attachmentThumb.src = "";
    el.attachmentThumb.classList.add("hidden");
  }
  if (el.attachmentName) el.attachmentName.textContent = "";
}

function setAttachment(file, fromGallery = false) {
  if (!file) return;
  pendingFile = file;
  el.attachmentBar?.classList.remove("hidden");
  if (el.attachmentName) {
    el.attachmentName.textContent = fromGallery ? `Galeria: ${file.name}` : file.name;
  }

  if (file.type && file.type.startsWith("image/")) {
    const reader = new FileReader();
    reader.onload = (ev) => {
      const dataUrl = String(ev.target?.result || "");
      if (el.attachmentThumb) {
        el.attachmentThumb.src = dataUrl;
        el.attachmentThumb.classList.remove("hidden");
      }
      selectedGalleryImageBase64 = fromGallery ? dataUrl : "";
    };
    reader.readAsDataURL(file);
  } else {
    selectedGalleryImageBase64 = "";
    el.attachmentThumb?.classList.add("hidden");
  }
}

function ehPedidoGeracaoMidia(texto) {
  const t = (texto || "").toLowerCase();
  return [
    "crie uma imagem",
    "criar uma imagem",
    "gere uma imagem",
    "gerar uma imagem",
    "faça uma imagem",
    "faca uma imagem",
    "faça a imagem",
    "faca a imagem",
    "imagem de ",
    "foto de ",
    "desenhe ",
    "escudo",
    "emblema",
    "vídeo",
    "video",
  ].some((p) => t.includes(p));
}

async function fetchRetry(url, opts, tries = 4) {
  let lastErr = null;
  for (let i = 0; i < tries; i++) {
    try {
      return await fetch(url, opts);
    } catch (err) {
      lastErr = err;
      if (i < tries - 1) await new Promise((r) => setTimeout(r, 1500 * (i + 1)));
    }
  }
  throw lastErr;
}

async function parseJsonSafe(resp) {
  const txt = await resp.text();
  try {
    return JSON.parse(txt);
  } catch (_) {
    throw new Error(txt || `HTTP ${resp.status}`);
  }
}

async function chamarAnalyze(file, promptText) {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("prompt", promptText || "Analise este arquivo e me dê um resumo claro e útil.");
  fd.append("style", getStyle());

  const resp = await fetchRetry(`${API_BASE}/analyze`, { method: "POST", body: fd });
  const data = await parseJsonSafe(resp);
  if (!resp.ok) throw new Error(data.detail || data.reply || `HTTP ${resp.status}`);
  return data;
}

async function chamarChat(text, galleryB64 = "") {
  const history = messages.slice(-12).map((m) => ({
    role: m.role,
    content: m.content || "",
    has_image: Boolean(m.imageBase64),
    has_video: Boolean(m.videoBase64),
  }));

  const resp = await fetchRetry(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message: text,
      history,
      style: getStyle(),
      user_id: userId,
      pro_code: getProCode(),
      creator_key: getCreatorKey(),
      gallery_image_base64: galleryB64 || "",
    }),
  });

  const data = await parseJsonSafe(resp);
  if (!resp.ok) throw new Error(data.detail || data.reply || `HTTP ${resp.status}`);
  return data;
}

async function handleSubmit(e) {
  e.preventDefault();
  if (isSending) return;

  const text = (el.promptInput?.value || "").trim();
  if (!text && !pendingFile && !selectedGalleryImageBase64) return;

  isSending = true;
  if (el.sendBtn) el.sendBtn.disabled = true;
  closePlusMenu();

  const usarGaleriaNoChat = Boolean(selectedGalleryImageBase64) && (!pendingFile || ehPedidoGeracaoMidia(text));

  const userMsg = {
    role: "user",
    type: "text",
    content: text || (pendingFile ? `Arquivo: ${pendingFile.name}` : "Imagem da galeria"),
  };
  messages.push(userMsg);
  renderMessage(userMsg);
  salvarMensagens();

  if (el.promptInput) {
    el.promptInput.value = "";
    el.promptInput.style.height = "auto";
  }

  const loadingEl = renderMessage({ role: "assistant", type: "text", content: "Pensando..." });

  try {
    let data;
    if (usarGaleriaNoChat) {
      data = await chamarChat(text || "Crie uma imagem com o escudo da galeria", selectedGalleryImageBase64);
      pendingFile = null;
      if (el.galleryInput) el.galleryInput.value = "";
    } else if (pendingFile) {
      data = await chamarAnalyze(pendingFile, text);
      clearAttachment();
    } else {
      data = await chamarChat(text, selectedGalleryImageBase64);
    }

    loadingEl?.remove();

    const botMsg = {
      role: "assistant",
      type: data.type || "text",
      content: data.reply || "",
      imageBase64: data.image_base64 || "",
      videoBase64: data.video_base64 || "",
    };
    messages.push(botMsg);
    renderMessage(botMsg);
    salvarMensagens();
  } catch (err) {
    loadingEl?.remove();
    const errMsg = {
      role: "assistant",
      type: "text",
      content: `Erro ao enviar: ${err?.message || "falha de rede"}.`,
    };
    messages.push(errMsg);
    renderMessage(errMsg);
  } finally {
    isSending = false;
    if (el.sendBtn) el.sendBtn.disabled = false;
  }
}

async function toggleMic() {
  if (isRecording && mediaRecorder) {
    mediaRecorder.stop();
    isRecording = false;
    el.micBtn?.classList.remove("recording");
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

      const fd = new FormData();
      fd.append("file", blob, "ditado.webm");
      try {
        const resp = await fetchRetry(`${API_BASE}/transcribe`, { method: "POST", body: fd });
        if (resp.ok) {
          const data = await parseJsonSafe(resp);
          if (data.text && el.promptInput) {
            el.promptInput.value = `${el.promptInput.value ? el.promptInput.value + " " : ""}${data.text}`.trim();
            el.promptInput.focus();
          }
        }
      } catch (_) {}
    };
    mediaRecorder.start();
    isRecording = true;
    el.micBtn?.classList.add("recording");
  } catch (_) {}
}

function novaConversa() {
  messages = [];
  localStorage.removeItem(STORAGE_CHAT);
  clearAttachment();
  renderAllMessages();
  closeDrawer();
}

el.openDrawerBtn?.addEventListener("click", openDrawer);
el.drawerCloseBtn?.addEventListener("click", closeDrawer);
el.drawerBackdrop?.addEventListener("click", closeDrawer);

el.navNewChatBtn?.addEventListener("click", novaConversa);
el.clearBtn?.addEventListener("click", novaConversa);
el.drawerClearHistoryBtn?.addEventListener("click", novaConversa);
el.navImagesBtn?.addEventListener("click", () => renderDrawerList("images"));
el.navLibraryBtn?.addEventListener("click", () => renderDrawerList("history"));
el.navVideosBtn?.addEventListener("click", () => {
  closeDrawer();
  if (el.promptInput) {
    el.promptInput.value = "Gere um vídeo curto de ";
    el.promptInput.focus();
  }
});
el.navScheduledBtn?.addEventListener("click", () => {
  closeDrawer();
  renderMessage({ role: "assistant", type: "text", content: "Agendamentos em breve no Rener." });
});
el.navCustomizeBtn?.addEventListener("click", () => {
  closeDrawer();
  const novoEstilo = prompt("Estilo de resposta (ex.: Amigável e direto, Técnico, Curto):", getStyle());
  if (novoEstilo && novoEstilo.trim()) {
    localStorage.setItem(STORAGE_STYLE, novoEstilo.trim());
    atualizarStatus();
  }
});

el.plusBtn?.addEventListener("click", (e) => {
  e.stopPropagation();
  togglePlusMenu();
});

document.addEventListener("click", (e) => {
  if (el.plusMenu && !el.plusMenu.classList.contains("hidden")) {
    if (!el.plusMenu.contains(e.target) && e.target !== el.plusBtn && !el.plusBtn?.contains(e.target)) {
      closePlusMenu();
    }
  }
});

el.galleryTileBtn?.addEventListener("click", () => {
  closePlusMenu();
  if (!el.galleryInput) return;
  el.galleryInput.removeAttribute("capture");
  el.galleryInput.setAttribute("accept", "image/*");
  el.galleryInput.value = "";
  el.galleryInput.click();
});

el.cameraTileBtn?.addEventListener("click", () => {
  closePlusMenu();
  if (!el.cameraInput) return;
  el.cameraInput.setAttribute("accept", "image/*");
  el.cameraInput.setAttribute("capture", "environment");
  el.cameraInput.value = "";
  el.cameraInput.click();
});

el.filesTileBtn?.addEventListener("click", () => {
  closePlusMenu();
  if (!el.fileInput) return;
  el.fileInput.value = "";
  el.fileInput.click();
});

el.imagePromptTileBtn?.addEventListener("click", () => {
  closePlusMenu();
  if (el.promptInput) {
    el.promptInput.value = "Crie uma imagem de ";
    el.promptInput.focus();
  }
});

el.videoPromptRowBtn?.addEventListener("click", () => {
  closePlusMenu();
  if (el.promptInput) {
    el.promptInput.value = "Gere um vídeo curto de ";
    el.promptInput.focus();
  }
});

el.creatorKeyRowBtn?.addEventListener("click", () => {
  closePlusMenu();
  const chave = prompt("Digite sua Chave Criador (ou deixe em branco para manter):", getCreatorKey());
  if (chave !== null) {
    localStorage.setItem(STORAGE_CREATOR, chave.trim());
    atualizarStatus();
  }
});

el.galleryInput?.addEventListener("change", (e) => {
  const f = e.target.files?.[0];
  if (f) setAttachment(f, true);
});

el.cameraInput?.addEventListener("change", (e) => {
  const f = e.target.files?.[0];
  if (f) setAttachment(f, false);
});

el.fileInput?.addEventListener("change", (e) => {
  const f = e.target.files?.[0];
  if (f) setAttachment(f, false);
});

el.removeAttachmentBtn?.addEventListener("click", clearAttachment);
el.composerForm?.addEventListener("submit", handleSubmit);
el.micBtn?.addEventListener("click", toggleMic);

el.promptInput?.addEventListener("input", () => {
  el.promptInput.style.height = "auto";
  el.promptInput.style.height = `${Math.min(el.promptInput.scrollHeight, 130)}px`;
});

document.addEventListener("touchstart", (e) => {
  touchStartX = e.touches[0]?.clientX || 0;
  touchCurrentX = touchStartX;
}, { passive: true });

document.addEventListener("touchmove", (e) => {
  touchCurrentX = e.touches[0]?.clientX || touchStartX;
}, { passive: true });

document.addEventListener("touchend", () => {
  const dx = touchCurrentX - touchStartX;
  if (touchStartX < 32 && dx > 70) openDrawer();
  else if (el.sideDrawer?.classList.contains("open") && dx < -70) closeDrawer();
}, { passive: true });

atualizarStatus();
messages = carregarMensagens();
renderAllMessages();
