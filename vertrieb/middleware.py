"""26.10.2026, auf Wunsch von Björn (Produktionsbericht-Pilot Trinkhalm-L1): MA bekommen
eigene CRM-Logins (Gruppe "Produktion"), sollen damit aber NUR die Produktionsbericht-
Eingabemaske/-liste sehen - keine Kunden-, Preis- oder Rechnungsdaten. Das wird hier
technisch durchgesetzt (nicht nur durch Ausblenden von Navigationslinks), damit ein direkt
aufgerufener Link/URL nicht versehentlich mehr zeigt als vorgesehen.

Mitglieder der Gruppe "Produktionsleiter" (siehe .produktionsleiter) sowie Superuser sind
ausgenommen, auch wenn sie zusätzlich in der Gruppe "Produktion" wären. Zusätzlicher,
unabhängiger Schutz: neue MA-Konten bekommen is_staff=False, damit /admin/ für sie ohnehin
nicht erreichbar ist (Django verlangt dort is_staff) - diese Middleware ist also keine
alleinige Verteidigungslinie, sondern eine zusätzliche."""
from django.shortcuts import redirect
from django.urls import Resolver404, resolve, reverse

from .produktionsleiter import ist_nur_produktion

ERLAUBTE_URL_NAMEN_FUER_PRODUKTION = {
    "vertrieb:produktionsbericht_erfassen",
    "vertrieb:produktionsbericht_list",
    "vertrieb:produktionsbericht_detail",
    "vertrieb:produktionsbericht_pdf",
    # 25.10.2026 (Korrektur-Workflow): MA müssen einen abgelehnten eigenen Bericht
    # bearbeiten können - produktionsbericht_korrigieren selbst prüft zusätzlich, dass nur
    # der ursprüngliche Einreicher zugreift (siehe views.py).
    "vertrieb:produktionsbericht_korrigieren",
    "logout",
}


class ProduktionszugriffMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_authenticated", False) and ist_nur_produktion(user):
            try:
                match = resolve(request.path_info)
            except Resolver404:
                match = None
            url_name = None
            if match is not None:
                url_name = f"{match.namespace}:{match.url_name}" if match.namespace else match.url_name
            if url_name not in ERLAUBTE_URL_NAMEN_FUER_PRODUKTION:
                return redirect(reverse("vertrieb:produktionsbericht_list"))
        return self.get_response(request)
