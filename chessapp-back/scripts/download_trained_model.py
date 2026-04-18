"""
download_trained_model.py
─────────────────────────
Descarga el modelo YOLOv8 entrenado en Roboflow y lo instala en
media/models/chess_yolo.pt para que chess_detector.py lo use.

Ejecutar DESPUÉS de que el entrenamiento en Roboflow haya terminado:
  python scripts/download_trained_model.py
"""

import os
import sys
import shutil
from pathlib import Path

WORKSPACE = "pablos-workspace-umt6p"
PROJECT   = "chess-pieces-ozqxc-bz6ws"

SCRIPT_DIR   = Path(__file__).parent
BACKEND_DIR  = SCRIPT_DIR.parent
MODELS_DIR   = BACKEND_DIR / "media" / "models"
OUTPUT_MODEL = MODELS_DIR / "chess_yolo.pt"


def get_api_key() -> str:
    key = os.environ.get("ROBOFLOW_API_KEY", "").strip()
    if key:
        return key
    key = input("API key de Roboflow: ").strip()
    if not key:
        sys.exit(1)
    return key


def main():
    from roboflow import Roboflow

    api_key = get_api_key()
    rf      = Roboflow(api_key=api_key)

    print(f"Conectando a {WORKSPACE}/{PROJECT}...")
    project = rf.workspace(WORKSPACE).project(PROJECT)

    # Listar versiones disponibles
    available = []
    print("Buscando versiones entrenadas", end="", flush=True)
    for v in range(1, 11):
        try:
            ver = project.version(v)
            available.append(v)
            print(f" {v}✓", end="", flush=True)
        except Exception:
            print(f" {v}✗", end="", flush=True)
    print()

    if not available:
        print("No se encontraron versiones. ¿Ha terminado el entrenamiento en Roboflow?")
        sys.exit(1)

    # Usar la última versión disponible (la más reciente)
    version_num = available[-1]
    print(f"Usando versión {version_num}")
    version = project.version(version_num)

    # Intentar descargar los pesos del modelo entrenado
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    tmp_dir = BACKEND_DIR / "tmp_model_download"
    tmp_dir.mkdir(exist_ok=True)

    try:
        # Método 1: exportar pesos directamente
        print("Descargando pesos del modelo...")
        version.export("yolov8")
        model_file = version.download("yolov8", location=str(tmp_dir))
        # Buscar el .pt dentro de lo descargado
        pt_files = list(tmp_dir.rglob("*.pt"))
        if pt_files:
            shutil.copy2(pt_files[0], OUTPUT_MODEL)
            print(f"✅ Modelo instalado en: {OUTPUT_MODEL}")
        else:
            raise FileNotFoundError("No se encontró .pt en la descarga")

    except Exception as e:
        print(f"Descarga directa no disponible ({e})")
        print()
        print("━" * 55)
        print("DESCARGA MANUAL:")
        print(f"  1. Ve a: https://app.roboflow.com/{WORKSPACE}/{PROJECT}")
        print(f"  2. Pestaña 'Versions' → versión {version_num}")
        print(f"  3. Busca 'Download' → 'YOLOv8 PyTorch Weights'")
        print(f"     (puede aparecer como 'Export weights' o 'Download model')")
        print(f"  4. Descarga el .pt y cópialo a:")
        print(f"     {OUTPUT_MODEL}")
        print("━" * 55)

    # Limpiar temporal
    shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
