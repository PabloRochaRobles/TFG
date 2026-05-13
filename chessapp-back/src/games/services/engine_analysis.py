"""
Análisis de posiciones con motores UCI (Stockfish, Obsidian, PlentyChess).

Este módulo es independiente del pipeline de visión: sólo necesita un FEN,
los binarios UCI bajo `ENGINES_DIR` y un disco para cachear resultados en
`ENGINE_ANALYSIS_LOCATION`.

Funciones públicas:
  - save_engine_analysis / load_engine_analysis / delete_engine_analysis:
        Persistencia en disco de resultados ya calculados.
  - analysis_best_posStockfish / analysis_best_posObsidian /
    analysis_best_posPlentyChess:
        Mejor jugada de un motor concreto sobre un FEN.
  - analysis_engines_parallel:
        Ejecuta los 3 motores en paralelo (3× más rápido que en serie).
  - consensus_analysis:
        Movimiento elegido por mayoría entre los 3 motores; fallback a
        Stockfish si no hay consenso.
"""

import json
import os
import sys
from collections import Counter

# Daphne/Twisted establece SelectorEventLoopPolicy en Windows, que no soporta
# subprocess_exec. Forzamos ProactorEventLoop para que los engines UCI puedan
# lanzar subprocesos — duplicado defensivamente del __init__.py para soportar
# imports directos de este módulo.
if sys.platform == 'win32':
    import asyncio as _asyncio
    _asyncio.set_event_loop_policy(_asyncio.WindowsProactorEventLoopPolicy())

import chess
import chess.engine

from .config import ENGINES_DIR, ENGINE_ANALYSIS_LOCATION


# Detección de plataforma para los binarios UCI:
#   - Local (Windows): los .exe que ya teníamos en misc/engines/
#   - Producción (Linux/Render): binarios sin extensión, con nombres simples
#     (los pone el Dockerfile en ENGINES_DIR como `stockfish`, `obsidian`,
#     `plentychess`).
if sys.platform == 'win32':
    _STOCKFISH_BIN   = 'stockfish-windows-x86-64-avx2.exe'
    _OBSIDIAN_BIN    = 'Obsidian160-avx2-pext.exe'
    _PLENTYCHESS_BIN = 'PlentyChess-7.0.0-windows-avx2.exe'
else:
    _STOCKFISH_BIN   = 'stockfish'
    _OBSIDIAN_BIN    = 'obsidian'
    _PLENTYCHESS_BIN = 'plentychess'


# -----------------------------------------------------------------------------
# Caché en disco del análisis completo
# -----------------------------------------------------------------------------

def save_engine_analysis(analysis_id, results):
    """Guarda los resultados del análisis de motores en ENGINE_ANALYSIS_LOCATION/<analysis_id>.json."""
    os.makedirs(ENGINE_ANALYSIS_LOCATION, exist_ok=True)
    path = os.path.join(ENGINE_ANALYSIS_LOCATION, f"{analysis_id}.json")
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({'results': results}, f)
        print(f"[ENGINE] Análisis guardado: {path}")
        return True
    except Exception as e:
        print(f"[ENGINE] Error al guardar análisis: {e}")
        return False


def load_engine_analysis(analysis_id):
    """Carga el análisis de motores guardado. Devuelve la lista de resultados o None."""
    path = os.path.join(ENGINE_ANALYSIS_LOCATION, f"{analysis_id}.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get('results')
    except Exception as e:
        print(f"[ENGINE] Error al cargar análisis: {e}")
        return None


def delete_engine_analysis(analysis_id):
    """Elimina el análisis de motores asociado. Devuelve True si se borró."""
    path = os.path.join(ENGINE_ANALYSIS_LOCATION, f"{analysis_id}.json")
    if os.path.exists(path):
        try:
            os.remove(path)
            print(f"[DELETE] Engine analysis {analysis_id}.json eliminado.")
            return True
        except Exception as e:
            print(f"[DELETE] Error al eliminar engine analysis: {e}")
    return False


# -----------------------------------------------------------------------------
# Motores individuales
# -----------------------------------------------------------------------------

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
    path_engine = os.path.join(ENGINES_DIR, _STOCKFISH_BIN)

    with chess.engine.SimpleEngine.popen_uci(path_engine) as engine:
        board = chess.Board(fen)
        info = engine.analyse(board, chess.engine.Limit(time=0.1))

        pv = info.get("pv") or []
        if not pv:
            raise ValueError(f"Stockfish no encontró jugadas para la posición: {fen}")
        best_move = pv[0]

        return {
            "movement_uci": best_move.uci(),
            "movement_san": board.san(best_move) if not board.move_stack else chess.Board(fen).san(best_move),
            "new_fen": board.fen(),
            "score": info["score"].white().score(mate_score=10000) / 100
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
    path_engine = os.path.join(ENGINES_DIR, _OBSIDIAN_BIN)

    with chess.engine.SimpleEngine.popen_uci(path_engine) as engine:
        board = chess.Board(fen)
        info = engine.analyse(board, chess.engine.Limit(time=0.1))

        pv = info.get("pv") or []
        if not pv:
            raise ValueError(f"Obsidian no encontró jugadas para la posición: {fen}")
        best_move = pv[0]

        return {
            "movement_uci": best_move.uci(),
            "movement_san": board.san(best_move) if not board.move_stack else chess.Board(fen).san(best_move),
            "new_fen": board.fen(),
            "score": info["score"].white().score(mate_score=10000) / 100
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
    path_engine = os.path.join(ENGINES_DIR, _PLENTYCHESS_BIN)

    with chess.engine.SimpleEngine.popen_uci(path_engine) as engine:
        board = chess.Board(fen)
        info = engine.analyse(board, chess.engine.Limit(time=0.1))

        pv = info.get("pv") or []
        if not pv:
            raise ValueError(f"PlentyChess no encontró jugadas para la posición: {fen}")
        best_move = pv[0]

        return {
            "movement_uci": best_move.uci(),
            "movement_san": board.san(best_move) if not board.move_stack else chess.Board(fen).san(best_move),
            "new_fen": board.fen(),
            "score": info["score"].white().score(mate_score=10000) / 100
        }


# -----------------------------------------------------------------------------
# Orquestación: 3 motores en paralelo + consenso
# -----------------------------------------------------------------------------

def analysis_engines_parallel(fen: str) -> tuple:
    """
    Ejecuta los 3 motores de ajedrez UNO TRAS OTRO.

    Originalmente esta función arrancaba los 3 motores en paralelo con un
    ThreadPoolExecutor para que el análisis fuera ~3× más rápido (~0.1 s
    en lugar de ~0.3 s por posición). En Render Free Tier (512 MB) ese
    pico simultáneo de memoria (cada motor spawnea su proceso UCI + carga
    NNUE: ~80-100 MB extra por motor → ~250-300 MB de pico) basta para
    desbordar el límite y provocar OOM + reinicio del contenedor con un
    TimeoutError al inicializar UCI.

    La versión secuencial nunca tiene más de un motor en memoria a la vez,
    pagando ~3× el tiempo total pero garantizando que cabe en 512 MB. El
    nombre `_parallel` se conserva por compatibilidad con los importadores
    en views.py; se considera un cambio internamente trivial.

    Devuelve: (resultado_stockfish, resultado_obsidian, resultado_plentychess)
    """
    from .memory_probe import mem_log
    mem_log("  engines.before_stockfish")
    stock    = analysis_best_posStockfish(fen)
    mem_log("  engines.after_stockfish")
    obsidian = analysis_best_posObsidian(fen)
    mem_log("  engines.after_obsidian")
    plenty   = analysis_best_posPlentyChess(fen)
    mem_log("  engines.after_plentychess")
    return stock, obsidian, plenty


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
