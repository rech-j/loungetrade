from django.contrib import admin

from .models import Transaction


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('sender', 'receiver', 'amount', 'tx_type', 'created_at')
    list_filter = ('tx_type', 'created_at')
    search_fields = ('sender__username', 'receiver__username', 'note')
    readonly_fields = ('created_at',)
