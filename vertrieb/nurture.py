"""Nachfass-Automatik für Musterversand-Leads + Versand-Bestätigungsmail für echte Bestellungen.

Teil 1 (bestehend): Button 'Musterkarton anfordern' (views.musterkarton_anfordern) legt einen
Packschein mit ist_musterversand=True an. Sobald der im Lager auf 'versendet'
gesetzt wird (views.packschein_versand_bestaetigen), läuft hier:

1. Bestätigungsmail an den Lead (best effort – ein fehlender/kaputter E-Mail-Versand
   darf den Packvorgang nicht blockieren, deshalb try/except statt hartem Fehler).
2. Anlage der ersten wöchentlichen Nachfass-Aktivität (+7 Tage), die anschließend vom
   management command 'nachfass_pruefen' (wöchentlicher Cron, siehe render.yaml)
   verlängert wird, solange der Deal noch nicht tatsächlich versendet hat (siehe Teil 2).

Teil 2 (neu, 17.10.2026, auf Wunsch von Björn): Sobald ein echter Lieferschein (nicht nur
der Musterversand-Packschein) über views.lieferschein_versand_bestaetigen mit Trackingnummer
versehen wird, verschickt lieferschein_versand_abgeschlossen() eine eigene, als HTML gestaltete
Versand-Bestätigungsmail an den Kunden. Anders als bei Teil 1 wird hier KEINE neue Nachfass-
Aktivität angelegt - der echte Versand ist stattdessen das Ende der Nachfass-Kette (siehe
nachfass_pruefen.py: eine bestehende Kette wird nicht mehr verlängert, sobald irgendein
Lieferschein des Deals eine Trackingnummer hat).
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, send_mail
from django.template.loader import render_to_string
from django.utils import timezone

from .models import Aktivitaet

logger = logging.getLogger(__name__)

NACHFASS_INTERVALL_TAGE = 7

# Hardcoded wie beim NACHFASS-Cron in render.yaml - fuer absolute Links (Logo, Tracking) in
# E-Mails, die ausserhalb eines Request-Kontexts (also ohne request.build_absolute_uri)
# zusammengebaut werden.
SITE_URL = "https://eckopack-crm.onrender.com"


def _empfaenger_email(deal):
    """Bevorzugt den im Deal hinterlegten Ansprechpartner, sonst den Hauptansprechpartner
    der Firma, sonst die allgemeine Firmen-E-Mail. Gibt None zurück, wenn nichts davon
    eine E-Mail-Adresse hat."""
    if deal.kontakt and deal.kontakt.email:
        return deal.kontakt.email
    hauptkontakt = deal.firma.kontakte.filter(ist_hauptansprechpartner=True).first()
    if hauptkontakt and hauptkontakt.email:
        return hauptkontakt.email
    if deal.firma.email:
        return deal.firma.email
    return None


def musterversand_abgeschlossen(packschein):
    deal = packschein.deal
    empfaenger = _empfaenger_email(deal)

    if empfaenger:
        betreff = f"Ihr Musterkarton ist unterwegs – ECKO-PACK"
        zeilen = ["Guten Tag,", "", "Ihr Musterkarton ist auf dem Weg zu Ihnen"]
        if packschein.trackingnummer:
            versanddienstleister = packschein.get_versanddienstleister_display() or "Versanddienstleister"
            zeilen[-1] += f" ({versanddienstleister}, Sendungsnummer {packschein.trackingnummer})"
        zeilen[-1] += "."
        zeilen += ["", "Wir freuen uns auf weitere Gespräche.", "", "Mit freundlichen Grüßen", "Ihr ECKO-PACK Team"]
        text = "\n".join(zeilen)
        try:
            send_mail(betreff, text, settings.DEFAULT_FROM_EMAIL, [empfaenger], fail_silently=False)
        except Exception:
            logger.exception(
                "Musterversand-Bestaetigungsmail konnte nicht gesendet werden (Packschein %s)",
                packschein.nummer,
            )
        else:
            packschein.bestaetigungsmail_gesendet_am = timezone.now()
            packschein.save(update_fields=["bestaetigungsmail_gesendet_am"])
    else:
        logger.warning(
            "Kein Empfaenger (E-Mail) fuer Musterversand-Bestaetigungsmail gefunden (Packschein %s, Deal %s)",
            packschein.nummer, deal.pk,
        )

    Aktivitaet.objects.create(
        typ="nachfass",
        betreff=f"Nachfass Musterversand: {deal.firma.name}",
        beschreibung=(
            f"Musterkarton wurde am {packschein.versendet_am or timezone.now().date()} versendet "
            f"(Packschein {packschein.nummer}). Bitte nach einer Woche nachfassen. Wird automatisch "
            f"wöchentlich verlängert, bis der Deal verloren ist oder die eigentliche Bestellung "
            f"tatsächlich versendet wurde (Lieferschein mit Trackingnummer)."
        ),
        datum=timezone.now() + timedelta(days=NACHFASS_INTERVALL_TAGE),
        firma=deal.firma,
        kontakt=deal.kontakt,
        deal=deal,
        zustaendiger=deal.zustaendiger,
    )


def lieferschein_versand_abgeschlossen(lieferschein):
    """Verschickt die (HTML-gestaltete) Versand-Bestätigungsmail an den Kunden, sobald ein
    echter Lieferschein (views.lieferschein_versand_bestaetigen) eine Trackingnummer erhält.

    Gibt (erfolg: bool, fehlermeldung: str|None) zurück, damit der aufrufende View dem
    Nutzer sofort sichtbar machen kann, wenn der Versand zwar erfasst, die Mail aber NICHT
    rausgegangen ist (anders als bei musterversand_abgeschlossen() oben oder beim woechentlichen
    Nachfass-Cron wird hier bewusst NICHT fail-silent geloggt - das ist eine kundenseitige
    Benachrichtigung, Björn soll das direkt im UI sehen, nicht erst im Render-Log suchen)."""
    deal = lieferschein.deal
    empfaenger = _empfaenger_email(deal)

    if not empfaenger:
        meldung = "keine E-Mail-Adresse für Firma/Ansprechpartner hinterlegt"
        logger.warning(
            "Kein Empfaenger (E-Mail) fuer Versand-Bestaetigungsmail gefunden (Lieferschein %s, Deal %s)",
            lieferschein.nummer, deal.pk,
        )
        return False, meldung

    kontext = {
        "lieferschein": lieferschein,
        "deal": deal,
        "firma": deal.firma,
        "ansprechpartner": deal.kontakt,
        "site_url": SITE_URL,
        "logo_url": f"{SITE_URL}/static/img/eckopack-logo.png",
    }
    betreff = f"Ihre Bestellung ist unterwegs – ECKO-PACK ({lieferschein.nummer})"
    text_body = render_to_string("vertrieb/email/versand_bestaetigung.txt", kontext)
    html_body = render_to_string("vertrieb/email/versand_bestaetigung.html", kontext)

    try:
        mail = EmailMultiAlternatives(betreff, text_body, settings.DEFAULT_FROM_EMAIL, [empfaenger])
        mail.attach_alternative(html_body, "text/html")
        mail.send(fail_silently=False)
    except Exception as exc:
        logger.exception(
            "Versand-Bestaetigungsmail konnte nicht gesendet werden (Lieferschein %s)",
            lieferschein.nummer,
        )
        return False, str(exc)

    lieferschein.bestaetigungsmail_gesendet_am = timezone.now()
    lieferschein.save(update_fields=["bestaetigungsmail_gesendet_am"])
    return True, None
