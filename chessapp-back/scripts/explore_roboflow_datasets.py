"""
explore_roboflow_datasets.py
════════════════════════════
Lista los datasets de piezas de ajedrez más populares en Roboflow Universe
y te permite seleccionar cuál usar para entrenar.

Ejecuta este script ANTES de train_chess_yolo.py si no sabes qué
workspace/project/version usar.

USO:
  python scripts/explore_roboflow_datasets.py

Necesitas una cuenta gratuita en https://roboflow.com para obtener la API key.
"""

import os
import sys
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Datasets públicos conocidos de piezas de ajedrez en Roboflow Universe
# (actualizados a abril 2025 — puedes añadir más o usar la búsqueda automática)
# ─────────────────────────────────────────────────────────────────────────────
KNOWN_DATASETS = [
    {
        "nombre":      "Chess Pieces (chess-annotator)",
        "workspace":   "chess-annotator",
        "project":     "chess-pieces-tnick",
        "version":     1,
        "imagenes":    "~3 000",
        "clases":      "white-king, white-queen, white-rook, white-bishop, white-knight, white-pawn, "
                       "black-king, black-queen, black-rook, black-bishop, black-knight, black-pawn",
        "descripcion": "Dataset equilibrado con piezas de ajedrez sobre tablero real.",
    },
    {
        "nombre":      "Chess Pieces Detection (roboflow public)",
        "workspace":   "chess-pieces-new",
        "project":     "chess-pieces-2",
        "version":     5,
        "imagenes":    "~2 500",
        "clases":      "Bishop, King, Knight, Pawn, Queen, Rook (sin color)",
        "descripcion": "Dataset sin distinción de color — necesita CHESS_YOLO_CLASS_MAP personalizado.",
    },
    {
        "nombre":      "Chess Piece Detection (griezmannnn)",
        "workspace":   "griezmannnn",
        "project":     "chess-piece-detection",
        "version":     2,
        "imagenes":    "~1 800",
        "clases":      "black_bishop, black_king, black_knight, black_pawn, black_queen, black_rook, "
                       "white_bishop, white_king, white_knight, white_pawn, white_queen, white_rook",
        "descripcion": "Nombres con guión bajo — funcionan con el CLASS_MAP si se añaden variantes.",
    },
    {
        "nombre":      "Chess Pieces YOLOv8 (roboflow2)",
        "workspace":   "roboflow-2",
        "project":     "chess-pieces-xgxpf",
        "version":     1,
        "imagenes":    "~4 000",
        "clases":      "wp, wr, wb, wn, wq, wk, bp, br, bb, bn, bq, bk",
        "descripcion": "Abreviaturas de dos letras — compatibles con el CLASS_MAP por defecto.",
    },
]


def check_roboflow():
    try:
        import roboflow  # noqa
        return True
    except ImportError:
        print("❌  roboflow no instalado. Ejecuta:  pip install roboflow")
        sys.exit(1)


def get_api_key() -> str:
    key = os.environ.get("ROBOFLOW_API_KEY", "").strip()
    if key:
        return key
    print("\n🔑  API Key de Roboflow (https://roboflow.com → Settings → API):")
    key = input("   Pega tu API key: ").strip()
    if not key:
        print("❌  Sin API key. Abortando.")
        sys.exit(1)
    return key


def try_access_dataset(rf, workspace: str, project: str, version: int) -> dict:
    """Intenta acceder al dataset y devuelve info básica."""
    try:
        proj    = rf.workspace(workspace).project(project)
        ver     = proj.version(version)
        return {"ok": True, "name": proj.name, "version": version}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def print_dataset_info(idx: int, ds: dict, status: str = ""):
    print(f"\n  [{idx}] {ds['nombre']}")
    print(f"       workspace : {ds['workspace']}")
    print(f"       project   : {ds['project']}")
    print(f"       versión   : {ds['version']}")
    print(f"       imágenes  : {ds['imagenes']}")
    print(f"       clases    : {ds['clases'][:80]}{'...' if len(ds['clases']) > 80 else ''}")
    print(f"       descripción: {ds['descripcion']}")
    if status:
        print(f"       acceso    : {status}")


def update_train_script(workspace: str, project: str, version: int):
    """Actualiza las constantes en train_chess_yolo.py con el dataset elegido."""
    train_script = Path(__file__).parent / "train_chess_yolo.py"
    if not train_script.exists():
        print(f"⚠️   No se encontró train_chess_yolo.py en {train_script}")
        return

    content = train_script.read_text(encoding="utf-8")

    # Reemplazar las constantes
    import re
    content = re.sub(r'WORKSPACE\s*=\s*"[^"]*"', f'WORKSPACE = "{workspace}"', content)
    content = re.sub(r'PROJECT\s*=\s*"[^"]*"',   f'PROJECT   = "{project}"',   content)
    content = re.sub(r'VERSION\s*=\s*\d+',        f'VERSION   = {version}',      content)

    train_script.write_text(content, encoding="utf-8")
    print(f"✅  train_chess_yolo.py actualizado con el dataset seleccionado.")


def main():
    print("═" * 65)
    print("  Explorador de datasets de ajedrez en Roboflow Universe")
    print("═" * 65)

    check_roboflow()
    api_key = get_api_key()

    from roboflow import Roboflow
    rf = Roboflow(api_key=api_key)

    print("\n🔎  Verificando acceso a los datasets conocidos...")
    accessible = []

    for idx, ds in enumerate(KNOWN_DATASETS, start=1):
        result = try_access_dataset(rf, ds["workspace"], ds["project"], ds["version"])
        status = "✅  accesible" if result["ok"] else f"❌  {result['error'][:60]}"
        print_dataset_info(idx, ds, status)
        if result["ok"]:
            accessible.append((idx, ds))

    if not accessible:
        print("\n⚠️   Ningún dataset de los conocidos es accesible con tu API key.")
        print("   Busca manualmente en:  https://universe.roboflow.com")
        print("   Busca 'chess pieces'  y copia el workspace/project de la URL.")
        print("   Luego actualiza train_chess_yolo.py manualmente.")
        sys.exit(0)

    print(f"\n{'─' * 65}")
    print(f"  Datasets accesibles: {[i for i, _ in accessible]}")
    choice_str = input(f"\n  ¿Qué dataset quieres usar? (1-{len(KNOWN_DATASETS)}): ").strip()

    try:
        choice = int(choice_str)
        selected = KNOWN_DATASETS[choice - 1]
    except (ValueError, IndexError):
        print("❌  Selección inválida.")
        sys.exit(1)

    print(f"\n✅  Seleccionado: {selected['nombre']}")

    # Advertencia sobre clases sin color
    if "sin color" in selected["descripcion"].lower() or "Bishop" in selected["clases"]:
        print("\n⚠️   ATENCIÓN: Este dataset NO distingue piezas blancas de negras.")
        print("   Para que chess_detector.py funcione correctamente necesitarás añadir")
        print("   un paso de clasificación de color en tu pipeline, o usar otro dataset.")
        cont = input("   ¿Continuar igualmente? (s/N): ").strip().lower()
        if cont != "s":
            sys.exit(0)

    # Actualizar train_chess_yolo.py
    update_train_script(selected["workspace"], selected["project"], selected["version"])

    print("\n🚀  Ahora ejecuta el entrenamiento con:")
    print("    python scripts/train_chess_yolo.py")
    print("\n   (La API key se reutilizará si exportas la variable de entorno)")
    print(f"    set ROBOFLOW_API_KEY={api_key[:8]}...  (Windows)")


if __name__ == "__main__":
    main()
