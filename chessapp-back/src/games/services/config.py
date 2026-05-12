"""
Constantes y rutas de configuración del paquete `services`.

Este módulo no contiene lógica: sólo rutas en disco y una constante de
tamaño del warpeado. Depende únicamente de `os.path` y de
`django.conf.settings`.

Las constantes específicas del antiguo pipeline YOLO + WHEN/WHICH
(MOTION_PIXEL_RATIO, JACCARD_*, OCC_*, FUSE_*, etc.) se eliminaron al
migrar la detección al clasificador EfficientNet-B0, que reside en
`games.chess_tracker.*` y se invoca a través de `effnet_adapter.analyze_video`.
"""

import os

from django.conf import settings


# -----------------------------------------------------------------------------
# Rutas en MEDIA_ROOT y BASE_DIR
# -----------------------------------------------------------------------------
TEMP_VIDEOS_LOCATION     = os.path.join(settings.MEDIA_ROOT, 'temp_videos')
TEMP_FRAMES_LOCATION     = os.path.join(settings.MEDIA_ROOT, 'temp_frames')
ENGINES_DIR              = os.path.join(settings.BASE_DIR, 'misc', 'engines')
DEBUG_LOCATION           = os.path.join(settings.MEDIA_ROOT, 'debug')
FENS_LOCATION            = os.path.join(settings.MEDIA_ROOT, 'fens')
ENGINE_ANALYSIS_LOCATION = os.path.join(settings.MEDIA_ROOT, 'engine_analysis')

# Modelo EfficientNet-B0 exportado a ONNX para inferencia con `onnxruntime`
# (huella RAM ~250 MB menor que torch+torchvision; necesario para Render Free).
# En local: convertido a partir de `full_final.pt` con `_convert_to_onnx.py`.
# En producción: descargado por el Dockerfile desde HuggingFace.
MODEL_PATH               = os.path.join(settings.MEDIA_ROOT, 'models', 'chess_effnet.onnx')


# -----------------------------------------------------------------------------
# Tablero warpeado para `get_warped_frame_preview` y utilidades de video_io
# -----------------------------------------------------------------------------
# El nuevo pipeline construye su propio warpeado 800x800 internamente via
# `chess_tracker.board_detector.BoardCalibration`. NORMALIZED_SIZE se conserva
# sólo para el endpoint de previsualización que se le devuelve al frontend
# durante la calibración manual.
NORMALIZED_SIZE = 1000


__all__ = [
    'TEMP_VIDEOS_LOCATION', 'TEMP_FRAMES_LOCATION', 'ENGINES_DIR',
    'DEBUG_LOCATION', 'FENS_LOCATION', 'ENGINE_ANALYSIS_LOCATION',
    'MODEL_PATH', 'NORMALIZED_SIZE',
]
