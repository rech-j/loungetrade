from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class PokerTable(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='poker_tables_created',
    )
    is_public = models.BooleanField(default=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    stake = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    starting_chips = models.PositiveIntegerField(default=1000)
    min_players = models.PositiveSmallIntegerField(default=3)
    max_players = models.PositiveSmallIntegerField(default=8)
    small_blind = models.PositiveIntegerField(default=10)
    big_blind = models.PositiveIntegerField(default=20)
    allow_rebuys = models.BooleanField(default=False)
    max_rebuys = models.PositiveSmallIntegerField(default=0)
    time_per_action = models.PositiveSmallIntegerField(default=30)
    hand_number = models.PositiveIntegerField(default=0)
    dealer_seat = models.PositiveSmallIntegerField(default=0)
    end_vote_active = models.BooleanField(default=False)
    end_vote_initiated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['creator', 'status']),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(stake__gte=1),
                name='poker_stake_positive',
            ),
        ]

    def __str__(self):
        return f'Poker Table #{self.pk} ({self.stake} LC) - {self.status}'


class PokerPlayer(models.Model):
    STATUS_CHOICES = [
        ('invited', 'Invited'),
        ('active', 'Active'),
        ('folded', 'Folded'),
        ('all_in', 'All In'),
        ('eliminated', 'Eliminated'),
        ('spectating', 'Spectating'),
        ('left', 'Left'),
    ]

    table = models.ForeignKey(PokerTable, on_delete=models.CASCADE, related_name='players')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='poker_seats',
    )
    seat = models.PositiveSmallIntegerField()
    chips = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=11, choices=STATUS_CHOICES, default='active')
    is_online = models.BooleanField(default=False)
    rebuys_used = models.PositiveSmallIntegerField(default=0)
    vote_end = models.BooleanField(default=False)
    coins_invested = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['table', 'seat'], name='unique_table_seat'),
            models.UniqueConstraint(fields=['table', 'user'], name='unique_table_user'),
        ]

    def __str__(self):
        return f'{self.user.username} @ seat {self.seat} ({self.chips} chips)'


class PokerHand(models.Model):
    STATUS_CHOICES = [
        ('preflop', 'Preflop'),
        ('flop', 'Flop'),
        ('turn', 'Turn'),
        ('river', 'River'),
        ('showdown', 'Showdown'),
        ('completed', 'Completed'),
    ]

    table = models.ForeignKey(PokerTable, on_delete=models.CASCADE, related_name='hands')
    hand_number = models.PositiveIntegerField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='preflop')
    dealer_seat = models.PositiveSmallIntegerField()
    community_cards = models.CharField(max_length=30, blank=True)
    pot = models.PositiveIntegerField(default=0)
    side_pots = models.JSONField(default=list, blank=True)
    player_hands = models.JSONField(default=dict, blank=True)
    current_seat = models.PositiveSmallIntegerField(default=0)
    current_bet = models.PositiveIntegerField(default=0)
    last_raise = models.PositiveIntegerField(default=0)
    winner_ids = models.JSONField(default=list, blank=True)
    round_bets = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-hand_number']
        constraints = [
            models.UniqueConstraint(fields=['table', 'hand_number'], name='unique_table_hand'),
        ]

    def __str__(self):
        return f'Hand #{self.hand_number} at Table #{self.table_id}'


class PokerAction(models.Model):
    ACTION_CHOICES = [
        ('fold', 'Fold'),
        ('check', 'Check'),
        ('call', 'Call'),
        ('bet', 'Bet'),
        ('raise', 'Raise'),
        ('all_in', 'All In'),
        ('post_blind', 'Post Blind'),
    ]

    hand = models.ForeignKey(PokerHand, on_delete=models.CASCADE, related_name='actions')
    player = models.ForeignKey(PokerPlayer, on_delete=models.CASCADE, related_name='actions')
    action = models.CharField(max_length=10, choices=ACTION_CHOICES)
    amount = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'{self.player.user.username}: {self.action} {self.amount}'
