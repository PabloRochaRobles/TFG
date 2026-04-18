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
]
