import json
from http.client import responses

from django.http import FileResponse
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import api_view
from django.core.files.storage import FileSystemStorage
import os
import uuid

from .serializers import VideoUploadSerializer
from django.conf import settings

import chess
from .services import (
    extract_key_frames, save_key_frames, delete_temporary_videos, delete_key_frames,
    auto_detect_board_corners, get_first_frame, get_initial_board_frame,
    frames_to_fens, save_fens, load_fens, delete_fens,
    save_corners_config, set_progress, get_progress,
    save_engine_analysis, load_engine_analysis, delete_engine_analysis,
    analysis_best_posStockfish, analysis_best_posObsidian, analysis_best_posPlentyChess, consensus_analysis,
    get_warped_frame_preview,
)

fs_video = FileSystemStorage(location=os.path.join(settings.MEDIA_ROOT, 'temp_videos'))
fs_frame = FileSystemStorage(location=os.path.join(settings.MEDIA_ROOT, 'temp_frames'))

class VideoUploadView(APIView):

    # POST: Recepción de un video desde el frontend, validación y almacenamiento en el backend
    @staticmethod
    def post(request):

        MAX_FILE_SIZE = 250 * 1024 * 1024                                                 # Tamaño máximo de video: 250MB

        serializer = VideoUploadSerializer(data=request.data)                               # Preparación de los datos para la validación
        if not serializer.is_valid():                                                       # Si no son validos:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)              # Devuelve 400 BAD REQUEST

        video_file = serializer.validated_data['video_file']                                # Se extrae el archivo ya limpio y seguro

        if video_file.size > MAX_FILE_SIZE:                                                 # Si el tamaño del video es mayor de lo permitido
            return Response({'error': 'El video insertado excede el tamaño permitido.'}, status=status.HTTP_400_BAD_REQUEST)    # Devuelve 400 BAD REQUEST

        try:
            # Creación de un nombre único.
            file_extension = os.path.splitext(video_file.name)[1]                           # Extracción de la extensión del archivo
            unique_file_name = str(uuid.uuid4()) + file_extension                           # Creación de un nombre con un identificador único
            saved_file_name = fs_video.save(unique_file_name, video_file)                         # Se guarda el archivo
            partida_id = str(uuid.uuid4())                                                  # Generación de un ID único para la partida

            return Response({'file': saved_file_name, 'id': partida_id, 'message': "Video subido con éxito."}, status=status.HTTP_201_CREATED)  # Se notifica del nombre del archivo, el ID de la partida, mensaje de que el video se ha subido y status 201 CREATED

        except Exception as e:                                                              # En caso de fallo, salta la excepción
            return Response({'error': "Fallo del servidor durante el almacenamiento."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)     # Se notifica del fallo y devuelve 500 INTERNAL SERVER ERROR

class AnalyzeVideoView(APIView):

    # POST: Análisis de un video de ajedrez con detección automática de tablero y generación de FENs
    @staticmethod
    def post(request, *args, **kwargs):
        file_name = request.data.get('video_file')                          # Extracción del nombre del fichero de la petición

        if not file_name:                                                   # Si no se recibe el nombre del fichero
            return Response({"error": "No se ha proporcionado el nombre del fichero."}, status=status.HTTP_400_BAD_REQUEST)

        video_path = fs_video.path(file_name)                               # Extracción de la ruta hasta el video

        if not os.path.exists(video_path):                                  # Si la ruta hasta el fichero no existe
            return Response({"error": "No se ha encontrado el video."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            video_name = os.path.splitext(file_name)[0]

            # 0. Si los FENs ya están en caché y no se proporcionan esquinas nuevas → devolver directamente
            corners_raw = request.data.get('corners')
            cached_fens = load_fens(video_name)
            if cached_fens and not corners_raw:
                set_progress(file_name, 100)
                print(f"[CACHE] FENs ya existentes para {video_name}, devolviendo sin reprocesar.")
                return Response({
                    "message": "Análisis cargado desde caché.",
                    "total_frames": len(cached_fens) - 1,
                    "analisis_id": video_name,
                    "total_fens": len(cached_fens),
                    "fens": cached_fens,
                }, status=status.HTTP_200_OK)

            set_progress(file_name, 0)

            # 1. Leer el primer frame para la detección de esquinas
            first_frame = get_first_frame(video_path)
            if first_frame is None:
                return Response({"error": "No se pudo leer el video."}, status=status.HTTP_400_BAD_REQUEST)

            # 2. Usar esquinas manuales si se proporcionan; si no, auto-detectar
            corners_raw = request.data.get('corners')
            if corners_raw and len(corners_raw) == 4:
                import numpy as np
                h, w = first_frame.shape[:2]
                corners = np.float32([[rx * w, ry * h] for rx, ry in corners_raw])
                print(f"[CORNERS] Usando calibración manual del frontend: {corners.tolist()}")
            else:
                corners = auto_detect_board_corners(first_frame)

            # 3. Obtener el frame inicial transformado como referencia para la detección FEN
            initial_frame = get_initial_board_frame(video_path, corners)

            # 4. Extraer los frames clave del video (posiciones estables tras cada movimiento)
            key_frames = extract_key_frames(video_path, corners, progress_key=file_name)  # Extracción de frames clave

            if isinstance(key_frames, dict) and key_frames.get('error'):    # Comprobación de errores
                return Response({"error": f"Fallo en la extracción de los frames clave: {key_frames['error']}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            if not key_frames:                                              # Si no se detectaron movimientos
                return Response({"error": "No se detectaron movimientos en el video."}, status=status.HTTP_400_BAD_REQUEST)

            # 5. Guardar los frames clave
            save_key_frames(key_frames, video_name)

            # 6. Generar la secuencia de FENs comparando celdas entre frames consecutivos
            all_frames = ([initial_frame] + key_frames) if initial_frame is not None else key_frames
            fens = frames_to_fens(all_frames, progress_key=file_name)       # Generación de FENs
            set_progress(file_name, 100)
            save_fens(fens, video_name)                                     # Persistencia en disco

            return Response({
                "message": "Análisis completado con éxito.",
                "total_frames": len(key_frames),
                "analisis_id": video_name,
                "total_fens": len(fens),
                "fens": fens,
            }, status=status.HTTP_200_OK)

        except Exception as e:                                              # Si salta la excepción
            return Response({'error': f"Fallo interno en el procesamiento: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

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
                reverse=True
            )
            return Response({'videos': files}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class VideoStreamView(APIView):

    def get(self, request, file_name, *args, **kwargs):

        video_path = fs_video.path(file_name)

        if not os.path.exists(video_path):
            return Response({"error: No se ha encontrado la ruta hasta el video"}, status=status.HTTP_404_NOT_FOUND)

        if not os.path.isfile(video_path):
            return Response({"error: No es un archivo valido"}, status=status.HTTP_404_NOT_FOUND)

        try:
            # Leer el archivo completo en memoria y cerrarlo antes de enviar la respuesta
            # Esto evita que el handle del archivo quede abierto durante el streaming (WinError 32 al borrar)
            with open(video_path, 'rb') as f:
                content = f.read()
            from django.http import HttpResponse
            response = HttpResponse(content, content_type='video/mp4')
            response['Content-Length'] = len(content)
            return response

        except Exception as e:
            return Response({'error': f"Fallo en el procesamiento: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class AnalysisChainView(APIView):

    # POST: Recibe una lista de FENs y devuelve, para cada uno, la cadena de los N mejores movimientos por consenso
    @staticmethod
    def post(request):
        fens  = request.data.get('fens', [])
        depth = int(request.data.get('depth', 5))

        if not fens:
            return Response({'error': 'No se han proporcionado posiciones FEN.'}, status=status.HTTP_400_BAD_REQUEST)

        # Acepta tanto una lista como una cadena con un único FEN
        if isinstance(fens, str):
            fens = [fens]

        results = []

        for fen in fens:
            chain = []
            current_fen = fen.strip()

            # Validar FEN
            try:
                chess.Board(current_fen)
            except ValueError:
                results.append({'initial_fen': fen, 'error': f'FEN no válido: {fen}'})
                continue

            for step in range(1, depth + 1):
                try:
                    stock   = analysis_best_posStockfish(current_fen)
                    obsidian = analysis_best_posObsidian(current_fen)
                    plenty  = analysis_best_posPlentyChess(current_fen)

                    agree = (stock['movement_uci'] == obsidian['movement_uci'] == plenty['movement_uci'])

                    consensus = consensus_analysis(stock, obsidian, plenty, current_fen)

                    chain.append({
                        'step': step,
                        'fen_before': current_fen,
                        'consensus_san': consensus['movement_san'],
                        'consensus_uci': consensus['movement_uci'],
                        'fen_after': consensus['new_fen'],
                        'full_agreement': agree,
                        'engines': {
                            'stockfish':   {'san': stock['movement_san'],   'uci': stock['movement_uci'],   'score': stock['score']},
                            'obsidian':    {'san': obsidian['movement_san'], 'uci': obsidian['movement_uci'], 'score': obsidian['score']},
                            'plentychess': {'san': plenty['movement_san'],  'uci': plenty['movement_uci'],  'score': plenty['score']},
                        },
                    })

                    current_fen = consensus['new_fen']

                except Exception as e:
                    chain.append({'step': step, 'error': str(e)})
                    break

            results.append({'initial_fen': fen.strip(), 'chain': chain})

        return Response({'results': results}, status=status.HTTP_200_OK)


class VideoFirstFrameView(APIView):
    """GET: Devuelve el primer frame del vídeo como imagen JPEG para la pantalla de calibración."""

    @staticmethod
    def get(request, file_name):
        import cv2 as _cv2
        from django.http import HttpResponse as _HR

        video_path = fs_video.path(file_name)
        if not os.path.exists(video_path):
            return Response({'error': 'Video no encontrado.'}, status=status.HTTP_404_NOT_FOUND)

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
            return Response({'error': 'Video no encontrado.'}, status=status.HTTP_404_NOT_FOUND)

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
    """GET: Devuelve el progreso actual del análisis de un vídeo (0-100)."""

    @staticmethod
    def get(request, file_name):
        return Response({'progress': get_progress(file_name)}, status=status.HTTP_200_OK)


class CalibrateCornersView(APIView):
    """
    POST: Guarda la calibración manual de las 4 esquinas del tablero.
    Body: { corners: [[rx0,ry0],[rx1,ry1],[rx2,ry2],[rx3,ry3]] }
    Coordenadas relativas [0-1] respecto al tamaño de imagen mostrado.
    Orden: [TL=a1, TR=a8, BR=h8, BL=h1].
    """

    @staticmethod
    def post(request):
        corners = request.data.get('corners')
        if not corners or len(corners) != 4:
            return Response({'error': 'Se requieren exactamente 4 esquinas.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            save_corners_config(corners)
            return Response({'message': 'Calibración guardada correctamente.'}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class FensView(APIView):

    # GET: Devuelve la secuencia de FENs de una partida ya analizada
    @staticmethod
    def get(request, analysis_id):
        fens = load_fens(analysis_id)
        if fens is None:
            return Response({"error": "No se encontraron FENs para este análisis."}, status=status.HTTP_404_NOT_FOUND)
        return Response({
            "analisis_id": analysis_id,
            "total_fens": len(fens),
            "fens": fens,
        }, status=status.HTTP_200_OK)



class EngineAnalysisView(APIView):
    """GET  /engine-analysis/<analysis_id>/  → devuelve análisis cacheado o 404
       POST /engine-analysis/               → guarda análisis { analysis_id, results }"""

    @staticmethod
    def get(request, analysis_id):
        results = load_engine_analysis(analysis_id)
        if results is None:
            return Response({"error": "No hay análisis de motores cacheado."}, status=status.HTTP_404_NOT_FOUND)
        return Response({"analysis_id": analysis_id, "results": results}, status=status.HTTP_200_OK)

    @staticmethod
    def post(request):
        analysis_id = request.data.get('analysis_id')
        results     = request.data.get('results')
        if not analysis_id or results is None:
            return Response({"error": "Faltan analysis_id o results."}, status=status.HTTP_400_BAD_REQUEST)
        save_engine_analysis(analysis_id, results)
        return Response({"message": "Análisis guardado."}, status=status.HTTP_200_OK)


# DELETE: Petición de borrado de un video desde el frontend y de su conjunto de frames clave si fuera necesario
@api_view(['DELETE'])
def delete_video_and_frames(request, file_name):
    if not file_name:                                                                                                    # Si no existe ese video:
        return Response({"error": "No se ha proporcionado el nombre del video."}, status=status.HTTP_400_BAD_REQUEST)   # Devuelve error y status 400 BAD REQUEST

    ok = delete_temporary_videos(file_name)                                                                             # Ejecuta la función de borrado de video

    if not ok:                                                                                                          # Si el borrado falló:
        return Response({"error": "No se encontró el video o no se pudo eliminar."}, status=status.HTTP_404_NOT_FOUND)  # Devuelve 404

    analysis_id = os.path.splitext(file_name)[0]
    delete_key_frames(analysis_id)        # Frames clave asociados (si existen)
    delete_fens(analysis_id)              # FENs asociados (si existen)
    delete_engine_analysis(analysis_id)   # Análisis de motores cacheado (si existe)

    return Response({"message": "Proceso de eliminación completado."}, status=status.HTTP_200_OK)                       # Se notifica de que el proceso ha terminado y se devuelve status 200