import os
import cv2
import numpy as np
from django.core.files.storage import FileSystemStorage
from django.conf import settings
from typing import List

TEMP_VIDEOS_LOCATION = os.path.join(settings.MEDIA_ROOT, 'temp_videos')
fs = FileSystemStorage(location=TEMP_VIDEOS_LOCATION)

NORMALIZED_SIZE = 1000

PUNTOS_ORIGEN = []
MAX_PUNTOS = 4
VENTANA_NOMBRE = 'Selecciona las 4 Esquinas del Tablero'

# Función de borrado de los videos obtenidos almacenados
def delete_temporary_videos(file_name):
    file_path = os.path.join(TEMP_VIDEOS_LOCATION, file_name)
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
            print(f"DEBUG: El video {file_name} ha sido eliminado")
            return True
        except:
            print(f"DEBUG: El video {file_name} no ha podido ser eliminado")
            return False
    else:
        print(f"DEBUG: El video {file_name} no existe")
        return True

# Función de apertura del video y comprobacion de que se ha podido abrir.
def open_video(video_path):
    video = cv2.VideoCapture(video_path)
    if not video.isOpened():
        return {"error": "No se pudo abrir el video."}
    else:
        return video

# Función para el procesamiento de una imagen
def process_image(frame):
    # Pasar a escala de grises
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    # Filtro Gaussiano
    blur = cv2.GaussianBlur(gray, ksize=(21, 21), sigmaX=0)


    return blur

def click_event(event, x, y, flags, param):
    """
    Función de callback del ratón que registra las coordenadas al hacer clic.
    """
    global PUNTOS_ORIGEN

    # Solo procesa el evento si el botón izquierdo del ratón fue presionado
    if event == cv2.EVENT_LBUTTONDOWN:
        if len(PUNTOS_ORIGEN) < MAX_PUNTOS:
            PUNTOS_ORIGEN.append((x, y))
            print(f"Punto {len(PUNTOS_ORIGEN)}: ({x}, {y})")

            # Dibujar un círculo en el punto seleccionado para dar feedback al usuario
            img_copy = param[0]
            cv2.circle(img_copy, (x, y), 5, (0, 0, 255), -1)  # Círculo rojo
            cv2.putText(img_copy, str(len(PUNTOS_ORIGEN)), (x + 10, y - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
            cv2.imshow(VENTANA_NOMBRE, img_copy)

        if len(PUNTOS_ORIGEN) == MAX_PUNTOS:
            # Una vez que tenemos los 4 puntos, cerramos la ventana
            cv2.destroyWindow(VENTANA_NOMBRE)
            print("Puntos de origen capturados.")

def get_corners(video_path):

    global PUNTOS_ORIGEN

    PUNTOS_ORIGEN = []

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print("ERROR: No se pudo abrir el video.")
        return None

    ret, frame = cap.read()
    cap.release()

    if not ret:
        print("ERROR: El video no contiene frames.")
        return None

    # Clonar la imagen para dibujar círculos sin modificar el original
    display_frame = frame.copy()

    # 1. Crear la Ventana (CRÍTICO para setMouseCallback)
    cv2.namedWindow(VENTANA_NOMBRE)

    # 2. Asignar la función de callback. Pasamos [display_frame] como param
    cv2.setMouseCallback(VENTANA_NOMBRE, click_event, param=[display_frame])

    print("\n>>> Orden de Clic: Esquina Superior Izquierda, Superior Derecha, Inferior Derecha, Inferior Izquierda <<<")

    # 3. Mostrar la imagen y esperar por la entrada del ratón (Paso interactivo)
    cv2.imshow(VENTANA_NOMBRE, display_frame)
    cv2.waitKey(0)

    # Si la ventana se cerró después de los 4 clics:
    if len(PUNTOS_ORIGEN) == MAX_PUNTOS:
        # 4. Devolver los puntos en el formato que OpenCV necesita
        return np.float32(PUNTOS_ORIGEN)
    else:
        print("ERROR: La selección fue cancelada o incompleta.")
        return None

def get_matriz(coords):
    destination_points = np.float32([
        [0, NORMALIZED_SIZE - 1],  # Superior Izquierda
        [NORMALIZED_SIZE - 1, NORMALIZED_SIZE - 1],  # Inferior Derecha
        [NORMALIZED_SIZE - 1, 0],  # Superior Derecha
        [0, 0],  # Inferior Izquierda
    ])

    # 2. Calcular la Matriz de Transformación (M)
    # cv2.getPerspectiveTransform calcula la matriz 3x3 que mapea los puntos de origen
    # (source_points) a los puntos de destino (destination_points).
    mat = cv2.getPerspectiveTransform(coords, destination_points)

    # 3. Devolver la Matriz y las Dimensiones de Salida
    return mat, (NORMALIZED_SIZE, NORMALIZED_SIZE)

def save_key_frames(key_frames, file_name):
    if not key_frames:
        print("Lista de frames vacia")
        return False

    try:
        key_frames_array = np.array(key_frames)
        np.savez_compressed(file_name, frames=key_frames_array)
        print(f"Frames clave almacenados en {file_name}")
        return True

    except Exception as e:
        print(f"Error al guardar los frames clave {e}")
        return False


def load_key_frames(file_name):
    if not os.path.exists(file_name):
        print("ERROR: No se pudo abrir el video.")
        return []
    try:
        loaded_data = np.load(file_name)

        key_frames_array = loaded_data["frames"]

        key_frames = [frame for frame in key_frames_array]

        return key_frames

    except Exception as e:
        print(f"Error al cargar los frames clave {e}")
        return []

# Función que extrae los frames posteriores a un movimiento realizado y devuelve el conjunto de todas las imagenes.
def extract_key_frames(video_path, mat, dims):

    # Llamada a la función de apertura del video
    cap = open_video(video_path)

    # Obteneción del primer frame para tener la referencia y comprobacion de la visualización del video
    ret, frame_ref = cap.read()
    if not ret:
        return {"error": "Video vacío."}

    w, h = dims

    frame_ref_warped = cv2.warpPerspective(frame_ref, mat, (w, h))

    # Llamada a la función de procesamiento de imagen
    blur_ref = process_image(frame_ref_warped)

    key_frames = [] # Lista de los frames claves (posteriores a haber hecho un movimiento)
    frames_since_motion = 0 # Contador de frames que han pasado sin que haya movimiento
    motion_detected = False # Detector de movimiento

    PIXEL_THRESHOLD = 30
    AREA_THRESHOLD_START = 150000
    AREA_THRESHOLD_END = 25000
    ESTABILITY_FRAMES = 10

    fgbg = cv2.createBackgroundSubtractorMOG2(history=500, varThreshold=16, detectShadows=True)

    # Bucle de procesamiento del video, lee frames mientras el video este abierto
    while cap.isOpened():
        ret, frame_curr = cap.read()
        if not ret: break  # Final del video

        frame_curr_warped = cv2.warpPerspective(frame_curr, mat, (w, h))

        # Procesamiento del frame actual
        blur_curr = process_image(frame_curr_warped)

        fgmask = fgbg.apply(blur_curr)

        # Diferencia y Umbralización
        frame_diff = cv2.absdiff(blur_ref, blur_curr)
        #cv2.imshow("Diferencia de Frames (DEBUG)", frame_diff)
        #cv2.waitKey(0)
        _, thresh = cv2.threshold(frame_diff, 30, 255, cv2.THRESH_BINARY)

        # 3. Detección de Contornos (Movimiento)
        # Contar el área total de movimiento detectado

        # motion_area = np.sum(thresh == 255)
        motion_area = np.sum(fgmask > 0)

        if motion_detected == False:

            if motion_area > AREA_THRESHOLD_START:
                motion_detected = True
                frames_since_motion = 0
            elif motion_area < 500:
                alpha = 0.99
                beta = 1.0 - alpha
                blur_ref = cv2.addWeighted(blur_ref, alpha, blur_curr, beta, 0)

        else:

            if motion_area < AREA_THRESHOLD_END:
                frames_since_motion += 1
            else:
                frames_since_motion = 0

        print(f"DEBUG: Frames since motion: {frames_since_motion}")
        print(f"DEBUG: Motion area: {motion_area}")

        # 4. Extracción del Frame Clave y Reinicio
        if motion_detected and frames_since_motion > ESTABILITY_FRAMES:  # 20 frames de estabilidad
            # El frame actual es el frame clave estable
            frame_rotate = cv2.rotate(blur_curr, cv2.ROTATE_180)
            print(f"DEBUG: Frame Guardado!")
            key_frames.append(frame_rotate)
            blur_ref = blur_curr.copy()
            motion_detected = False
            frames_since_motion = 0

        print("/////////////////////////////////")

    cap.release()
    return key_frames