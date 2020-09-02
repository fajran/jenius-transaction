from django.contrib import admin

from .models import Transaction

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    def user(obj):
        return obj.account.user

    def account(obj):
        return obj.account.name

    def card_number(obj):
        return obj.account.card_number

    list_display = ('id', 'timestamp', user, account, card_number, 'transaction_id', 'category', 'amount')

