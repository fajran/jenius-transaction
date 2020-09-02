import re

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from jajan.account.models import Account
from jajan.history.models import Transaction

from jenius.transaction.parser import Parser

class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('--user-id', required=True, type=int)
        parser.add_argument('--file', required=True, type=str)

    def handle(self, *args, **options):
        user_id = options['user_id']
        user = User.objects.get(pk=user_id)

        inp = options['file']
        with open(inp, 'rb') as f:
            p = Parser()
            data = p.parse(f)

            try:
                card_number = re.sub(r'\s+', '', data.details['card_number'])
                account = Account.objects.get(user=user, name=data.details['account'], card_number=card_number)

                self.stdout.write(self.style.SUCCESS('Found existing account: {} ({})'.format(account.name, account.card_number)))
            except Account.DoesNotExist:
                account = Account(user=user,
                        name=data.details['account'],
                        custom_name=None,
                        number=data.details['account_number'],
                        currency=data.details['currency'],
                        cashtag=data.details['cashtag'],
                        card_number=card_number)
                account.save()

                self.stdout.write(self.style.SUCCESS('Created a new account: {} ({})'.format(account.name, account.card_number)))

            for item in data.transactions:
                try:
                    tx = Transaction.objects.get(account=account, transaction_id=item['id'])

                    if tx.category != item['category']:
                        tx['category'] = item['category']
                        tx.save()
                        self.stdout.write('Updated category on transaction {}'.format(tx.transaction_id))

                    else:
                        self.stdout.write('Found existing transaction {}'.format(tx.transaction_id))


                except Transaction.DoesNotExist:
                    tx = Transaction(account=account,
                            transaction_id=item['id'],
                            amount=item['amount'],
                            category=item['category'],
                            timestamp=item['date'],
                            description=item['description'],
                            note=item['note'],
                            exchange_rate=item['rate'],
                            reference=item['reference'],
                            currency=item['currency'],
                            transaction_currency=item['transaction_currency'],
                            type=item['type'],
                            custom_category=None)
                    tx.save()

                    self.stdout.write('Stored a new transaction {}'.format(tx.transaction_id))

