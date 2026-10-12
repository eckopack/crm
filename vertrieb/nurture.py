"""Nachfass-Automatik für Musterversand-Leads.

Ablauf: Button 'Musterkarton anfordern' (views.musterkarton_anfordern) legt einen
Packschein mit ist_musterversand=True an. Sobald der im Lager auf 'versendet'
gesetzt wird (views.packschein_versand_bestaetigen), läuft hier:

1. Bestätigungsmail an den Lead (best effort – ein fehlender/kaputter E-Mail-Versand
   darf den Packvorgang nicht blockieren, deshalb try/except statt hartem Fehler).
2. Anlage der ersten wöchentlichen Nachfass-Aktivität (+7 Tage), die anschließend vom
   management command 'nachfass_pruefen' (wöchentlicher Cron, siehe render.yaml)
   verlängert wird, solange der Deal die Angebotsphase noch nicht erreicht hat.
"""

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from datetime import timedelta

from .models import Aktivitaet

logger = logging.getLogger(__name__)

NACHFASS_INTERVALL_TAGE = 7


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
            f"(Packschein {packschein.nummer}). Bitte nach einer Woche nachfassen, solange der Deal "
            f"noch nicht in der Angebotsphase ist. Wird automatisch verlängert, bis die Phase wechselt."
        ),
        datum=timezone.now() + timedelta(days=NACHFASS_INTERVALL_TAGE),
        firma=deal.firma,
        kontakt=deal.kontakt,
        deal=deal,
        zustaendiger=deal.zustaendiger,
    )
