from django.contrib import admin
from .models import ChessGame

@admin.register(ChessGame)
class ChessGameAdmin(admin.ModelAdmin):
    list_display = ('white_player', 'black_player', 'stake', 'status', 'winner', 'created_at')
    list_filter = ('status',)
    readonly_fields = ('created_at', 'started_at', 'ended_at')
