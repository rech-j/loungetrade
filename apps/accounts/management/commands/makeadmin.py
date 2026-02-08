from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Grant admin privileges to a user'

    def add_arguments(self, parser):
        parser.add_argument('username', type=str)

    def handle(self, *args, **options):
        username = options['username']
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            raise CommandError(f'User "{username}" does not exist.')

        user.profile.is_admin_user = True
        user.profile.save(update_fields=['is_admin_user'])
        self.stdout.write(self.style.SUCCESS(f'User "{username}" is now an admin.'))
