import csv

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import render

from apps.accounts.decorators import rate_limit

from .forms import MintForm, TradeForm
from .models import Transaction
from .services import InsufficientFunds, InvalidTrade, mint_coins, transfer_coins


@login_required
@rate_limit('trade', max_requests=20, window=60)
def trade_view(request):
    if request.method == 'POST':
        form = TradeForm(request.POST)
        if form.is_valid():
            try:
                recipient = User.objects.get(
                    username=form.cleaned_data['recipient_username']
                )
                transfer_coins(
                    sender=request.user,
                    receiver=recipient,
                    amount=form.cleaned_data['amount'],
                    note=form.cleaned_data.get('note', ''),
                )
                messages.success(
                    request,
                    f'Sent {form.cleaned_data["amount"]} coins to {recipient.username}.'
                )
                form = TradeForm()
            except User.DoesNotExist:
                messages.error(request, 'User not found.')
            except (InsufficientFunds, InvalidTrade) as e:
                messages.error(request, str(e))
    else:
        form = TradeForm()

    return render(request, 'economy/trade.html', {
        'form': form,
        'balance': request.user.profile.balance,
    })


@login_required
@rate_limit('mint', max_requests=30, window=60)
def mint_view(request):
    if not request.user.profile.is_admin_user:
        return HttpResponseForbidden('Access denied.')

    if request.method == 'POST':
        form = MintForm(request.POST)
        if form.is_valid():
            try:
                target = User.objects.get(
                    username=form.cleaned_data['recipient_username']
                )
                mint_coins(
                    admin_user=request.user,
                    target_user=target,
                    amount=form.cleaned_data['amount'],
                    note=form.cleaned_data.get('note', ''),
                )
                messages.success(
                    request,
                    f'Minted {form.cleaned_data["amount"]} coins to {target.username}.'
                )
                form = MintForm()
            except User.DoesNotExist:
                messages.error(request, 'User not found.')
            except InvalidTrade as e:
                messages.error(request, str(e))
    else:
        form = MintForm()

    return render(request, 'economy/mint.html', {'form': form})


@login_required
def history_view(request):
    transactions = Transaction.objects.filter(
        Q(sender=request.user) | Q(receiver=request.user)
    ).select_related('sender', 'receiver').order_by('-created_at')

    tx_filter = request.GET.get('filter', 'all')
    if tx_filter == 'sent':
        transactions = transactions.filter(sender=request.user)
    elif tx_filter == 'received':
        transactions = transactions.filter(receiver=request.user)
    elif tx_filter == 'games':
        transactions = transactions.filter(tx_type__in=['game_win', 'game_loss'])

    paginator = Paginator(transactions, 25)
    page_number = request.GET.get('page')
    page = paginator.get_page(page_number)

    return render(request, 'economy/history.html', {
        'page': page,
        'current_filter': tx_filter,
    })


@login_required
def export_transactions(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="transactions.csv"'
    writer = csv.writer(response)
    writer.writerow(['Date', 'Type', 'From', 'To', 'Amount', 'Note'])
    for tx in Transaction.objects.filter(
        Q(sender=request.user) | Q(receiver=request.user)
    ).select_related('sender', 'receiver').order_by('-created_at'):
        writer.writerow([
            tx.created_at.strftime('%Y-%m-%d %H:%M'),
            tx.get_tx_type_display(),
            tx.sender.username if tx.sender else 'System',
            tx.receiver.username if tx.receiver else '',
            tx.amount,
            tx.note,
        ])
    return response
