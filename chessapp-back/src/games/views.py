import json
import os
import shutil
import threading
import uuid

import chess
from django.conf import settings
from django.core.cache import cache
from django.core.files.storage import FileSystemStorage
from django.http import FileResponse
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import VideoUploadSerializer
from .services import (
    extract_key_frames, save_key_frames, delete_temporary_videos, delete_key_frames,
    auto_detect_board_corners, get_first_frame, get_initial_board_frame,
    frames_to_fens_yolo, save_fens, load_fens, delete_fens,
    save_corners_config, set_progress, get_progress,
    save_engine_analysis, load_engine_analysis, delete_engine_analysis,
    analysis_best_posStockfish, analysis_best_posObsidian, analysis_best_posPlentyChess,
    consensus_analysis, analysis_engines_parallel,
    get_warped_frame_preview,
)

fs_video = FileSystemStorage(location=os.path.join(settings.MEDIA_ROOT, 'temp_videos'))
fs_frame = FileSystemStorage(location=os.path.join(settings.MEDIA_ROOT, 'temp_frames'))

# Tiempo de vida de los resultados en caché (1 hora)
CACHE_TTL = 3600


# ─────────────────────────────────────────────────────────────────────────────
# Tarea de análisis en segundo plano
# ─────────────────────────────────────────────────────────────────────────────

def _run_analysis_background(task_id: str, file_name: str, video_path: str,
                              corners_raw, analysis_id: str):
    """
    Hilo de fondo que ejecuta el pipeline completo de análisis de vídeo:
      1. Detección de esquinas del tablero
      2. Extracción de frames clave (detección de movimiento)
      3. Generación de FENs con YOLOv8 (o fallback por deltas)

    El progreso y el resultado se almacenan en Django Cache bajo la clave
    'analysis_task_<task_id>' para que el WebSocket consumer los lea.

    Escala de progreso:
      0–50  → extracción de frames clave (extract_key_frames)
      50–100 → generación de FENs (frames_to_fens_yolo)
    """
    import numpy as np

    def _update(pct: int, **extra):
        data = {'status': 'processing', 'progress': pct, **extra}
        cache.set(f'analysis_task_{task_id}', data, timeout=CACHE_TTL)
        set_progress(file_name, pct)  # Mantiene compatibilidad con endpoint de polling

    try:
        _update(0)

        # 1. Leer primer frame
        first_frame = get_first_frame(video_path)
        if first_frame is None:
            raise ValueError("No se pudo leer el vídeo.")

        # 2. Esquinas: manual o auto-detección
        if corners_raw and len(corners_raw) == 4:
            h, w = first_frame.shape[:2]
            corners = np.float32([[rx * w, ry * h] for rx, ry in corners_raw])
        else:
            corners = auto_detect_board_corners(first_frame)

        # 3. Frame inicial de referencia
        initial_frame = get_initial_board_frame(video_path, corners)

        # 4. Extraer frames clave (progreso 0→50 gestionado dentro de extract_key_frames)
        result = extract_key_frames(video_path, corners, progress_key=file_name)

        if isinstance(result, dict) and result.get('error'):
            raise ValueError(f"Extracción de frames fallida: {result['error']}")

        key_frames, key_frames_orig, mat = result

        if not key_frames:
            raise ValueError("No se detectaron movimientos en el vídeo.")

        # 5. Guardar frames clave
        save_key_frames(key_frames, analysis_id)

        # 6. Generar FENs con YOLOv8 (progreso 50→100) con streaming parcial
        all_frames = ([initial_frame] + key_frames) if initial_frame is not None else key_frames
        # Frames originales (sin warpear) para mejorar la detección YOLO
        all_original_frames = ([None] + key_frames_orig) if key_frames_orig else None

        fens_stream_key = f'analysis_task_{task_id}_fens'
        streaming_fens = [chess.STARTING_FEN]
        last_streamed = chess.STARTING_FEN
        cache.set(fens_stream_key, streaming_fens[:], timeout=CACHE_TTL)

        def _on_fen(fen: str, _index: int):
            nonlocal last_streamed
            if fen != last_streamed:
                streaming_fens.append(fen)
                last_streamed = fen
                cache.set(fens_stream_key, streaming_fens[:], timeout=CACHE_TTL)

        fens = frames_to_fens_yolo(
            all_frames,
            progress_key=file_name,
            on_fen=_on_fen,
            original_frames=all_original_frames,
            M=mat,
        )

        # Eliminar FENs duplicados consecutivos (frames donde no se detectó movimiento)
        fens_uniq = [fens[0]] if fens else []
        for f in fens[1:]:
            if f != fens_uniq[-1]:
                fens_uniq.append(f)
        fens = fens_uniq

        set_progress(file_name, 100)
        save_fens(fens, analysis_id)

        # 7. Almacenar resultado completo en caché
        cache.set(f'analysis_task_{task_id}', {
            'status':      'complete',
            'progress':    100,
            'message':     'Análisis completado con éxito.',
            'analisis_id': analysis_id,
            'total_frames': len(key_frames),
            'total_fens':  len(fens),
            'fens':        fens,
        }, timeout=CACHE_TTL)

    except Exception as exc:
        import traceback
        traceback.print_exc()
        cache.set(f'analysis_task_{task_id}', {
            'status': 'error',
            'error':  str(exc),
        }, timeout=CACHE_TTL)


# ─────────────────────────────────────────────────────────────────────────────
# Vistas
# ─────────────────────────────────────────────────────────────────────────────

class VideoUploadView(APIView):

    @staticmethod
    def post(request):
        MAX_FILE_SIZE = 250 * 1024 * 1024

        serializer = VideoUploadSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        video_file = serializer.validated_data['video_file']

        if video_file.size > MAX_FILE_SIZE:
            return Response(
                {'error': 'El vídeo insertado excede el tamaño permitido.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            file_extension  = os.path.splitext(video_file.name)[1]
            unique_file_name = str(uuid.uuid4()) + file_extension
            dest_dir  = os.path.join(settings.MEDIA_ROOT, 'temp_videos')
            os.makedirs(dest_dir, exist_ok=True)
            dest_path = os.path.join(dest_dir, unique_file_name)

            if hasattr(video_file, 'temporary_file_path'):
                shutil.copy2(video_file.temporary_file_path(), dest_path)
            else:
                with open(dest_path, 'wb') as out:
                    for chunk in video_file.chunks(chunk_size=8 * 1024 * 1024):
                        out.write(chunk)

            partida_id = str(uuid.uuid4())
            return Response(
                {'file': unique_file_name, 'id': partida_id, 'message': 'Vídeo subido con éxito.'},
                status=status.HTTP_201_CREATED,
            )

        except Exception as exc:
            print(f"[UPLOAD] Error al guardar el vídeo: {exc}")
            return Response(
                {'error': 'Fallo del servidor durante el almacenamiento.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class AnalyzeVideoView(APIView):
    """
    POST: Inicia el análisis de un vídeo en un hilo de fondo y devuelve
    inmediatamente un task_id para monitorizar el progreso vía WebSocket.

    Respuesta:
      { "task_id": "uuid", "analisis_id": "nombre_sin_extension",
        "message": "Análisis iniciado." }

    El cliente debe conectar al WebSocket:
      ws://<servidor>/ws/progress/<task_id>/
    para recibir actualizaciones de progreso y el resultado final.

    Compatibilidad con caché: si los FENs ya existen y no se envían esquinas
    nuevas, devuelve el resultado directamente (sin iniciar nuevo análisis).
    """

    @staticmethod
    def post(request, *args, **kwargs):
        file_name = request.data.get('video_file')
        if not file_name:
            return Response(
                {'error': 'No se ha proporcionado el nombre del fichero.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        video_path = fs_video.path(file_name)
        if not os.path.exists(video_path):
            return Response(
                {'error': 'No se ha encontrado el vídeo.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            video_name   = os.path.splitext(file_name)[0]
            corners_raw  = request.data.get('corners')

            # ── Caché: si ya existen FENs y no se piden esquinas nuevas ──────
            cached_fens = load_fens(video_name)
            if cached_fens and not corners_raw:
                set_progress(file_name, 100)
                return Response({
                    'task_id':      None,
                    'analisis_id':  video_name,
                    'message':      'Análisis cargado desde caché.',
                    'total_fens':   len(cached_fens),
                    'fens':         cached_fens,
                    'from_cache':   True,
                }, status=status.HTTP_200_OK)

            # ── Iniciar análisis en segundo plano ─────────────────────────────
            task_id = str(uuid.uuid4())
            set_progress(file_name, 0)
            cache.set(f'analysis_task_{task_id}', {'status': 'processing', 'progress': 0}, timeout=CACHE_TTL)

            thread = threading.Thread(
                target=_run_analysis_background,
                args=(task_id, file_name, video_path, corners_raw, video_name),
                daemon=True,
            )
            thread.start()

            return Response({
                'task_id':     task_id,
                'analisis_id': video_name,
                'message':     'Análisis iniciado. Conéctate al WebSocket para seguir el progreso.',
            }, status=status.HTTP_202_ACCEPTED)

        except Exception as exc:
            return Response(
                {'error': f'Fallo interno al iniciar el análisis: {str(exc)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class AnalysisResultView(APIView):
    """
    GET /api/partidas/result/<task_id>/

    Devuelve el resultado del análisis una vez completado.
    Útil como alternativa al WebSocket para clientes que no soporten WS.

    Respuestas posibles:
      { "status": "processing", "progress": 45 }
      { "status": "complete",   "fens": [...], ... }
      { "status": "error",      "error": "..." }
      { "status": "not_found" }  → 404
    """

    @staticmethod
    def get(request, task_id):
        result = cache.get(f'analysis_task_{task_id}')
        if result is None:
            return Response({'status': 'not_found'}, status=status.HTTP_404_NOT_FOUND)
        return Response(result, status=status.HTTP_200_OK)


class VideoListView(APIView):

    @staticmethod
    def get(request):
        try:
            video_dir = os.path.join(settings.MEDIA_ROOT, 'temp_videos')
            if not os.path.exists(video_dir):
                return Response({'videos': []}, status=status.HTTP_200_OK)
            files = sorted(
                [f for f in os.listdir(video_dir) if os.path.isfile(os.path.join(video_dir, f))],
                key=lambda f: os.path.getmtime(os.path.join(video_dir, f)),
                reverse=True,
            )
            return Response({'videos': files}, status=status.HTTP_200_OK)
        except Exception as exc:
            return Response({'error': str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class VideoStreamView(APIView):

    def get(self, request, file_name, *args, **kwargs):
        video_path = fs_video.path(file_name)
        if not os.path.exists(video_path):
            return Response({'error': 'No se ha encontrado el vídeo.'}, status=status.HTTP_404_NOT_FOUND)
        if not os.path.isfile(video_path):
            return Response({'error': 'No es un archivo válido.'}, status=status.HTTP_404_NOT_FOUND)
        try:
            with open(video_path, 'rb') as f:
                content = f.read()
            from django.http import HttpResponse
            response = HttpResponse(content, content_type='video/mp4')
            response['Content-Length'] = len(content)
            return response
        except Exception as exc:
            return Response({'error': f'Fallo en el streaming: {str(exc)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AnalysisChainView(APIView):
    """
    POST: Recibe una lista de FENs y devuelve, para cada uno, la cadena de
    los N mejores movimientos por consenso.

    Optimización respecto a la versión anterior:
      - Los 3 motores se ejecutan EN PARALELO por cada paso (3× más rápido).
      - Para una partida de 40 jugadas con depth=5:
          Antes: 40 × 5 × 3 motores × 0.1s = ~60 s
          Ahora: 40 × 5 × 0.1s (paralelo)  = ~20 s
    """

    @staticmethod
    def post(request):
        fens  = request.data.get('fens', [])
        depth = int(request.data.get('depth', 5))

        if not fens:
            return Response({'error': 'No se han proporcionado posiciones FEN.'}, status=status.HTTP_400_BAD_REQUEST)

        if isinstance(fens, str):
            fens = [fens]

        results = []

        for fen in fens:
            chain       = []
            current_fen = fen.strip()

            try:
                chess.Board(current_fen)
            except ValueError as fen_err:
                print(f"[ENGINE] FEN inválido: {current_fen!r} — {fen_err}")
                results.append({'initial_fen': fen, 'error': f'FEN no válido: {fen_err}', 'chain': []})
                continue

            for step in range(1, depth + 1):
                try:
                    # ── Tres motores en paralelo (ThreadPoolExecutor) ─────────
                    stock, obsidian, plenty = analysis_engines_parallel(current_fen)

                    agree     = (stock['movement_uci'] == obsidian['movement_uci'] == plenty['movement_uci'])
                    consensus = consensus_analysis(stock, obsidian, plenty, current_fen)

                    chain.append({
                        'step':           step,
                        'fen_before':     current_fen,
                        'consensus_san':  consensus['movement_san'],
                        'consensus_uci':  consensus['movement_uci'],
                        'fen_after':      consensus['new_fen'],
                        'full_agreement': agree,
                        'engines': {
                            'stockfish':   {'san': stock['movement_san'],    'uci': stock['movement_uci'],    'score': stock['score']},
                            'obsidian':    {'san': obsidian['movement_san'], 'uci': obsidian['movement_uci'], 'score': obsidian['score']},
                            'plentychess': {'san': plenty['movement_san'],   'uci': plenty['movement_uci'],   'score': plenty['score']},
                        },
                    })
                    current_fen = consensus['new_fen']

                except Exception as exc:
                    import traceback as _tb
                    err_msg = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
                    print(f"[ENGINE] Error en step {step} (fen={current_fen!r}): {err_msg}")
                    _tb.print_exc()
                    chain.append({'step': step, 'error': err_msg})
                    break

            results.append({'initial_fen': fen.strip(), 'chain': chain})

        return Response({'results': results}, status=status.HTTP_200_OK)


class VideoFirstFrameView(APIView):
    """GET: Devuelve el primer frame del vídeo como JPEG para la pantalla de calibración."""

    @staticmethod
    def get(request, file_name):
        import cv2 as _cv2
        from django.http import HttpResponse as _HR

        video_path = fs_video.path(file_name)
        if not os.path.exists(video_path):
            return Response({'error': 'Vídeo no encontrado.'}, status=status.HTTP_404_NOT_FOUND)

        frame = get_first_frame(video_path)
        if frame is None:
            return Response({'error': 'No se pudo leer el frame.'}, status=status.HTTP_400_BAD_REQUEST)

        ret, buf = _cv2.imencode('.jpg', frame, [_cv2.IMWRITE_JPEG_QUALITY, 85])
        if not ret:
            return Response({'error': 'Error al codificar el frame.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return _HR(buf.tobytes(), content_type='image/jpeg')


class WarpedFramePreviewView(APIView):
    """POST: Devuelve el primer frame warpeado con las 4 esquinas dadas como JPEG."""

    @staticmethod
    def post(request, file_name):
        import cv2 as _cv2
        from django.http import HttpResponse as _HR

        video_path = fs_video.path(file_name)
        if not os.path.exists(video_path):
            return Response({'error': 'Vídeo no encontrado.'}, status=status.HTTP_404_NOT_FOUND)

        corners_raw = request.data.get('corners')
        if not corners_raw or len(corners_raw) != 4:
            return Response({'error': 'Se requieren exactamente 4 esquinas.'}, status=status.HTTP_400_BAD_REQUEST)

        warped = get_warped_frame_preview(video_path, corners_raw)
        if warped is None:
            return Response({'error': 'No se pudo obtener el frame.'}, status=status.HTTP_400_BAD_REQUEST)

        ret, buf = _cv2.imencode('.jpg', warped, [_cv2.IMWRITE_JPEG_QUALITY, 85])
        if not ret:
            return Response({'error': 'Error al codificar el frame.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return _HR(buf.tobytes(), content_type='image/jpeg')


class AnalysisProgressView(APIView):
    """
    GET: Devuelve el progreso actual del análisis (0–100).
    Mantenido por compatibilidad con código que no use WebSocket.
    """

    @staticmethod
    def get(request, file_name):
        return Response({'progress': get_progress(file_name)}, status=status.HTTP_200_OK)


class CalibrateCornersView(APIView):
    """POST: Guarda la calibración manual de las 4 esquinas del tablero."""

    @staticmethod
    def post(request):
        corners = request.data.get('corners')
        if not corners or len(corners) != 4:
            return Response({'error': 'Se requieren exactamente 4 esquinas.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            save_corners_config(corners)
            return Response({'message': 'Calibración guardada correctamente.'}, status=status.HTTP_200_OK)
        except Exception as exc:
            return Response({'error': str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class FensView(APIView):

    @staticmethod
    def get(request, analysis_id):
        fens = load_fens(analysis_id)
        if fens is None:
            return Response({'error': 'No se encontraron FENs para este análisis.'}, status=status.HTTP_404_NOT_FOUND)
        return Response({
            'analisis_id': analysis_id,
            'total_fens':  len(fens),
            'fens':        fens,
        }, status=status.HTTP_200_OK)


class EngineAnalysisView(APIView):
    """GET  /engine-analysis/<analysis_id>/  → devuelve análisis cacheado o 404
       POST /engine-analysis/               → guarda análisis { analysis_id, results }"""

    @staticmethod
    def get(request, analysis_id):
        results = load_engine_analysis(analysis_id)
        if results is None:
            return Response({'error': 'No hay análisis de motores cacheado.'}, status=status.HTTP_404_NOT_FOUND)
        return Response({'analysis_id': analysis_id, 'results': results}, status=status.HTTP_200_OK)

    @staticmethod
    def post(request):
        analysis_id = request.data.get('analysis_id')
        results     = request.data.get('results')
        if not analysis_id or results is None:
            return Response({'error': 'Faltan analysis_id o results.'}, status=status.HTTP_400_BAD_REQUEST)
        save_engine_analysis(analysis_id, results)
        return Response({'message': 'Análisis guardado.'}, status=status.HTTP_200_OK)


@api_view(['DELETE'])
def delete_video_and_frames(request, file_name):
    if not file_name:
        return Response({'error': 'No se ha proporcionado el nombre del vídeo.'}, status=status.HTTP_400_BAD_REQUEST)

    ok = delete_temporary_videos(file_name)
    if not ok:
        return Response({'error': 'No se encontró el vídeo o no se pudo eliminar.'}, status=status.HTTP_404_NOT_FOUND)

    analysis_id = os.path.splitext(file_name)[0]
    delete_key_frames(analysis_id)
    delete_fens(analysis_id)
    delete_engine_analysis(analysis_id)

    return Response({'message': 'Proceso de eliminación completado.'}, status=status.HTTP_200_OK)
