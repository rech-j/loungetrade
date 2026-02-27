from django.conf import settings
from django.db import models


class CoinFlipChallenge(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('declined', 'Declined'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('expired', 'Expired'),
    ]
    COIN_CHOICES = [
        ('heads', 'Heads'),
        ('tails', 'Tails'),
    ]

    challenger = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='coinflip_challenges_sent',
    )
    opponent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='coinflip_challenges_received',
    )
    stake = models.PositiveIntegerField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    winner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='coinflip_wins',
    )
    flip_result = models.CharField(max_length=5, choices=COIN_CHOICES, null=True, blank=True)
    challenger_choice = models.CharField(max_length=5, choices=COIN_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'games_gamechallenge'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at']),
        ]

    def __str__(self):
        return (
            f'{self.challenger.username} vs {self.opponent.username} '
            f'({self.stake} coins) - {self.status}'
        )
