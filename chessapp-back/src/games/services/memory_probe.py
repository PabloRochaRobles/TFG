"""Sondas de memoria para diagnosticar OOM en producción.

Imprime el RSS (Resident Set Size) del proceso actual en MB en puntos
estratégicos del pipeline. Se usa para identificar qué subsistema empuja
la memoria por encima del techo de la plataforma de hosting.

Es importación segura: si `psutil` no está instalado, los logs imprimen -1
en lugar de petar. La librería pesa ~1 MB en disco — coste despreciable.
"""

import os

try:
    import psutil
    _PROC = psutil.Process(os.getpid())

    def rss_mb() -> float:
        """Resident set size del proceso actual en MB."""
        return _PROC.memory_info().rss / (1024 * 1024)
except ImportError:  # pragma: no cover
    def rss_mb() -> float:
        return -1.0


def mem_log(label: str) -> None:
    """Imprime una sonda etiquetada y la flusha inmediatamente."""
    print(f"[MEM] {label}: {rss_mb():.1f} MB", flush=True)
