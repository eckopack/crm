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
Versand erzeugt werden darf (siehe views.rechnung_erstellen)."""

from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.utils import timezone

from vertrieb.models import Aktivitaet

NACHFASS_INTERVALL_TAGE = 7


class Command(BaseCommand):
    help = (
        "Verlaengert ueberfaellige Nachfass-Aktivitaeten um eine weitere Woche und erinnert "
        "den zustaendigen Mitarbeiter per E-Mail, bis der zugehoerige Deal entweder verloren "
        "ist oder einen tatsaechlich versendeten Lieferschein hat."
    )

    def handle(self, *args, **options):
        jetzt = timezone.now()
        ueberfaellige = Aktivitaet.objects.filter(
            typ="nachfass", erledigt=False, datum__lt=jetzt,
        ).select_related("deal", "deal__firma", "deal__zustaendiger")

        verlaengert = 0
        beendet = 0

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
                        f"Erinnerung: Lead {deal.firma.name} nachfassen",
                        (
                            f"Der Musterversand an {deal.firma.name} liegt eine Woche zurueck "
                            f"und der Deal ist noch nicht in der Angebotsphase. Bitte nachfassen.\n\n"
                            f"Deal: {deal.titel}"
                        ),
                        settings.DEFAULT_FROM_EMAIL,
                        [deal.zustaendiger.email],
                        fail_silently=True,
                    )
                except Exception:
                    pass

        self.stdout.write(self.style.SUCCESS(
            f"Nachfass-Pruefung abgeschlossen: {verlaengert} verlaengert, {beendet} beendet."
        ))
