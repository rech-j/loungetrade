import re

from django import template

register = template.Library()


@register.simple_tag
def get_challenge_id(link):
    """Extract a challenge ID from a coin flip play link like /coinflip/play/42/."""
    match = re.search(r'/coinflip/play/(\d+)/', link or '')
    return int(match.group(1)) if match else None
