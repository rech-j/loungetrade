import re

from django import template

register = template.Library()


@register.simple_tag
def get_challenge_id(link):
    """Extract a challenge ID from a game play link like /games/play/42/."""
    match = re.search(r'/games/play/(\d+)/', link or '')
    return int(match.group(1)) if match else None
