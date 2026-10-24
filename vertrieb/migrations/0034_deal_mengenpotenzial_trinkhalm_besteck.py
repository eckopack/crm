# Erstellt von Hand am 24.10.2026 (Grundgerüst von makemigrations, Reihenfolge + Daten-
# migration manuell ergänzt) - auf Wunsch von Björn: das bisherige einzelne Mengenpotenzial-
# Feld wird nach Produktkategorie aufgeteilt (Trinkhalm/Besteck, siehe Deal-Model-Doku).
#
# Bestehende Werte werden vollständig nach "Besteck" übernommen - Björns ausdrückliche
# Entscheidung im Chat vom 24.10.2026: "erstmal alle mengenpotenziale bei besteck lassen,
# ich ändere danach manuell". Eine automatische Zuordnung zu Trinkhalm wäre geraten gewesen,
# da das alte Feld keine Kategorie kannte.

from django.db import migrations, models


def alte_werte_nach_besteck_uebernehmen(apps, schema_editor):
    Deal = apps.get_model("vertrieb", "Deal")
    Deal.objects.exclude(potenzial_tonnen__isnull=True).update(
        potenzial_tonnen_besteck=models.F("potenzial_tonnen")
    )


def besteck_nach_alt_zurueckschreiben(apps, schema_editor):
    # Bewusst nur fuer den (unwahrscheinlichen) Fall eines Downgrades: schreibt den
    # Besteck-Wert zurueck in das alte Feld. Zwischenzeitlich manuell nach Trinkhalm
    # verschobene Mengen gingen dabei verloren - das ist bei einem Rueckbau der Migration
    # unvermeidbar und entspricht dem generellen Verzicht auf Rueckbau bei Datenmigrationen
    # in diesem Projekt (siehe z.B. Migration 0032).
    Deal = apps.get_model("vertrieb", "Deal")
    Deal.objects.exclude(potenzial_tonnen_besteck__isnull=True).update(
        potenzial_tonnen=models.F("potenzial_tonnen_besteck")
    )


class Migration(migrations.Migration):

    dependencies = [
        ("vertrieb", "0033_firma_kontakt_archivieren_deal_schutz"),
    ]

    operations = [
        migrations.AddField(
            model_name="deal",
            name="potenzial_tonnen_besteck",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Geschätzte Jahres-/Bezugsmenge Besteck in Tonnen, unabhängig vom EUR-Wert.",
                max_digits=10,
                null=True,
                verbose_name="Mengenpotenzial Besteck (Tonnen)",
            ),
        ),
        migrations.AddField(
            model_name="deal",
            name="potenzial_tonnen_trinkhalm",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Geschätzte Jahres-/Bezugsmenge Trinkhalme in Tonnen, unabhängig vom EUR-Wert.",
                max_digits=10,
                null=True,
                verbose_name="Mengenpotenzial Trinkhalm (Tonnen)",
            ),
        ),
        migrations.RunPython(alte_werte_nach_besteck_uebernehmen, besteck_nach_alt_zurueckschreiben),
        migrations.RemoveField(
            model_name="deal",
            name="potenzial_tonnen",
        ),
    ]
