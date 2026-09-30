import os

file_path = r"c:\Users\Varsha\Ahinsadham\Ahinsadham-main\heart_charity\templatetags\custom_tags.py"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

old = '''@register.simple_tag(takes_context=True)
def url_replace(context, field, value):
    dict_ = context['request'].GET.copy()
    dict_[field] = value
    return dict_.urlencode()'''

new = '''@register.simple_tag(takes_context=True)
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
    return dict_.urlencode()'''

content = content.replace(old, new).replace(old.replace('\n', '\r\n'), new)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Done")
