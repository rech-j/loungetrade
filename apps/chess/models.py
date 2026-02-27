from django.conf import settings
from django.db import models

STARTING_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'
TIME_CONTROL = 600  # 10 minutes in seconds


class ChessGame(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    END_REASON_CHOICES = [
        ('checkmate', 'Checkmate'),
        ('stalemate', 'Stalemate'),
        ('draw', 'Draw agreed'),
        ('resign', 'Resignation'),
        ('timeout', 'Timeout'),
        ('cancelled', 'Cancelled'),
    ]
    SIDE_CHOICES = [
        ('white', 'White'),
        ('black', 'Black'),
        ('random', 'Random'),
    ]

    # Players — white/black assigned when game becomes active
    white_player = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='chess_as_white',
        null=True, blank=True,
    )
    black_player = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='chess_as_black',
        null=True, blank=True,
    )
    # The user who created the challenge
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='chess_created',
    )
    # The opponent (invited player)
    opponent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='chess_received',
    )
    # Which side the creator wants
    creator_side = models.CharField(max_length=6, choices=SIDE_CHOICES, default='random')

    stake = models.PositiveIntegerField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    winner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='chess_wins',
    )
    end_reason = models.CharField(max_length=10, choices=END_REASON_CHOICES, null=True, blank=True)

    # Game state
    fen = models.CharField(max_length=200, default=STARTING_FEN)
    moves_uci = models.TextField(blank=True)  # space-separated UCI moves e.g. "e2e4 e7e5"

    # Timers (seconds remaining)
    white_time = models.PositiveIntegerField(default=TIME_CONTROL)
    black_time = models.PositiveIntegerField(default=TIME_CONTROL)
    last_move_at = models.DateTimeField(null=True, blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['status', 'created_at'])]

    def __str__(self):
        return (
            f'{self.creator.username} vs {self.opponent.username} '            f'({self.stake} LC) - {self.status}'
        )

    def get_player_side(self, user):
        """Return 'white', 'black', or None for the given user."""
        if self.white_player_id == user.pk:
            return 'white'
        if self.black_player_id == user.pk:
            return 'black'
        return None

    def get_other_player(self, user):
        """Return the opponent User object."""
        if self.creator_id == user.pk:
            return self.opponent
        return self.creator
