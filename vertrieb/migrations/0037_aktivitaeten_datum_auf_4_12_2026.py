# Erstellt von Hand am 24.10.2026 - auf Wunsch von Björn: "bitte alle Aktivitäten auf
# 4.12.2026 setzen". Betrifft ALLE Aktivitaet-Datensätze (aktuell 40, Stand 24.10.2026),
# unabhängig von Typ, Zuständigkeit oder erledigt-Status - verschiebt nur das Datum
# (24.12.2026 -> 04.12.2026 jeweils fuer den TAG, der Monat/das Jahr), die Uhrzeit jedes
# einzelnen Datensatzes bleibt dabei UNVERAENDERT (z. B. 11.10.2026 15:54 Uhr wird zu
# 04.12.2026 15:54 Uhr), da Björn nur "das Datum" genannt hat, nicht die Uhrzeit - siehe
# verify_aktivitaeten_datum_verschieben.py fuer den Verifikationsnachweis dieser Annahme.
#
# Einmaliger Aufräumschritt fuer den JETZIGEN Datenbestand (Björn will offenbar alle
# offenen Aufgaben auf einen gemeinsamen Stichtag buendeln) - kein automatischer
# Verhaltenswechsel fuer kuenftig neu angelegte Aktivitaeten (weder manuell noch durch
# die automatische Nachfass-/Nurture-Logik in signals.py).

from django.db import migrations
from django.utils import timezone


def datum_auf_4_dezember_2026_setzen(apps, schema_editor):
    # Wichtig: Django liefert aktivitaet.datum hier als UTC-aware datetime (USE_TZ=True).
    # Ein .replace(year=..., month=..., day=...) direkt darauf wuerde das UTC-Kalenderdatum
    # veraendern, nicht die lokale (Europe/Berlin) Uhrzeit, die Björn gemeint hat - das
    # fuehrt durch den Sommer-/Winterzeit-Unterschied (Okt. = MESZ +02:00, Dez. = MEZ
    # +01:00) zu einer um eine Stunde verschobenen Uhrzeit. Deshalb zuerst in die lokale
    # Zeitzone umrechnen, DORT nur Jahr/Monat/Tag ersetzen (Uhrzeit bleibt unveraendert),
    # und erst danach wieder speichern - siehe verify_aktivitaeten_datum_verschieben.py.
    Aktivitaet = apps.get_model("vertrieb", "Aktivitaet")
    for aktivitaet in Aktivitaet.objects.all():
        lokal = timezone.localtime(aktivitaet.datum)
        aktivitaet.datum = lokal.replace(year=2026, month=12, day=4)
        aktivitaet.save(update_fields=["datum"])


def noop_rueckbau(apps, schema_editor):
    # Kein sinnvoller Rueckbau moeglich: das urspruengliche Datum jeder einzelnen
    # Aktivitaet ist nach dem Ueberschreiben nicht mehr rekonstruierbar. Entspricht dem
    # generellen Verzicht auf echten Rueckbau bei Datenmigrationen in diesem Projekt
    # (siehe z. B. Migration 0032/0034/0035/0036).
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("vertrieb", "0036_trinkhalm_leerwerte_auf_null"),
    ]

    operations = [
        migrations.RunPython(datum_auf_4_dezember_2026_setzen, noop_rueckbau),
    ]
