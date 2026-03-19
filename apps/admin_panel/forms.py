from django import forms


class BalanceAdjustmentForm(forms.Form):
    amount = forms.IntegerField(
        widget=forms.NumberInput(attrs={
            'class': 'vintage-input',
            'placeholder': 'Positive to add, negative to deduct',
        }),
    )
    note = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={
            'class': 'vintage-input',
            'placeholder': 'Reason for adjustment (required)',
        }),
    )

    def clean_amount(self):
        amount = self.cleaned_data['amount']
        if amount == 0:
            raise forms.ValidationError('Amount cannot be zero.')
        return amount


class RefundForm(forms.Form):
    user_id = forms.IntegerField(widget=forms.HiddenInput())
    amount = forms.IntegerField(
        min_value=1,
        widget=forms.NumberInput(attrs={
            'class': 'vintage-input',
            'placeholder': 'Amount to refund',
        }),
    )
    note = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={
            'class': 'vintage-input',
            'placeholder': 'Reason for refund (required)',
        }),
    )
