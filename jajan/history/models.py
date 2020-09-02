from django.db import models

from jajan.account.models import Account

class Transaction(models.Model):
    class Meta:
        unique_together = (('account', 'transaction_id',),)

    account = models.ForeignKey(Account, on_delete=models.CASCADE)
    transaction_id = models.CharField(max_length=50)

    amount = models.DecimalField(decimal_places=2, max_digits=15)
    category = models.CharField(max_length=50)
    timestamp = models.DateTimeField()
    description = models.CharField(max_length=50)
    note = models.CharField(max_length=50, null=True)
    exchange_rate = models.DecimalField(decimal_places=2, max_digits=15)
    reference = models.CharField(max_length=50, null=True)
    currency = models.CharField(max_length=3)
    transaction_currency = models.CharField(max_length=3)
    type = models.CharField(max_length=50)
    custom_category = models.CharField(max_length=50, null=True)

