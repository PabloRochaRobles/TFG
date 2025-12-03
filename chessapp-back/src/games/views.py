from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.core.files.storage import FileSystemStorage
import os
import uuid

from .serializers import VideoUploadSerializer
from django.conf import settings

fs = FileSystemStorage(location=os.path.join(settings.MEDIA_ROOT, 'temp_videos'))

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
            # Creación de un nombnre único.
            file_extension = os.path.splitext(video_file.name)[1]                           # Extracción de la extensión del archivo
            unique_file_name = str(uuid.uuid4()) + file_extension                           # Creación de un nombre con un identificador único
            saved_file_name = fs.save(unique_file_name, video_file)                         # Se guarda el archivo
            partida_id = str(uuid.uuid4())                                                  # Generación de un ID único para la partida

            return Response({'file': saved_file_name, 'id': partida_id, 'message': "Video subido con éxito."}, status=status.HTTP_201_CREATED)  # Se notifica del nombre del archivo, el ID de la partida, mensaje de que el video se ha subido y status 201 CREATED

        except Exception as e:                                                              # En caso de fallo, salta la excepción
            return Response({'error': "Fallo del servidor durante el almacenamiento."}, status=status.HTTP_400_BAD_REQUEST)     # Se notifica del fallo y devuelve 400 BAD REQUEST