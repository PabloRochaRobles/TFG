"""
train_chess_yolo.py
═══════════════════
Script completo para:
  1. Descargar el dataset de piezas de ajedrez desde Roboflow.
  2. Entrenar un modelo YOLOv8 de detección.
  3. Copiar el mejor modelo a media/models/chess_yolo.pt para que
     chess_detector.py lo cargue automáticamente.

USO RÁPIDO
──────────
  python scripts/train_chess_yolo.py

El script pedirá interactivamente la API key de Roboflow.
Si prefieres pasarla por entorno:
  set ROBOFLOW_API_KEY=tu_clave   (Windows)
  export ROBOFLOW_API_KEY=tu_clave (Linux/Mac)

REQUISITOS PREVIOS
──────────────────
  pip install roboflow ultralytics

OBTENER LA API KEY DE ROBOFLOW
───────────────────────────────
  1. Regístrate (gratis) en  https://roboflow.com
  2. Ve a Settings → Roboflow API → copia tu "Private API Key"

DATASET RECOMENDADO
───────────────────
  Este script usa el dataset público "Chess Pieces" disponible en
  Roboflow Universe. Contiene ~3 000 imágenes anotadas con las 12 clases
  estándar (white/black × king/queen/rook/bishop/knight/pawn).

  Si prefieres otro dataset, cambia las constantes WORKSPACE / PROJECT /
  VERSION en la sección de configuración más abajo.

TIEMPO ESTIMADO DE ENTRENAMIENTO
──────────────────────────────────
  CPU (sin GPU):  ~2–3 h para 50 epochs con yolov8n
  GPU (CUDA):     ~10–20 min

  Para uso sin GPU se recomienda yolov8n (nano).
  Si tienes GPU, puedes usar yolov8s (small) para mejor precisión.
"""

import os
import sys
import shutil
from pathlib import Path

# ── Modo de descarga ──────────────────────────────────────────────────────────
#
# OPCIÓN A — Descarga automática via API de Roboflow:
#   Pon LOCAL_DATASET_PATH = None  y rellena WORKSPACE/PROJECT/VERSION.
#
# OPCIÓN B — Dataset descargado manualmente (recomendada si la API falla):
#   1. Ve a la página del dataset en Roboflow Universe.
#   2. Pulsa "Download Dataset" → Format: YOLOv8 → "download zip to computer".
#   3. Extrae el zip en la carpeta  chessapp-back/dataset_chess/
#      (debe quedar: dataset_chess/train/, dataset_chess/valid/, dataset_chess/data.yaml)
#   4. Pon LOCAL_DATASET_PATH igual a esa ruta (o deja None para usar el valor por defecto).
#
LOCAL_DATASET_PATH = None   # None = usar Roboflow API | "ruta/al/dataset" = usar local

# ── Configuración Roboflow (solo si LOCAL_DATASET_PATH es None) ───────────────
WORKSPACE = "pablos-workspace-umt6p"     # Workspace de Pablo en Roboflow
PROJECT   = "chess-pieces-ozqxc-bz6ws"  # Proyecto forkeado
VERSION   = 1                            # La detección automática encontrará la versión correcta

# ── Configuración del entrenamiento ──────────────────────────────────────────
MODEL_SIZE = "yolov8n"   # "yolov8n" (nano, rápido) | "yolov8s" (small, más preciso)
EPOCHS     = 50          # Nº de épocas (50 suele ser suficiente para ajedrez)
IMGSZ      = 640         # Resolución de entrenamiento (640 es el estándar YOLOv8)
BATCH      = 16          # Reducir a 8 si hay problemas de memoria en CPU
PATIENCE   = 15          # Early stopping: detiene si no mejora en N épocas
DEVICE     = None        # None = auto-detección (GPU si está disponible, CPU si no)

# ── Rutas del proyecto ────────────────────────────────────────────────────────
SCRIPT_DIR   = Path(__file__).parent
BACKEND_DIR  = SCRIPT_DIR.parent
# Usar ruta sin espacios ni tildes para que Roboflow pueda escribir en Windows
DATASET_DIR  = Path("C:/chess_dataset")
MODELS_DIR   = BACKEND_DIR / "media" / "models"
OUTPUT_MODEL = MODELS_DIR / "chess_yolo.pt"

# ─────────────────────────────────────────────────────────────────────────────

def check_dependencies():
    """Verifica que roboflow y ultralytics estén instalados."""
    missing = []
    try:
        import roboflow  # noqa
    except ImportError:
        missing.append("roboflow")
    try:
        import ultralytics  # noqa
    except ImportError:
        missing.append("ultralytics")

    if missing:
        print(f"\n❌  Faltan dependencias: {', '.join(missing)}")
        print(f"   Instálalas con:  pip install {' '.join(missing)}")
        sys.exit(1)

    print("✅  Dependencias verificadas (roboflow + ultralytics)")


def get_api_key() -> str:
    """Obtiene la API key de Roboflow desde variable de entorno o input."""
    key = os.environ.get("ROBOFLOW_API_KEY", "").strip()
    if key:
        print(f"🔑  API key leída desde variable de entorno ROBOFLOW_API_KEY")
        return key

    print("\n── API Key de Roboflow ──────────────────────────────────────────")
    print("   Obtenla en: https://roboflow.com → Settings → Roboflow API")
    key = input("V4CCnzZE4VF4XVGdkxbn").strip()
    if not key:
        print("❌  No se proporcionó API key. Abortando.")
        sys.exit(1)
    return key


def download_dataset(api_key: str) -> Path:
    """
    Descarga el dataset desde Roboflow en formato YOLOv8.
    Si la versión configurada no existe, lista las disponibles y deja elegir.
    Devuelve la ruta al directorio del dataset descargado.
    """
    from roboflow import Roboflow

    print(f"\n📥  Descargando dataset...")
    print(f"    Workspace : {WORKSPACE}")
    print(f"    Proyecto  : {PROJECT}")
    print(f"    Versión   : {VERSION}")

    rf = Roboflow(api_key=api_key)

    try:
        project = rf.workspace(WORKSPACE).project(PROJECT)
    except Exception as exc:
        print(f"\n❌  No se pudo acceder al proyecto '{WORKSPACE}/{PROJECT}'.")
        print(f"   Error: {exc}")
        print("\n   SOLUCIÓN: Busca un dataset de piezas de ajedrez en:")
        print("   https://universe.roboflow.com  (busca 'chess pieces')")
        print("   y actualiza las constantes WORKSPACE / PROJECT / VERSION al principio del script.")
        sys.exit(1)

    # Intentar la versión configurada; si falla, detectar las disponibles
    chosen_version = VERSION
    try:
        ver_obj = project.version(chosen_version)
    except RuntimeError:
        print(f"\n⚠️   La versión {VERSION} no existe en este proyecto.")

        # Buscar versiones disponibles probando 1–10
        available = []
        print("    Buscando versiones disponibles", end="", flush=True)
        for v in range(1, 11):
            try:
                project.version(v)
                available.append(v)
                print(f" {v}✓", end="", flush=True)
            except RuntimeError:
                print(f" {v}✗", end="", flush=True)
        print()

        if not available:
            print("\n❌  No se encontró ninguna versión accesible (1–10).")
            print("   Comprueba en Roboflow que el dataset es público o que tu cuenta tiene acceso.")
            sys.exit(1)

        print(f"\n    Versiones disponibles: {available}")
        if len(available) == 1:
            chosen_version = available[0]
            print(f"    Usando versión {chosen_version} automáticamente.")
        else:
            choice = input(f"    ¿Qué versión quieres descargar? ({available[0]}–{available[-1]}): ").strip()
            try:
                chosen_version = int(choice)
                if chosen_version not in available:
                    raise ValueError
            except ValueError:
                chosen_version = available[-1]
                print(f"    Entrada inválida — usando la última versión disponible: {chosen_version}")

        ver_obj = project.version(chosen_version)

    print(f"    Descargando versión {chosen_version}...")
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    dataset = ver_obj.download("yolov8", location=str(DATASET_DIR))

    dataset_path = Path(dataset.location)

    # Verificar que el directorio tiene archivos (a veces Roboflow falla en Windows)
    all_files = list(dataset_path.rglob("*")) if dataset_path.exists() else []
    if not all_files:
        print(f"\n⚠️   El directorio está vacío. Roboflow no descargó los archivos localmente.")
        print(f"     Esto ocurre con algunos proyectos propios en Windows.")
        print(f"\n{'─'*60}")
        print(f"DESCARGA MANUAL (rápida):")
        print(f"  1. Ve a: https://app.roboflow.com/{WORKSPACE}/{PROJECT}")
        print(f"  2. Pestaña 'Versions' → versión {chosen_version}")
        print(f"  3. Botón 'Download Dataset' → Format: YOLOv8 → 'download zip to computer'")
        print(f"  4. Extrae el ZIP en:  C:\\chess_dataset\\")
        print(f"     Debe quedar:  C:\\chess_dataset\\train\\  C:\\chess_dataset\\valid\\  C:\\chess_dataset\\data.yaml")
        print(f"  5. Vuelve a ejecutar este script — detectará el dataset local automáticamente.")
        print(f"{'─'*60}\n")
        sys.exit(1)

    print(f"✅  Dataset descargado en: {dataset_path}")
    return dataset_path


def find_data_yaml(dataset_path: Path) -> Path:
    """Localiza el archivo data.yaml generado por Roboflow."""
    # Roboflow puede crear el yaml en la raíz o en una subcarpeta
    candidates = list(dataset_path.rglob("data.yaml"))
    if not candidates:
        print(f"❌  No se encontró data.yaml en {dataset_path}")
        print(f"   Estructura del directorio:")
        for p in sorted(dataset_path.rglob("*"))[:20]:
            print(f"     {p}")
        sys.exit(1)
    yaml_path = candidates[0]
    print(f"📄  data.yaml encontrado: {yaml_path}")
    return yaml_path


def verify_class_names(yaml_path: Path):
    """
    Comprueba que los nombres de clase del dataset son compatibles con
    el CLASS_MAP en chess_detector.py e imprime un aviso si no lo son.
    """
    import yaml

    with open(yaml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    names = data.get("names", [])
    print(f"\n📋  Clases en el dataset ({len(names)}): {names}")

    # Clases esperadas por chess_detector.py (DEFAULT_CLASS_MAP)
    known_classes = {
        "white-king", "white-queen", "white-rook", "white-bishop", "white-knight", "white-pawn",
        "black-king", "black-queen", "black-rook", "black-bishop", "black-knight", "black-pawn",
        "wK", "wQ", "wR", "wB", "wN", "wP",
        "bK", "bQ", "bR", "bB", "bN", "bP",
        "White King", "White Queen", "White Rook", "White Bishop", "White Knight", "White Pawn",
        "Black King", "Black Queen", "Black Rook", "Black Bishop", "Black Knight", "Black Pawn",
        "K", "Q", "R", "B", "N", "P", "k", "q", "r", "b", "n", "p",
    }

    unknown = [n for n in names if n not in known_classes]
    if unknown:
        print(f"\n⚠️   Las siguientes clases NO están en el CLASS_MAP de chess_detector.py:")
        print(f"    {unknown}")
        print(f"\n    Añádelas a settings.py en CHESS_YOLO_CLASS_MAP:")
        print(f"    CHESS_YOLO_CLASS_MAP = {{")
        for cls in unknown:
            print(f"        '{cls}': '?',  # ← asigna el símbolo FEN correcto")
        print(f"    }}")
        print(f"\n    El entrenamiento continuará, pero debes mapear estas clases para que")
        print(f"    chess_detector.py las interprete correctamente.")
        input("\n    Pulsa ENTER para continuar de todas formas...")
    else:
        print("✅  Todas las clases son compatibles con chess_detector.py")

    return names


def train_model(yaml_path: Path) -> Path:
    """
    Entrena el modelo YOLOv8 con el dataset descargado.
    Devuelve la ruta al mejor modelo entrenado (best.pt).
    """
    from ultralytics import YOLO

    print(f"\n🚀  Iniciando entrenamiento...")
    print(f"    Modelo base : {MODEL_SIZE}.pt")
    print(f"    Épocas      : {EPOCHS}")
    print(f"    Imagen      : {IMGSZ}px")
    print(f"    Batch       : {BATCH}")
    print(f"    Paciencia   : {PATIENCE} épocas (early stopping)")
    device_label = "auto" if DEVICE is None else str(DEVICE)
    print(f"    Dispositivo : {device_label} (GPU si está disponible, CPU si no)")
    print()

    model = YOLO(f"{MODEL_SIZE}.pt")

    # Detect device
    train_device = DEVICE
    if train_device is None:
        try:
            import torch
            train_device = 0 if torch.cuda.is_available() else "cpu"
            if train_device == 0:
                print(f"    🎮  GPU detectada: {torch.cuda.get_device_name(0)}")
            else:
                print(f"    💻  Sin GPU disponible — entrenando en CPU (más lento)")
        except ImportError:
            train_device = "cpu"

    results = model.train(
        data     = str(yaml_path),
        epochs   = EPOCHS,
        imgsz    = IMGSZ,
        batch    = BATCH,
        patience = PATIENCE,
        device   = train_device,
        project  = str(BACKEND_DIR / "runs" / "chess_train"),
        name     = "exp",
        exist_ok = True,
        # Augmentaciones extra útiles para tableros de ajedrez
        hsv_h    = 0.015,   # Variación de tono (iluminación variable)
        hsv_s    = 0.5,     # Variación de saturación
        hsv_v    = 0.4,     # Variación de brillo
        degrees  = 5,       # Pequeña rotación (cámaras no siempre perfectamente verticales)
        fliplr   = 0.0,     # Sin volteo horizontal (cambia significado de blancas/negras)
        flipud   = 0.0,     # Sin volteo vertical
        mosaic   = 0.5,     # Mosaico reducido (piezas en otros cuadros pueden confundir)
    )

    # Localizar best.pt
    best_pt = Path(results.save_dir) / "weights" / "best.pt"
    if not best_pt.exists():
        # Fallback: buscar en todo el directorio de resultados
        candidates = list(Path(results.save_dir).rglob("best.pt"))
        if not candidates:
            print(f"❌  No se encontró best.pt en {results.save_dir}")
            sys.exit(1)
        best_pt = candidates[0]

    print(f"\n✅  Entrenamiento completado.")
    print(f"    Mejor modelo: {best_pt}")
    return best_pt


def install_model(best_pt: Path):
    """Copia best.pt a media/models/chess_yolo.pt."""
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    # Hacer backup si ya existe un modelo previo
    if OUTPUT_MODEL.exists():
        backup = OUTPUT_MODEL.with_suffix(".backup.pt")
        shutil.copy2(OUTPUT_MODEL, backup)
        print(f"📦  Backup del modelo anterior → {backup}")

    shutil.copy2(best_pt, OUTPUT_MODEL)
    print(f"✅  Modelo instalado en: {OUTPUT_MODEL}")


def run_quick_test():
    """Prueba rápida de que el modelo cargado detecta piezas correctamente."""
    print("\n🔍  Verificando que chess_detector puede cargar el modelo...")

    # Añadir el backend al path para importar chess_detector
    sys.path.insert(0, str(BACKEND_DIR))

    # Configurar Django mínimamente (solo para que settings.py no falle)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
    try:
        import django
        django.setup()
    except Exception as exc:
        print(f"⚠️   No se pudo inicializar Django ({exc})")
        print(f"    El modelo está instalado igualmente — pruébalo arrancando el servidor.")
        return

    # Resetear caché del modelo (puede que ya esté cargado desde otra ejecución)
    try:
        from src.games.chess_detector import reset_model_cache, is_available, get_model
        reset_model_cache()
        if is_available():
            model = get_model()
            print(f"✅  Modelo cargado correctamente.")
            print(f"    Clases: {list(model.names.values())}")
        else:
            print(f"❌  chess_detector.is_available() devolvió False.")
            print(f"    Revisa que el modelo esté en: {OUTPUT_MODEL}")
    except Exception as exc:
        print(f"⚠️   Test fallido ({exc}). El modelo puede funcionar igualmente.")


def main():
    print("═" * 60)
    print("  Descarga y entrenamiento — Chess YOLOv8")
    print("═" * 60)

    # 1. Verificar dependencias
    check_dependencies()

    # 2. Obtener dataset (local o via Roboflow API)
    # Auto-detección: si DATASET_DIR ya tiene data.yaml, usarlo directamente
    existing_yaml = list(DATASET_DIR.rglob("data.yaml")) if DATASET_DIR.exists() else []
    if existing_yaml:
        print(f"📂  Dataset local detectado en: {DATASET_DIR}")
        dataset_path = DATASET_DIR
    elif LOCAL_DATASET_PATH is not None:
        dataset_path = Path(LOCAL_DATASET_PATH)
        if not dataset_path.exists():
            print(f"❌  LOCAL_DATASET_PATH no existe: {dataset_path}")
            print("    Extrae el zip descargado de Roboflow en esa ruta.")
            sys.exit(1)
        print(f"📂  Usando dataset local: {dataset_path}")
    else:
        api_key = get_api_key()
        dataset_path = download_dataset(api_key)

    # 3. Localizar data.yaml
    yaml_path = find_data_yaml(dataset_path)

    # 4. Verificar nombres de clase
    verify_class_names(yaml_path)

    # 5. Entrenar
    best_pt = train_model(yaml_path)

    # 6. Instalar modelo
    install_model(best_pt)

    # 7. Test rápido
    run_quick_test()

    print("\n" + "═" * 60)
    print("  ✅  Todo listo. Ahora arranca el servidor con:")
    print("      daphne -b 0.0.0.0 -p 8000 core.asgi:application")
    print("═" * 60)


if __name__ == "__main__":
    main()
