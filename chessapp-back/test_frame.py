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
from src.games.services import extract_key_frames, save_key_frames, load_key_frames
from src.games.services import get_corners
from src.games.services import get_matriz

def visualize_key_frames(video_path):
    frames_clave = load_key_frames("test1.npz")

    # --- Llamada a la funcion que extrae los frames clave (en los que se han realizado movimientos)
    #coords = get_corners(video_path)
    #mat, dims = get_matriz(coords)
    #frames_clave_not_saved = extract_key_frames(video_path, mat, dims)
    #save_key_frames(frames_clave_not_saved, "test1")


    if isinstance(frames_clave, dict) and frames_clave.get("error"):
        print(f"ERROR: {frames_clave['error']}")
        return

    print(f"Se extrajeron {len(frames_clave)} frames clave.")

    for i, frame in enumerate(frames_clave):
        # 3. Mostrar el frame
        cv2.imshow(f"Jugada {i + 1}", frame)

        # 4. Esperar la entrada del teclado para pasar al siguiente
        key = cv2.waitKey(0) & 0xFF # Espera una pulsación de tecla indefinidamente

        if key == ord('q') or key == 27:  # Presiona 'q' o ESC para salir del bucle
            break

    cv2.destroyAllWindows()  # Cierra todas las ventanas de OpenCV al finalizar


if __name__ == '__main__':
    # RUTA: Asegúrate de que esta ruta apunte a un video de prueba válido en tu PC
    RUTA_VIDEO_PRUEBA = "C:/Users/Admin/Videos/Ajedrez/test1.mp4"

    # Ejecutar la prueba
    visualize_key_frames(RUTA_VIDEO_PRUEBA)