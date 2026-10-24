"""Benachrichtigt den zuständigen Mitarbeiter, sobald ein Deal die Angebotsphase neu
erreicht, und beendet dabei die automatische Musterversand-Nachfass-Kette (siehe
nurture.py), damit sie nicht parallel zum normalen Angebotsverfahren weiterläuft.

Seit 23.10.2026 zusätzlich: startet/beendet die Angebot-Nachfasskette an den Kunden (siehe
AngebotNachfassStatus in models.py) anhand von Angebot.status-Wechseln - rein ereignis-
basiert, analog zum Deal-Phasenwechsel oben. Das eigentliche Verschicken der Mails macht
weiterhin der tägliche Cron (management/commands/nachfass_pruefen.py), hier wird nur die
Kette gestartet (Status->"versendet") bzw. vorzeitig beendet (Status weg von "versendet").

Seit 24.10.2026 zusätzlich: haelt Rechnung.status synchron mit den erfassten
RechnungZahlung-Eintraegen (siehe Model-Doku bei Rechnung.bezahlter_betrag) - ereignisbasiert
an die Zahlung gekoppelt (post_save/post_delete), nicht an die Erfassungs-View
(views.rechnung_zahlung_erfassen), damit der Status auch bei einer Erfassung/Korrektur ueber
das Admin-Interface korrekt bleibt."""

from datetime import timedelta

from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

from .models import (
    ANGEBOT_NACHFASS_INTERVALLE_TAGE, Aktivitaet, Angebot, AngebotNachfassStatus, Deal,
    Rechnung, RechnungZahlung,
)


@receiver(pre_save, sender=Deal)
def deal_phase_wechsel(sender, instance, **kwargs):
    if not instance.pk:
        return  # neu angelegter Deal, kein Phasenwechsel
    try:
        alter_deal = Deal.objects.get(pk=instance.pk)
    except Deal.DoesNotExist:
        return

    if alter_deal.phase == instance.phase:
        return
    if not (instance.phase == "angebot" and alter_deal.phase in ("lead", "qualifiziert")):
        return

    # Offene Nachfass-Aktivitäten dieses Deals beenden – der Lead ist jetzt im
    # normalen Angebotsverfahren, die automatische Kette hat ihren Zweck erfüllt.
    Aktivitaet.objects.filter(deal=instance, typ="nachfass", erledigt=False).update(erledigt=True)

    Aktivitaet.objects.create(
        typ="aufgabe",
        betreff=f"Lead in Angebotsphase: {instance.firma.name}",
        beschreibung=(
            "Dieser Lead ist jetzt in der Angebotsphase. Die automatische "
            "Musterversand-Nachfass-Automatik wurde beendet – bitte normales "
            "Angebotsverfahren starten."
        ),
        datum=timezone.now(),
        firma=instance.firma,
        kontakt=instance.kontakt,
        deal=instance,
        zustaendiger=instance.zustaendiger,
    )


@receiver(pre_save, sender=Angebot)
def angebot_status_wechsel(sender, instance, **kwargs):
    if not instance.pk:
        return  # neu angelegtes Angebot, kein Statuswechsel
    try:
        altes_angebot = Angebot.objects.get(pk=instance.pk)
    except Angebot.DoesNotExist:
        return
    if altes_angebot.status == instance.status:
        return

    jetzt = timezone.now()
    bestehender = AngebotNachfassStatus.objects.filter(angebot=instance).first()

    # Kette startet: Status wechselt NEU auf "versendet".
    if instance.status == "versendet":
        erster_schritt_tage = ANGEBOT_NACHFASS_INTERVALLE_TAGE[1]
        if bestehender is None:
            AngebotNachfassStatus.objects.create(
                angebot=instance, sprache=instance.sprache, versendet_am=jetzt,
                naechster_schritt=1, naechster_versand_am=jetzt + timedelta(days=erster_schritt_tage),
            )
        elif not bestehender.aktiv:
            # Erneut versendet (z.B. nach Ueberarbeitung) - Kette von vorn beginnen.
            bestehender.sprache = instance.sprache
            bestehender.versendet_am = jetzt
            bestehender.naechster_schritt = 1
            bestehender.naechster_versand_am = jetzt + timedelta(days=erster_schritt_tage)
            bestehender.aktiv = True
            bestehender.beendet_am = None
            bestehender.beendet_grund = ""
            bestehender.save()
        return

    # Kette endet vorzeitig: Status wechselt WEG von "versendet" (Kunde hat reagiert -
    # angenommen/abgelehnt -, oder Björn hat manuell "abgelaufen"/"entwurf" gesetzt).
    if altes_angebot.status == "versendet" and bestehender is not None and bestehender.aktiv:
        bestehender.aktiv = False
        bestehender.beendet_am = jetzt
        bestehender.beendet_grund = "abgelaufen" if instance.status == "abgelaufen" else "reagiert"
        bestehender.save(update_fields=["aktiv", "beendet_am", "beendet_grund"])


def _rechnung_bezahlt_status_aktualisieren(rechnung):
    """Setzt Rechnung.status anhand der tatsaechlich erfassten Zahlungen: "bezahlt", sobald
    die Summe die Bruttosumme erreicht/uebersteigt, zurueck auf "versendet", falls eine
    Zahlung nachtraeglich korrigiert/geloescht wurde und der Betrag nicht mehr reicht.
    Ruehrt bewusst "entwurf" und "storniert" nicht an - eine Zahlung zu einer Rechnung, die
    noch nicht versendet oder bereits storniert ist, aendert daran nichts."""
    if rechnung.status == "versendet" and rechnung.ist_vollstaendig_bezahlt:
        rechnung.status = "bezahlt"
        rechnung.save(update_fields=["status"])
    elif rechnung.status == "bezahlt" and not rechnung.ist_vollstaendig_bezahlt:
        rechnung.status = "versendet"
        rechnung.save(update_fields=["status"])


@receiver(post_save, sender=RechnungZahlung)
def rechnungzahlung_gespeichert(sender, instance, **kwargs):
    _rechnung_bezahlt_status_aktualisieren(instance.rechnung)


@receiver(post_delete, sender=RechnungZahlung)
def rechnungzahlung_geloescht(sender, instance, **kwargs):
    try:
        rechnung = Rechnung.objects.get(pk=instance.rechnung_id)
    except Rechnung.DoesNotExist:
        return
    _rechnung_bezahlt_status_aktualisieren(rechnung)
