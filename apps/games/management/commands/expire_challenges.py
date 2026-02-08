from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.games.models import GameChallenge


class Command(BaseCommand):
    help = 'Expire pending game challenges older than 24 hours'

    def add_arguments(self, parser):
        parser.add_argument(
            '--hours', type=int, default=24,
            help='Expire challenges older than this many hours (default: 24)',
        )

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(hours=options['hours'])
        expired = GameChallenge.objects.filter(
            status='pending',
            created_at__lt=cutoff,
        ).update(status='expired')
        self.stdout.write(self.style.SUCCESS(f'Expired {expired} challenges.'))
