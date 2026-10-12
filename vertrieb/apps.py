from django.apps import AppConfig


class VertriebConfig(AppConfig):
    name = "vertrieb"

    def ready(self):
        from . import signals  # noqa: F401
