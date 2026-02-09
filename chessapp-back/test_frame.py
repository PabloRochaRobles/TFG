from operator import truediv

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
from src.games.services import extract_key_frames, save_key_frames, load_key_frames, show_key_frames, delete_key_frames, \
    analysis_best_posObsidian, analysis_best_posPlentyChess
from src.games.services import get_corners
from src.games.services import get_matriz
from src.games.services import analysis_best_pos, analysis_best_posStockfish, analysis_best_posObsidian, make_move

def visualize_key_frames(video_path):

    fen = "3r2k1/7p/6pB/5p2/p6P/NbRP1P2/6PK/8 b - - 4 33"

    ini = analysis_best_posStockfish(fen)
    print(ini["movement_uci"])

    for i in range (1,11):
        ini = analysis_best_posStockfish(ini["new_fen"])
        print(ini["movement_uci"])

    #print(make_move(fen, "g1h2"))

    '''
    res = analysis_best_posStockfish("2r3k1/1b5p/5RpB/1N3p2/p7/3P3P/5PP1/6K1 w - - 0 28")

    print(f"---- Analysis Best Pos Stockfish ----")
    score = res["puntuacion"]
    score_str = f"{score:.2f}" if isinstance(score, float) else str(score)
    print(f"Evaluacion: {score_str}")

    print("---- Secuencia Sugerida ----")
    for i, jugada in enumerate(res["secuencia"], 1):
        print(f" Paso [{i}]: {jugada}")

    res2 = analysis_best_posObsidian("2r3k1/1b5p/5RpB/1N3p2/p7/3P3P/5PP1/6K1 w - - 0 28")

    print(f"---- Analysis Best Pos Obsidian ----")
    score2 = res2["puntuacion"]
    score2_str = f"{score2:.2f}" if isinstance(score2, float) else str(score2)
    print(f"Evaluacion: {score2_str}")

    print("---- Secuencia Sugerida ----")
    for j, jugada2 in enumerate(res2["secuencia"], 1):
        print(f" Paso [{j}]: {jugada2}")

    mejores_movimientos = analysis_best_posPlentyChess("2r3k1/1b5p/5RpB/1N3p2/p7/3P3P/5PP1/6K1 w - - 0 28")

    print("\n=== MEJORES MOVIMIENTOS PARA BLANCAS ===")
    for i, (mov, eval) in enumerate(mejores_movimientos, 1):
        print(f"{i}. {mov} (Evaluación: {eval / 100:.2f})")

    # delete_key_frames("test2.npz")

    #path_frames = os.path.join('media/temp_frames', "test5.npz")

    #if os.path.exists(path_frames):
    #    key_frames = load_key_frames("test5.npz")
    #    show_key_frames(key_frames)
    #else:
    #    coords = get_corners(video_path)
    #    key_frames = extract_key_frames(video_path, coords)
    #    save_key_frames(key_frames, "test5")
    #    show_key_frames(key_frames)
    '''


if __name__ == '__main__':
    # RUTA: Asegúrate de que esta ruta apunte a un video de prueba válido en tu PC
    RUTA_VIDEO_PRUEBA = "C:/Users/Admin/Videos/Ajedrez/test5.mp4"

    # Ejecutar la prueba
    visualize_key_frames(RUTA_VIDEO_PRUEBA)