# Erstellt von Hand am 24.10.2026 - auf Wunsch von Björn: "alle leeren Trinkhalm Mengen mit 0
# ausfüllen". Bisher hatte jeder Deal, dessen Mengenpotenzial per Migration 0034 komplett nach
# Besteck übernommen wurde (oder der seither neu per Lead-Import angelegt wurde), ein leeres
# (NULL) Trinkhalm-Feld - das stand in Liste/Pipeline als "–" statt als Zahl. Diese Migration
# setzt alle noch leeren potenzial_tonnen_trinkhalm-Werte explizit auf 0, OHNE bereits befüllte
# Werte (auch nicht-null 0-Werte) anzufassen.
#
# Wichtig fuer kuenftige Deals: der Lead-Import (import_leadliste.py) laesst
# potenzial_tonnen_trinkhalm weiterhin bewusst leer (NULL), nicht 0 - siehe Kommentar dort.
# Diese Migration ist ein einmaliger Aufräumschritt fuer den JETZIGEN Datenbestand, kein
# Verhaltenswechsel fuer neu importierte Leads.

from decimal import Decimal

from django.db import migrations


def leere_trinkhalm_werte_auf_null_setzen(apps, schema_editor):
    Deal = apps.get_model("vertrieb", "Deal")
    Deal.objects.filter(potenzial_tonnen_trinkhalm__isnull=True).update(
        potenzial_tonnen_trinkhalm=Decimal("0")
    )


def noop_rueckbau(apps, schema_editor):
    # Kein sinnvoller Rueckbau moeglich: nach dem Befuellen ist nicht mehr unterscheidbar,
    # welche 0-Werte vorher NULL waren und welche schon immer 0 waren. Entspricht dem
    # generellen Verzicht auf echten Rueckbau bei Datenmigrationen in diesem Projekt (siehe
    # z. B. Migration 0032/0034/0035).
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("vertrieb", "0035_gaiasip_notiz_entfernen"),
    ]

    operations = [
        migrations.RunPython(leere_trinkhalm_werte_auf_null_setzen, noop_rueckbau),
    ]
