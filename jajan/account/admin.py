from django.contrib import admin

from .models import Account

@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    def user(obj):
        return '{} (id={})'.format(obj.user.username, obj.user.id)

    list_display = ('id', user, 'name', 'card_number')

