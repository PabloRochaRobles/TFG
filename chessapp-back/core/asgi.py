"""
ASGI config for core project.

Combina:
  - HTTP estándar de Django (todas las rutas /api/...)
  - WebSocket de Django Channels (rutas /ws/...)

Para desarrollo se usa InMemoryChannelLayer (sin Redis).
Para producción: instalar redis y cambiar CHANNEL_LAYERS en settings.py.
"""

import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from django.core.asgi import get_asgi_application

from src.games.routing import websocket_urlpatterns

application = ProtocolTypeRouter({
    # Peticiones HTTP normales (Django vistas, DRF, etc.)
    'http': get_asgi_application(),

    # Conexiones WebSocket (progreso de análisis en tiempo real)
    'websocket': AllowedHostsOriginValidator(
        AuthMiddlewareStack(
            URLRouter(websocket_urlpatterns)
        )
    ),
})
