"""
routing.py — Rutas WebSocket para la app de juegos de ajedrez.

Registradas en core/asgi.py bajo el prefijo 'ws/'.
"""

from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    # ws://servidor/ws/progress/<task_id>/
    # El cliente se conecta aquí tras iniciar un análisis asíncrono para
    # recibir actualizaciones de progreso en tiempo real.
    re_path(r'^ws/progress/(?P<task_id>[^/]+)/$', consumers.AnalysisProgressConsumer.as_asgi()),

    # ws://servidor/ws/live/<task_id>/
    # Análisis en directo desde la cámara: el cliente envía un mensaje
    # JSON inicial con las 4 esquinas del tablero y, a partir de ahí,
    # fotogramas JPEG binarios cada vez que detecta inmovilidad.
    re_path(r'^ws/live/(?P<task_id>[^/]+)/$', consumers.LiveAnalysisConsumer.as_asgi()),
]
