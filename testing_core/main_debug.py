import os
import sys
from types import ModuleType


# ==============================================================================
# 1. MOCK DE DJANGO Y REST_FRAMEWORK
# (Hacemos creer a services.py que está dentro de Django para no tener que modificarlo)
# ==============================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

class MockSettings:
    BASE_DIR = BASE_DIR
    MEDIA_ROOT = MEDIA_ROOT
    CHESS_YOLO_MODEL_PATH = os.path.join(MEDIA_ROOT, 'models', 'chess_yolo.pt')

# Engañamos a los imports de django
mock_django_conf = ModuleType('django.conf')
mock_django_conf.settings = MockSettings()
sys.modules['django'] = ModuleType('django')
sys.modules['django.conf'] = mock_django_conf

# Engañamos a los imports de rest_framework
mock_rf = ModuleType('rest_framework')
mock_rf_response = ModuleType('rest_framework.response')
mock_rf_status = ModuleType('rest_framework.status')
mock_rf_response.Response = lambda *args, **kwargs: None
mock_rf_status.HTTP_500_INTERNAL_SERVER_ERROR = 500
mock_rf_status.HTTP_404_NOT_FOUND = 404
mock_rf_status.HTTP_400_BAD_REQUEST = 400
sys.modules['rest_framework'] = mock_rf
sys.modules['rest_framework.response'] = mock_rf_response
sys.modules['rest_framework.status'] = mock_rf_status

# ==============================================================================
# 2. IMPORTAR TUS SERVICIOS (Ahora funcionarán sin crashear)
# ==============================================================================
import datetime


class Tee:
    """Clase para duplicar la salida a la consola y a un fichero de log."""
    def __init__(self, *files):
        self.files = files
    def write(self, obj):
        for f in self.files:
            f.write(obj)
            f.flush()
    def flush(self):
        for f in self.files:
            f.flush()
import cv2
import numpy as np
from services import (
    get_first_frame, 
    auto_detect_board_corners, 
    extract_key_frames, 
    frames_to_fens_yolo,
    get_initial_board_frame,
    save_corners_config
)

# ==============================================================================
# 3. LÓGICA DE EJECUCIÓN DEL TEST
# ==============================================================================
def main():
    video_path = os.path.join(BASE_DIR, 'videos', 'test3.mp4') # CAMBIA EL NOMBRE AQUÍ
    
    if not os.path.exists(video_path):
        print(f"ERROR: No se encuentra el vídeo en {video_path}")
        return

    print(f"--- Iniciando Análisis de Debug para {os.path.basename(video_path)} ---")

    # 1. Obtener primer frame y esquinas
    first_frame = get_first_frame(video_path)
    
    # Preguntar si se desea calibrar manualmente simulando la App
    ans = input("¿Deseas calibrar las esquinas manualmente antes de empezar? (s/n): ").strip().lower()
    if ans == 's':
        points = []
        def mouse_callback(event, x, y, flags, param):
            if event == cv2.EVENT_LBUTTONDOWN:
                if len(points) < 4:
                    points.append((x, y))
                    cv2.circle(clone, (x, y), 5, (0, 255, 0), -1)
                    labels = ['a1', 'a8', 'h8', 'h1']
                    cv2.putText(clone, labels[len(points)-1], (x+10, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                    cv2.imshow("Calibracion", clone)

        clone = first_frame.copy()
        cv2.putText(clone, "Click en a1, a8, h8, h1. Presiona 'c' para confirmar o 'r' para reiniciar.", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
        cv2.imshow("Calibracion", clone)
        cv2.setMouseCallback("Calibracion", mouse_callback)

        print("Ventana de calibración abierta. Haz click en las 4 esquinas y presiona 'c'.")
        while True:
            key = cv2.waitKey(1) & 0xFF
            if key == ord('c') and len(points) == 4:
                break
            elif key == ord('r'):
                points.clear()
                clone = first_frame.copy()
                cv2.putText(clone, "Click en a1, a8, h8, h1. Presiona 'c' para confirmar o 'r' para reiniciar.", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
                cv2.imshow("Calibracion", clone)
        cv2.destroyWindow("Calibracion")

        h, w = first_frame.shape[:2]
        corners_rel = [[x/w, y/h] for x, y in points]
        save_corners_config(corners_rel)

    corners = auto_detect_board_corners(first_frame)
    print(f"Esquinas detectadas: {corners.tolist() if corners is not None else 'Ninguna'}")

    initial_frame = get_initial_board_frame(video_path, corners)

    # 2. Extraer key frames
    print("\n--- Fase 1: Extrayendo Keyframes ---")
    result = extract_key_frames(video_path, corners)
    key_frames, key_frames_orig, detected_states, mat, accepted_moves = result
    print(f"Total keyframes extraídos: {len(key_frames)}")

    # 3. Generar FENs con YOLO
    print("\n--- Fase 2: Generando FENs ---")
    all_frames = ([initial_frame] + key_frames) if initial_frame is not None else key_frames
    all_original_frames = ([None] + key_frames_orig) if key_frames_orig else None

    fens = frames_to_fens_yolo(
        all_frames=all_frames,
        original_frames=all_original_frames,
        M=mat,
        detected_states=detected_states,
        accepted_moves=accepted_moves
    )

    print("\n--- COMPARATIVA DE MOVIMIENTOS (GROUND TRUTH VS DETECTADO) ---")
    print(f"{'#':<4} | {'Real (Ground Truth)':<20} | {'Detectado (Sistema)':<20} | {'Estado':<15}")
    print("-" * 75)

    # Lista de movimientos reales proporcionada para test3.mp4
    GROUND_TRUTH = [
        "d2d4", "g8f6", "c2c4", "e7e6", "g1f3", "b7b6", "g2g3", "c8b7",
        "f8b2", "c1d2", "c7c5", "d2b4", "c5b4", "e1g1", "a7a5", "a2a3",
        "b8a6", "a3b4", "a6b4", "b1c3", "e8g8", "d1d2", "a8c8", "b2b3",
        "f6e4", "c3e4", "b7e4", "f3e5", "e4g2", "g1g2", "d7d6", "e5d3",
        "b4d3", "d2d3", "d6d5", "f1c1", "d8d6", "d3c3", "c8c6", "c4c5",
        "d6b8", "c3d2", "h7h6", "c5b6"
    ]

    failed = False
    max_len = max(len(fens) - 1, len(GROUND_TRUTH))
    
    for i in range(1, max_len + 1):
        real_move = GROUND_TRUTH[i - 1] if i - 1 < len(GROUND_TRUTH) else "---"
        
        detected_move = "---"
        if i <= len(accepted_moves) and accepted_moves[i - 1]:
            detected_move = accepted_moves[i - 1].uci()
            
        status = ""
        if real_move == detected_move and not failed:
            status = "✅ OK"
        elif real_move == detected_move and failed:
            status = "⚠️ Coincidencia (Tablero corrupto)"
        elif real_move != detected_move:
            status = "❌ FALLO / DESVÍO"
            failed = True
            
        print(f"{i:02d}   | {real_move:<20} | {detected_move:<20} | {status}")
        
    print("-" * 75)
    if failed:
        print("\n⚠️ NOTA: El 'Efecto Dominó' comenzó en la primera ❌.")
        print("A partir de ese punto, el tablero virtual se desincroniza del tablero físico,")
        print("causando que los siguientes movimientos sean catalogados como ilegales.")

if __name__ == "__main__":
    # Crea los directorios necesarios para que no falle al guardar logs o imágenes de debug
    debug_dir = os.path.join(MEDIA_ROOT, 'debug')
    logs_dir = os.path.join(debug_dir, 'logs')
    os.makedirs(logs_dir, exist_ok=True)

    # Configura el archivo de log con fecha y hora para no sobreescribir
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filepath = os.path.join(logs_dir, f'log_{timestamp}.txt')

    # Guarda las salidas originales
    original_stdout = sys.stdout
    original_stderr = sys.stderr

    # Abre el archivo de log y crea el duplicador de salida
    with open(log_filepath, 'w', encoding='utf-8') as logfile:
        tee = Tee(original_stdout, logfile)
        sys.stdout = tee
        sys.stderr = tee

        # Configurar el logger de services para que escriba a sys.stdout (=Tee),
        # capturando así TODOS los mensajes en consola y en el fichero de log.
        import logging as _logging
        _fmt = _logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        _handler = _logging.StreamHandler(sys.stdout)   # sys.stdout es ya el Tee
        _handler.setLevel(_logging.DEBUG)
        _handler.setFormatter(_fmt)
        _svc_logger = _logging.getLogger('services')
        _svc_logger.handlers.clear()
        _svc_logger.addHandler(_handler)
        _svc_logger.setLevel(_logging.DEBUG)
        _svc_logger.propagate = False

        try:
            main()
        except Exception as e:
            print(f"\n\n--- ERROR INESPERADO ---\n")
            import traceback
            traceback.print_exc()
        finally:
            # Restaura las salidas originales
            sys.stdout = original_stdout
            sys.stderr = original_stderr
            print(f"\nAnálisis completado. El log se ha guardado en: {log_filepath}")