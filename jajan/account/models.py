from django.contrib.auth.models import User
from django.db import models

class Account(models.Model):
    class Meta:
        unique_together = (('user', 'name', 'card_number',),)

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=50)
    custom_name = models.CharField(max_length=50, null=True)
    number = models.CharField(max_length=50)
    currency = models.CharField(max_length=3)
    cashtag = models.CharField(max_length=50)
    card_number = models.CharField(max_length=16)

    def __str__(self):
        return '{} / {} ({})'.format(self.user.username, self.name, self.card_number)

