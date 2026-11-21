const API_BASE = "https://rener-ia.onrender.com";

const STORAGE_KEYS = {
  history: "rener_chat_history_v1",
  sessions: "rener_chat_sessions_v1",
  library: "rener_media_library_v1",
  scheduled: "rener_scheduled_prompts_v1",
  userId: "rener_user_id_v1",
  creatorKey: "rener_creator_key_v1",
  proCode: "rener_pro_code_v1",
  style: "rener_style_v1",
};

const openDrawerBtn = document.getElementById("openDrawerBtn");
const drawerCloseBtn = document.getElementById("drawerCloseBtn");
const drawerBackdrop = document.getElementById("drawerBackdrop");
const sideDrawer = document.getElementById("sideDrawer");
const drawerList = document.getElementById("drawerList");
const drawerModeText = document.getElementById("drawerModeText");
const drawerClearHistoryBtn = document.getElementById("drawerClearHistoryBtn");

const navNewChatBtn = document.getElementById("navNewChatBtn");
const navLibraryBtn = document.getElementById("navLibraryBtn");
const navImagesBtn = document.getElementById("navImagesBtn");
const navScheduledBtn = document.getElementById("navScheduledBtn");
const navCustomizeBtn = document.getElementById("navCustomizeBtn");
const navVideosBtn = document.getElementById("navVideosBtn");

const clearBtn = document.getElementById("clearBtn");
const statusBadge = document.getElementById("statusBadge");
const chatArea = document.getElementById("chatArea");
const welcomeCard = document.getElementById("welcomeCard");

const attachmentBar = document.getElementById("attachmentBar");
const attachmentThumb = document.getElementById("attachmentThumb");
const attachmentName = document.getElementById("attachmentName");
const removeAttachmentBtn = document.getElementById("removeAttachmentBtn");

const plusBtn = document.getElementById("plusBtn");
const plusMenu = document.getElementById("plusMenu");
const cameraTileBtn = document.getElementById("cameraTileBtn");
const galleryTileBtn = document.getElementById("galleryTileBtn");
const filesTileBtn = document.getElementById("filesTileBtn");
const imagePromptTileBtn = document.getElementById("imagePromptTileBtn");
const videoPromptRowBtn = document.getElementById("videoPromptRowBtn");
const creatorKeyRowBtn = document.getElementById("creatorKeyRowBtn");

const composerForm = document.getElementById("composerForm");
const promptInput = document.getElementById("promptInput");
const micBtn = document.getElementById("micBtn");
const sendBtn = document.getElementById("sendBtn");

const cameraInput = document.getElementById("cameraInput");
const galleryInput = document.getElementById("galleryInput");
const fileInput = document.getElementById("fileInput");

let history = [];
let attachedFile = null;
let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;
let isSending = false;

function getUserId() {
  let id = localStorage.getItem(STORAGE_KEYS.userId);
  if (!id) {
    id = "user_" + Math.random().toString(36).slice(2, 10);
    localStorage.setItem(STORAGE_KEYS.userId, id);
  }
  return id;
}

function loadJson(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}

function saveJson(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // ignora erro de quota do navegador
  }
}

function updateModeBadge() {
  const creatorKey = (localStorage.getItem(STORAGE_KEYS.creatorKey) || "").trim();
  const proCode = (localStorage.getItem(STORAGE_KEYS.proCode) || "").trim();
  if (creatorKey) {
    drawerModeText.textContent = "Modo Criador";
    statusBadge.textContent = "Criador • Online";
  } else if (proCode) {
    drawerModeText.textContent = "Modo Pro";
    statusBadge.textContent = "Pro • Online";
  } else {
    drawerModeText.textContent = "Modo Padrão";
    statusBadge.textContent = "Online";
  }
}

function openDrawer() {
  sideDrawer.classList.add("open");
  drawerBackdrop.classList.add("open");
}

function closeDrawer() {
  sideDrawer.classList.remove("open");
  drawerBackdrop.classList.remove("open");
}

function syncWelcomeVisibility() {
  if (!welcomeCard) return;
  const hasMessages = chatArea.querySelectorAll(".message").length > 0;
  welcomeCard.classList.toggle("hidden", hasMessages);
}

function saveCurrentSessionSnapshot() {
  if (!history.length) return;
  const sessions = loadJson(STORAGE_KEYS.sessions, []);
  const firstUserMsg = history.find((m) => m.role === "user" && m.content);
  const title = (firstUserMsg?.content || "Conversa").trim().slice(0, 42);
  const preview = (history[history.length - 1]?.content || "").trim().slice(0, 64);

  const filtered = sessions.filter((s) => s.title !== title);
  filtered.unshift({
    id: Date.now().toString(),
    title,
    preview,
    messages: history.map((m) => ({
      role: m.role,
      content: m.content || "",
      has_image: Boolean(m.has_image),
      has_video: Boolean(m.has_video),
    })),
  });
  saveJson(STORAGE_KEYS.sessions, filtered.slice(0, 15));
}

function addToLibrary(type, label, dataUrlOrText) {
  const lib = loadJson(STORAGE_KEYS.library, []);
  lib.unshift({
    id: Date.now().toString(),
    type,
    label,
    preview: typeof dataUrlOrText === "string" && dataUrlOrText.startsWith("data:") ? dataUrlOrText : "",
    text: typeof dataUrlOrText === "string" && !dataUrlOrText.startsWith("data:") ? dataUrlOrText.slice(0, 120) : label,
  });
  saveJson(STORAGE_KEYS.library, lib.slice(0, 20));
}

function appendMessage(role, text = "", options = {}) {
  const div = document.createElement("div");
  div.className = `message ${role}`;

  if (text) {
    const p = document.createElement("div");
    p.textContent = text;
    div.appendChild(p);
  }

  if (options.imageSrc) {
    const img = document.createElement("img");
    img.src = options.imageSrc;
    img.alt = "Imagem gerada pelo Rener";
    div.appendChild(img);

    const dlBtn = document.createElement("button");
    dlBtn.type = "button";
    dlBtn.className = "download-img-btn";
    dlBtn.textContent = "⬇ Guardar imagem";
    dlBtn.addEventListener("click", () => {
      const a = document.createElement("a");
      a.href = options.imageSrc;
      a.download = `rener-${Date.now()}.png`;
      a.click();
    });
    div.appendChild(dlBtn);
  }

  if (options.videoSrc) {
    const video = document.createElement("video");
    video.src = options.videoSrc;
    video.controls = true;
    video.playsInline = true;
    div.appendChild(video);
  }

  chatArea.appendChild(div);
  chatArea.scrollTop = chatArea.scrollHeight;
  syncWelcomeVisibility();
  return div;
}

function renderDrawerSessions() {
  const sessions = loadJson(STORAGE_KEYS.sessions, []);
  drawerList.innerHTML = "";
  if (!sessions.length) {
    const empty = document.createElement("button");
    empty.type = "button";
    empty.className = "drawer-item-card";
    empty.innerHTML = "<strong>Sem conversas guardadas</strong><small>As tuas conversas aparecem aqui</small>";
    drawerList.appendChild(empty);
    return;
  }

  sessions.forEach((sess) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "drawer-item-card";
    btn.innerHTML = `<strong>${sess.title}</strong><small>${sess.preview || "Conversa guardada"}</small>`;
    btn.addEventListener("click", () => {
      chatArea.querySelectorAll(".message").forEach((el) => el.remove());
      history = Array.isArray(sess.messages) ? sess.messages : [];
      saveJson(STORAGE_KEYS.history, history);
      history.forEach((m) => appendMessage(m.role, m.content || ""));
      closeDrawer();
    });
    drawerList.appendChild(btn);
  });
}

function renderDrawerLibrary() {
  const lib = loadJson(STORAGE_KEYS.library, []);
  drawerList.innerHTML = "";
  if (!lib.length) {
    const empty = document.createElement("button");
    empty.type = "button";
    empty.className = "drawer-item-card";
    empty.innerHTML = "<strong>Biblioteca vazia</strong><small>Imagens e criações recentes ficam registadas aqui</small>";
    drawerList.appendChild(empty);
    return;
  }

  lib.forEach((item) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "drawer-item-card";
    btn.innerHTML = `<strong>${item.type === "image" ? "🖼 Imagem" : "🎬 Criação"}: ${item.label}</strong><small>${item.text || ""}</small>`;
    btn.addEventListener("click", () => {
      if (item.preview) {
        appendMessage("assistant", `Da biblioteca (${item.label}):`, { imageSrc: item.preview });
      } else {
        focusPromptWith(item.label);
      }
      closeDrawer();
    });
    drawerList.appendChild(btn);
  });
}

function renderDrawerScheduled() {
  const scheduled = loadJson(STORAGE_KEYS.scheduled, [
    { label: "Resumo diário rápido", prompt: "Faz um resumo rápido e direto dos principais pontos de hoje." },
    { label: "Ideia visual criativa", prompt: "Gere uma imagem detalhada e nítida de um estádio lotado à noite." },
  ]);
  saveJson(STORAGE_KEYS.scheduled, scheduled);

  drawerList.innerHTML = "";
  const addBtn = document.createElement("button");
  addBtn.type = "button";
  addBtn.className = "drawer-item-card";
  addBtn.innerHTML = "<strong>+ Novo atalho programado</strong><small>Guarda um pedido recorrente para usar quando quiseres</small>";
  addBtn.addEventListener("click", () => {
    const label = prompt("Nome do atalho programado:");
    if (!label) return;
    const text = prompt("Texto/pedido que será inserido no chat:");
    if (!text) return;
    const next = [{ label: label.trim(), prompt: text.trim() }, ...scheduled];
    saveJson(STORAGE_KEYS.scheduled, next);
    renderDrawerScheduled();
  });
  drawerList.appendChild(addBtn);

  scheduled.forEach((item) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "drawer-item-card";
    btn.innerHTML = `<strong>◔ ${item.label}</strong><small>${item.prompt}</small>`;
    btn.addEventListener("click", () => {
      focusPromptWith(item.prompt);
      closeDrawer();
    });
    drawerList.appendChild(btn);
  });
}

function renderDrawerCustomize() {
  const currentStyle = localStorage.getItem(STORAGE_KEYS.style) || "Amigável e direto";
  const currentCreator = localStorage.getItem(STORAGE_KEYS.creatorKey) || "";
  const currentPro = localStorage.getItem(STORAGE_KEYS.proCode) || "";

  drawerList.innerHTML = "";

  const styleBtn = document.createElement("button");
  styleBtn.type = "button";
  styleBtn.className = "drawer-item-card";
  styleBtn.innerHTML = `<strong>Estilo de resposta</strong><small>Atual: ${currentStyle} (toca para alterar)</small>`;
  styleBtn.addEventListener("click", () => {
    const novo = prompt("Estilo de resposta (ex.: Amigável e direto, Técnico, Criativo):", currentStyle);
    if (novo !== null) {
      localStorage.setItem(STORAGE_KEYS.style, novo.trim() || "Amigável e direto");
      renderDrawerCustomize();
    }
  });

  const creatorBtn = document.createElement("button");
  creatorBtn.type = "button";
  creatorBtn.className = "drawer-item-card";
  creatorBtn.innerHTML = `<strong>Chave de Criador</strong><small>${currentCreator ? "Configurada" : "Não configurada (toca para definir)"}</small>`;
  creatorBtn.addEventListener("click", () => {
    const nova = prompt("Chave de Criador (deixa em branco para remover):", currentCreator);
    if (nova !== null) {
      localStorage.setItem(STORAGE_KEYS.creatorKey, nova.trim());
      updateModeBadge();
      renderDrawerCustomize();
    }
  });

  const proBtn = document.createElement("button");
  proBtn.type = "button";
  proBtn.className = "drawer-item-card";
  proBtn.innerHTML = `<strong>Código Pro</strong><small>${currentPro ? "Ativo" : "Não configurado (toca para definir)"}</small>`;
  proBtn.addEventListener("click", () => {
    const novo = prompt("Código Pro (deixa em branco para remover):", currentPro);
    if (novo !== null) {
      localStorage.setItem(STORAGE_KEYS.proCode, novo.trim());
      updateModeBadge();
      renderDrawerCustomize();
    }
  });

  drawerList.appendChild(styleBtn);
  drawerList.appendChild(creatorBtn);
  drawerList.appendChild(proBtn);
}

function focusPromptWith(prefixText) {
  promptInput.value = prefixText;
  autoResizeTextarea();
  promptInput.focus();
}

function startNewConversation() {
  saveCurrentSessionSnapshot();
  history = [];
  saveJson(STORAGE_KEYS.history, history);
  chatArea.querySelectorAll(".message").forEach((el) => el.remove());
  clearAttachment();
  syncWelcomeVisibility();
  renderDrawerSessions();
}

function autoResizeTextarea() {
  promptInput.style.height = "auto";
  promptInput.style.height = `${Math.min(promptInput.scrollHeight, 140)}px`;
}

function clearAttachment() {
  attachedFile = null;
  cameraInput.value = "";
  galleryInput.value = "";
  fileInput.value = "";
  attachmentThumb.src = "";
  attachmentThumb.classList.add("hidden");
  attachmentName.textContent = "";
  attachmentBar.classList.add("hidden");
}

function handleFileSelection(file) {
  if (!file) return;
  attachedFile = file;
  attachmentName.textContent = file.name;
  attachmentBar.classList.remove("hidden");

  if (file.type && file.type.startsWith("image/")) {
    const reader = new FileReader();
    reader.onload = () => {
      attachmentThumb.src = String(reader.result || "");
      attachmentThumb.classList.remove("hidden");
    };
    reader.readAsDataURL(file);
  } else {
    attachmentThumb.src = "";
    attachmentThumb.classList.add("hidden");
  }
  plusMenu.classList.add("hidden");
}

function togglePlusMenu() {
  plusMenu.classList.toggle("hidden");
}

async function sendFileAnalysis(file, promptText) {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("prompt", promptText || "Analise este ficheiro e dá-me um resumo claro e útil.");
  formData.append("style", localStorage.getItem(STORAGE_KEYS.style) || "Amigável e direto");

  const resp = await fetch(`${API_BASE}/analyze`, {
    method: "POST",
    body: formData,
  });
  const data = await resp.json();
  if (!resp.ok) {
    throw new Error(data.detail || "Falha ao analisar o ficheiro.");
  }
  return data.reply || "Análise concluída.";
}

async function sendChatMessage(messageText) {
  const payload = {
    message: messageText,
    history: history.slice(-10).map((m) => ({
      role: m.role,
      content: m.content || "",
      has_image: Boolean(m.has_image),
      has_video: Boolean(m.has_video),
    })),
    style: localStorage.getItem(STORAGE_KEYS.style) || "Amigável e direto",
    user_id: getUserId(),
    pro_code: (localStorage.getItem(STORAGE_KEYS.proCode) || "").trim(),
    creator_key: (localStorage.getItem(STORAGE_KEYS.creatorKey) || "").trim(),
  };

  const resp = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await resp.json();
  if (!resp.ok) {
    throw new Error(data.detail || "Erro de comunicação com o servidor.");
  }
  return data;
}

composerForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  if (isSending) return;

  const text = promptInput.value.trim();
  const currentFile = attachedFile;
  if (!text && !currentFile) return;

  plusMenu.classList.add("hidden");
  isSending = true;
  sendBtn.disabled = true;

  const userDisplay = currentFile
    ? `${text || "Analisa este ficheiro"} [${currentFile.name}]`
    : text;
  appendMessage("user", userDisplay);

  promptInput.value = "";
  autoResizeTextarea();
  clearAttachment();

  const loadingBubble = appendMessage("assistant", "A pensar...");

  try {
    if (currentFile) {
      const reply = await sendFileAnalysis(currentFile, text);
      loadingBubble.remove();
      appendMessage("assistant", reply);
      history.push({ role: "user", content: userDisplay });
      history.push({ role: "assistant", content: reply });
    } else {
      const data = await sendChatMessage(text);
      loadingBubble.remove();

      if (data.type === "image" && data.image_base64) {
        const imgSrc = `data:image/png;base64,${data.image_base64}`;
        appendMessage("assistant", data.reply || "Aqui está:", { imageSrc });
        addToLibrary("image", text.slice(0, 36) || "Imagem gerada", imgSrc);
        history.push({ role: "user", content: text });
        history.push({ role: "assistant", content: data.reply || "Imagem gerada", has_image: true });
      } else if (data.type === "video" && data.video_base64) {
        const videoSrc = `data:video/mp4;base64,${data.video_base64}`;
        appendMessage("assistant", data.reply || "Aqui está:", { videoSrc });
        addToLibrary("video", text.slice(0, 36) || "Vídeo gerado", text);
        history.push({ role: "user", content: text });
        history.push({ role: "assistant", content: data.reply || "Vídeo gerado", has_video: true });
      } else {
        const reply = data.reply || "";
        appendMessage("assistant", reply);
        history.push({ role: "user", content: text });
        history.push({ role: "assistant", content: reply });
      }
    }

    saveJson(STORAGE_KEYS.history, history.slice(-30));
    saveCurrentSessionSnapshot();
    renderDrawerSessions();
  } catch (err) {
    loadingBubble.remove();
    appendMessage("assistant", err?.message || "Ocorreu um erro ao processar o pedido.");
  } finally {
    isSending = false;
    sendBtn.disabled = false;
  }
});

micBtn.addEventListener("click", async () => {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    appendMessage("assistant", "A gravação de voz não é suportada neste navegador.");
    return;
  }

  if (!isRecording) {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioChunks = [];
      mediaRecorder = new MediaRecorder(stream);
      mediaRecorder.ondataavailable = (ev) => {
        if (ev.data.size > 0) audioChunks.push(ev.data);
      };
      mediaRecorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(audioChunks, { type: "audio/webm" });
        const formData = new FormData();
        formData.append("file", blob, "ditado.webm");

        try {
          const resp = await fetch(`${API_BASE}/transcribe`, { method: "POST", body: formData });
          const data = await resp.json();
          if (data.text) {
            focusPromptWith(data.text);
          }
        } catch {
          appendMessage("assistant", "Não foi possível transcrever o áudio.");
        }
      };
      mediaRecorder.start();
      isRecording = true;
      micBtn.classList.add("recording");
    } catch {
      appendMessage("assistant", "Permissão de microfone negada.");
    }
  } else {
    mediaRecorder?.stop();
    isRecording = false;
    micBtn.classList.remove("recording");
  }
});

openDrawerBtn.addEventListener("click", () => {
  renderDrawerSessions();
  openDrawer();
});
drawerCloseBtn.addEventListener("click", closeDrawer);
drawerBackdrop.addEventListener("click", closeDrawer);
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeDrawer();
});

// Gesto de deslizar/puxar pela borda lateral esquerda
let edgeTouchStartX = null;
let edgeTouchStartY = null;

document.addEventListener("touchstart", (e) => {
  const touch = e.touches[0];
  if (!touch) return;
  if (!sideDrawer.classList.contains("open") && touch.clientX <= 28) {
    edgeTouchStartX = touch.clientX;
    edgeTouchStartY = touch.clientY;
  } else if (sideDrawer.classList.contains("open")) {
    edgeTouchStartX = touch.clientX;
    edgeTouchStartY = touch.clientY;
  }
}, { passive: true });

document.addEventListener("touchmove", (e) => {
  if (edgeTouchStartX === null || edgeTouchStartY === null) return;
  const touch = e.touches[0];
  if (!touch) return;
  const dx = touch.clientX - edgeTouchStartX;
  const dy = Math.abs(touch.clientY - edgeTouchStartY);
  if (dy > 45) return;

  if (!sideDrawer.classList.contains("open") && dx > 55) {
    edgeTouchStartX = null;
    renderDrawerSessions();
    openDrawer();
  } else if (sideDrawer.classList.contains("open") && dx < -55) {
    edgeTouchStartX = null;
    closeDrawer();
  }
}, { passive: true });

navNewChatBtn.addEventListener("click", () => {
  startNewConversation();
  closeDrawer();
});
navLibraryBtn.addEventListener("click", renderDrawerLibrary);
navImagesBtn.addEventListener("click", () => {
  closeDrawer();
  focusPromptWith("Gere uma imagem de ");
});
navScheduledBtn.addEventListener("click", renderDrawerScheduled);
navCustomizeBtn.addEventListener("click", renderDrawerCustomize);
navVideosBtn.addEventListener("click", () => {
  closeDrawer();
  focusPromptWith("Gere um vídeo curto de ");
});

drawerClearHistoryBtn.addEventListener("click", () => {
  saveJson(STORAGE_KEYS.sessions, []);
  renderDrawerSessions();
});

clearBtn.addEventListener("click", startNewConversation);
plusBtn.addEventListener("click", togglePlusMenu);
removeAttachmentBtn.addEventListener("click", clearAttachment);

cameraTileBtn.addEventListener("click", () => cameraInput.click());
galleryTileBtn.addEventListener("click", () => galleryInput.click());
filesTileBtn.addEventListener("click", () => fileInput.click());
imagePromptTileBtn.addEventListener("click", () => {
  plusMenu.classList.add("hidden");
  focusPromptWith("Gere uma imagem de ");
});
videoPromptRowBtn.addEventListener("click", () => {
  plusMenu.classList.add("hidden");
  focusPromptWith("Gere um vídeo curto de ");
});
creatorKeyRowBtn.addEventListener("click", () => {
  plusMenu.classList.add("hidden");
  openDrawer();
  renderDrawerCustomize();
});

cameraInput.addEventListener("change", (e) => handleFileSelection(e.target.files?.[0]));
galleryInput.addEventListener("change", (e) => handleFileSelection(e.target.files?.[0]));
fileInput.addEventListener("change", (e) => handleFileSelection(e.target.files?.[0]));
promptInput.addEventListener("input", autoResizeTextarea);

updateModeBadge();
renderDrawerSessions();
syncWelcomeVisibility();
