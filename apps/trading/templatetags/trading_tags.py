"""Custom template tags and filters for trading app."""

from django import template

register = template.Library()


@register.filter
def get_item(dictionary: dict, key: str):
    """
    Get an item from a dictionary by key.

    Usage: {{ my_dict|get_item:key_variable }}

    Args:
        dictionary: The dictionary to look up
        key: The key to retrieve

    Returns:
        The value for the key, or None if not found
    """
    if dictionary is None:
        return None
    return dictionary.get(key)
