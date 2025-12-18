from django.apps import AppConfig


class HeartCharityConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "heart_charity"

    def ready(self):
        import heart_charity.signals

