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

    "Recepción de un video desde el frontend, validación y almacenamiento."
    def post(self, request):
        # Validación de los datos en la entrada
        serializer = VideoUploadSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        video_file = serializer.validated_data['video_file']

        # Validación del tamaño máximo (250MB)
        MAX_FILE_SIZE = 250 * 1024 * 1024

        if video_file.size > MAX_FILE_SIZE:
            return Response({'error': 'El video insertado excede el tamaño permitido.'}, status=status.HTTP_400_BAD_REQUEST)

        # Almacenamiento temporal del video en el backend
        try:
            # Creación de un nombnre único.
            file_extension = os.path.splitext(video_file.name)[1]
            unique_file_name = str(uuid.uuid4()) + file_extension

            # Guardado del archivo
            saved_file_name = fs.save(unique_file_name, video_file)

            # Generación de un ID para la partida
            partida_id = str(uuid.uuid4())

            return Response({'file': saved_file_name, 'id': partida_id, 'message': "Video subido con éxito."}, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response({'error': "Fallo del servidor durante el almacenamiento."}, status=status.HTTP_400_BAD_REQUEST)