"""
run_test_suite.py — Arnés de pruebas batch para el TFG.

Ejecuta el MISMO pipeline de visión que usa la aplicación (clasificador
EfficientNet-B0 en ONNX) sobre un lote de vídeos, comparando cada
reconstrucción con un PGN de referencia (ground-truth), sin pasar por la
app (ni upload, ni WebSocket, ni autenticación).

Lo único manual es marcar las 4 esquinas de cada vídeo una sola vez: el
script abre una ventana, clicas a1 -> a8 -> h8 -> h1, te muestra el
tablero rectificado con la rejilla 8x8 para que confirmes el encuadre, y
guarda la calibración en disco. En ejecuciones posteriores reutiliza esa
calibración (no vuelve a preguntar).

────────────────────────────────────────────────────────────────────────
CONVENCIÓN DE NOMBRES (carpeta test_final)

  video<X>_<vista>.mp4       vídeo de prueba (X = número de partida)
  video<X>.pgn               PGN ground-truth de la partida (mismas
                             jugadas para todas las vistas de esa partida)

  Ejemplos:
    video1.pgn
    video1_cenital.mp4
    video1_20.mp4
    video1_45.mp4
    video1_70.mp4
    video2.pgn
    video2_cenital.mp4
    ...

El prefijo antes del primer '_' identifica la partida (video1, video2,
...) y selecciona el PGN correspondiente (video1.pgn, ...).
La calibración se guarda como  <video>.calib.json  junto al vídeo.

────────────────────────────────────────────────────────────────────────
USO

  cd chessapp-back
  .\.venv\Scripts\Activate.ps1
  python run_test_suite.py --dir test_final

  # Recalibrar un vídeo (ignora el .calib.json existente):
  python run_test_suite.py --dir test_final --recalibrate video1_45.mp4

  # Solo una partida:
  python run_test_suite.py --dir test_final --only video1

Salida: tabla por consola + results.csv en la carpeta --dir.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
import tkinter as tk
from pathlib import Path

import cv2
from PIL import Image, ImageTk

# El paquete del pipeline vive en chessapp-back/src/games/chess_tracker.
# Lo añadimos al path para importarlo sin arrancar Django.
_SRC = Path(__file__).resolve().parent / "src"
sys.path.insert(0, str(_SRC))

# NOTA: NO se importa `calibrate_interactive` de board_detector porque usa
# el GUI de OpenCV (cv2.namedWindow/imshow), no disponible en la build
# `opencv-python-headless` del backend. La calibración se hace aquí con
# tkinter + PIL. `warp_board` y `draw_grid` sí se reutilizan: solo dibujan
# sobre arrays (no usan HighGUI) y funcionan en headless.
from games.chess_tracker.board_detector import (  # noqa: E402
    BoardCalibration, draw_grid, warp_board,
    load_calibration, save_calibration,
)
from games.chess_tracker.pipeline import (  # noqa: E402
    process_video, compare_with_ground_truth,
)
from games.chess_tracker.square_classifier.infer import (  # noqa: E402
    SquareClassifierInference,
)

# Mismo modelo y mismos parámetros que usa la app (effnet_adapter.py).
_MODEL_PATH = Path(__file__).resolve().parent / "media" / "models" / "chess_effnet.onnx"
_STABLE_FRAME_KWARGS = {"anomaly_min_changed": 10}


def _first_frame(video_path: Path):
    """Primer fotograma del vídeo (BGR) o None si no se puede leer."""
    cap = cv2.VideoCapture(str(video_path))
    try:
        ok, frame = cap.read()
        return frame if ok else None
    finally:
        cap.release()


_CORNER_LABELS = ("a1", "a8", "h8", "h1")


def _fit_scale(w: int, h: int, max_w: int = 1200, max_h: int = 760) -> float:
    """Factor de escala para que la imagen quepa en pantalla (<= 1.0)."""
    return min(max_w / w, max_h / h, 1.0)


def _pick_corners_tk(frame_bgr, title: str) -> list[tuple[float, float]]:
    """Ventana tkinter: el usuario clica a1, a8, h8, h1 sobre el frame.

    Devuelve las 4 coordenadas en píxeles de la imagen ORIGINAL (se
    corrige la escala de visualización). Lanza RuntimeError si se cierra
    la ventana sin completar las 4 esquinas.
    """
    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    s = _fit_scale(w, h)
    disp = Image.fromarray(rgb).resize((int(w * s), int(h * s)))

    root = tk.Tk()
    root.title(title)
    state = {"pts": [], "cancel": False}

    info = tk.Label(root, font=("Arial", 13), pady=6,
                    text="Clic esquina 1/4: a1   (a1 → a8 → h8 → h1)")
    info.pack()
    canvas = tk.Canvas(root, width=disp.width, height=disp.height,
                       highlightthickness=0)
    canvas.pack()
    photo = ImageTk.PhotoImage(disp)
    canvas.create_image(0, 0, anchor="nw", image=photo)
    canvas._photo_ref = photo  # evita que el GC libere la imagen

    def on_click(e):
        pts = state["pts"]
        if len(pts) >= 4:
            return
        pts.append((e.x / s, e.y / s))   # -> coords imagen original
        i = len(pts) - 1
        canvas.create_oval(e.x - 5, e.y - 5, e.x + 5, e.y + 5,
                           fill="#00ff00", outline="black")
        canvas.create_text(e.x + 12, e.y - 10, text=_CORNER_LABELS[i],
                           fill="#00ff00", font=("Arial", 12, "bold"))
        if len(pts) < 4:
            info.config(text=f"Clic esquina {len(pts) + 1}/4: "
                             f"{_CORNER_LABELS[len(pts)]}")
        else:
            info.config(text="4 esquinas marcadas — continuando...")
            root.after(350, root.destroy)

    def on_close():
        state["cancel"] = True
        root.destroy()

    canvas.bind("<Button-1>", on_click)
    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()

    if state["cancel"] or len(state["pts"]) != 4:
        raise RuntimeError("Calibración cancelada por el usuario")
    return state["pts"]


def _confirm_preview_tk(preview_bgr, title: str) -> bool:
    """Muestra el tablero rectificado + rejilla. Devuelve True si el
    usuario pulsa 'Aceptar', False si pulsa 'Rehacer' o cierra."""
    rgb = cv2.cvtColor(preview_bgr, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    s = _fit_scale(w, h, max_w=720, max_h=720)
    disp = Image.fromarray(rgb).resize((int(w * s), int(h * s)))

    root = tk.Tk()
    root.title(title)
    res = {"ok": False}

    tk.Label(root, font=("Arial", 13), pady=6,
             text="¿La rejilla coincide con las casillas?").pack()
    photo = ImageTk.PhotoImage(disp)
    img_lbl = tk.Label(root, image=photo)
    img_lbl._photo_ref = photo
    img_lbl.pack()
    bar = tk.Frame(root)
    bar.pack(pady=8)

    def accept():
        res["ok"] = True
        root.destroy()

    def redo():
        res["ok"] = False
        root.destroy()

    tk.Button(bar, text="Aceptar", width=16, command=accept).pack(side="left", padx=10)
    tk.Button(bar, text="Rehacer", width=16, command=redo).pack(side="left", padx=10)
    root.protocol("WM_DELETE_WINDOW", redo)
    root.mainloop()
    return res["ok"]


def _ensure_calibration(video_path: Path, recalibrate: bool) -> BoardCalibration:
    """Devuelve la calibración del vídeo, pidiéndola por clicks si hace falta.

    Tras marcar las esquinas muestra el tablero rectificado con rejilla
    para confirmar el encuadre. Calibración por tkinter+PIL (el GUI de
    OpenCV no está disponible en la build headless del backend).
    """
    calib_path = video_path.with_suffix(video_path.suffix + ".calib.json")
    if calib_path.exists() and not recalibrate:
        return load_calibration(calib_path)

    frame = _first_frame(video_path)
    if frame is None:
        raise RuntimeError(f"No se pudo leer el primer frame de {video_path.name}")

    while True:
        pts = _pick_corners_tk(frame, f"Calibrar: {video_path.name}")
        calib = BoardCalibration(a1=pts[0], a8=pts[1], h8=pts[2], h1=pts[3])
        preview = draw_grid(warp_board(frame, calib))
        if _confirm_preview_tk(preview, f"Confirmar encuadre: {video_path.name}"):
            break
        # 'Rehacer' o ventana cerrada -> repetir calibración

    save_calibration(calib, calib_path)
    print(f"  calibración guardada en {calib_path.name}")
    return calib


def _verdict(correct: int, total: int) -> str:
    if total > 0 and correct == total:
        return "SUPERADA"
    if correct > 0:
        return "PARCIAL"
    return "FALLIDA"


def main() -> None:
    ap = argparse.ArgumentParser(description="Arnés de pruebas batch ChessVision")
    ap.add_argument("--dir", required=True, help="Carpeta con vídeos y PGNs")
    ap.add_argument("--only", default=None,
                    help="Procesar solo vídeos cuyo nombre EMPIECE por este "
                         "prefijo (p. ej. --only video1)")
    ap.add_argument("--match", default=None,
                    help="Procesar solo vídeos cuyo nombre CONTENGA esta "
                         "subcadena (p. ej. --match _70 para todos los de 70°)")
    ap.add_argument("--recalibrate", default=None,
                    help="Forzar recalibración de este fichero de vídeo concreto")
    args = ap.parse_args()

    base = Path(args.dir)
    if not base.is_dir():
        sys.exit(f"No existe la carpeta {base}")
    if not _MODEL_PATH.exists():
        sys.exit(f"No se encuentra el modelo ONNX en {_MODEL_PATH}")

    videos = sorted(
        p for p in base.glob("*.mp4")
        if (args.only is None or p.stem.startswith(args.only))
        and (args.match is None or args.match in p.stem)
    )
    if not videos:
        sys.exit("No hay vídeos .mp4 que procesar.")

    print(f"Cargando clasificador ONNX: {_MODEL_PATH.name}")
    clf = SquareClassifierInference.load(str(_MODEL_PATH))

    rows = []
    for video_path in videos:
        game = video_path.stem.split("_")[0]
        pgn_path = base / f"{game}.pgn"
        print(f"\n=== {video_path.name}  (juego {game}) ===")
        if not pgn_path.exists():
            print(f"  [SKIP] Falta el PGN ground-truth: {pgn_path.name}")
            continue

        try:
            recal = (args.recalibrate is not None
                     and video_path.name == args.recalibrate)
            calib = _ensure_calibration(video_path, recalibrate=recal)
        except RuntimeError as e:
            print(f"  [SKIP] {e}")
            continue

        print("  procesando vídeo...")
        result = process_video(
            str(video_path), calib, clf,
            stable_frame_kwargs=_STABLE_FRAME_KWARGS,
        )
        cmp = compare_with_ground_truth(result.moves, pgn_path)

        total = cmp["truth_plies"]
        correct = cmp["correct"]
        first_mismatch = cmp["first_mismatch"]
        # "Aciertos hasta el primer fallo" = longitud de la racha inicial
        # correcta. `first_mismatch` es None tanto si la reconstrucción fue
        # perfecta como si no hubo nada que comparar (0 jugadas
        # reconstruidas). Para distinguirlos se usa `match_until`
        # (= min(plies_verdad, plies_reconstruidos)): si no hubo fallo, la
        # racha correcta es justo ese prefijo comparado; si se
        # reconstruyeron 0 jugadas, match_until = 0 y el resultado es 0.
        until_first_fail = (
            cmp["match_until"] if first_mismatch is None else first_mismatch
        )
        verdict = _verdict(correct, total)

        print(f"  reconstruidos: {cmp['reconstructed_plies']}  "
              f"correctos: {correct}/{total}  "
              f"hasta 1.er fallo: {until_first_fail}  -> {verdict}")
        print(f"  stats pipeline: {result.stats()}")

        rows.append({
            "video": video_path.name,
            "juego": game,
            "aciertos_hasta_primer_fallo": until_first_fail,
            "total_aciertos": correct,
            "plies_referencia": total,
            "plies_reconstruidos": cmp["reconstructed_plies"],
            "primer_fallo": "" if first_mismatch is None else first_mismatch,
            "veredicto": verdict,
        })

    if not rows:
        print("\nNo se generó ningún resultado.")
        return

    # Tabla por consola
    print("\n" + "=" * 78)
    print(f"{'Vídeo':<28}{'Hasta 1.er fallo':>18}{'Total aciertos':>16}{'Veredicto':>14}")
    print("-" * 78)
    for r in rows:
        print(f"{r['video']:<28}{r['aciertos_hasta_primer_fallo']:>18}"
              f"{r['total_aciertos']:>16}{r['veredicto']:>14}")
    print("=" * 78)

    # CSV para volcar a las tablas LaTeX de la memoria
    csv_path = base / "results.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\nCSV escrito en {csv_path}")


if __name__ == "__main__":
    main()
