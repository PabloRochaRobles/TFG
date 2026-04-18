"""
consumers.py — Consumer WebSocket para progreso de análisis en tiempo real.

Flujo completo:
  1. El cliente conecta a:  ws://<servidor>/ws/progress/<task_id>/
  2. El backend hace el análisis en un hilo de fondo (views.py).
  3. Cada cierto tiempo el consumer lee el progreso desde Django Cache y
     lo envía al cliente.
  4. Cuando el análisis termina (progress=100 o error), cierra la conexión.

Ventajas frente al polling HTTP anterior:
  - Una única conexión persistente en lugar de N peticiones GET.
  - El servidor empuja el resultado final por el mismo canal (sin petición extra).
  - Latencia de actualización ≤ 500 ms configurada en POLL_INTERVAL_SECS.
"""

import asyncio
import json
import logging

from channels.generic.websocket import AsyncWebsocketConsumer

logger = logging.getLogger(__name__)

# Intervalo de comprobación del progreso (segundos)
POLL_INTERVAL_SECS = 0.5

# Tiempo máximo de espera antes de cerrar la conexión si no hay actividad (segundos)
MAX_WAIT_SECS = 600  # 10 minutos


class AnalysisProgressConsumer(AsyncWebsocketConsumer):
    """
    Consumer WebSocket que informa al cliente del progreso del análisis de vídeo.

    Protocolo de mensajes (JSON):

      Desde el servidor al cliente:
        { "type": "progress",  "progress": 45 }
        { "type": "complete",  "progress": 100, "analisis_id": "...",
          "total_fens": N, "fens": [...], "message": "..." }
        { "type": "error",     "error": "mensaje de error" }

      El cliente no necesita enviar nada; la conexión es unidireccional.
    """

    async def connect(self):
        self.task_id = self.scope['url_route']['kwargs']['task_id']
        self.fens_sent = 0
        await self.accept()
        logger.info("[WS] Cliente conectado para task_id=%s", self.task_id)
        # Arrancamos el bucle de progreso como tarea asíncrona independiente
        asyncio.create_task(self._progress_loop())

    async def disconnect(self, close_code):
        logger.info("[WS] Cliente desconectado (task_id=%s, code=%s)", self.task_id, close_code)

    async def receive(self, text_data=None, bytes_data=None):
        # El cliente no necesita enviar mensajes, pero los aceptamos sin error
        pass

    async def _progress_loop(self):
        """
        Bucle que lee el estado del análisis desde Django Cache y lo empuja
        al cliente vía WebSocket cada POLL_INTERVAL_SECS segundos.

        Se detiene cuando:
          - El análisis termina (status = 'complete' o 'error').
          - El cliente cierra la conexión.
          - Se supera MAX_WAIT_SECS sin recibir datos.
        """
        from django.core.cache import cache

        elapsed = 0.0

        while elapsed < MAX_WAIT_SECS:
            await asyncio.sleep(POLL_INTERVAL_SECS)
            elapsed += POLL_INTERVAL_SECS

            try:
                data = cache.get(f'analysis_task_{self.task_id}')
            except Exception as exc:
                logger.warning("[WS] Error leyendo cache: %s", exc)
                continue

            if data is None:
                # Tarea no iniciada todavía o caché expirada
                continue

            # Enviar FENs parciales según se generan
            try:
                fens_stream = cache.get(f'analysis_task_{self.task_id}_fens') or []
                while self.fens_sent < len(fens_stream):
                    await self._safe_send({
                        'type':  'fen_ready',
                        'fen':   fens_stream[self.fens_sent],
                        'index': self.fens_sent,
                    })
                    self.fens_sent += 1
            except Exception as exc:
                logger.debug("[WS] Error enviando fen_ready: %s", exc)

            status = data.get('status', 'processing')

            if status == 'complete':
                await self._safe_send({
                    'type':        'complete',
                    'progress':    100,
                    'analisis_id': data.get('analisis_id', ''),
                    'total_fens':  data.get('total_fens',  0),
                    'fens':        data.get('fens',        []),
                    'message':     data.get('message',     'Análisis completado.'),
                })
                await self.close()
                return

            elif status == 'error':
                await self._safe_send({
                    'type':  'error',
                    'error': data.get('error', 'Error desconocido'),
                })
                await self.close()
                return

            else:
                # En progreso
                progress = data.get('progress', 0)
                await self._safe_send({
                    'type':     'progress',
                    'progress': progress,
                })

        # Se agotó el tiempo de espera
        logger.warning("[WS] Tiempo de espera agotado para task_id=%s", self.task_id)
        await self._safe_send({'type': 'error', 'error': 'Tiempo de espera agotado.'})
        await self.close()

    async def _safe_send(self, payload: dict):
        """Envía JSON al cliente ignorando errores si la conexión ya se cerró."""
        try:
            await self.send(text_data=json.dumps(payload))
        except Exception as exc:
            logger.debug("[WS] No se pudo enviar mensaje (conexión cerrada): %s", exc)
