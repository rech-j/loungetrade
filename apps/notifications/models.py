from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models


class Notification(models.Model):
    NOTIF_TYPES = [
        ('coin_received', 'Coin Received'),
        ('game_invite', 'Game Invite'),
        ('game_result', 'Game Result'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
    )
    notif_type = models.CharField(max_length=15, choices=NOTIF_TYPES)
    title = models.CharField(max_length=100)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    link = models.CharField(
        max_length=200,
        blank=True,
        validators=[RegexValidator(r'^(/[a-zA-Z0-9/_-]*)?$', 'Must be a relative URL path.')],
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read']),
        ]

    def __str__(self):
        return f'{self.user.username}: {self.title}'
