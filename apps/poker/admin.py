from django.contrib import admin

from .models import PokerAction, PokerHand, PokerPlayer, PokerTable


@admin.register(PokerTable)
class PokerTableAdmin(admin.ModelAdmin):
    list_display = ('pk', 'creator', 'stake', 'status', 'hand_number', 'created_at')
    list_filter = ('status',)
    list_select_related = ('creator',)
    readonly_fields = ('created_at', 'started_at', 'ended_at')


@admin.register(PokerPlayer)
class PokerPlayerAdmin(admin.ModelAdmin):
    list_display = ('user', 'table', 'seat', 'chips', 'status', 'coins_invested')
    list_filter = ('status',)
    list_select_related = ('user', 'table')


@admin.register(PokerHand)
class PokerHandAdmin(admin.ModelAdmin):
    list_display = ('table', 'hand_number', 'status', 'pot', 'created_at')
    list_filter = ('status',)
    list_select_related = ('table',)


@admin.register(PokerAction)
class PokerActionAdmin(admin.ModelAdmin):
    list_display = ('hand', 'player', 'action', 'amount', 'created_at')
    list_select_related = ('hand', 'player', 'player__user')
