import os
import cv2
import chess
import chess.engine
import numpy as np
from django.conf import settings
from rest_framework.response import Response
from rest_framework import status

TEMP_VIDEOS_LOCATION = os.path.join(settings.MEDIA_ROOT, 'temp_videos')
TEMP_FRAMES_LOCATION = os.path.join(settings.MEDIA_ROOT, 'temp_frames')

NORMALIZED_SIZE = 1000
PUNTOS_ORIGEN = []
MAX_PUNTOS = 4
VENTANA_NOMBRE = 'Selecciona las 4 Esquinas del Tablero'

# Función de borrado de los videos obtenidos del FrontEnd y almacenados.
def delete_temporary_videos(file_name):
    file_path = os.path.join(TEMP_VIDEOS_LOCATION, file_name)                   # Almacena en la variable la ruta hasta el archivo que se quiere borrar                                            # Si la ruta hasta el video existe
    try:
        if os.path.exists(file_path):                                           # Si el archivo existe:
            os.remove(file_path)                                                    # Se elimina el video especificado por la ruta
            print(f"El video {file_name} ha sido eliminado")                        # Se notifica que el video ha sido eliminado
            return True                                                             # Devuelve verdadero

        else:                                                                   # Si no existe:
            return Response({"error: No se ha encontrado el video"},
                            status=status.HTTP_400_BAD_REQUEST)                     # Se notifica del fallo y devuelve 400 BAD REQUEST

    except Exception as e:                                                      # Si algo falla, salta la excepción
        return Response({'error': f"Fallo interno en el procesamiento: {str(e)}"},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)                   # Se notifica del fallo y devuelve 500 INTERNAL SERVER ERROR


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
def extract_key_frames(video_path, coords):

    # Variables de la función
    key_frames = []                                                         # Lista de los frames claves
    frames_since_motion = 0                                                 # Contador de frames que han pasado sin que haya movimiento
    motion_detected = False                                                 # Detector de movimiento
    area_threshold_start = 150000                                           # Valor minimo que debe superarse para considerar que se está realizando un movimiento
    area_threshold_end = 25000                                              # Valor máximo en el que se considera que hay estabilidad en la imagen
    stability_frames = 10                                                   # Umbral que debe superarse para considerar que el tablero ya ha estado en estabilidad y la jugada anterior terminó

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

            #cv2.imshow(f"DEBUG: Diferencia de Frames Normal", cv2.rotate(frame_curr_warped, cv2.ROTATE_180))
            #cv2.waitKey(0)
            print(f"DEBUG: Frame Guardado!")

        print("/////////////////////////////////")

    video.release()                                                         # Cierra del video
    return key_frames                                                       # Devuelve la lista con todos los frames claves

def analysis_best_pos(fen):
    path_engine = "C:/Users/Admin/Videos/Ajedrez/stockfish/stockfish-windows-x86-64-avx2.exe"

    with chess.engine.SimpleEngine.popen_uci(path_engine) as engine:

        board = chess.Board(fen)

        analysis = engine.analyse(board, chess.engine.Limit(time=1), multipv=3)

        top_moves = []

        for entry in analysis:
            move = entry["pv"][0]
            score = entry["score"].relative.score(mate_score=10000)

            top_moves.append({"move_san": board.san(move),
                              "move_uci": move.uci(),
                              "score": score / 100.0 if score is not None else "Mate"})

        return top_moves

def analysis_best_posStockfish(fen):
    path_engine = "C:/Users/Admin/Videos/Ajedrez/stockfish/stockfish-windows-x86-64-avx2.exe"

    with chess.engine.SimpleEngine.popen_uci(path_engine) as engine:

        board = chess.Board(fen)

        info = engine.analyse(board, chess.engine.Limit(time=1))

        pv_moves = info["pv"]
        linea_seg = []
        temp_board = board.copy()
        depth = 10

        for i, move in enumerate(pv_moves[:depth]):
            san_move = temp_board.san(move)
            linea_seg.append({"move_san": san_move,})
            temp_board.push(move)

        return {
            "puntuacion": info["score"].relative.score(mate_score=10000) / 100.0,
            "secuencia": linea_seg
        }

def analysis_best_posObsidian(fen):
    path_engine = "C:/Users/Admin/Videos/Ajedrez/Obsidian160-avx2-pext.exe"

    with chess.engine.SimpleEngine.popen_uci(path_engine) as engine:

        board = chess.Board(fen)

        info = engine.analyse(board, chess.engine.Limit(time=1))

        return {
            "puntuacion": info["score"].relative.score(mate_score=10000) / 100.0,
            "secuencia": [board.san(m) for m in info["pv"][:10]],
        }