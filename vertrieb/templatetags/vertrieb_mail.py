"""Eigene Template-Filter fuer HTML-Mail-Vorlagen (24.10.2026, auf Wunsch von Björn: "kein
Zeilenumbruch... nur Fließtext... nicht schön" zur Angebot-Versandmail).

Ursache des gemeldeten Problems: Django's eingebauter |linebreaks-Filter erzeugt pro Absatz
ein nacktes <p>...</p> OHNE Inline-Style. In normalem HTML reicht das (Browser wenden den
Standard-<p>-Rand an), aber viele E-Mail-Clients (u.a. diverse Webmailer) entfernen oder
ignorieren Standard-Rand-Stile bei <p> - das Ergebnis ist ein Block ohne sichtbaren
Absatzabstand, der wie ununterbrochener Fließtext wirkt. Alle anderen Mail-Vorlagen in diesem
Projekt umgehen das, indem JEDES <p> seinen Rand per Inline-style="margin:...` explizit selbst
mitbringt (siehe z. B. musterversand_bestaetigung.html) - genau das macht dieser Filter auch
für dynamisch aus der Datenbank kommenden Text (AngebotNachfassVorlage.text,
MusterboxNachfassVorlage.text), wo bisher der nackte |linebreaks-Filter verwendet wurde."""

from django import template
from django.utils.html import linebreaks
from django.utils.safestring import mark_safe

register = template.Library()

# Gleicher Stil wie die fest im Template stehenden Absaetze (siehe z. B.
# angebot_versand.html, musterversand_bestaetigung.html) - Rand nur unten, damit sich
# Abstaende zwischen aufeinanderfolgenden Absaetzen nicht verdoppeln.
_ABSATZ_STYLE = "margin:0 0 16px 0; font-size:16px; color:#3c3c3b; line-height:1.5;"


@register.filter(name="email_absaetze", is_safe=True)
def email_absaetze(text):
    """Wie der eingebaute |linebreaks-Filter, aber jedes erzeugte <p> traegt sein
    Rand-Styling als Inline-style mit sich - robust auch in E-Mail-Clients, die
    Standard-<p>-Raender ignorieren oder entfernen."""
    html = linebreaks(text or "", autoescape=True)
    html = html.replace("<p>", f'<p style="{_ABSATZ_STYLE}">')
    return mark_safe(html)
