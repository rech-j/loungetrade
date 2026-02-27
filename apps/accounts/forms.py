import logging
import os

from django import forms
from django.conf import settings
from django.utils import timezone
from PIL import Image

from .models import UserProfile

logger = logging.getLogger(__name__)


class ProfileEditForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['display_name', 'avatar']
        widgets = {
            'display_name': forms.TextInput(attrs={
                'class': 'vintage-input',
                'placeholder': 'Display name',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['avatar'].widget.attrs.update({
            'class': 'block w-full text-sm text-slate file:mr-4 file:py-2 file:px-4 '
                     'file:border-0 file:bg-gold file:text-ink '
                     'file:cursor-pointer hover:file:bg-gold-dark hover:file:text-cream',
            'accept': 'image/*',
        })

    ALLOWED_AVATAR_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}

    def clean_avatar(self):
        avatar = self.cleaned_data.get('avatar')
        max_size = getattr(settings, 'AVATAR_MAX_SIZE', 2 * 1024 * 1024)
        if avatar and hasattr(avatar, 'size'):
            if avatar.size > max_size:
                raise forms.ValidationError('Image must be under 2MB.')
            ext = os.path.splitext(avatar.name)[1].lower()
            if ext not in self.ALLOWED_AVATAR_EXTENSIONS:
                raise forms.ValidationError(
                    'Unsupported file type. Please upload a JPG, PNG, GIF, or WebP.'
                )
        return avatar

    def clean_display_name(self):
        name = self.cleaned_data.get('display_name')
        cooldown_seconds = getattr(settings, 'NAME_CHANGE_COOLDOWN_SECONDS', 86400)
        if name and self.instance.display_name != name:
            if self.instance.name_changed_at:
                cooldown = timezone.now() - self.instance.name_changed_at
                if cooldown.total_seconds() < cooldown_seconds:
                    hours_left = int((cooldown_seconds - cooldown.total_seconds()) / 3600)
                    raise forms.ValidationError(
                        f'You can change your name again in {hours_left} hours.'
                    )
        return name

    def save(self, commit=True):
        profile = super().save(commit=False)
        if 'display_name' in self.changed_data:
            profile.name_changed_at = timezone.now()
        if commit:
            profile.save()
        # Resize avatar after save
        if 'avatar' in self.changed_data and profile.avatar:
            self._resize_avatar(profile)
        return profile

    def _resize_avatar(self, profile):
        max_dim = getattr(settings, 'AVATAR_MAX_DIMENSION', 400)
        try:
            img = Image.open(profile.avatar.path)
            if img.width > max_dim or img.height > max_dim:
                img.thumbnail((max_dim, max_dim), Image.LANCZOS)
                img.save(profile.avatar.path, quality=85)
        except (OSError, IOError) as e:
            logger.warning('Avatar resize failed for user %s: %s', profile.user.username, e)
