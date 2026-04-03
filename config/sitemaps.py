from django.contrib.sitemaps import Sitemap
from django.urls import reverse


class StaticViewSitemap(Sitemap):
    protocol = 'https'

    def items(self):
        return [
            ('landing', 1.0, 'daily'),
            ('account_login', 0.3, 'monthly'),
            ('account_signup', 0.3, 'monthly'),
            ('leaderboard', 0.8, 'hourly'),
        ]

    def location(self, item):
        return reverse(item[0])

    def priority(self, item):
        return item[1]

    def changefreq(self, item):
        return item[2]
