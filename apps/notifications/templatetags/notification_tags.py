import re

from django import template

register = template.Library()

ICON_MAP = {
    'coin_received': '\u2733',  # star
    'game_invite': '\u2694',    # crossed swords
    'game_result': '\u265B',    # crown/queen
}


@register.filter
def notif_icon(notif_type):
    """Return a Unicode icon for a notification type."""
    return ICON_MAP.get(notif_type, '\u2022')


@register.simple_tag
def get_game_info(link):
    """Parse a notification link and return a dict with game_type and game_id."""
    if not link:
        return None

    patterns = [
        (r'/chess/play/(\d+)/', 'chess'),
        (r'/coinflip/play/(\d+)/', 'coinflip'),
        (r'/poker/play/(\d+)/', 'poker'),
    ]
    for pattern, game_type in patterns:
        match = re.search(pattern, link)
        if match:
            return {'game_type': game_type, 'game_id': int(match.group(1))}
    return None
