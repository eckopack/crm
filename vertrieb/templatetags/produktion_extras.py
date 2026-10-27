"""Template-Filter für den Produktionsbericht-Workflow (26.10.2026) - genutzt in base.html,
um MA (Gruppe "Produktion", technisch ohnehin auf die Eingabemaske beschränkt, siehe
vertrieb/middleware.py) eine stark vereinfachte Navigation zu zeigen statt der vollen
CRM-Navigation, die sie wegen der Middleware-Sperre größtenteils gar nicht nutzen könnten.

Seit 27.10.2026 zusätzlich: der Template-Tag {% t "schluessel" %} für die Übersetzung der
MA-Oberfläche (Tschechisch/Ukrainisch, siehe produktion_sprachen.py) ins Deutsche/die
jeweils aktive Sprache - liest "ma_sprache" aus dem Request-Kontext (siehe
context_processors.ma_sprache), damit die Templates selbst nichts von der aktiven Sprache
wissen müssen."""

from django import template

from ..produktion_sprachen import uebersetzen as _uebersetzen
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


@register.simple_tag(takes_context=True, name="t")
def t(context, schluessel):
    """{% t "formular.einreichen" %} - siehe Moduldoku oben. Fällt auf "de" zurück, wenn
    "ma_sprache" aus irgendeinem Grund im Kontext fehlt (z. B. ein Template, das außerhalb
    einer normalen Request-Verarbeitung gerendert wird)."""
    sprache = context.get("ma_sprache", "de")
    return _uebersetzen(schluessel, sprache)


@register.simple_tag(takes_context=True, name="t_feld")
def t_feld(context, prefix, code):
    """{% t_feld "schicht" bericht.schicht %} übersetzt einen Wahlfeld-Code (z. B.
    prefix="schicht", code="frueh" -> Schlüssel "schicht.frueh") in die aktive Sprache -
    siehe UEBERSETZUNGEN in produktion_sprachen.py. Ein leerer Code (z. B. nicht gesetzter
    Ausschussgrund) wird zu "<prefix>.leer"."""
    sprache = context.get("ma_sprache", "de")
    schluessel = f"{prefix}.{code}" if code else f"{prefix}.leer"
    return _uebersetzen(schluessel, sprache)
