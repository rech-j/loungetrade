import logging
import os

from django import forms
from django.conf import settings
from django.utils import timezone
from PIL import Image, ImageOps

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

    crop_x = forms.FloatField(widget=forms.HiddenInput(), required=False)
    crop_y = forms.FloatField(widget=forms.HiddenInput(), required=False)
    crop_width = forms.FloatField(widget=forms.HiddenInput(), required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['avatar'].widget = forms.FileInput(attrs={
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
            # Verify the file is a real, uncorrupted image before accepting it.
            # This catches polyglot files (valid header + malicious payload) before
            # anything is written to disk.
            try:
                img = Image.open(avatar)
                img.verify()
            except Exception:
                raise forms.ValidationError('Invalid or corrupt image file.')
            finally:
                # verify() consumes the file pointer; reset so Django can save it.
                avatar.seek(0)
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
        if 'avatar' in self.changed_data and profile.avatar:
            x = self.cleaned_data.get('crop_x')
            y = self.cleaned_data.get('crop_y')
            w = self.cleaned_data.get('crop_width')
            crop_data = {'x': x, 'y': y, 'width': w} if all(v is not None for v in (x, y, w)) else None
            self._resize_avatar(profile, crop_data)
        return profile

    def _resize_avatar(self, profile, crop_data=None):
        max_dim = getattr(settings, 'AVATAR_MAX_DIMENSION', 400)
        try:
            img = Image.open(profile.avatar.path)
            img = ImageOps.exif_transpose(img)
            if crop_data:
                x = max(0, int(crop_data['x']))
                y = max(0, int(crop_data['y']))
                w = int(crop_data['width'])
                if w > 0:
                    img = img.crop((x, y, x + w, y + w))
            if img.width > max_dim or img.height > max_dim:
                img.thumbnail((max_dim, max_dim), Image.LANCZOS)
            img.save(profile.avatar.path, quality=85)
        except (OSError, IOError) as e:
            logger.warning('Avatar resize failed for user %s: %s', profile.user.username, e)
            # Delete the file rather than leaving an unprocessed upload on disk.
            try:
                profile.avatar.delete(save=True)
            except Exception:
                logger.warning('Failed to delete avatar after resize error for user %s', profile.user.username)
