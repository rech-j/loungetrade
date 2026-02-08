from django import forms


INPUT_CLASSES = (
    'w-full px-3 py-2 border border-stone rounded-lg bg-cream text-ink '
    'dark:bg-ink dark:text-cream dark:border-slate focus:outline-none '
    'focus:ring-2 focus:ring-gold'
)


class TradeForm(forms.Form):
    recipient_username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': INPUT_CLASSES,
            'placeholder': 'Search for a user...',
            'autocomplete': 'off',
            'hx-get': '/profile/search/',
            'hx-trigger': 'keyup changed delay:300ms',
            'hx-target': '#user-results',
        }),
    )
    amount = forms.IntegerField(
        min_value=1,
        widget=forms.NumberInput(attrs={
            'class': INPUT_CLASSES,
            'placeholder': 'Amount',
        }),
    )
    note = forms.CharField(
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={
            'class': INPUT_CLASSES,
            'placeholder': 'Note (optional)',
        }),
    )


class MintForm(forms.Form):
    recipient_username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': INPUT_CLASSES,
            'placeholder': 'Username to mint to...',
            'autocomplete': 'off',
            'hx-get': '/profile/search/',
            'hx-trigger': 'keyup changed delay:300ms',
            'hx-target': '#user-results',
        }),
    )
    amount = forms.IntegerField(
        min_value=1,
        widget=forms.NumberInput(attrs={
            'class': INPUT_CLASSES,
            'placeholder': 'Amount to mint',
        }),
    )
    note = forms.CharField(
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={
            'class': INPUT_CLASSES,
            'placeholder': 'Note (optional)',
        }),
    )
