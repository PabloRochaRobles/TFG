# ──────────────────────────────────────────────────────────────────────────────
# Imagen para desplegar el backend de ChessVision en Render Free.
#
# Lo que hace este Dockerfile:
#   1. Parte de Python 3.11 slim sobre Debian.
#   2. Instala system deps: OpenCV, build-essential (g++ para compilar
#      Obsidian), curl/git/tar para descargas.
#   3. Coloca los 3 motores UCI Linux en `misc/engines/`:
#        - Stockfish:    binario oficial Linux x86-64 avx2 (descarga directa)
#        - Obsidian:     compilado desde fuente (no publican binarios Linux)
#        - PlentyChess:  binario oficial Linux x86-64 avx2 (descarga directa)
#      Renombrados a `stockfish`, `obsidian`, `plentychess` (lo que espera
#      engine_analysis.py en Linux).
#   4. Descarga el modelo YOLO `chess_yolo.pt` desde HuggingFace.
#   5. Instala dependencias Python (torch CPU-only, mucho más ligero) y
#      copia el código.
#   6. Arranca Daphne en el puerto que pase Render (var $PORT).
# ──────────────────────────────────────────────────────────────────────────────

FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive

# System deps:
#   libgl1, libglib2.0-0   → OpenCV (cv2)
#   build-essential, git   → compilar Obsidian
#   curl, ca-certificates  → descargas de assets de GitHub/HF
#   tar                    → extraer el .tar de Stockfish
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        build-essential \
        git \
        curl \
        ca-certificates \
        tar \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ──────────────────────────────────────────────────────────────────────────────
# Stockfish 18 (Linux x86-64, avx2)
# ──────────────────────────────────────────────────────────────────────────────

ARG STOCKFISH_URL=https://github.com/official-stockfish/Stockfish/releases/download/sf_18/stockfish-ubuntu-x86-64-avx2.tar

RUN mkdir -p /app/misc/engines && cd /tmp \
    && curl -L -o stockfish.tar "${STOCKFISH_URL}" \
    && tar -xf stockfish.tar \
    && find stockfish -type f -name 'stockfish*' -executable -exec cp {} /app/misc/engines/stockfish \; \
    && chmod +x /app/misc/engines/stockfish \
    && rm -rf stockfish.tar stockfish

# ──────────────────────────────────────────────────────────────────────────────
# PlentyChess 7.0.0 (Linux x86-64, avx2)
# Nota: el tag de release es `b-v7.0.0`, no `v7.0.0`.
# ──────────────────────────────────────────────────────────────────────────────

ARG PLENTYCHESS_URL=https://github.com/Yoshie2000/PlentyChess/releases/download/b-v7.0.0/PlentyChess-7.0.0-linux-avx2

RUN curl -L -o /app/misc/engines/plentychess "${PLENTYCHESS_URL}" \
    && chmod +x /app/misc/engines/plentychess

# ──────────────────────────────────────────────────────────────────────────────
# Obsidian 16.0 — compilado desde fuente
#
# El repo gab8192/Obsidian no publica binarios Linux, así que clonamos y
# compilamos. Usamos `make nopgo` (sin Profile-Guided Optimization): ~10-20%
# más lento que el binario oficial Windows pero compila en ~30-60s y produce
# un binario funcional. `download-net` baja los pesos NNUE necesarios.
# ──────────────────────────────────────────────────────────────────────────────

ARG OBSIDIAN_TAG=v16.0

RUN cd /tmp \
    && git clone --depth 1 --branch ${OBSIDIAN_TAG} https://github.com/gab8192/Obsidian.git obsidian-src \
    && cd obsidian-src/src \
    && make download-net \
    && make nopgo \
    && cp Obsidian /app/misc/engines/obsidian \
    && chmod +x /app/misc/engines/obsidian \
    && cd / && rm -rf /tmp/obsidian-src

# ──────────────────────────────────────────────────────────────────────────────
# Modelo YOLO (`chess_yolo.pt`)
#
# Subir a HuggingFace como "Model" público y poner aquí la URL de descarga
# directa (`/resolve/main/...`).
# Ejemplo: https://huggingface.co/<user>/<repo>/resolve/main/chess_yolo.pt
# ──────────────────────────────────────────────────────────────────────────────

ARG YOLO_MODEL_URL=https://huggingface.co/CHANGEME/CHANGEME/resolve/main/chess_yolo.pt

RUN mkdir -p /app/media/models \
    && curl -L -o /app/media/models/chess_yolo.pt "${YOLO_MODEL_URL}"

# ──────────────────────────────────────────────────────────────────────────────
# Python deps
#
# torch CPU-only es ~250 MB en lugar de los 1+ GB con CUDA. Render Free
# no tiene GPU, así que la versión CPU es lo único que necesitamos.
# ──────────────────────────────────────────────────────────────────────────────

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.txt

# ──────────────────────────────────────────────────────────────────────────────
# Código de la app
# ──────────────────────────────────────────────────────────────────────────────

COPY . .

# `collectstatic` para que whitenoise sirva los estáticos del admin.
RUN python manage.py collectstatic --noinput --clear

# Render asigna el puerto vía $PORT (típicamente 10000). Lo respetamos.
ENV PORT=8000
EXPOSE ${PORT}

# Migraciones al arrancar. Si fallan se loguea pero el server arranca igual
# (útil para debug del primer deploy). Si están aplicadas no hacen nada.
CMD bash -c "python manage.py migrate --noinput || true && \
             daphne -b 0.0.0.0 -p ${PORT} core.asgi:application"
