import os
import cv2
import numpy as np
from django.conf import settings

TEMP_VIDEOS_LOCATION = os.path.join(settings.MEDIA_ROOT, 'temp_videos')
TEMP_FRAMES_LOCATION = os.path.join(settings.MEDIA_ROOT, 'temp_frames')

NORMALIZED_SIZE = 1000
PUNTOS_ORIGEN = []
MAX_PUNTOS = 4
VENTANA_NOMBRE = 'Selecciona las 4 Esquinas del Tablero'

# Función de borrado de los videos obtenidos del FrontEnd y almacenados.
def delete_temporary_videos(file_name):
    file_path = os.path.join(TEMP_VIDEOS_LOCATION, file_name)                   # Almacena en la variable la ruta hasta el archivo que se quiere borrar
    if os.path.exists(file_path):                                               # Si la ruta hasta el video existe
        try:
            os.remove(file_path)                                                # Se elimina el video especificado por la ruta
            print(f"DEBUG: El video {file_name} ha sido eliminado")             # Se notifica que el video ha sido eliminado
            return True
        except Exception as e:                                                  # Si algo falla, salta la excepción
            print(f"DEBUG: El video no ha podido ser eliminado: {e}")           # Se notifica cual es el fallo
            return False
    else:                                                                       # Si la ruta hasta el archivo no existe
        print(f"DEBUG: El video {file_name} no existe")                         # Se notifica de que ese archivo no existe
        return True

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
def click_event(event, x, y, flags, param):

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
    destination_points = np.float32([                                   # Conjunto de coordenadas de destino
        [0, NORMALIZED_SIZE - 1],                                           # Superior Izquierda
        [NORMALIZED_SIZE - 1, NORMALIZED_SIZE - 1],                         # Inferior Derecha
        [NORMALIZED_SIZE - 1, 0],                                           # Superior Derecha
        [0, 0],                                                             # Inferior Izquierda
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
    if os.path.exists(os.path.join(TEMP_FRAMES_LOCATION, file_name)):                # Localiza el archivo que contiene los frames claves
        try:
            os.remove(os.path.join(TEMP_FRAMES_LOCATION, file_name))                 # Ejecuta la orden de borrado del archivo con los frames claves
            print(f"Frames clave {file_name} eliminado.")                           # Se informa que se ha conseguido borrar el archivo
            return True
        except Exception as e:                                                      # Si da fallo en el borrado salta la excepción
            print(f"Error al eliminar los frames clave {e}")                        # Se informa del fallo
            return False
    else:
        print("ERROR: No se pudo abrir el archivo.")                                # Si no lo localiza, muestra el error
        return False

# Función para ajustar la nitidez: PROBABLEMENTE PARA ELIMINAR
def increase_sharpness(frame, blur_ksize: int = 25, weight: float = 6, threshold: int = 0):
    if blur_ksize % 2 == 0:
        raise ValueError("blur_ksize debe ser impar")

    is_color = len(frame.shape) == 3
    gray_image = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if is_color else frame.copy()

    blurred = cv2.GaussianBlur(gray_image, (blur_ksize, blur_ksize), 0)

    # 2. Calcular la máscara de detalles (diferencia entre original y desenfocada)
    # Convertimos a float para evitar problemas de saturación con valores negativos
    detail_mask = cv2.subtract(gray_image.astype(np.float32), blurred.astype(np.float32))

    # 3. Aplicar umbral a la máscara de detalles (opcional para reducir ruido)
    if threshold > 0:
        detail_mask = np.where(np.abs(detail_mask) < threshold, 0, detail_mask)

    # 4. Sumar la máscara de detalles (amplificada) a la imagen original
    # Convertimos de nuevo a tipo de imagen para la suma
    sharpened_image = cv2.addWeighted(gray_image.astype(np.float32), 1.0, detail_mask, weight, 0)

    # Asegurarse de que los valores estén en el rango [0, 255] y convertir a uint8
    sharpened_image = np.clip(sharpened_image, 0, 255).astype(np.uint8)

    # Si la imagen original era a color, convertimos de nuevo a color
    if is_color:
        sharpened_image = cv2.cvtColor(sharpened_image, cv2.COLOR_GRAY2BGR)

    return sharpened_image

# Función que extrae los frames posteriores a un movimiento realizado y devuelve el conjunto de todas las imágenes.
def extract_key_frames(video_path):

    # Variables de la función
    key_frames = []                                                         # Lista de los frames claves
    frames_since_motion = 0                                                 # Contador de frames que han pasado sin que haya movimiento
    motion_detected = False                                                 # Detector de movimiento
    area_threshold_start = 150000                                           # Valor minimo que debe superarse para considerar que se está realizando un movimiento
    area_threshold_end = 25000                                              # Valor máximo en el que se considera que hay estabilidad en la imagen
    stability_frames = 10                                                   # Umbral que debe superarse para considerar que el tablero ya ha estado en estabilidad y la jugada anterior terminó

    coords = get_corners(video_path)                                        # Llamada a la función obtener las esquinas del tablero
    mat = get_matriz(coords)                                                # Llamada a la función de la matriz de transformación                                                            # Almacena los valores de la variable dims en dos variables

    video = open_video(video_path)                                          # Llamada a la función que abre el video y almacenamiento en la variable
    ret, frame_ref = video.read()                                           # Obtención del primer frame

    if not ret:
        return {f"DEBUG: error": "Video vacío."}                                    # Si no se pudo leer el frame, notifica del error

    frame_ref_warped = cv2.warpPerspective(frame_ref, mat, (NORMALIZED_SIZE, NORMALIZED_SIZE))          # Modificación del frame alterando la perspectiva para visualizar solamente el tablero
    blur_ref = process_image(frame_ref_warped)                                                          # Llamada a la función de procesamiento de imagen

    fgbg = cv2.createBackgroundSubtractorMOG2(history=500, varThreshold=16, detectShadows=True)     # Algoritmo de substracción de fondo. Detectando los píxeles cambiantes y los estables

    while video.isOpened():                                                 # Bucle de procesamiento del video
        ret, frame_curr = video.read()                                      # Extrae el frame actual
        if not ret:                                                         # Si devuelve falso, el video ha acabado
            break

        frame_curr_warped = cv2.warpPerspective(frame_curr, mat, (NORMALIZED_SIZE, NORMALIZED_SIZE))    # Modificación del frame actual alterando la perspectiva para visualizar solamente el tablero
        blur_curr = process_image(frame_curr_warped)                                                    # Procesamiento de la imagen del frame actual
        fgmask = fgbg.apply(blur_curr)                                                                  # Almacena la máscara de movimiento en la variable
        frame_diff = cv2.absdiff(blur_ref, blur_curr)                                                   # Cálculo de la diferencia absoluta entre el frame de referencia y el actual
        _, thresh = cv2.threshold(frame_diff, 30, 255, cv2.THRESH_BINARY)                               # Función que realiza la umbralización
        motion_area = np.sum(fgmask > 0)                                                                # Cuantificación del movimiento. Para detectar si se está realizando un movimiento o no

        if motion_detected == False:                                        # En caso de que no se detecte un movimiento:

            if motion_area > area_threshold_start:                          # Si se considera que esta ocurriendo un movimiento
                motion_detected = True                                          # Se pone la variable que detecta el movimiento a true
                frames_since_motion = 0                                         # Y se reestablece cuenta a 0
            elif motion_area < 500:                                         # Si la imagen tiene muy poco movimiento
                alpha = 0.99
                beta = 1.0 - alpha
                blur_ref = cv2.addWeighted(blur_ref, alpha, blur_curr, beta, 0) # Calculo el promedio ponderado de la imagen de referencia y la actual

        else:                                                               # En caso de que se detecte un movimiento:

            if motion_area < area_threshold_end:                            # Si el movimiento es menor al umbral
                frames_since_motion += 1                                        # Se considera estable y se añade +1
            else:                                                           # Si el movimiento es mayor o igual al umbral
                frames_since_motion = 0                                         # No se considera estable y se reestablece a 0 el contador

        print(f"DEBUG: Frames since motion: {frames_since_motion}")
        print(f"DEBUG: Motion area: {motion_area}")

        if motion_detected and frames_since_motion > stability_frames:      # Si se ha detectado movimiento y se ha alcanzado el número de frames de estabilidad desde la jugada anterior:

            frame_rotate = cv2.rotate(frame_curr_warped, cv2.ROTATE_180)    # Se aplica una rotación de 180 grados al frame recortad
            key_frames.append(frame_rotate)                                 # Se añade el frame rotado a la lista con los frames claves
            blur_ref = blur_curr.copy()                                     # El frame actual pasa a ser el de referencia
            motion_detected = False                                         # Se cambia la variable de movimiento detectado a falso
            frames_since_motion = 0                                         # Se reestablece la cuenta de frames desde un movimiento

            cv2.imshow(f"DEBUG: Diferencia de Frames Normal", cv2.rotate(frame_curr_warped, cv2.ROTATE_180))
            cv2.waitKey(0)
            print(f"DEBUG: Frame Guardado!")

        print("/////////////////////////////////")

    video.release()                                                         # Cierra del video
    return key_frames                                                       # Devuelve la lista con todos los frames claves