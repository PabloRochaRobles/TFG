import cv2
import os
import time
import django
import numpy as np

# 1. Configurar el entorno de Django para poder importar tu lógica
# Solo necesario si ejecutas el script fuera de manage.py
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

# 2. Importar la función de tu servicio
from src.games.services import extract_key_frames, save_key_frames, load_key_frames, show_key_frames
from src.games.services import get_corners
from src.games.services import get_matriz

def visualize_key_frames(video_path):

    path_frames = os.path.join('media/temp_frames', "test1.npz")

    if os.path.exists(path_frames):
        key_frames = load_key_frames("test1.npz")
        show_key_frames(key_frames)
    else:
        coords = get_corners(video_path)
        mat, dims = get_matriz(coords)
        key_frames = extract_key_frames(video_path, mat, dims)
        save_key_frames(key_frames, "test1")
        show_key_frames(key_frames)


if __name__ == '__main__':
    # RUTA: Asegúrate de que esta ruta apunte a un video de prueba válido en tu PC
    RUTA_VIDEO_PRUEBA = "C:/Users/Admin/Videos/Ajedrez/test1.mp4"

    # Ejecutar la prueba
    visualize_key_frames(RUTA_VIDEO_PRUEBA)