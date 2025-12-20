from django import template
from num2words import num2words

register = template.Library()

@register.filter
def get_item(dictionary, key):
    if isinstance(dictionary, dict):
        return dictionary.get(key)
    return None



@register.filter(name='number_to_words')
def number_to_words(value):
    """Convert a number to words in English"""
    try:
        amount = float(value)
        words = num2words(amount, lang='en_IN')
        return words.title() + " Rupees Only"
    except (ValueError, TypeError):
        return ""
