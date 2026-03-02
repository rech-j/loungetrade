from django.conf import settings
from django.db import models


class Transaction(models.Model):
    TX_TYPES = [
        ('trade', 'Trade'),
        ('mint', 'Mint'),
        ('game', 'Game'),
        # Legacy types kept for backward compatibility with existing rows.
        ('game_win', 'Game Win'),
        ('game_loss', 'Game Loss'),
    ]

    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sent_transactions',
    )
    receiver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='received_transactions',
    )
    amount = models.PositiveIntegerField()
    tx_type = models.CharField(max_length=20, choices=TX_TYPES)
    note = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['sender', 'tx_type', '-created_at']),
            models.Index(fields=['receiver', 'tx_type', '-created_at']),
        ]

    def __str__(self):
        sender_name = self.sender.username if self.sender else 'System'
        return f'{sender_name} → {self.receiver.username}: {self.amount} coins'
