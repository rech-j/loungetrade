from django.contrib import admin

from .models import Transaction


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('sender', 'receiver', 'amount', 'tx_type', 'created_at')
    list_filter = ('tx_type', 'created_at')
    list_select_related = ('sender', 'receiver')
    search_fields = ('sender__username', 'receiver__username', 'note')
    raw_id_fields = ('sender', 'receiver')
    readonly_fields = ('created_at',)
