"""Benachrichtigt den zuständigen Mitarbeiter, sobald ein Deal die Angebotsphase neu
erreicht, und beendet dabei die automatische Musterversand-Nachfass-Kette (siehe
nurture.py), damit sie nicht parallel zum normalen Angebotsverfahren weiterläuft."""

from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.utils import timezone

from .models import Aktivitaet, Deal


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
