from django import template

register = template.Library()


@register.filter
def percentage(value, total):
    """Return value as a percentage of total, formatted to 1 decimal place."""
    try:
        return f'{(value / total) * 100:.1f}'
    except (ZeroDivisionError, TypeError):
        return '0.0'


@register.filter
def intcomma_short(value):
    """Format large numbers with K/M suffixes."""
    try:
        value = int(value)
    except (ValueError, TypeError):
        return value
    if value >= 1_000_000:
        return f'{value / 1_000_000:.1f}M'
    if value >= 10_000:
        return f'{value / 1_000:.1f}K'
    return f'{value:,}'
