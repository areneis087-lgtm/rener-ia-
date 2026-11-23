
const BACKEND_URL = "https://rener-ia.onrender.com";

const elements = {
    sidebar: document.getElementById("sidebar"),
    menuButton: document.getElementById("menu-button"),
    closeSidebar: document.getElementById("close-sidebar"),
    newChat: document.getElementById("new-chat"),
    clearChat: document.getElementById("clear-chat"),
    attachmentButton: document.getElementById("attachment-button"),
    attachmentMenu: document.getElementById("attachment-menu"),
    cameraButton: document.getElementById("camera-button"),
    galleryButton: document.getElementById("gallery-button"),
    filesButton: document.getElementById("files-button"),
    cameraInput: document.getElementById("camera-input"),
    galleryInput: document.getElementById("gallery-input"),
    filesInput: document.getElementById("files-input"),
    preview: document.getElementById("attachment-preview"),
    messageInput: document.getElementById("message-input"),
    sendButton: document.getElementById("send-button"),
    messages: document.getElementById("chat-messages"),
    welcome: document.getElementById("welcome-screen"),
    micButton: document.getElementById("mic-button")
};

let selectedImage = null;
let selectedFile = null;
let isSending = false;

const MAX_IMAGE_SIZE = 10 * 1024 * 1024;
const MAX_FILE_SIZE = 15 * 1024 * 1024;

let userId = localStorage.getItem("rener_user_id");

if (!userId) {
    userId = crypto.randomUUID
        ? crypto.randomUUID()
        : "user-" + Date.now() + "-" + Math.random().toString(36).slice(2);

    localStorage.setItem("rener_user_id", userId);
}

// MENU LATERAL

elements.menuButton.addEventListener("click", () => {
    elements.sidebar.classList.add("open");
});

elements.closeSidebar.addEventListener("click", () => {
    elements.sidebar.classList.remove("open");
});

// MENU DE ANEXOS

elements.attachmentButton.addEventListener("click", () => {
    elements.attachmentMenu.classList.toggle("hidden");
});

function closeAttachmentMenu() {
    elements.attachmentMenu.classList.add("hidden");
}

elements.cameraButton.addEventListener("click", () => {
    closeAttachmentMenu();
    elements.cameraInput.click();
});

elements.galleryButton.addEventListener("click", () => {
    closeAttachmentMenu();
    elements.galleryInput.click();
});

elements.filesButton.addEventListener("click", () => {
    closeAttachmentMenu();
    elements.filesInput.click();
});

// SELEÇÃO DE IMAGEM

elements.cameraInput.addEventListener("change", event => {
    handleImageSelection(event.target.files[0]);
    event.target.value = "";
});

elements.galleryInput.addEventListener("change", event => {
    handleImageSelection(event.target.files[0]);
    event.target.value = "";
});

function handleImageSelection(file) {
    if (!file) return;

    if (!file.type.startsWith("image/")) {
        alert("Selecione uma imagem válida.");
        return;
    }

    if (file.size > MAX_IMAGE_SIZE) {
        alert("A imagem deve ter no máximo 10 MB.");
        return;
    }

    selectedImage = file;
    selectedFile = null;

    renderAttachmentPreview(file, true);
}

// SELEÇÃO DE DOCUMENTOS

elements.filesInput.addEventListener("change", event => {
    const file = event.target.files[0];

    if (!file) return;

    if (file.type.startsWith("image/")) {
        alert("Para enviar fotos, use a opção Galeria.");
        event.target.value = "";
        return;
    }

    if (file.size > MAX_FILE_SIZE) {
        alert("O documento deve ter no máximo 15 MB.");
        event.target.value = "";
        return;
    }

    selectedFile = file;
    selectedImage = null;

    renderAttachmentPreview(file, false);
    event.target.value = "";
});

// PRÉVIA DO ANEXO

function renderAttachmentPreview(file, isImage) {
    elements.preview.innerHTML = "";

    const card = document.createElement("div");
    card.className = "preview-card";

    if (isImage) {
        const image = document.createElement("img");
        image.src = URL.createObjectURL(file);
        image.alt = "Prévia da imagem";
        card.appendChild(image);
    } else {
        const icon = document.createElement("span");
        icon.textContent = "📄";
        icon.style.fontSize = "30px";
        card.appendChild(icon);
    }

    const name = document.createElement("span");
    name.className = "preview-name";
    name.textContent = file.name;
    card.appendChild(name);

    const remove = document.createElement("button");
    remove.className = "remove-attachment";
    remove.textContent = "✕";
    remove.type = "button";
    remove.addEventListener("click", clearAttachment);
    card.appendChild(remove);

    elements.preview.appendChild(card);
}

function clearAttachment() {
    selectedImage = null;
    selectedFile = null;
    elements.preview.innerHTML = "";
    elements.cameraInput.value = "";
    elements.galleryInput.value = "";
    elements.filesInput.value = "";
}

// MENSAGENS

function addMessage(text, type, imageUrl = null) {
    elements.welcome.classList.add("hidden");

    const message = document.createElement("div");
    message.className = `message ${type}`;

    const content = document.createElement("div");
    content.textContent = text || "";
    message.appendChild(content);

    if (imageUrl) {
        const image = document.createElement("img");
        image.src = imageUrl;
        image.alt = "Imagem enviada";
        message.appendChild(image);
    }

    elements.messages.appendChild(message);

    const chatContainer = document.getElementById("chat-container");
    chatContainer.scrollTop = chatContainer.scrollHeight;

    return message;
}

function addLoadingMessage() {
    return addMessage("A Rener IA está pensando...", "assistant");
}

// CONVERTER ARQUIVO EM BASE64

function fileToBase64(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();

        reader.onload = () => {
            const result = String(reader.result);
            resolve(result.split(",")[1]);
        };

        reader.onerror = () => {
            reject(new Error("Não foi possível ler o arquivo."));
        };

        reader.readAsDataURL(file);
    });
}

// ENVIAR MENSAGEM

async function sendMessage() {
    if (isSending) return;

    const messageText = elements.messageInput.value.trim();

    if (!messageText && !selectedImage && !selectedFile) {
        return;
    }

    isSending = true;
    elements.sendButton.disabled = true;

    const imageToSend = selectedImage;
    const fileToSend = selectedFile;

    addMessage(
        messageText || (imageToSend ? "Analise esta imagem." : "Analise este documento."),
        "user",
        imageToSend ? URL.createObjectURL(imageToSend) : null
    );

    elements.messageInput.value = "";
    elements.messageInput.style.height = "auto";

    clearAttachment();

    const loading = addLoadingMessage();

    try {
        let endpoint = "/chat";
        let payload;

        if (fileToSend) {
            endpoint = "/analyze";

            const base64 = await fileToBase64(fileToSend);

            payload = {
                user_id: userId,
                message: messageText || "Analise este documento.",
                file_name: fileToSend.name,
                file_type: fileToSend.type,
                file_base64: base64
            };
        } else {
            payload = {
                user_id: userId,
                message: messageText,
                gallery_image_base64: imageToSend
                    ? await fileToBase64(imageToSend)
                    : null,
                image_name: imageToSend ? imageToSend.name : null
            };
        }

        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 120000);

        let response;

        try {
            response = await fetch(`${BACKEND_URL}${endpoint}`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify(payload),
                signal: controller.signal
            });
        } finally {
            clearTimeout(timeout);
        }

        const data = await response.json().catch(() => ({}));

        if (!response.ok) {
            throw new Error(data.detail || data.error || `Erro HTTP ${response.status}`);
        }

        const answer =
            data.response ||
            data.answer ||
            data.message ||
            "Não recebi uma resposta válida do servidor.";

        loading.remove();
        addMessage(answer, "assistant");

    } catch (error) {
        loading.remove();

        const message = error.name === "AbortError"
            ? "A solicitação demorou demais. Tente novamente."
            : error.message || "Não foi possível conectar ao servidor.";

        addMessage(`Erro: ${message}`, "assistant");

    } finally {
        isSending = false;
        elements.sendButton.disabled = false;
        elements.messageInput.focus();
    }
}

elements.sendButton.addEventListener("click", sendMessage);

elements.messageInput.addEventListener("keydown", event => {
    if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        sendMessage();
    }
});

elements.messageInput.addEventListener("input", () => {
    elements.messageInput.style.height = "auto";
    elements.messageInput.style.height =
        Math.min(elements.messageInput.scrollHeight, 160) + "px";
});

// NOVA CONVERSA

elements.newChat.addEventListener("click", () => {
    elements.messages.innerHTML = "";
    elements.welcome.classList.remove("hidden");
    elements.sidebar.classList.remove("open");
    clearAttachment();
});

// LIMPAR CONVERSA

elements.clearChat.addEventListener("click", () => {
    if (!confirm("Deseja limpar esta conversa?")) return;

    elements.messages.innerHTML = "";
    elements.welcome.classList.remove("hidden");
    clearAttachment();
});

// MICROFONE

elements.micButton.addEventListener("click", async () => {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        alert("Seu navegador não permite gravação de áudio.");
        return;
    }

    if (!window.MediaRecorder) {
        alert("Gravação de áudio não é compatível com este navegador.");
        return;
    }

    let stream;

    try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });

        const recorder = new MediaRecorder(stream);
        const chunks = [];

        recorder.ondataavailable = event => {
            if (event.data.size > 0) chunks.push(event.data);
        };

        recorder.onstop = async () => {
            stream.getTracks().forEach(track => track.stop());

            const audioBlob = new Blob(chunks, {
                type: recorder.mimeType || "audio/webm"
            });

            const formData = new FormData();
            formData.append("file", audioBlob, "audio.webm");
            formData.append("user_id", userId);

            try {
                elements.micButton.textContent = "⏳";

                const response = await fetch(`${BACKEND_URL}/transcribe`, {
                    method: "POST",
                    body: formData
                });

                const data = await response.json();

                if (!response.ok) {
                    throw new Error(data.detail || "Erro ao transcrever áudio.");
                }

                elements.messageInput.value =
                    (elements.messageInput.value + " " + (data.text || "")).trim();

                elements.messageInput.dispatchEvent(new Event("input"));

            } catch (error) {
                alert(error.message);
            } finally {
                elements.micButton.textContent = "🎤";
            }
        };

        recorder.start();
        elements.micButton.textContent = "⏹️";

        setTimeout(() => {
            if (recorder.state === "recording") {
                recorder.stop();
            }
        }, 15000);

        elements.micButton.onclick = () => {
            if (recorder.state === "recording") recorder.stop();
        };

    } catch (error) {
        if (stream) stream.getTracks().forEach(track => track.stop());
        alert("Não foi possível acessar o microfone: " + error.message);
    }
};

// FECHAR MENU AO CLICAR FORA

document.addEventListener("click", event => {
    if (
        !elements.attachmentMenu.contains(event.target) &&
        !elements.attachmentButton.contains(event.target)
    ) {
        closeAttachmentMenu();
    }
});
