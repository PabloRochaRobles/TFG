"""
Modelos ORM de la app `games`.

Por ahora sólo registramos la metadata mínima para asociar cada vídeo subido
con el usuario propietario. Los ficheros (vídeo, FENs, análisis de motores)
siguen viviendo en disco bajo `media/`; lo único que la BD aporta es la
relación `user → file_name` que permite filtrar la lista de partidas y
verificar la propiedad antes de cualquier operación.

Si en el futuro hace falta consultar/filtrar por más metadata (fecha,
resultado, oponente, etc.), aquí es donde se añade.
"""

import os

from django.conf import settings
from django.db import models


class Video(models.Model):
    """Vídeo subido por un usuario. Apunta al fichero en `media/temp_videos/`.

    El `analysis_id` (clave de los JSONs de FENs y análisis de motores) se
    deriva del `file_name` quitando la extensión, igual que hace el resto del
    código actual — así no rompemos compatibilidad con `save_fens`,
    `save_engine_analysis`, etc.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='videos',
    )
    file_name = models.CharField(max_length=255, unique=True)
    original_name = models.CharField(max_length=255, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f'{self.file_name} ({self.user.username})'

    @property
    def analysis_id(self) -> str:
        """Identificador del análisis = file_name sin extensión."""
        return os.path.splitext(self.file_name)[0]
