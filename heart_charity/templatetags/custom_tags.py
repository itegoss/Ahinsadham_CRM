from django import template
from num2words import num2words

register = template.Library()

@register.filter
def get_item(dictionary, key):
    if isinstance(dictionary, dict):
        return dictionary.get(key)
    return None

@register.filter
def number_to_words(value):
    """Convert a number to words in English"""
    try:
        amount = float(value)
        # Convert to words and capitalize
        words = num2words(amount, to='cardinal', lang='en')
        return words.capitalize() + " Rupees Only"
    except (ValueError, TypeError):
        return str(value)
