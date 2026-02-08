from io import BytesIO

from django import forms
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.utils import timezone
from PIL import Image

from .models import UserProfile

MAX_AVATAR_SIZE = 2 * 1024 * 1024  # 2MB
AVATAR_MAX_DIMENSION = 400


class ProfileEditForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['display_name', 'avatar']
        widgets = {
            'display_name': forms.TextInput(attrs={
                'class': 'w-full px-3 py-2 border border-stone rounded-lg bg-cream text-ink '
                         'dark:bg-ink dark:text-cream dark:border-slate focus:outline-none '
                         'focus:ring-2 focus:ring-gold',
                'placeholder': 'Display name',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['avatar'].widget.attrs.update({
            'class': 'block w-full text-sm text-slate file:mr-4 file:py-2 file:px-4 '
                     'file:rounded-lg file:border-0 file:bg-gold file:text-ink '
                     'file:cursor-pointer hover:file:bg-gold/80',
            'accept': 'image/*',
        })

    def clean_avatar(self):
        avatar = self.cleaned_data.get('avatar')
        if avatar and hasattr(avatar, 'size'):
            if avatar.size > MAX_AVATAR_SIZE:
                raise forms.ValidationError('Image must be under 2MB.')
        return avatar

    def clean_display_name(self):
        name = self.cleaned_data.get('display_name')
        if name and self.instance.display_name != name:
            if self.instance.name_changed_at:
                cooldown = timezone.now() - self.instance.name_changed_at
                if cooldown.total_seconds() < 86400:
                    hours_left = int((86400 - cooldown.total_seconds()) / 3600)
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
        try:
            img = Image.open(profile.avatar.path)
            if img.width > AVATAR_MAX_DIMENSION or img.height > AVATAR_MAX_DIMENSION:
                img.thumbnail((AVATAR_MAX_DIMENSION, AVATAR_MAX_DIMENSION), Image.LANCZOS)
                img.save(profile.avatar.path, quality=85)
        except Exception:
            pass  # Don't break profile save if resize fails
