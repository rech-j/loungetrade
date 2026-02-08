from django.conf import settings
from django.db import models


class UserProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='profile',
    )
    display_name = models.CharField(max_length=30, blank=True)
    avatar = models.ImageField(upload_to='avatars/', blank=True)
    balance = models.PositiveIntegerField(default=0)
    is_admin_user = models.BooleanField(default=False)
    name_changed_at = models.DateTimeField(null=True, blank=True)
    dark_mode = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.get_display_name()

    def get_display_name(self):
        return self.display_name or self.user.username
