import django.views


class StatusPage(django.views.View):  # DCA-HEX-018: a class-based view outside the incoming adapters
    def get(self) -> str:
        return "ok"
