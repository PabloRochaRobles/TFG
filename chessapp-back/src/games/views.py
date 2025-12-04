import json

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.core.files.storage import FileSystemStorage
import os
import uuid

from .serializers import VideoUploadSerializer
from django.conf import settings

from .services import extract_key_frames, save_key_frames, delete_temporary_videos, delete_key_frames

fs_video = FileSystemStorage(location=os.path.join(settings.MEDIA_ROOT, 'temp_videos'))
fs_frame = FileSystemStorage(location=os.path.join(settings.MEDIA_ROOT, 'temp_frames'))

class VideoUploadView(APIView):

    # POST: Recepción de un video desde el frontend, validación y almacenamiento en el backend
    def post(self, request):

        MAX_FILE_SIZE = 250 * 1024 * 1024                                                   # Tamaño máximo de video: 250MB

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

    #
    def post(self, request, *args, **kwargs):
        file_name = request.data.get['file_name']
        source_points = request.data.get['source_points']

        if not file_name or not source_points:
            return Response({"error: No se han proporcionado el nombre o las coordenadas"}, status=status.HTTP_400_BAD_REQUEST)

        video_path = fs_video.path(file_name)
        if not os.path.exists(video_path):
            return Response({"error: No se ha encontrado el video"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            key_frames = extract_key_frames(video_path)

            if isinstance(key_frames, dict) and key_frames.get('error'):
                return Response({"error": f"Fallo en la extracción de los frames clave: {key_frames['error']}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            video_name = os.path.splitext(file_name)[0]
            saved_frames = save_key_frames(key_frames, video_name)

            if not saved_frames:
                return Response({'error': f"Fallo interno durante el guardado de los frames"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            return Response({"message": "Analisis de frames completado", "total_frames": len(saved_frames), "analisis_id": video_name}, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({'error': f"Fallo interno en el procesamiento: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# DELETE: Petición de borrado de un video desde el frontend y de su conjunto de frames clave si fuera necesario
@api_view(['DELETE'])
def delete_video_and_frames(request):
    saved_file_name = request.data.get('file_id')                                                                       # Extracción del nombre del video recibido como parametro desde la petición.

    if not saved_file_name:                                                                                             # Si no existe ese video:
        return Response({"error: No se ha proporcionado el ID del video."}, status=status.HTTP_400_BAD_REQUEST)             # Devuelve error y status 400 BAD REQUEST
    ok = delete_temporary_videos(saved_file_name)                                                                       # Ejecuta la función de borrado de video
    if ok:                                                                                                              # Si la ejecución de borrado de video se ha completado:
        delete_key_frames(os.path.splitext(saved_file_name)[0])                                                             # Borramos los frames claves asociados (si los tuviera creados)

    return Response({"message": "Proceso de eliminación completado."}, status=status.HTTP_200_OK)