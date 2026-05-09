"""
services/ — Paquete de servicios del backend.

Este `__init__.py` actúa como barrel file: re-exporta los nombres públicos
de los submódulos para que el resto del proyecto pueda seguir haciendo
`from games.services import extract_key_frames, save_fens, ...` sin tener
que conocer la organización interna.

Submódulos:
  - config              → constantes y rutas
  - progress            → tracking de progreso por análisis
  - video_io            → I/O de vídeo y frames + utilidades de debug
  - fen_persistence     → save/load/delete de la lista de FENs en disco
  - engine_analysis     → motores UCI (Stockfish, Obsidian, PlentyChess)
  - matchers            → helpers de visión compartidos (WHEN ↔ WHICH)
  - move_extraction     → fase WHEN: extracción de keyframes
  - move_identification → fase WHICH: identificación de moves
"""

# Constantes y rutas (paths, umbrales WHEN/WHICH, banderas) — ver services/config.py
from .config import *  # noqa: F401,F403

# Progreso de análisis (por clave de vídeo) — ver services/progress.py
from .progress import set_progress, get_progress  # noqa: F401

# I/O de vídeo y frames (open/process/get_matriz/save/delete + save_debug_image
# + helpers de primer frame y warp preview) — ver services/video_io.py
from .video_io import (  # noqa: F401
    delete_temporary_videos, open_video, process_image, get_matriz,
    save_key_frames, delete_key_frames, save_debug_image,
    get_first_frame, get_warped_frame_preview,
)

# Helpers de visión compartidos por WHEN y WHICH — ver services/matchers.py
from .matchers import (  # noqa: F401
    _pixel_changed_squares,
    _move_changed_squares,
    _consecutive_keyframes_are_duplicates,
    _fuse_consecutive_duplicate_keyframes,
    _cell_variance_map,
    _variance_diff_all,
    _changed_squares_occ,
    _board_to_state_symbols,
    _yolo_state_agreement,
    _yolo_score_state,
    _yolo_color_map,
    _yolo_diff_squares,
    _yolo_diff_score_move,
    _yolo_match_single_move_diff,
    _variance_score_for_move,
    _pure_variance_match,
    _break_tie_by_variance,
    _intelligent_tiebreak,
    _yolo_change_centroid_tiebreak,
    _yolo_match_single_move,
    _yolo_match_double_move,
    _match_move_by_jaccard,
    _try_multi_move_jaccard,
    _get_occupied_squares_estimate,
    _try_state_recovery,
)


# Fase WHICH — identificación de movimientos — ver services/move_identification.py
from .move_identification import identify_moves_from_keyframes  # noqa: F401


# Fase WHEN — extracción de keyframes — ver services/move_extraction.py
from .move_extraction import extract_key_frames  # noqa: F401


# Persistencia en disco de la lista de FENs — ver services/fen_persistence.py
from .fen_persistence import save_fens, load_fens, delete_fens  # noqa: F401


# Análisis con motores UCI (Stockfish, Obsidian, PlentyChess) — ver services/engine_analysis.py
from .engine_analysis import (  # noqa: F401
    save_engine_analysis, load_engine_analysis, delete_engine_analysis,
    analysis_best_posStockfish, analysis_best_posObsidian, analysis_best_posPlentyChess,
    analysis_engines_parallel, consensus_analysis,
)


