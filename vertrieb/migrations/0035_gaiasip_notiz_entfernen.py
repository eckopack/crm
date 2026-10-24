# Erstellt von Hand am 24.10.2026 - auf Wunsch von Björn: "Gaiasip Interesse bitte überall
# entfernen". Das war nie eine eigene Modellspalte, sondern eine von mehreren Zeilen, die der
# Lead-Import (import_leadliste.py) in Deal.notizen geschrieben hat ("Gaiasip-Interesse: ...").
# Der Import selbst wurde angepasst, diese Zeile künftig nicht mehr zu erzeugen - diese
# Migration bereinigt zusätzlich die bereits importierten/bestehenden Notizen-Texte, damit der
# Hinweis nicht erst beim nächsten Reimport verschwindet.

from django.db import migrations


def gaiasip_zeile_entfernen(apps, schema_editor):
    Deal = apps.get_model("vertrieb", "Deal")
    for deal in Deal.objects.filter(notizen__icontains="Gaiasip-Interesse"):
        zeilen = [z for z in deal.notizen.split("\n") if not z.startswith("Gaiasip-Interesse:")]
        deal.notizen = "\n".join(zeilen)
        deal.save(update_fields=["notizen"])


def noop_rueckbau(apps, schema_editor):
    # Kein sinnvoller Rueckbau moeglich: der urspruengliche Text inkl. Gaiasip-Zeile ist nach
    # dem Entfernen nicht mehr rekonstruierbar. Entspricht dem generellen Verzicht auf echten
    # Rueckbau bei Datenmigrationen in diesem Projekt (siehe z.B. Migration 0032/0034).
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("vertrieb", "0034_deal_mengenpotenzial_trinkhalm_besteck"),
    ]

    operations = [
        migrations.RunPython(gaiasip_zeile_entfernen, noop_rueckbau),
    ]
