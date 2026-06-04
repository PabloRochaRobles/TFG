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


# =============================================================================
# Consumer para análisis EN DIRECTO desde la cámara del cliente.
# Es independiente del consumer anterior (que se mantiene exactamente igual).
# =============================================================================


class LiveAnalysisConsumer(AsyncWebsocketConsumer):
    """Análisis de partida en tiempo real, mientras el usuario graba.

    Protocolo:

      Cliente → servidor:
        1. (texto JSON) {"type": "init",
                          "corners": [[ax,ay],[bx,by],[cx,cy],[dx,dy]]}
           Las 4 esquinas en píxeles absolutos del fotograma, en orden
           a1, a8, h8, h1 (mismo orden que el flujo offline).
        2. (binario)    JPEG codificado del fotograma actual. Repetir
                        cada vez que el cliente detecte inmovilidad
                        sobre el tablero.

      Servidor → cliente (texto JSON):
        {"type": "ready", "fen": "..."}
          Tras procesar init, indica que está listo para recibir frames
          y devuelve el FEN inicial (posición de partida).
        {"type": "frame_result", "decision": "...", "score": float,
         "margin": float, "no_move_score": float}
          Por cada frame procesado. `decision` ∈ {move, no-move,
          low-margin, garbage, duplicate}.
        {"type": "fen_ready", "fen": "...", "uci_moves": [...],
         "index": int}
          Adicional al frame_result cuando la decisión fue 'move'.
        {"type": "error", "error": "mensaje"}
          Error recuperable; la sesión sigue abierta a menos que se
          cierre explícitamente.

    Autenticación: se confía en la unicidad del `task_id` (UUID v4)
    como capacidad, igual que el consumer de progreso del flujo offline.
    """

    async def connect(self):
        self.task_id = self.scope['url_route']['kwargs'].get('task_id')
        if not self.task_id:
            await self.close(code=4001)
            return
        self.session = None
        await self.accept()
        logger.info("[LIVE] Cliente conectado, task_id=%s", self.task_id)

    async def disconnect(self, close_code):
        logger.info(
            "[LIVE] Cliente desconectado (task_id=%s, code=%s)",
            self.task_id, close_code,
        )
        # Libera la referencia a la sesión y permite al GC recoger el
        # frame rectificado almacenado en memoria.
        self.session = None

    async def receive(self, text_data=None, bytes_data=None):
        if text_data is not None:
            await self._handle_text(text_data)
        elif bytes_data is not None:
            await self._handle_binary(bytes_data)

    async def _safe_send(self, payload: dict):
        """Envía JSON al cliente ignorando errores si la conexión ya se cerró."""
        try:
            await self.send(text_data=json.dumps(payload))
        except Exception as exc:
            logger.debug("[LIVE] No se pudo enviar mensaje (conexión cerrada): %s", exc)

    # ------------------------------------------------------------------
    # Mensajes de control (texto JSON)
    # ------------------------------------------------------------------

    async def _handle_text(self, raw: str):
        try:
            data = json.loads(raw)
        except Exception:
            await self._safe_send({'type': 'error', 'error': 'JSON inválido'})
            return

        msg_type = data.get('type')
        if msg_type == 'init':
            await self._init_session(data)
        else:
            await self._safe_send({
                'type': 'error',
                'error': f"Tipo de mensaje desconocido: {msg_type!r}",
            })

    async def _init_session(self, data: dict):
        from .chess_tracker.board_detector import BoardCalibration
        from .services.live_analyzer import LiveSession

        corners = data.get('corners')
        if not corners or len(corners) != 4:
            await self._safe_send({
                'type': 'error',
                'error': 'Se requieren exactamente 4 esquinas en `corners`.',
            })
            return
        try:
            calib = BoardCalibration(
                a1=(float(corners[0][0]), float(corners[0][1])),
                a8=(float(corners[1][0]), float(corners[1][1])),
                h8=(float(corners[2][0]), float(corners[2][1])),
                h1=(float(corners[3][0]), float(corners[3][1])),
            )
        except Exception as exc:
            await self._safe_send({
                'type': 'error',
                'error': f'Calibración inválida: {exc}',
            })
            return

        # Construir la sesión es relativamente caro (toca el singleton
        # del clasificador): se hace fuera del event loop.
        self.session = await asyncio.to_thread(LiveSession, calib)
        await self._safe_send({
            'type': 'ready',
            'fen':  self.session.board.fen(),
        })
        logger.info("[LIVE] Sesión inicializada (task_id=%s)", self.task_id)

    # ------------------------------------------------------------------
    # Mensajes binarios (frames JPEG)
    # ------------------------------------------------------------------

    async def _handle_binary(self, buf: bytes):
        if self.session is None:
            await self._safe_send({
                'type': 'error',
                'error': 'Sesión no inicializada; envía `init` antes de los frames.',
            })
            return

        from .services.live_analyzer import LiveSession

        img = await asyncio.to_thread(LiveSession.decode_jpeg, buf)
        if img is None:
            await self._safe_send({
                'type': 'error',
                'error': 'No se pudo decodificar el JPEG recibido.',
            })
            return

        # La clasificación + inferencia es CPU-bound; off-thread.
        result = await asyncio.to_thread(self.session.process_frame, img)
        await self._safe_send({'type': 'frame_result', **result})
        if result.get('decision') == 'move':
            await self._safe_send({
                'type':      'fen_ready',
                'fen':       result['fen'],
                'uci_moves': result['moves'],
                'index':     result['index'],
            })
