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
