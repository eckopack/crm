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

AENDERUNG 18.10.2026 (auf Wunsch von Björn, zweimal an diesem Tag überarbeitet): Dieser Befehl
verlaengert NACH WIE VOR ausschliesslich die interne Erinnerungs-Aktivitaet an den zustaendigen
Mitarbeiter (oben unveraendert) - das ist eine eigene, laenger laufende Kette, die bewusst nicht
an die Deal-Phase gekoppelt ist (siehe AENDERUNG 17.10.2026 oben). NEU dazugekommen ist ein
ZWEITER, komplett unabhaengiger Durchlauf (unten): die 8-woechige Musterbox-Nachfasskette an den
KUNDEN (vertrieb.nurture.musterbox_nachfass_senden, gesteuert über models.MusterboxNachfassStatus).
Diese Kette existiert NUR fuer Deals mit einem Musterversand-Packschein (dort angelegt, siehe
nurture.musterversand_abgeschlossen) und endet - anders als die interne Erinnerung oben -
GENAU DANN ohne weitere Mail, wenn der Deal die Phase lead/qualifiziert verlaesst (Angebot
o.ae. = Reaktion da) oder als verloren markiert wird, bzw. automatisch nach der 8. Mail; dann
wird zusaetzlich eine interne Aufgabe fuer den zustaendigen Mitarbeiter angelegt. Die zuvor
hier verschickte generische, immer gleiche Kundenmail (models.NachfassKundenmailVorlage) wurde
dafuer ersatzlos entfernt - Deals ohne Musterversand-Historie bekommen seitdem gar keine
automatische Kundenmail mehr."""

import logging
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.utils import timezone

from vertrieb import nurture
from vertrieb.models import Aktivitaet, MusterboxNachfassStatus

NACHFASS_INTERVALL_TAGE = 7
MUSTERBOX_NACHFASS_WOCHEN = 8
MUSTERBOX_NACHFASS_INTERVALL_TAGE = 7
logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Verlaengert ueberfaellige interne Nachfass-Erinnerungen um eine weitere Woche und "
        "verschickt daneben, unabhaengig davon, die faellige Woche der 8-woechigen Musterbox-"
        "Nachfasskette an Kunden mit Musterversand-Historie - bis der Deal die Phase lead/"
        "qualifiziert verlaesst, verloren ist, oder die 8 Wochen ohne Reaktion ablaufen."
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

        # --- Musterbox-Nachfasskette an den Kunden (komplett unabhaengig von der internen
        # Erinnerung oben - siehe Moduldoku) --------------------------------------------
        musterbox_versendet = 0
        musterbox_fehlgeschlagen = 0
        musterbox_beendet_reaktion = 0
        musterbox_beendet_abgelaufen = 0

        musterbox_faellige = MusterboxNachfassStatus.objects.filter(
            aktiv=True, naechster_versand_am__lt=jetzt,
        ).select_related("deal", "deal__firma", "deal__zustaendiger", "deal__kontakt")

        for status in musterbox_faellige:
            deal = status.deal

            if deal.phase not in ("lead", "qualifiziert"):
                # Reaktion da (Angebot/Verhandlung/Gewonnen) oder Deal verloren - die Kette
                # endet hier sofort, OHNE weitere Mail (auf Wunsch von Björn, 18.10.2026).
                status.aktiv = False
                status.beendet_am = jetzt
                status.beendet_grund = "verloren" if deal.phase == "verloren" else "angebot"
                status.save(update_fields=["aktiv", "beendet_am", "beendet_grund"])
                musterbox_beendet_reaktion += 1
                continue

            try:
                musterbox_erfolg, _fehlermeldung = nurture.musterbox_nachfass_senden(deal, status)
            except Exception:
                logger.exception(
                    "Unerwarteter Fehler bei der Musterbox-Nachfassmail (Deal %s, Woche %s)",
                    deal.pk, status.naechste_woche,
                )
                musterbox_erfolg = False

            if musterbox_erfolg:
                musterbox_versendet += 1
            else:
                musterbox_fehlgeschlagen += 1

            if status.naechste_woche >= MUSTERBOX_NACHFASS_WOCHEN:
                status.aktiv = False
                status.beendet_am = jetzt
                status.beendet_grund = "abgelaufen"
                status.save(update_fields=["aktiv", "beendet_am", "beendet_grund"])
                musterbox_beendet_abgelaufen += 1

                Aktivitaet.objects.create(
                    typ="aufgabe",
                    betreff=f"Lead ausgelaufen nach 8 Wochen, bitte manuell prüfen: {deal.firma.name}",
                    beschreibung=(
                        f"Die automatische 8-woechige Musterbox-Nachfasskette fuer folgenden Deal "
                        f"ist ohne Reaktion ausgelaufen. Bitte manuell pruefen und ggf. persoenlich "
                        f"nachfassen.\n\n"
                        f"Deal: {deal.titel}\n"
                        f"Firma: {deal.firma.name}\n"
                        f"Phase: {deal.get_phase_display()}\n"
                        f"Link: {nurture.SITE_URL}{deal.get_absolute_url()}"
                    ),
                    datum=jetzt,
                    firma=deal.firma,
                    kontakt=deal.kontakt,
                    deal=deal,
                    zustaendiger=deal.zustaendiger,
                )
            else:
                status.naechste_woche += 1
                status.naechster_versand_am = jetzt + timedelta(days=MUSTERBOX_NACHFASS_INTERVALL_TAGE)
                status.save(update_fields=["naechste_woche", "naechster_versand_am"])

        self.stdout.write(self.style.SUCCESS(
            f"Nachfass-Pruefung abgeschlossen: {verlaengert} interne Erinnerung(en) verlaengert, "
            f"{beendet} beendet. Musterbox-Kette: {musterbox_versendet} Kundenmail(s) versendet, "
            f"{musterbox_fehlgeschlagen} fehlgeschlagen, {musterbox_beendet_reaktion} wegen "
            f"Reaktion/verloren beendet, {musterbox_beendet_abgelaufen} nach 8 Wochen abgelaufen."
        ))
