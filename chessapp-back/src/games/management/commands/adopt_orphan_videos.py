"""
Adopta los .mp4 sueltos en media/temp_videos/ que no tienen fila Video.

Asigna esos vídeos huérfanos a un usuario destinatario (por defecto: el
primer superuser disponible). Útil tras el cambio a multi-usuario para no
perder los vídeos que ya estaban en disco antes de introducir el modelo
Video.

USO
───
  python manage.py adopt_orphan_videos                  # asigna a primer superuser
  python manage.py adopt_orphan_videos --user admin     # asigna a username concreto
  python manage.py adopt_orphan_videos --dry-run        # solo lista, no escribe
"""

import os

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from src.games.models import Video


class Command(BaseCommand):
    help = 'Adopta vídeos huérfanos en media/temp_videos/ asignándolos a un usuario.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user',
            type=str,
            default=None,
            help='Username destinatario (por defecto: primer superuser).',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Lista los huérfanos sin escribir nada.',
        )

    def handle(self, *args, **opts):
        User = get_user_model()

        # Resolver usuario destinatario.
        if opts['user']:
            try:
                user = User.objects.get(username=opts['user'])
            except User.DoesNotExist:
                raise CommandError(f"Usuario '{opts['user']}' no encontrado.")
        else:
            user = User.objects.filter(is_superuser=True).order_by('id').first()
            if user is None:
                raise CommandError(
                    "No hay superusers en la BD. Crea uno con `manage.py createsuperuser` "
                    "o pasa --user <username>."
                )

        # Listar ficheros en media/temp_videos/.
        videos_dir = os.path.join(settings.MEDIA_ROOT, 'temp_videos')
        if not os.path.isdir(videos_dir):
            self.stdout.write(self.style.WARNING(f'No existe {videos_dir}, nada que adoptar.'))
            return

        existing_in_db = set(Video.objects.values_list('file_name', flat=True))
        on_disk = [
            f for f in os.listdir(videos_dir)
            if os.path.isfile(os.path.join(videos_dir, f))
        ]
        orphans = sorted(set(on_disk) - existing_in_db)

        if not orphans:
            self.stdout.write(self.style.SUCCESS('Sin huérfanos: todo en disco ya está en BD.'))
            return

        self.stdout.write(f'Huérfanos detectados ({len(orphans)}):')
        for f in orphans:
            self.stdout.write(f'  - {f}')

        if opts['dry_run']:
            self.stdout.write(self.style.WARNING('--dry-run activo: no se escribe nada.'))
            return

        # Crear filas Video para cada huérfano, en bulk.
        Video.objects.bulk_create([
            Video(user=user, file_name=f, original_name='') for f in orphans
        ])

        self.stdout.write(self.style.SUCCESS(
            f'Adoptados {len(orphans)} vídeos por el usuario "{user.username}".'
        ))
