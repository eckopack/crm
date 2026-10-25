"""Template-Filter für den Produktionsbericht-Workflow (26.10.2026) - genutzt in base.html,
um MA (Gruppe "Produktion", technisch ohnehin auf die Eingabemaske beschränkt, siehe
vertrieb/middleware.py) eine stark vereinfachte Navigation zu zeigen statt der vollen
CRM-Navigation, die sie wegen der Middleware-Sperre größtenteils gar nicht nutzen könnten."""

from django import template

from ..produktionsleiter import ist_nur_produktion as _ist_nur_produktion
from ..produktionsleiter import ist_produktionsleiter as _ist_produktionsleiter

register = template.Library()


@register.filter(name="ist_nur_produktion")
def ist_nur_produktion(user):
    return _ist_nur_produktion(user)


@register.filter(name="ist_produktionsleiter")
def ist_produktionsleiter(user):
    return _ist_produktionsleiter(user)


@register.filter(name="offene_produktionsberichte")
def offene_produktionsberichte(user):
    """Anzahl der auf Freigabe wartenden Produktionsberichte, als kleiner Zähler neben dem
    Navigationslink (26.10.2026, Björns Rückfrage "was fehlt noch..." - vorher gab es in der
    Navigation keinerlei Hinweis darauf, dass überhaupt etwas auf Freigabe wartet). Nur für
    den Produktionsleiter berechnet - für alle anderen (inkl. MA) ohnehin 0, da der
    zugehörige Navigationspunkt in base.html nur für ist_produktionsleiter gerendert wird."""
    if not _ist_produktionsleiter(user):
        return 0
    from ..models import Produktionsbericht

    return Produktionsbericht.objects.filter(status="eingereicht").count()
