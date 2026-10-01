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

@register.simple_tag(takes_context=True)
def url_replace(context, field, value):
    request = context.get('request')
    if request:
        dict_ = request.GET.copy()
    else:
        from django.http import QueryDict
        dict_ = QueryDict('', mutable=True)
    dict_[field] = value
    if 'active_tab' in context and 'active_tab' not in dict_:
        dict_['active_tab'] = context['active_tab']
    return dict_.urlencode()

@register.filter
def safe_url(file_field):
    if not file_field:
        return ""
    try:
        url = file_field.url
        if url:
            return url
    except Exception:
        pass
    try:
        name = getattr(file_field, 'name', None)
        if name:
            from django.conf import settings
            bucket = getattr(settings, 'GS_BUCKET_NAME', 'ahinsadham-media')
            return f"https://storage.googleapis.com/{bucket}/{name}"
    except Exception:
        pass
    return ""
