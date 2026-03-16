import json
import os
from collections import Counter

import cv2
import chess
import chess.engine
import numpy as np
from django.conf import settings
from rest_framework.response import Response
from rest_framework import status

TEMP_VIDEOS_LOCATION  = os.path.join(settings.MEDIA_ROOT, 'temp_videos')
TEMP_FRAMES_LOCATION  = os.path.join(settings.MEDIA_ROOT, 'temp_frames')
ENGINES_DIR           = os.path.join(settings.BASE_DIR, 'misc', 'engines')
DEBUG_LOCATION        = os.path.join(settings.MEDIA_ROOT, 'debug')   # Imágenes de diagnóstico
FENS_LOCATION         = os.path.join(settings.MEDIA_ROOT, 'fens')
CORNERS_CONFIG_PATH   = os.path.join(settings.MEDIA_ROOT, 'corners_config.json')  # Calibración manual

NORMALIZED_SIZE = 1000
PUNTOS_ORIGEN = []
MAX_PUNTOS = 4
VENTANA_NOMBRE = 'Selecciona las 4 Esquinas del Tablero'
CELL_CHANGE_THRESHOLD = 10          # Diferencia media de píxeles para considerar una celda cambiada

# -----------------------------------------
# Progreso de análisis (por clave de vídeo)
# -----------------------------------------
_analysis_progress: dict = {}

def set_progress(key: str, pct: int) -> None:
    """Actualiza el progreso de análisis para la clave dada (0-100)."""
    _analysis_progress[key] = min(100, max(0, pct))

def get_progress(key: str) -> int:
    """Devuelve el progreso actual para la clave dada (0-100)."""
    return _analysis_progress.get(key, 0)

# -----------------------------------------
# Funciones de Manejo de Video
# -----------------------------------------

# Función de borrado de los videos obtenidos del FrontEnd y almacenados.
def delete_temporary_videos(file_name):
    file_path = os.path.join(TEMP_VIDEOS_LOCATION, file_name)                   # Almacena en la variable la ruta hasta el archivo que se quiere borrar
    print(f"[DELETE] Buscando archivo en: {file_path}")
    print(f"[DELETE] Archivo existe: {os.path.exists(file_path)}")
    try:
        if os.path.exists(file_path):                                           # Si el archivo existe:
            os.remove(file_path)                                                    # Se elimina el video especificado por la ruta
            print(f"[DELETE] El video {file_name} ha sido eliminado")               # Se notifica que el video ha sido eliminado
            return True                                                             # Devuelve verdadero

        else:                                                                   # Si no existe:
            print(f"[DELETE] Archivo no encontrado: {file_path}")
            return False                                                             # Devuelve falso

    except Exception as e:                                                      # Si algo falla, salta la excepción
        print(f"[DELETE] Excepción al borrar: {str(e)}")
        return False                                                                 # Devuelve falso

# Función de apertura del video de ajedrez
def open_video(video_path):
    video = cv2.VideoCapture(video_path)                    # Abre el video y se almacena el manejador en la variable
    if not video.isOpened():                                # Si no se ha conseguido abrir el video
        return {"error": "No se pudo abrir el video."}      # Se notifica del error
    else:                                                   # Si se consigue abrir el video
        return video                                        # Se devuelve el manejador

# Función para el procesamiento de una imagen eliminando ruido y facilitando la detección de movimiento para recopilar los frames claves
def process_image(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)              # Se tranforma el frame al formato de escala de grises
    blur = cv2.GaussianBlur(gray, ksize=(21, 21), sigmaX=0)     # Se le aplica un filtro Gaussiano a la imagen en escala de grises
    return blur                                                 # Devuelve el frame con estos filtros aplicados

# Función que registra las coordenadas al hacer clic
def click_event(event, x, y, _flags, param):

    global PUNTOS_ORIGEN

    if event == cv2.EVENT_LBUTTONDOWN:                                                  # Si el botón izquierdo del ratón fue pulsado:
        if len(PUNTOS_ORIGEN) < MAX_PUNTOS:                                             # Si no se han pulsado el número máximo de puntos posibles
            PUNTOS_ORIGEN.append((x, y))                                                    # Añade las coordenadas seleccionadas
            print(f"Punto {len(PUNTOS_ORIGEN)}: ({x}, {y})")                                # Se muestra cuáles son esas coordenadas
            img_copy = param[0]                                                             # Se copia la imagen
            cv2.circle(img_copy, (x, y), 5, (0, 0, 255), -1)                                # Se muestra la imagen con un círculo rojo donde se ha pulsado
            cv2.putText(img_copy, str(len(PUNTOS_ORIGEN)), (x + 10, y - 10),                # Se muestra un número junto al círculo indicando que número de pulsación es
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
            cv2.imshow(VENTANA_NOMBRE, img_copy)                                            # Se muestran los cambios realizados

        if len(PUNTOS_ORIGEN) == MAX_PUNTOS:                                            # Si se ha pulsado el número máximo de puntos posibles:
            cv2.destroyWindow(VENTANA_NOMBRE)                                           # Se cierran todas las ventanas
            print("Puntos de origen capturados.")                                       # Se informa que todos los puntos han sido captados

# Función para enmarcar el tablero de ajedrez haciendo que el usuario pulse las esquinas de este
def get_corners(video_path):

    global PUNTOS_ORIGEN
    PUNTOS_ORIGEN = []

    video = open_video(video_path)                                                      # Llamada a la función de apertura del video
    ret, frame = video.read()                                                           # Obtención del primer frame y de la variable de confirmación
    video.release()                                                                     # Cierre del video

    if not ret:                                                                         # Si da falso
        print(f"DEBUG: Error. Video vacio")                                             # El frame está vacío

    display_frame = frame.copy()                                                        # Clonación del frame para poder sobreescribirlo
    cv2.namedWindow(VENTANA_NOMBRE)                                                     # Creación de una ventana
    cv2.setMouseCallback(VENTANA_NOMBRE, click_event, param=[display_frame])            # Llamada a la función callback "click_event" pasandole el frames clonado

    print("\n>>> Orden de Clic: Esquina Superior Izquierda, Superior Derecha, Inferior Derecha, Inferior Izquierda <<<")

    cv2.imshow(VENTANA_NOMBRE, display_frame)                                           # Mostrar el frame
    cv2.waitKey(0)                                                                      # Esperar a que se realicen las pulsaciones

    if len(PUNTOS_ORIGEN) == MAX_PUNTOS:                                                # Si se han realizado MAX_PUNTOS pulsaciones:
        return np.float32(PUNTOS_ORIGEN)                                                    # Se devuelven los puntos marcados
    else:                                                                               # Si se ha realizado un número distinto de pulsaciones:
        print("ERROR: La selección fue cancelada o incompleta.")                            # Informar del error
        return None                                                                         # No se devuelve nada

# Función que transforma el cómo se ve el tablero tras aplicarle el cambio de perspectiva arreglando que la imagen no se distorsione
def get_matriz(coords):
    # coords llega en orden [a1, a8, h8, h1] tal como los toca el usuario en la calibración.
    # Orientación de la imagen tal como la ve la cámara lateral (blancas a la izquierda):
    #   a1 = arriba-izquierda,  a8 = arriba-derecha
    #   h1 = abajo-izquierda,   h8 = abajo-derecha
    #
    # Mapeo de destino en la imagen normalizada (NORMALIZED_SIZE × NORMALIZED_SIZE):
    #   coords[0] (a1) → (0, 0)   arriba-izquierda
    #   coords[1] (a8) → (N, 0)   arriba-derecha
    #   coords[2] (h8) → (N, N)   abajo-derecha
    #   coords[3] (h1) → (0, N)   abajo-izquierda
    #
    # Ejes resultantes:
    #   x (columnas, izq→der): rank 1 → rank 8  (rank_index = col = i%8)
    #   y (filas, arr→abj):    file a → file h   (file_index  = row = i//8)
    # → cell_index_to_square(i) = chess.square(i//8, i%8)
    N = NORMALIZED_SIZE - 1
    destination_points = np.float32([
        [0, 0  ],   # coords[0] (a1) → arriba-izquierda
        [N, 0  ],   # coords[1] (a8) → arriba-derecha
        [N, N  ],   # coords[2] (h8) → abajo-derecha
        [0, N  ],   # coords[3] (h1) → abajo-izquierda
    ])

    mat = cv2.getPerspectiveTransform(coords, destination_points)       # Transformación de los puntos marcados por el usuario a los puntos de destino
    return mat                                                          # Devuelve la matriz ya transformada

# Función para el guardado de todos los frames detectados como clave (en los que se han realizado movimiento)
def save_key_frames(key_frames, file_name):
    if not key_frames:                                              # Si la lista de frames esta
        print("Lista de frames vacia")
        return False
    try:
        os.makedirs(TEMP_FRAMES_LOCATION, exist_ok=True)       # Creación si fuera necesario de la carpeta donde se almacenan los frames clave
    except Exception as e:
        print(f"Error en la creación del directorio {e}")           # Si da algún error en la creación de la carpeta, salta esta excepción
        return False

    path = os.path.join(TEMP_FRAMES_LOCATION, file_name)             # Variable que almacena el path completo incluyendo el nombre del archivo por ser creado

    try:
        key_frames_array = np.array(key_frames)
        np.savez_compressed(path, frames=key_frames_array)          # Guarda el array en el path indicado en un archivo tipo .npz
        print(f"DEBUG: Frames clave almacenados en {path}")
        return True

    except Exception as e:
        print(f"DEBUG: Error al guardar los frames clave {e}")      # Si da fallo en el almacenamiento, salta esta excepción
        return False

# Función para el cargado de todos los frames detectados como clave en un array
def load_key_frames(file_name):

    path = os.path.join(TEMP_FRAMES_LOCATION, file_name)         # Variable que almacena el path completo incluyendo el nombre del archivo del cual se quiere extraer los frames

    if not os.path.exists(path):
        print("ERROR: No se pudo abrir el archivo.")            # Si no existe el path, se notifica el error. Se devuelve un array vacio
        return []
    try:
        loaded_data = np.load(path)                             # Carga los datos del .npz en la variable

        key_frames_array = loaded_data["frames"]                # Extrae los datos de la variable y los almacena en un array

        key_frames = [frame for frame in key_frames_array]      # Recorre el array extrae todos los frames almacenados

        return key_frames                                       # Devuelve la lista de frames clave

    except Exception as e:
        print(f"Error al cargar los frames clave {e}")          # Si da fallo al sacar los frame claves salta la excepción
        return []                                               # Devuelve la lista vacia

# Funcion para la muestra de todos los frames detectados como clave
def show_key_frames(key_frames):
    if isinstance(key_frames, dict) and key_frames.get("error"):    # Comprobación del tipo y del contenido
        print(f"ERROR: {key_frames['error']}")                      # Si falla se notifica del error
        return False

    print(f"Se extrajeron {len(key_frames)} frames clave.")         # Si es correcto, se hace recuento del número de frames clave que hay

    for i, frame in enumerate(key_frames):                          # Bucle del que se van a extraer cada uno de los frames

        cv2.imshow(f"Jugada {i + 1}", frame)                        # Muestra el frame clave

        key = cv2.waitKey(0) & 0xFF                                 # Espera a que se pulse una tecla para continuar con la función

        if key == ord('q') or key == 27:                            # Si se pulsa 'q' o ESC se sale de la visualización del programa
            break

    cv2.destroyAllWindows()                                         # Cierra todas las ventanas creadas al finalizar

# Función para el borrado del archivo que contiene los frames clave
def delete_key_frames(file_name):
    path_frames = os.path.join(os.path.join(TEMP_FRAMES_LOCATION, file_name), '.npz')                           # Se crea una variable que almacena toda la ruta hasta el fichero que contiene los frames claves
    try:
        if os.path.exists(path_frames):                                                                         # Si existe el archivo:
            os.remove(os.path.join(TEMP_FRAMES_LOCATION, file_name))                                                # Ejecuta la orden de borrado del archivo con los frames claves
            print(f"Frames clave {file_name} eliminado.")                                                           # Se informa que se ha conseguido borrar el archivo
            return True
        else:                                                                                                   # Si no localiza el archivo:
            print("No se ha analizado la partida")                                                                  # Significa que no se ha procedido al análisis de la partida
            return False

    except Exception as e:                                                                                      # Si da fallo en el borrado salta la excepción
        return Response({'error': f"Fallo interno en el procesamiento: {str(e)}"},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)                                               # Se notifica del fallo y devuelve 500 INTERNAL SERVER ERROR

# Función que extrae los frames posteriores a un movimiento realizado y devuelve el conjunto de todas las imágenes.
def extract_key_frames(video_path, coords, progress_key=None):

    # Variables de la función
    key_frames = []                 # Lista de los frames claves
    frames_since_motion = 0         # Frames consecutivos de estabilidad desde el último movimiento
    motion_detected = False         # Indica si actualmente se está detectando un movimiento

    # ── Umbrales ───────────────────────────────────────────────────────────────
    # Se usa diferencia entre frames consecutivos para detectar movimiento y estabilidad.
    # Vista lateral: las piezas son objetos 3D que se proyectan en el plano de la cámara,
    # por lo que los diffs pueden ser más variables que desde una vista cenital.
    threshold_start     = 1200      # Píxeles distintos entre frames consecutivos para detectar inicio
    threshold_end       = 600       # Píxeles distintos entre frames consecutivos para considerar estabilidad (bajado de 800)
    stability_frames    = 6         # Frames consecutivos estables necesarios para guardar frame clave (bajado de 12)
    min_change_from_ref = 1500      # Diff mínima contra referencia para confirmar movimiento real (bajado de 2000)
    log_interval        = 300       # Cada cuántos frames imprimir estadísticas de diff
    frame_count         = 0         # Contador de frames procesados

    mat   = get_matriz(coords)
    video = open_video(video_path)
    total_frames = int(video.get(cv2.CAP_PROP_FRAME_COUNT)) or 1           # Total de frames para el progreso
    ret, frame_ref = video.read()                                           # Obtención del primer frame

    if not ret:
        return {"error": "Video vacío."}

    frame_ref_warped = cv2.warpPerspective(frame_ref, mat, (NORMALIZED_SIZE, NORMALIZED_SIZE))  # Transformación de perspectiva
    blur_ref  = process_image(frame_ref_warped)                                                 # Última posición estable conocida del tablero
    blur_prev = blur_ref.copy()                                                                 # Frame anterior para diff consecutiva

    while video.isOpened():
        ret, frame_curr = video.read()
        if not ret:
            break

        frame_count += 1
        if progress_key:
            set_progress(progress_key, int(frame_count / total_frames * 50))
        frame_curr_warped = cv2.warpPerspective(frame_curr, mat, (NORMALIZED_SIZE, NORMALIZED_SIZE))
        blur_curr = process_image(frame_curr_warped)

        # Diferencia entre frames consecutivos: detecta movimiento activo entre fotogramas adyacentes
        consec_diff  = cv2.absdiff(blur_prev, blur_curr)
        _, consec_thresh = cv2.threshold(consec_diff, 15, 255, cv2.THRESH_BINARY)
        consec_area  = int(np.sum(consec_thresh > 0))

        # Log periódico para calibrar umbrales: imprime el diff en reposo cada log_interval frames
        if frame_count % log_interval == 0:
            print(f"[FRAMES] frame={frame_count} consec_area={consec_area} "
                  f"motion={motion_detected} key_frames={len(key_frames)}")

        if not motion_detected:
            if consec_area > threshold_start:                               # Inicio de movimiento detectado
                motion_detected     = True
                frames_since_motion = 0
                print(f"[FRAMES] Movimiento iniciado en frame {frame_count} (consec_area={consec_area})")
            else:
                # Actualización gradual del frame de referencia para compensar cambios de iluminación
                blur_ref = cv2.addWeighted(blur_ref, 0.99, blur_curr, 0.01, 0)

        else:                                                               # Durante el movimiento
            if consec_area < threshold_end:
                frames_since_motion += 1                                    # Frame estable: incrementar contador
            else:
                frames_since_motion = 0                                     # Movimiento aún activo: reiniciar

            if frames_since_motion >= stability_frames:                     # Tablero estabilizado tras el movimiento
                # Confirmar movimiento real comparando contra la última posición estable de referencia
                ref_diff = cv2.absdiff(blur_ref, blur_curr)
                _, ref_thresh = cv2.threshold(ref_diff, 25, 255, cv2.THRESH_BINARY)
                ref_area = int(np.sum(ref_thresh > 0))

                if ref_area > min_change_from_ref:
                    key_frames.append(frame_curr_warped.copy())             # Guardar frame clave
                    blur_ref = blur_curr.copy()                             # Nueva referencia = posición actual
                    print(f"[FRAMES] Frame clave #{len(key_frames)} guardado (ref_area={ref_area})")
                else:
                    print(f"[FRAMES] Movimiento ignorado como falsa alarma (ref_area={ref_area})")

                motion_detected     = False
                frames_since_motion = 0

        blur_prev = blur_curr

    video.release()
    return key_frames

# -----------------------------------------
# Utilidad de debug: guardado de imágenes de diagnóstico
# -----------------------------------------

def save_debug_image(name, image):
    """
    Guarda una imagen en media/debug/<name>.jpg para diagnóstico visual.
    No lanza excepción si falla (el debug no debe interrumpir el análisis).
    """
    try:
        os.makedirs(DEBUG_LOCATION, exist_ok=True)
        path = os.path.join(DEBUG_LOCATION, f"{name}.jpg")
        # cv2.imwrite falla silenciosamente en Windows con rutas que contienen caracteres
        # no-ASCII (tildes, etc.). Se usa imencode + open() para evitarlo.
        ret, buf = cv2.imencode('.jpg', image)
        if ret:
            with open(path, 'wb') as f:
                f.write(buf.tobytes())
            print(f"[DEBUG] Imagen guardada: {path}")
        else:
            print(f"[DEBUG] imencode falló para '{name}'")
    except Exception as e:
        print(f"[DEBUG] No se pudo guardar imagen de debug '{name}': {e}")


# -----------------------------------------
# Calibración manual de esquinas del tablero
# -----------------------------------------

def save_corners_config(corners_rel):
    """
    Guarda las 4 esquinas del tablero como coordenadas relativas [0-1] en CORNERS_CONFIG_PATH.
    corners_rel: lista de 4 pares [[rx0,ry0], [rx1,ry1], [rx2,ry2], [rx3,ry3]]
    Orden: [TL=a1, TR=a8, BR=h8, BL=h1] (orientación lateral estándar).
    """
    data = {'corners_rel': [[float(x), float(y)] for x, y in corners_rel]}
    with open(CORNERS_CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f)
    print(f"[CORNERS] Calibración guardada: {data['corners_rel']}")


def load_corners_config(image_size):
    """
    Carga las esquinas guardadas y las escala al tamaño de imagen dado.
    image_size: (width, height) del frame de vídeo.
    Devuelve np.float32 con 4 esquinas en píxeles, o None si no hay config.
    """
    if not os.path.exists(CORNERS_CONFIG_PATH):
        return None
    try:
        with open(CORNERS_CONFIG_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        corners_rel = data.get('corners_rel')
        if not corners_rel or len(corners_rel) != 4:
            return None
        w, h = image_size
        corners = np.float32([[rx * w, ry * h] for rx, ry in corners_rel])
        print(f"[CORNERS] Calibración cargada: {corners.tolist()}")
        return corners
    except Exception as e:
        print(f"[CORNERS] Error cargando calibración: {e}")
        return None


# -----------------------------------------
# Detección automática de esquinas del tablero
# -----------------------------------------

def order_corners(corners):
    """Ordena 4 esquinas detectadas en orden [TL, TR, BR, BL]."""
    s    = corners.sum(axis=1)            # TL: min(x+y),  BR: max(x+y)
    diff = corners[:, 0] - corners[:, 1]  # TR: max(x-y),  BL: min(x-y)
    ordered = np.zeros((4, 2), dtype=np.float32)
    ordered[0] = corners[np.argmin(s)]
    ordered[1] = corners[np.argmax(diff)]
    ordered[2] = corners[np.argmax(s)]
    ordered[3] = corners[np.argmin(diff)]
    return ordered


def auto_detect_board_corners(frame):
    """
    Detecta automáticamente las 4 esquinas exteriores del tablero de ajedrez.
    Devuelve float32 en orden [TL, TR, BR, BL] compatible con get_matriz().

    POSICIÓN ESTÁNDAR DE GRABACIÓN (obligatoria para el mapeo correcto):
      - Cámara elevada desde el LADO DEL REY (columna h), mirando hacia la columna a.
      - Blancas a la IZQUIERDA de la imagen, negras a la DERECHA.
      - El tablero debe ser visible en su totalidad.
      TL=a1  TR=a8  BR=h8  BL=h1

    Estrategias en orden de prioridad:
      0. Calibración manual guardada (corners_config.json) — siempre tiene prioridad
      1. findChessboardCorners (casillas vacías visibles)
      2. Líneas de Hough (detecta la cuadrícula)
      3. Canny + contorno convexo con CLAHE
      4. Umbral adaptativo + contorno con CLAHE
      5. Fallback: recorte central al 80%
    """
    h, w   = frame.shape[:2]
    gray   = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    kernel = np.ones((5, 5), np.uint8)

    def _save_corner_debug(corners_result, label):
        """Dibuja las esquinas sobre el frame original y lo guarda en media/debug/."""
        vis = frame.copy()
        pts = corners_result.astype(int)
        labels_pos = ['TL(a1)', 'TR(a8)', 'BR(h8)', 'BL(h1)']
        colors     = [(0,255,0),(0,165,255),(0,0,255),(255,0,0)]
        for pt, lbl, col in zip(pts, labels_pos, colors):
            cv2.circle(vis, tuple(pt), 12, col, -1)
            cv2.putText(vis, lbl, (pt[0]+14, pt[1]-8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, col, 2)
        # Cuadrilátero
        cv2.polylines(vis, [pts.reshape(-1,1,2)], True, (255,255,0), 3)
        cv2.putText(vis, label, (10,30), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255,255,0), 2)
        save_debug_image("corners_detected", vis)

    # --- Prioridad 0: Calibración manual guardada ---
    stored = load_corners_config((w, h))
    if stored is not None:
        print("[CORNERS] Usando calibración manual guardada")
        _save_corner_debug(stored, "calibracion manual")
        return stored

    # --- Estrategia 1: findChessboardCorners ---
    # Funciona bien cuando al menos las casillas centrales del tablero son visibles.
    small  = cv2.resize(gray, (640, 480))
    sh, sw = small.shape[:2]
    for pat in [(7, 7), (6, 6), (5, 5)]:
        flags = (cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE
                 | cv2.CALIB_CB_FAST_CHECK)
        ret, pts = cv2.findChessboardCorners(small, pat, flags)
        if ret:
            pts = pts.reshape(pat[1], pat[0], 2) * np.float32([w / sw, h / sh])
            nr, nc = pat[1], pat[0]
            dx = (pts[0, -1] - pts[0, 0]) / (nc - 1)
            dy = (pts[-1, 0] - pts[0, 0]) / (nr - 1)
            tl = np.clip(pts[0,  0] - dx - dy, [0, 0], [w - 1, h - 1])
            tr = np.clip(pts[0, -1] + dx - dy, [0, 0], [w - 1, h - 1])
            br = np.clip(pts[-1,-1] + dx + dy, [0, 0], [w - 1, h - 1])
            bl = np.clip(pts[-1, 0] - dx + dy, [0, 0], [w - 1, h - 1])
            result = np.float32([tl, tr, br, bl])
            print(f"[CORNERS] Detectado con findChessboardCorners {pat}")
            _save_corner_debug(result, f"findChessboardCorners {pat}")
            return result

    # Aplicar CLAHE para mejorar el contraste antes de las estrategias de borde
    clahe    = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)

    # --- Estrategia 1: Líneas de Hough ---
    # Detecta las líneas horizontales y verticales de la cuadrícula del tablero.
    blurred = cv2.GaussianBlur(enhanced, (5, 5), 0)
    edges   = cv2.Canny(blurred, 20, 80)
    min_votes = int(min(h, w) * 0.25)
    lines = cv2.HoughLines(edges, 1, np.pi / 180, threshold=min_votes)
    if lines is not None:
        h_ys, v_xs = [], []
        for line in lines:
            rho, theta = line[0]
            cos_t, sin_t = np.cos(theta), np.sin(theta)
            if abs(sin_t) < 0.25 and abs(cos_t) > 1e-3:     # línea casi vertical
                v_xs.append(rho / cos_t)
            elif abs(cos_t) < 0.25 and abs(sin_t) > 1e-3:   # línea casi horizontal
                h_ys.append(rho / sin_t)
        if len(h_ys) >= 2 and len(v_xs) >= 2:
            top, bottom = min(h_ys), max(h_ys)
            left, right = min(v_xs), max(v_xs)
            if (bottom - top) > h * 0.3 and (right - left) > w * 0.3:
                left   = max(0.0, left);  right  = min(float(w - 1), right)
                top    = max(0.0, top);   bottom = min(float(h - 1), bottom)
                result = np.float32([[left, top], [right, top],
                                     [right, bottom], [left, bottom]])
                print("[CORNERS] Detectado con líneas de Hough")
                _save_corner_debug(result, "Hough lines")
                return result

    # --- Estrategia 2 y 3: Canny/umbral adaptativo + contorno ---
    min_area = h * w * 0.05

    def find_quad(binary):
        cnts, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in sorted(cnts, key=cv2.contourArea, reverse=True)[:15]:
            if cv2.contourArea(c) < min_area:
                break
            # Intentar approxPolyDP directamente
            peri = cv2.arcLength(c, True)
            for eps in (0.01, 0.02, 0.03, 0.05, 0.08):
                approx = cv2.approxPolyDP(c, eps * peri, True)
                if len(approx) == 4:
                    return np.float32([p[0] for p in approx])
            # Fallback: casco convexo del contorno
            hull = cv2.convexHull(c)
            peri = cv2.arcLength(hull, True)
            for eps in (0.02, 0.05, 0.10):
                approx = cv2.approxPolyDP(hull, eps * peri, True)
                if len(approx) == 4:
                    return np.float32([p[0] for p in approx])
        return None

    # Estrategia 2: Canny + dilatación con CLAHE
    edges2 = cv2.Canny(cv2.GaussianBlur(enhanced, (7, 7), 0), 20, 80)
    edges2 = cv2.dilate(edges2, kernel, iterations=2)
    result = find_quad(edges2)
    if result is not None:
        result = order_corners(result)
        print("[CORNERS] Detectado con Canny + contorno")
        _save_corner_debug(result, "Canny contour")
        return result

    # Estrategia 3: Umbral adaptativo con CLAHE
    thresh = cv2.adaptiveThreshold(cv2.GaussianBlur(enhanced, (11, 11), 0), 255,
                                   cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                   cv2.THRESH_BINARY_INV, 11, 2)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
    result = find_quad(thresh)
    if result is not None:
        result = order_corners(result)
        print("[CORNERS] Detectado con umbral adaptativo")
        _save_corner_debug(result, "adaptive threshold")
        return result

    # Fallback: recorte central del 80% (margen 10% por lado)
    print("[CORNERS] Auto-detección falló, usando recorte central (80%)")
    mx, my = w * 0.10, h * 0.10
    result = np.float32([[mx, my], [w - mx, my], [w - mx, h - my], [mx, h - my]])
    _save_corner_debug(result, "FALLBACK 80% crop")
    return result


def get_first_frame(video_path):
    """Lee y devuelve el primer frame del video sin mantenerlo abierto."""
    cap = open_video(video_path)
    if isinstance(cap, dict):
        return None
    ret, frame = cap.read()
    cap.release()
    return frame if ret else None


def refine_warp_with_grid(warped):
    """
    Aplica una corrección secundaria al tablero ya transformado por perspectiva.

    Estrategia:
      - Detecta las líneas de la cuadrícula del tablero en la imagen warpeada
        usando la transformada de Hough.
      - A partir de las líneas horizontales y verticales más dominantes, estima
        la posición real de cada borde de celda.
      - Si la cuadrícula detectada difiere más de 30 px del ideal (celdas iguales),
        aplica una segunda homografía para corregir la distorsión residual.

    Devuelve la imagen corregida (o la original si la detección falla).
    """
    try:
        gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 30, 90)
        lines = cv2.HoughLines(edges, 1, np.pi / 180, threshold=80)
        if lines is None or len(lines) < 6:
            return warped

        h_lines, v_lines = [], []
        for line in lines[:60]:
            rho, theta = line[0]
            if abs(theta) < 0.2 or abs(theta - np.pi) < 0.2:       # casi vertical
                v_lines.append(abs(rho))
            elif abs(theta - np.pi / 2) < 0.2:                      # casi horizontal
                h_lines.append(abs(rho))

        h_lines = sorted(set(round(x / 20) * 20 for x in h_lines))
        v_lines = sorted(set(round(x / 20) * 20 for x in v_lines))

        # Necesitamos al menos las 4 líneas exteriores del tablero en cada eje
        if len(h_lines) < 2 or len(v_lines) < 2:
            return warped

        # Esquinas detectadas del tablero en la imagen warpeada
        x0, x1 = v_lines[0], v_lines[-1]
        y0, y1 = h_lines[0], h_lines[-1]

        # Si la desviación del borde ideal es menor de 30 px, no es necesario corregir
        if (abs(x0) < 30 and abs(x1 - (NORMALIZED_SIZE - 1)) < 30 and
                abs(y0) < 30 and abs(y1 - (NORMALIZED_SIZE - 1)) < 30):
            return warped

        N = float(NORMALIZED_SIZE - 1)
        src = np.float32([[x0, y0], [x1, y0], [x1, y1], [x0, y1]])
        dst = np.float32([[0, 0], [N, 0], [N, N], [0, N]])
        refine_mat = cv2.getPerspectiveTransform(src, dst)
        refined = cv2.warpPerspective(warped, refine_mat, (NORMALIZED_SIZE, NORMALIZED_SIZE))
        print(f"[WARP] Corrección secundaria aplicada: bordes detectados "
              f"x=[{x0:.0f},{x1:.0f}] y=[{y0:.0f},{y1:.0f}]")
        return refined

    except Exception as e:
        print(f"[WARP] refine_warp_with_grid falló: {e}")
        return warped


def get_initial_board_frame(video_path, corners):
    """
    Obtiene el primer frame del video con la transformación de perspectiva aplicada
    (mismo proceso que los frames clave). Guarda el resultado en media/debug/warped_initial.jpg.
    """
    frame = get_first_frame(video_path)
    if frame is None:
        return None
    mat    = get_matriz(corners)
    warped = cv2.warpPerspective(frame, mat, (NORMALIZED_SIZE, NORMALIZED_SIZE))

    # Debug: dibujar la cuadrícula de las 64 celdas sobre el frame transformado
    grid_vis = warped.copy()
    cs = NORMALIZED_SIZE // 8
    for i in range(9):
        cv2.line(grid_vis, (i * cs, 0), (i * cs, NORMALIZED_SIZE), (0, 255, 0), 1)
        cv2.line(grid_vis, (0, i * cs), (NORMALIZED_SIZE, i * cs), (0, 255, 0), 1)
    # Etiquetar esquinas
    corner_labels = {(0, 0): 'a1', (cs*7, 0): 'a8', (0, cs*7): 'h1', (cs*7, cs*7): 'h8'}
    for (cx, cy), lbl in corner_labels.items():
        cv2.putText(grid_vis, lbl, (cx + 4, cy + 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
    save_debug_image("warped_initial", grid_vis)

    return warped


# -----------------------------------------
# Comparación de celdas del tablero para detección de movimientos
# -----------------------------------------

def get_board_cells(board_image):
    """Divide la imagen del tablero (NORMALIZED_SIZE × NORMALIZED_SIZE) en 64 celdas 8×8."""
    cs = NORMALIZED_SIZE // 8
    return [board_image[r*cs:(r+1)*cs, c*cs:(c+1)*cs] for r in range(8) for c in range(8)]


def get_changed_cells(frame_before, frame_after, threshold=CELL_CHANGE_THRESHOLD):
    """
    Compara las 64 celdas entre dos frames y devuelve los índices de las
    celdas que cambiaron significativamente, ordenados por magnitud (mayor primero).

    Mejoras respecto a la versión anterior:
    - Cada celda se normaliza por su brillo medio antes de comparar (elimina efecto
      de cambios globales de iluminación que afectan a todas las celdas igual).
    - Se resta la mediana de los diffs de todas las celdas (compensación de modo común):
      si la luz cambia uniformemente, el diff de todas las celdas sube en la misma cantidad
      y la mediana lo absorbe; sólo las celdas con movimiento real destacan por encima.
    - Se limita a 6 resultados (en un movimiento normal se tocan 2 celdas; en enroque, 4).
    """
    def to_gray(img):
        return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img

    cells_b = get_board_cells(to_gray(frame_before))
    cells_a = get_board_cells(to_gray(frame_after))

    raw_diffs = []
    for cb, ca in zip(cells_b, cells_a):
        cb_f = cb.astype(np.float32)
        ca_f = ca.astype(np.float32)
        # Normalizar por brillo medio de cada celda (independiente de iluminación global)
        diff = float(np.mean(np.abs(
            (ca_f - np.mean(ca_f)) - (cb_f - np.mean(cb_f))
        )))
        raw_diffs.append(diff)

    # Compensar variación común de iluminación restando la mediana de todas las celdas
    median_diff = float(np.median(raw_diffs))
    changes = []
    for i, d in enumerate(raw_diffs):
        residual = d - median_diff
        if residual > threshold:
            changes.append((i, residual))

    changes.sort(key=lambda x: x[1], reverse=True)
    return [idx for idx, _ in changes[:6]]


def classify_cells_occupation(frame_before, frame_after, changed_indices):
    """
    Para cada índice de celda cambiada, clasifica si la celda ganó (+1) o perdió (-1)
    una pieza, midiendo la densidad de bordes (las piezas 3D generan más bordes que
    una celda vacía de tablero).

    Retorna un dict {cell_index: +1 | -1 | 0}.
    """
    def to_gray(img):
        return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img

    def edge_density(cell):
        return float(np.mean(cv2.Canny(cell, 30, 100)))

    cells_b = get_board_cells(to_gray(frame_before))
    cells_a = get_board_cells(to_gray(frame_after))

    result = {}
    for idx in changed_indices:
        ed_b = edge_density(cells_b[idx])
        ed_a = edge_density(cells_a[idx])
        delta = ed_a - ed_b
        if delta > 4:       # más bordes → pieza llegó
            result[idx] = +1
        elif delta < -4:    # menos bordes → pieza salió
            result[idx] = -1
        else:
            result[idx] = 0
    return result


def cell_index_to_square(cell_index):
    """
    Convierte índice de celda (0–63, fila a fila desde arriba-izquierda)
    en casilla de python-chess para la orientación LATERAL estándar de grabación:

        Posición de cámara:
          - Cámara elevada desde el lado del rey (columna h), mirando hacia la columna a.
          - Blancas a la IZQUIERDA, negras a la DERECHA en la imagen.
          - Columna h cerca de la cámara → fila inferior de la imagen (fila 7).
          - Columna a lejos de la cámara → fila superior de la imagen (fila 0).

        Mapeo en la imagen normalizada (1000×1000):
          Fila (i//8): 0=columna a, 7=columna h  →  archivo de ajedrez = i//8
          Col  (i%8):  0=rango 1,  7=rango 8     →  rango de ajedrez  = i%8

          cell  0 (fila 0, col 0) = a1  →  chess.A1  ✓
          cell  7 (fila 0, col 7) = a8  →  chess.A8  ✓
          cell 56 (fila 7, col 0) = h1  →  chess.H1  ✓
          cell 63 (fila 7, col 7) = h8  →  chess.H8  ✓
    """
    return chess.square(cell_index // 8, cell_index % 8)


def detect_move_from_squares(board, changed_squares,
                              frame_before=None, frame_after=None, changed_indices=None):
    """
    Dado el estado del tablero y las casillas que cambiaron, devuelve el
    movimiento legal que mejor explica los cambios.

    Estrategia en dos niveles:
      1. Clasificación origen/destino: si se puede identificar qué celda perdió
         una pieza (fuente) y cuál la recibió (destino), se busca directamente
         el movimiento legal from_square→to_square.  Mucho más preciso que sólo
         contar solapamiento.
      2. Máximo solapamiento (fallback): si la clasificación no es concluyente,
         se usa el método original de máxima intersección.
    """
    changed_set = set(changed_squares)
    castling_extras = {
        chess.G1: {chess.H1, chess.F1},
        chess.C1: {chess.A1, chess.D1},
        chess.G8: {chess.H8, chess.F8},
        chess.C8: {chess.A8, chess.D8},
    }

    # ── Nivel 1: clasificación origen / destino ──────────────────────────────
    if frame_before is not None and frame_after is not None and changed_indices is not None:
        classification = classify_cells_occupation(frame_before, frame_after, changed_indices)
        sources = {cell_index_to_square(i) for i, c in classification.items() if c == -1}
        dests   = {cell_index_to_square(i) for i, c in classification.items() if c == +1}

        if sources and dests:
            print(f"[FEN]   Clasificación → fuentes={[chess.square_name(s) for s in sources]} "
                  f"destinos={[chess.square_name(d) for d in dests]}")
            # Buscar movimiento legal que encaje exactamente
            for move in board.legal_moves:
                if move.from_square in sources and move.to_square in dests:
                    return move
            # Enroque: el rey puede no clasificarse correctamente por la torre
            for move in board.legal_moves:
                if board.is_castling(move):
                    involved = {move.from_square, move.to_square} | castling_extras.get(move.to_square, set())
                    if len(involved & changed_set) >= 3:
                        return move

    # ── Nivel 2: fallback por máximo solapamiento ────────────────────────────
    best_move, best_overlap = None, 0
    for move in board.legal_moves:
        involved = {move.from_square, move.to_square}
        if board.is_castling(move):
            involved |= castling_extras.get(move.to_square, set())
        overlap = len(involved & changed_set)
        if overlap > best_overlap:
            best_overlap, best_move = overlap, move

    return best_move if best_overlap >= 2 else None


# -----------------------------------------
# Generación y persistencia de FENs
# -----------------------------------------

def detect_two_moves(board, changed_squares):
    """
    Cuando se detectan demasiadas celdas cambiadas para ser un único movimiento
    (>4 celdas), intenta encontrar dos movimientos legales consecutivos que juntos
    expliquen los cambios observados.

    Estrategia:
      - Para cada movimiento legal posible como primer movimiento (move1),
        comprueba cuántas de las celdas cambiadas cubre.
      - Aplica move1 temporalmente y busca move2 que cubra el resto.
      - Devuelve (move1, move2) si la cobertura combinada es suficiente, o None.

    Complejidad: O(legal_moves²) ≈ 40×40 = 1600 iteraciones máx. → rápido.
    """
    changed_set = set(changed_squares)
    if len(changed_set) < 3:
        return None

    castling_extras = {
        chess.G1: {chess.H1, chess.F1},
        chess.C1: {chess.A1, chess.D1},
        chess.G8: {chess.H8, chess.F8},
        chess.C8: {chess.A8, chess.D8},
    }

    for move1 in list(board.legal_moves):
        inv1 = {move1.from_square, move1.to_square}
        if board.is_castling(move1):
            inv1 |= castling_extras.get(move1.to_square, set())
        if not (inv1 & changed_set):
            continue                          # move1 no toca ninguna celda cambiada

        board.push(move1)
        for move2 in list(board.legal_moves):
            inv2 = {move2.from_square, move2.to_square}
            if board.is_castling(move2):
                inv2 |= castling_extras.get(move2.to_square, set())
            combined = inv1 | inv2
            # Aceptar si la unión cubre al menos len-1 celdas cambiadas
            if len(combined & changed_set) >= max(3, len(changed_set) - 1):
                board.pop()
                return move1, move2
        board.pop()

    return None


def frames_to_fens(all_frames, initial_fen=None, progress_key=None):
    """
    Convierte una secuencia de frames del tablero en una lista de FENs.
      all_frames[0]  → posición inicial (antes de cualquier movimiento)
      all_frames[i]  → posición después del movimiento i

    La lógica NO necesita reconocer las piezas visualmente: sólo detecta
    qué casillas cambiaron entre frames consecutivos y busca el movimiento
    legal de python-chess que mejor explica ese cambio.

    Retorna lista de FENs con len(all_frames) elementos.
    """
    if initial_fen is None:
        initial_fen = chess.STARTING_FEN

    board          = chess.Board(initial_fen)
    fens           = [initial_fen]
    consecutive_failures = 0          # Fallos consecutivos sin detectar movimiento
    MAX_FAILURES   = 5                # Tras este nº de fallos seguidos se imprime aviso

    total_steps = max(1, len(all_frames) - 1)
    for i in range(total_steps):
        if progress_key:
            set_progress(progress_key, 50 + int(i / total_steps * 50))
        try:
            frame_a = all_frames[i]
            frame_b = all_frames[i + 1]

            changed = get_changed_cells(frame_a, frame_b)
            squares = [cell_index_to_square(idx) for idx in changed]
            print(f"[FEN] Frame {i}→{i+1}: {len(changed)} celdas cambiadas → "
                  f"casillas {[chess.square_name(s) for s in squares]}")

            # Guardar debug de los 8 primeros pares para inspección visual
            if i < 8:
                _save_frame_pair_debug(i, frame_a, frame_b, changed)

            if not changed:
                print(f"[FEN] Sin cambios detectados, manteniendo FEN anterior")
                fens.append(board.fen())
                consecutive_failures += 1
                continue

            # ── Detección de doble movimiento ────────────────────────────────
            # Si hay >4 celdas cambiadas y no es un enroque, es probable que el frame
            # capturado ya contenga 2 movimientos (jugadas muy rápidas sin pausa intermedia).
            if len(changed) > 4:
                two = detect_two_moves(board, squares)
                if two:
                    m1, m2 = two
                    san1 = board.san(m1)
                    board.push(m1)
                    fens.append(board.fen())            # FEN intermedio (tras mov 1)
                    san2 = board.san(m2)
                    board.push(m2)
                    fens.append(board.fen())            # FEN final (tras mov 2)
                    consecutive_failures = 0
                    print(f"[FEN] ✓ Doble movimiento detectado: {san1} + {san2}")
                    continue

            # ── Detección de movimiento simple ────────────────────────────────
            move = detect_move_from_squares(board, squares,
                                            frame_before=frame_a, frame_after=frame_b,
                                            changed_indices=changed)

            if move:
                san = board.san(move)
                board.push(move)
                fens.append(board.fen())
                consecutive_failures = 0
                print(f"[FEN] ✓ Movimiento detectado: {san} ({move.uci()})")
            else:
                # Reintento con umbral más bajo (posible movimiento sutil)
                changed_r = get_changed_cells(frame_a, frame_b,
                                              threshold=CELL_CHANGE_THRESHOLD // 2)
                squares_r = [cell_index_to_square(idx) for idx in changed_r]
                move2 = detect_move_from_squares(board, squares_r,
                                                 frame_before=frame_a, frame_after=frame_b,
                                                 changed_indices=changed_r)
                if move2:
                    san = board.san(move2)
                    board.push(move2)
                    fens.append(board.fen())
                    consecutive_failures = 0
                    print(f"[FEN] ✓ Movimiento detectado (umbral relajado): {san} ({move2.uci()})")
                else:
                    fens.append(board.fen())
                    consecutive_failures += 1
                    if consecutive_failures >= MAX_FAILURES:
                        print(f"[FEN] ⚠ {consecutive_failures} fallos consecutivos — "
                              f"revisa media/debug/frame_pair_*.jpg")
                    else:
                        print(f"[FEN] No se pudo determinar el movimiento (fallo #{consecutive_failures})")

        except Exception as e:
            print(f"[FEN] Error procesando frame {i}: {e}")
            fens.append(board.fen())
            consecutive_failures += 1

    return fens


def _save_frame_pair_debug(idx, frame_a, frame_b, changed_indices):
    """
    Guarda un collage con los dos frames y resalta las celdas detectadas como cambiadas.
    Útil para depurar los primeros movimientos.
    """
    try:
        cs = NORMALIZED_SIZE // 8
        vis_a = frame_a.copy()
        vis_b = frame_b.copy()
        for ci in changed_indices:
            r, c = ci // 8, ci % 8
            x1, y1 = c * cs, r * cs
            cv2.rectangle(vis_a, (x1, y1), (x1 + cs, y1 + cs), (0, 0, 255), 3)
            cv2.rectangle(vis_b, (x1, y1), (x1 + cs, y1 + cs), (0, 255, 0), 3)
        collage = np.hstack([
            cv2.resize(vis_a, (500, 500)),
            cv2.resize(vis_b, (500, 500)),
        ])
        cv2.putText(collage, f"Frame {idx} (antes)", (10, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        cv2.putText(collage, f"Frame {idx+1} (despues)", (510, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        save_debug_image(f"frame_pair_{idx:02d}", collage)
    except Exception as e:
        print(f"[DEBUG] _save_frame_pair_debug falló: {e}")


def save_fens(fens, analysis_id):
    """
    Guarda la secuencia de FENs en media/fens/<analysis_id>.json asociada a un análisis previo. 
    Crea el directorio si no existe.
    
    Parametros:
        - fens: Lista de FENs a guardar.
        - analysis_id: Identificador único del análisis para nombrar el archivo de FENs.

    Devuelve la ruta del archivo de FENs guardado.
    """
    os.makedirs(FENS_LOCATION, exist_ok=True)
    path = os.path.join(FENS_LOCATION, f"{analysis_id}.json")
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({'fens': fens, 'total': len(fens)}, f)
    print(f"[FEN] {len(fens)} FENs guardados en {path}")
    return path

def load_fens(analysis_id):
    """
    Carga la secuencia de FENs desde media/fens/<analysis_id>.json asociada a un análisis previo. 
    
    Parametros:
    - analysis_id: Identificador único del análisis que se usó para guardar las FENs.

    Devuelve una lista de FENs o None si no se encuentra el archivo.
    """

    path = os.path.join(FENS_LOCATION, f"{analysis_id}.json")
    if not os.path.exists(path):
        return None
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data.get('fens', [])


def delete_fens(analysis_id):
    """Elimina el archivo de FENs asociado a un analysis_id. Devuelve True si se borró, False si no existía."""
    path = os.path.join(FENS_LOCATION, f"{analysis_id}.json")
    if os.path.exists(path):
        try:
            os.remove(path)
            print(f"[DELETE] FENs {analysis_id}.json eliminados.")
            return True
        except Exception as e:
            print(f"[DELETE] Error al eliminar FENs {analysis_id}.json: {e}")
            return False
    return False


# -----------------------------------------
# Funciones de Análisis de Partida
# -----------------------------------------

def analysis_best_posStockfish(fen):

    """
    Obtiene la mejor jugada para la posición dada en formato FEN utilizando el motor Stockfish.
        Parametros:
        - fen: Cadena FEN que representa la posición actual del tablero.
        
        - Devuelve un diccionario con:
            - movement_uci: Movimiento recomendado en formato UCI (ejemplo: "e2e4").
            - movement_san: Movimiento recomendado en formato SAN (ejemplo: "e4").
            - new_fen: FEN resultante después de aplicar el movimiento recomendado.
            - score: Evaluación de la posición después del movimiento recomendado (en centipawns, positivo para blancas, negativo para negras).
    """

    path_engine = os.path.join(ENGINES_DIR, 'stockfish-windows-x86-64-avx2.exe')

    with chess.engine.SimpleEngine.popen_uci(path_engine) as engine:

        board = chess.Board(fen)

        info = engine.analyse(board, chess.engine.Limit(time=0.1))

        best_move = info["pv"][0]

        return {
            "movement_uci": best_move.uci(),
            "movement_san": board.san(best_move) if not board.move_stack else chess.Board(fen).san(best_move),
            "new_fen": board.fen(),
            "score": info["score"].relative.score(mate_score=10000) / 100
        }

def analysis_best_posObsidian(fen):

    """
    Obtiene la mejor jugada para la posición dada en formato FEN utilizando el motor Obsidian.
        Parametros:
        - fen: Cadena FEN que representa la posición actual del tablero.
        
        - Devuelve un diccionario con:
            - movement_uci: Movimiento recomendado en formato UCI (ejemplo: "e2e4").
            - movement_san: Movimiento recomendado en formato SAN (ejemplo: "e4").
            - new_fen: FEN resultante después de aplicar el movimiento recomendado.
            - score: Evaluación de la posición después del movimiento recomendado (en centipawns, positivo para blancas, negativo para negras).
    """

    path_engine = os.path.join(ENGINES_DIR, 'Obsidian160-avx2-pext.exe')

    with chess.engine.SimpleEngine.popen_uci(path_engine) as engine:

        board = chess.Board(fen)

        info = engine.analyse(board, chess.engine.Limit(time=0.1))

        best_move = info["pv"][0]

        return {
            "movement_uci": best_move.uci(),
            "movement_san": board.san(best_move) if not board.move_stack else chess.Board(fen).san(best_move),
            "new_fen": board.fen(),
            "score": info["score"].relative.score(mate_score=10000) / 100
        }

def analysis_best_posPlentyChess(fen):

    """
    Obtiene la mejor jugada para la posición dada en formato FEN utilizando el motor PlentyChess.

        Parametros:
        - fen: Cadena FEN que representa la posición actual del tablero.
        
        - Devuelve un diccionario con:
            - movement_uci: Movimiento recomendado en formato UCI (ejemplo: "e2e4").
            - movement_san: Movimiento recomendado en formato SAN (ejemplo: "e4").
            - new_fen: FEN resultante después de aplicar el movimiento recomendado.
            - score: Evaluación de la posición después del movimiento recomendado (en centipawns, positivo para blancas, negativo para negras).
    """
    
    path_engine = os.path.join(ENGINES_DIR, 'PlentyChess-7.0.0-windows-avx2.exe')

    with chess.engine.SimpleEngine.popen_uci(path_engine) as engine:

        board = chess.Board(fen)

        info = engine.analyse(board, chess.engine.Limit(time=0.1))

        best_move = info["pv"][0]

        return {
            "movement_uci": best_move.uci(),
            "movement_san": board.san(best_move) if not board.move_stack else chess.Board(fen).san(best_move),
            "new_fen": board.fen(),
            "score": info["score"].relative.score(mate_score=10000) / 100
        }

def consensus_analysis(stock, obsidian, plenty, fen):

    """
    Dada una posición en formato FEN y las recomendaciones de movimiento de tres motores de ajedrez (Stockfish, Obsidian y PlentyChess),
    esta función determina el movimiento recomendado por consenso entre los motores. El movimiento de consenso se define como el movimiento 
    que al menos dos de los motores recomiendan. Si no hay consenso, se selecciona el movimiento recomendado por Stockfish como predeterminado.

    Parámetros:
    - stock: Diccionario con la recomendación de movimiento de Stockfish, movimiento en formato UCI, movimiento en formato SAN, FEN resultante y evaluación de la posición.
    - obsidian: Diccionario con la recomendación de movimiento de Obsidian, cono formato similar al de Stockfish.
    - plenty: Diccionario con la recomendación de movimiento de PlentyChess, con formato similar al de Stockfish.
    - fen: Cadena FEN que representa la posición actual del tablero.

    Devuelve un diccionario con:
    - movement_uci: Movimiento recomendado por consenso en formato UCI (ejemplo: "e2e4").
    - movement_san: Movimiento recomendado por consenso en formato SAN (ejemplo: "e4").
    - new_fen: FEN resultante después de aplicar el movimiento recomendado por consenso.
    """

    board = chess.Board(fen)
    moves = [
        stock["movement_uci"],
        obsidian["movement_uci"],
        plenty["movement_uci"]
    ]

    count = Counter(moves)

    most_common_uci = count.most_common(1)[0][0]

    try:
        move = chess.Move.from_uci(most_common_uci)

    except ValueError as e:
        raise ValueError(f"Movimiento invalido: {moves}. Error: {e}")

    if move not in board.legal_moves:
        print(f"\n ERROR: El movimiento {most_common_uci} NO es legal en esta posición")
        print(f"Posición: {board.board_fen()}")
        print(f"\nMovimientos legales disponibles:")
        for legal_move in list(board.legal_moves)[:10]:
            print(f"  - {legal_move.uci()} ({board.san(legal_move)})")

        raise ValueError(
            f"El movimiento {most_common_uci} no es legal en la posición {fen}. "
            f"Los motores probablemente analizaron una posición diferente."
        )

    move_san = board.san(move)
    board.push(move)
    return {
        "movement_uci": most_common_uci,
        "movement_san": move_san,
        "new_fen": board.fen(),
    }
