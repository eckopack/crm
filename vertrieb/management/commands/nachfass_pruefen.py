"""Wöchentliche Nachfass-Pruefung fuer Musterversand-Leads.

Wird nicht direkt per Cron gegen die SQLite-Datei aufgerufen (die liegt nur auf der
Disk des Web-Service), sondern ueber den internen HTTP-Endpoint
vertrieb.views.interner_nachfass_cron, den ein separater Render-Cron-Job per HTTPS
anstoesst. So braucht der Cron-Job selbst keinen Datenbankzugriff.

AENDERUNG 17.10.2026 (auf Wunsch von Björn): Die Kette lief bisher nur, solange der Deal noch
in Phase "lead"/"qualifiziert" war, und endete automatisch, sobald ein Angebot erstellt wurde.
Das stoppte das Nachfassen genau dann, wenn es am wichtigsten waere (Angebot raus, aber noch
keine Reaktion). Jetzt läuft die Kette durch alle Phasen weiter (ausser "verloren") und endet
erst, wenn der Deal tatsaechlich einen versendeten Lieferschein hat (Trackingnummer gesetzt,
siehe Lieferschein.tatsaechlich_versendet / views.lieferschein_versand_bestaetigen) - vorher
"Rechnung erzeugt" o.ae. zu pruefen waere zu frueh, weil die Rechnung selbst erst NACH dem
Versand erzeugt werden darf (siehe views.rechnung_erstellen).

AENDERUNG 18.10.2026 (auf Wunsch von Björn): Zusaetzlich zur bisherigen internen Erinnerung an
den zustaendigen Mitarbeiter verschickt jeder Lauf jetzt auch eine eigene Nachfass-Mail direkt
an den Kunden (vertrieb.nurture.nachfass_kundenmail_senden). Betreff/Text dieser Kundenmail
sind KEIN Code, sondern ein Datensatz (models.NachfassKundenmailVorlage), den Björn/Vertrieb
jederzeit selbst im Django-Admin aendern koennen, ohne Deploy. Ein Fehler beim Kundenmail-Versand
(z.B. keine E-Mail-Adresse hinterlegt) wird nur geloggt und blockiert weder die interne
Erinnerung noch die Verlaengerung der Nachfass-Kette - anders als beim direkten Versand-Button
(views.lieferschein_versand_bestaetigen), der ein sofort sichtbares UI-Feedback hat, laeuft
dieser Cron unbeaufsichtigt. Hinweis: die Kundenmail geht bei jeder Verlaengerung raus, also
potenziell woechentlich mit demselben Text, solange ein Deal offen bleibt - falls das zu haeufig
wirkt, kann Björn den Text anpassen oder uns bitten, eine Haeufigkeitsbegrenzung einzubauen."""

import logging
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.utils import timezone

from vertrieb import nurture
from vertrieb.models import Aktivitaet

NACHFASS_INTERVALL_TAGE = 7
logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Verlaengert ueberfaellige Nachfass-Aktivitaeten um eine weitere Woche, erinnert "
        "den zustaendigen Mitarbeiter per E-Mail und verschickt eine Nachfass-Mail an den "
        "Kunden, bis der zugehoerige Deal entweder verloren ist oder einen tatsaechlich "
        "versendeten Lieferschein hat."
    )

    def handle(self, *args, **options):
        jetzt = timezone.now()
        ueberfaellige = Aktivitaet.objects.filter(
            typ="nachfass", erledigt=False, datum__lt=jetzt,
        ).select_related("deal", "deal__firma", "deal__zustaendiger")

        verlaengert = 0
        beendet = 0
        kundenmail_versendet = 0
        kundenmail_fehlgeschlagen = 0

        for aktivitaet in ueberfaellige:
            deal = aktivitaet.deal
            aktivitaet.erledigt = True
            aktivitaet.save(update_fields=["erledigt"])

            bereits_versendet = deal is not None and deal.lieferscheine.exclude(trackingnummer="").exists()
            if deal is None or deal.phase == "verloren" or bereits_versendet:
                # Deal verloren, tatsaechlich versendet, oder ohne Deal-Bezug - die Kette
                # endet hier, kein neuer Eintrag. (Vor dem 17.10.2026 endete die Kette
                # stattdessen schon beim Erreichen der Angebotsphase - siehe Kommentar oben.)
                beendet += 1
                continue

            Aktivitaet.objects.create(
                typ="nachfass",
                betreff=aktivitaet.betreff,
                beschreibung=aktivitaet.beschreibung,
                datum=jetzt + timedelta(days=NACHFASS_INTERVALL_TAGE),
                firma=deal.firma,
                kontakt=deal.kontakt,
                deal=deal,
                zustaendiger=deal.zustaendiger,
            )
            verlaengert += 1

            if deal.zustaendiger and deal.zustaendiger.email:
                try:
                    send_mail(
                        f"Erinnerung: {deal.firma.name} nachfassen ({deal.get_phase_display()})",
                        (
                            f"Die Nachfass-Frist fuer folgenden Deal ist abgelaufen. Bitte nachfassen.\n\n"
                            f"Deal: {deal.titel}\n"
                            f"Firma: {deal.firma.name}\n"
                            f"Phase: {deal.get_phase_display()}\n"
                            f"Link: {nurture.SITE_URL}{deal.get_absolute_url()}"
                        ),
                        settings.DEFAULT_FROM_EMAIL,
                        [deal.zustaendiger.email],
                        fail_silently=True,
                    )
                except Exception:
                    pass

            try:
                kundenmail_erfolg, _fehlermeldung = nurture.nachfass_kundenmail_senden(deal)
            except Exception:
                logger.exception(
                    "Unerwarteter Fehler beim Versand der Nachfass-Kundenmail (Deal %s)", deal.pk,
                )
                kundenmail_erfolg = False
            if kundenmail_erfolg:
                kundenmail_versendet += 1
            else:
                kundenmail_fehlgeschlagen += 1

        self.stdout.write(self.style.SUCCESS(
            f"Nachfass-Pruefung abgeschlossen: {verlaengert} verlaengert, {beendet} beendet, "
            f"{kundenmail_versendet} Kundenmails versendet, {kundenmail_fehlgeschlagen} fehlgeschlagen."
        ))
