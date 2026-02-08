from django.contrib import admin

from .models import GameChallenge


@admin.register(GameChallenge)
class GameChallengeAdmin(admin.ModelAdmin):
    list_display = ('challenger', 'opponent', 'stake', 'status', 'winner', 'created_at')
    list_filter = ('status',)
    search_fields = ('challenger__username', 'opponent__username')
    readonly_fields = ('created_at', 'resolved_at')
