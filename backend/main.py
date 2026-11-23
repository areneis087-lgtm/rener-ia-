
import os
import io
import json
import base64
import logging
import mimetypes
from typing import Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from groq import Groq

from pypdf import PdfReader
from docx import Document
from openpyxl import load_workbook

# =========================================================
# CONFIGURAÇÕES
# =========================================================

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rener-ia")

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

CHAT_MODEL = os.getenv(
    "CHAT_MODEL",
    "openai/gpt-oss-120b"
)

VISION_MODEL = os.getenv(
    "VISION_MODEL",
    "qwen/qwen3.8-27b"
)

TRANSCRIPTION_MODEL = os.getenv(
    "TRANSCRIPTION_MODEL",
    "whisper-large-v3"
)

MAX_IMAGE_SIZE = 10 * 1024 * 1024
MAX_DOCUMENT_SIZE = 15 * 1024 * 1024
MAX_AUDIO_SIZE = 25 * 1024 * 1024

client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

app = FastAPI(
    title="Rener IA API",
    description="Backend da assistente Rener IA",
    version="2.0.0"
)

# =========================================================
# CORS
# =========================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================================================
# MODELOS DE DADOS
# =========================================================

class ChatRequest(BaseModel):
    user_id: Optional[str] = None
    message: str = ""
    gallery_image_base64: Optional[str] = None
    image_name: Optional[str] = None


class AnalyzeRequest(BaseModel):
    user_id: Optional[str] = None
    message: str = "Analise este documento."
    file_name: str
    file_type: Optional[str] = None
    file_base64: str


# =========================================================
# FUNÇÕES AUXILIARES
# =========================================================

def get_client():
    if not client:
        raise HTTPException(
            status_code=503,
            detail="GROQ_API_KEY não foi configurada no servidor."
        )

    return client


def decode_base64_file(value: str) -> bytes:
    try:
        if "," in value and value.startswith("data:"):
            value = value.split(",", 1)[1]

        return base64.b64decode(value, validate=True)

    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Arquivo em Base64 inválido."
        )


def extract_document_text(
    file_bytes: bytes,
    filename: str
) -> str:

    extension = os.path.splitext(filename)[1].lower()

    try:
        if extension == ".pdf":
            reader = PdfReader(io.BytesIO(file_bytes))

            pages = []

            for page in reader.pages:
                pages.append(page.extract_text() or "")

            return "\n".join(pages)

        elif extension == ".docx":
            document = Document(io.BytesIO(file_bytes))

            paragraphs = [
                paragraph.text
                for paragraph in document.paragraphs
            ]

            return "\n".join(paragraphs)

        elif extension == ".xlsx":
            workbook = load_workbook(
                io.BytesIO(file_bytes),
                read_only=True,
                data_only=True
            )

            content = []

            for sheet in workbook.worksheets:
                content.append(f"\nPlanilha: {sheet.title}")

                for row in sheet.iter_rows(values_only=True):
                    values = [
                        str(value)
                        for value in row
                        if value is not None
                    ]

                    if values:
                        content.append(" | ".join(values))

            workbook.close()
            return "\n".join(content)

        elif extension == ".csv":
            try:
                return file_bytes.decode("utf-8-sig")
            except UnicodeDecodeError:
                return file_bytes.decode("latin-1")

        elif extension in (".txt", ".json"):
            try:
                text = file_bytes.decode("utf-8-sig")

                if extension == ".json":
                    try:
                        return json.dumps(
                            json.loads(text),
                            ensure_ascii=False,
                            indent=2
                        )
                    except json.JSONDecodeError:
                        return text

                return text

            except UnicodeDecodeError:
                return file_bytes.decode("latin-1")

        else:
            raise HTTPException(
                status_code=415,
                detail="Formato não suportado. Envie PDF, TXT, DOCX, CSV, XLSX ou JSON."
            )

    except HTTPException:
        raise

    except Exception as error:
        logger.exception("Erro ao ler documento")

        raise HTTPException(
            status_code=400,
            detail=f"Não foi possível ler o documento: {str(error)}"
        )


def ask_groq(messages, model=None):
    api = get_client()

    try:
        completion = api.chat.completions.create(
            model=model or CHAT_MODEL,
            messages=messages,
            temperature=0.7,
            max_completion_tokens=3000
        )

        return completion.choices[0].message.content or ""

    except Exception as error:
        logger.exception("Erro na API Groq")

        raise HTTPException(
            status_code=502,
            detail=f"Erro ao consultar a inteligência artificial: {str(error)}"
        )


def system_prompt():
    return (
        "Você é a Rener IA, uma assistente virtual inteligente, "
        "prestativa, educada e objetiva. "
        "Responda sempre em português do Brasil, a menos que o usuário "
        "peça outro idioma. Explique assuntos difíceis de forma simples. "
        "Não invente informações e admita quando não souber uma resposta."
    )


# =========================================================
# ROTA PRINCIPAL
# =========================================================

@app.get("/")
async def home():
    return {
        "status": "online",
        "name": "Rener IA",
        "version": "2.0.0",
        "message": "Servidor funcionando corretamente."
    }


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "groq_configured": bool(GROQ_API_KEY)
    }


# =========================================================
# CHAT E ANÁLISE DE IMAGENS
# =========================================================

@app.post("/chat")
async def chat(request: ChatRequest):

    message = request.message.strip()

    image_base64 = request.gallery_image_base64

    if not message and not image_base64:
        raise HTTPException(
            status_code=400,
            detail="Digite uma mensagem ou envie uma imagem."
        )

    messages = [
        {
            "role": "system",
            "content": system_prompt()
        }
    ]

    if image_base64:

        image_bytes = decode_base64_file(image_base64)

        if len(image_bytes) > MAX_IMAGE_SIZE:
            raise HTTPException(
                status_code=413,
                detail="A imagem ultrapassa o limite de 10 MB."
            )

        filename = request.image_name or "imagem.jpg"

        mime_type, _ = mimetypes.guess_type(filename)

        if not mime_type or not mime_type.startswith("image/"):
            mime_type = "image/jpeg"

        encoded_image = base64.b64encode(
            image_bytes
        ).decode("utf-8")

        if not message:
            message = "Descreva e analise esta imagem detalhadamente."

        messages.append({
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": message
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": (
                            f"data:{mime_type};base64,{encoded_image}"
                        )
                    }
                }
            ]
        })

        answer = ask_groq(
            messages,
            model=VISION_MODEL
        )

    else:

        messages.append({
            "role": "user",
            "content": message
        })

        answer = ask_groq(
            messages,
            model=CHAT_MODEL
        )

    return {
        "response": answer,
        "user_id": request.user_id
    }


# =========================================================
# ANÁLISE DE DOCUMENTOS
# =========================================================

@app.post("/analyze")
async def analyze_document(request: AnalyzeRequest):

    if not request.file_name:
        raise HTTPException(
            status_code=400,
            detail="Nome do arquivo não informado."
        )

    file_bytes = decode_base64_file(
        request.file_base64
    )

    if len(file_bytes) > MAX_DOCUMENT_SIZE:
        raise HTTPException(
            status_code=413,
            detail="O documento ultrapassa o limite de 15 MB."
        )

    document_text = extract_document_text(
        file_bytes,
        request.file_name
    )

    if not document_text.strip():
        raise HTTPException(
            status_code=400,
            detail="Não foi possível encontrar texto no documento."
        )

    # Evita enviar documentos enormes de uma só vez.
    document_text = document_text[:50000]

    user_instruction = request.message.strip()

    if not user_instruction:
        user_instruction = "Analise este documento."

    prompt = f"""
O usuário enviou o documento: {request.file_name}

Solicitação do usuário:
{user_instruction}

Conteúdo extraído do documento:
-------------------------------
{document_text}
-------------------------------

Analise o conteúdo e responda em português brasileiro.
Se o usuário pedir um resumo, faça um resumo organizado.
Se pedir informações específicas, procure no conteúdo fornecido.
Não invente informações que não estejam no documento.
"""

    answer = ask_groq([
        {
            "role": "system",
            "content": system_prompt()
        },
        {
            "role": "user",
            "content": prompt
        }
    ])

    return {
        "response": answer,
        "file_name": request.file_name,
        "user_id": request.user_id
    }


# =========================================================
# TRANSCRIÇÃO DE ÁUDIO
# =========================================================

@app.post("/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    user_id: Optional[str] = Form(None)
):

    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="Arquivo de áudio não informado."
        )

    audio_bytes = await file.read()

    if not audio_bytes:
        raise HTTPException(
            status_code=400,
            detail="O arquivo de áudio está vazio."
        )

    if len(audio_bytes) > MAX_AUDIO_SIZE:
        raise HTTPException(
            status_code=413,
            detail="O áudio ultrapassa o limite de 25 MB."
        )

    api = get_client()

    try:
        transcription = api.audio.transcriptions.create(
            file=(
                file.filename,
                audio_bytes
            ),
            model=TRANSCRIPTION_MODEL,
            response_format="json",
            language="pt"
        )

        return {
            "text": transcription.text,
            "user_id": user_id
        }

    except Exception as error:
        logger.exception("Erro na transcrição")

        raise HTTPException(
            status_code=502,
            detail=f"Erro ao transcrever áudio: {str(error)}"
        )


# =========================================================
# INICIALIZAÇÃO LOCAL
# =========================================================

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port
    )
