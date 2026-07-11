from social_django.middleware import SocialAuthExceptionMiddleware
from social_core.exceptions import AuthForbidden
from django.shortcuts import render

class CustomSocialAuthExceptionMiddleware(SocialAuthExceptionMiddleware):
    def process_exception(self, request, exception):
        if isinstance(exception, AuthForbidden):
            # Catch AuthForbidden and render a premium, creative custom error page
            return render(request, "auth_forbidden.html", status=403)
        return super().process_exception(request, exception)
