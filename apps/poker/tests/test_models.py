from django.contrib.auth.models import User
from django.db import IntegrityError
from django.test import TestCase

from apps.poker.models import PokerPlayer, PokerTable


class PokerTableModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('alice', password='pass')

    def test_create_table(self):
        table = PokerTable.objects.create(creator=self.user, stake=100)
        self.assertEqual(table.status, 'pending')
        self.assertEqual(table.starting_chips, 1000)
        self.assertEqual(table.small_blind, 10)
        self.assertEqual(table.big_blind, 20)

    def test_str(self):
        table = PokerTable.objects.create(creator=self.user, stake=50)
        self.assertIn('50 LC', str(table))


class PokerPlayerModelTest(TestCase):
    def setUp(self):
        self.user1 = User.objects.create_user('alice', password='pass')
        self.user2 = User.objects.create_user('bob', password='pass')
        self.table = PokerTable.objects.create(creator=self.user1, stake=100)

    def test_unique_seat(self):
        PokerPlayer.objects.create(table=self.table, user=self.user1, seat=0, chips=1000)
        with self.assertRaises(IntegrityError):
            PokerPlayer.objects.create(table=self.table, user=self.user2, seat=0, chips=1000)

    def test_unique_user(self):
        PokerPlayer.objects.create(table=self.table, user=self.user1, seat=0, chips=1000)
        with self.assertRaises(IntegrityError):
            PokerPlayer.objects.create(table=self.table, user=self.user1, seat=1, chips=1000)
