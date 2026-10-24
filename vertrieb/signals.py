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
das Admin-Interface korrekt bleibt.

Seit 24.10.2026 zusätzlich: generalisiert dieselbe Statuslogik auf Stornorechnungen/
Rechnungskorrekturen (Rechnung.storno_zu) - _rechnung_status_neu_berechnen() wertet jetzt
sowohl Zahlungen als auch verknuepfte Korrekturen aus (siehe Rechnung.korrektursumme/
effektiver_bruttobetrag) und kann den Status auf "storniert" setzen. Wird einer Korrektur-
Rechnung Status/Inhalt gespeichert oder sie geloescht, wird NICHT ihr eigener Status
neu berechnet (das waere eine Rekursion), sondern der Status des Originals, auf das sie
sich bezieht (siehe rechnung_korrektur_gespeichert/rechnung_korrektur_geloescht)."""

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


def _rechnung_status_neu_berechnen(rechnung):
    """Bestimmt Rechnung.status neu aus den erfassten Zahlungen (bezahlter_betrag) UND den
    verknuepften, tatsaechlich versendeten Korrekturen/Stornorechnungen (korrektursumme/
    effektiver_bruttobetrag) - generalisierte Fassung (24.10.2026, Stornorechnung-Feature)
    der urspruenglich nur zahlungsbasierten Logik. Reihenfolge wichtig: eine vollstaendig
    (oder ueber-)stornierte Rechnung wird "storniert", auch wenn sie vorher schon bezahlt
    war (dann mit negativem offener_betrag = Erstattung offen). Ruehrt "entwurf" nicht an -
    eine Rechnung, die noch nicht versendet wurde, hat weder Zahlungen noch Korrekturen,
    die hier etwas aendern duerften."""
    if rechnung.status not in ("versendet", "bezahlt", "storniert"):
        return

    if rechnung.effektiver_bruttobetrag <= 0 and rechnung.korrektursumme < 0:
        neuer_status = "storniert"
    elif rechnung.ist_vollstaendig_bezahlt:
        neuer_status = "bezahlt"
    else:
        neuer_status = "versendet"

    if neuer_status != rechnung.status:
        rechnung.status = neuer_status
        rechnung.save(update_fields=["status"])


@receiver(post_save, sender=RechnungZahlung)
def rechnungzahlung_gespeichert(sender, instance, **kwargs):
    _rechnung_status_neu_berechnen(instance.rechnung)


@receiver(post_delete, sender=RechnungZahlung)
def rechnungzahlung_geloescht(sender, instance, **kwargs):
    try:
        rechnung = Rechnung.objects.get(pk=instance.rechnung_id)
    except Rechnung.DoesNotExist:
        return
    _rechnung_status_neu_berechnen(rechnung)


@receiver(post_save, sender=Rechnung)
def rechnung_korrektur_gespeichert(sender, instance, created, **kwargs):
    """Wenn eine Stornorechnung/Korrektur (storno_zu gesetzt) gespeichert wird - typischerweise
    beim Versand (Statuswechsel auf "versendet", siehe nurture.rechnung_versand_senden) -, muss
    der Status DES ORIGINALS neu berechnet werden, nicht der der Korrektur selbst. Der Guard
    auf storno_zu_id ist zwingend: ohne ihn wuerde JEDE Rechnung (auch ganz normale, ohne
    Korrekturbezug) hier ihren eigenen Status neu berechnen wollen und sich damit potenziell
    rekursiv selbst erneut speichern."""
    if not instance.storno_zu_id:
        return
    try:
        original = Rechnung.objects.get(pk=instance.storno_zu_id)
    except Rechnung.DoesNotExist:
        return
    _rechnung_status_neu_berechnen(original)


@receiver(post_delete, sender=Rechnung)
def rechnung_korrektur_geloescht(sender, instance, **kwargs):
    """Analog zu rechnung_korrektur_gespeichert, falls eine Korrektur geloescht wird (in der
    Praxis nur ein Entwurf - RechnungDeleteView blockt das Loeschen bereits versendeter/
    bezahlter Dokumente generell, siehe dort)."""
    if not instance.storno_zu_id:
        return
    try:
        original = Rechnung.objects.get(pk=instance.storno_zu_id)
    except Rechnung.DoesNotExist:
        return
    _rechnung_status_neu_berechnen(original)
