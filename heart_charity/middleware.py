from social_django.middleware import SocialAuthExceptionMiddleware
from social_core.exceptions import AuthForbidden
from django.shortcuts import render

class CustomSocialAuthExceptionMiddleware(SocialAuthExceptionMiddleware):
    def process_exception(self, request, exception):
        if isinstance(exception, AuthForbidden):
            # Catch AuthForbidden and render a premium, creative custom error page
            return render(request, "auth_forbidden.html", status=403)
        return super().process_exception(request, exception)


class UTMAttributionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        utm_params = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term', 'utm_id']
        # Check if any UTM parameter is present in GET query params
        if any(param in request.GET for param in utm_params):
            for param in utm_params:
                val = request.GET.get(param)
                if val:
                    request.session[param] = val
        response = self.get_response(request)
        return response

