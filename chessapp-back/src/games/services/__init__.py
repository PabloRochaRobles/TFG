"""
services/ — Paquete de servicios del backend.

Este `__init__.py` actúa como barrel file: re-exporta los nombres públicos
de los submódulos para que el resto del proyecto pueda seguir haciendo
`from games.services import ...` sin tener que conocer la organización
interna.

Submódulos:
  - config              → constantes y rutas (paths, MODEL_PATH, etc.)
  - progress            → tracking de progreso por análisis
  - video_io            → I/O de vídeo y frames + utilidades de preview
  - fen_persistence     → save/load/delete de la lista de FENs en disco
  - engine_analysis     → motores UCI (Stockfish, Obsidian, PlentyChess)
  - effnet_adapter      → pipeline EfficientNet-B0 end-to-end (detección +
                          reconstrucción de FENs). Sustituye al antiguo par
                          WHEN/WHICH basado en YOLO.
"""

# Constantes y rutas — ver services/config.py
from .config import *  # noqa: F401,F403

# Progreso de análisis (por clave de vídeo) — ver services/progress.py
from .progress import set_progress, get_progress  # noqa: F401

# Sondas de memoria para diagnosticar OOM — ver services/memory_probe.py
from .memory_probe import mem_log  # noqa: F401

# I/O de vídeo y frames — ver services/video_io.py
from .video_io import (  # noqa: F401
    delete_temporary_videos, open_video, process_image, get_matriz,
    save_key_frames, delete_key_frames, save_debug_image,
    get_first_frame, get_warped_frame_preview,
)

# Pipeline EfficientNet-B0 (detección + reconstrucción de FENs) — ver
# services/effnet_adapter.py
from .effnet_adapter import analyze_video  # noqa: F401

# Persistencia en disco de la lista de FENs — ver services/fen_persistence.py
from .fen_persistence import save_fens, load_fens, delete_fens  # noqa: F401

# Análisis con motores UCI — ver services/engine_analysis.py
from .engine_analysis import (  # noqa: F401
    save_engine_analysis, load_engine_analysis, delete_engine_analysis,
    analysis_best_posStockfish, analysis_best_posObsidian, analysis_best_posPlentyChess,
    analysis_engines_parallel, consensus_analysis,
)
