from django import forms
from django.contrib.auth.models import User


INPUT_CLASSES = 'vintage-input'


class TradeForm(forms.Form):
    recipient_username = forms.CharField(
        max_length=150,
        min_length=1,
        widget=forms.TextInput(attrs={
            'id': 'id_recipient_username',
            'class': INPUT_CLASSES,
            'placeholder': 'Search for a user...',
            'autocomplete': 'off',
            'spellcheck': 'false',
            'autocapitalize': 'none',
            'inputmode': 'search',
            'aria-controls': 'user-results',
            'hx-get': '/profile/search/',
            'hx-trigger': 'keyup changed delay:300ms',
            'hx-target': '#user-results',
            'hx-vals': 'js:{q: event.target.value}',
        }),
    )
    amount = forms.IntegerField(
        min_value=1,
        max_value=1000000,
        widget=forms.NumberInput(attrs={
            'id': 'id_amount',
            'class': INPUT_CLASSES,
            'placeholder': 'Amount',
            'min': '1',
        }),
    )
    note = forms.CharField(
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={
            'id': 'id_note',
            'class': INPUT_CLASSES,
            'placeholder': 'Note (optional)',
            'maxlength': '200',
        }),
    )

    def clean_recipient_username(self):
        username = self.cleaned_data['recipient_username'].strip()
        if not User.objects.filter(username=username).exists():
            raise forms.ValidationError('User not found.')
        return username

    def clean_note(self):
        return self.cleaned_data['note'].strip()

class MintForm(forms.Form):
    recipient_username = forms.CharField(
        max_length=150,
        min_length=1,
        widget=forms.TextInput(attrs={
            'id': 'id_mint_recipient',
            'class': INPUT_CLASSES,
            'placeholder': 'Username to mint to...',
            'autocomplete': 'off',
            'spellcheck': 'false',
            'autocapitalize': 'none',
            'inputmode': 'search',
            'aria-controls': 'user-results',
            'hx-get': '/profile/search/',
            'hx-trigger': 'keyup changed delay:300ms',
            'hx-target': '#user-results',
            'hx-vals': 'js:{q: event.target.value}',
        }),
    )
    amount = forms.IntegerField(
        min_value=1,
        max_value=10000000,
        widget=forms.NumberInput(attrs={
            'id': 'id_mint_amount',
            'class': INPUT_CLASSES,
            'placeholder': 'Amount to mint',
            'min': '1',
        }),
    )
    note = forms.CharField(
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={
            'id': 'id_mint_note',
            'class': INPUT_CLASSES,
            'placeholder': 'Note (optional)',
            'maxlength': '200',
        }),
    )

    def clean_recipient_username(self):
        username = self.cleaned_data['recipient_username'].strip()
        if not User.objects.filter(username=username).exists():
            raise forms.ValidationError('User not found.')
        return username
    

    def clean_note(self):
        return self.cleaned_data['note'].strip()
