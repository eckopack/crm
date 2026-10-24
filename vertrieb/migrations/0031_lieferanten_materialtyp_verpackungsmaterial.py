# Erstellt von Hand am 24.10.2026 (NICHT per `makemigrations` autogeneriert) - auf Wunsch von
# Björn, im Zuge der Materialwirtschaft-Erweiterung um Rohmaterial-/Verpackungsmaterial-
# Lieferanten (TECNARO GmbH, traceless materials GmbH).
#
# WICHTIG, warum von Hand: `makemigrations` erkennt die Umbenennung von Artikel.lieferant/
# Charge.lieferant (bisher CharField) zu lieferant_freitext NICHT zuverlässig, weil im selben
# Zug ein NEUES Feld mit dem alten Namen "lieferant" (jetzt ForeignKey) hinzukommt - der
# Autodetector interpretiert das als AlterField (CharField -> ForeignKey, GLEICHER Spaltenname),
# was bestehende Freitext-Werte beim Migrieren zerstören würde, statt sie unter dem neuen Namen
# lieferant_freitext zu erhalten. Reihenfolge hier deshalb bewusst: erst RenameField (verlustfrei),
# danach erst das neue FK-Feld per AddField unter dem freigewordenen Namen "lieferant" anlegen.
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("vertrieb", "0030_rechnung_storno_zu"),
    ]

    operations = [
        # --- Firma: neue, nur für Lieferanten relevante Felder (reine Ergänzung, keine Umbenennung) ---
        migrations.AddField(
            model_name="firma",
            name="ust_idnr",
            field=models.CharField(blank=True, max_length=20, verbose_name="USt-IdNr."),
        ),
        migrations.AddField(
            model_name="firma",
            name="kundennummer_bei_lieferant",
            field=models.CharField(
                blank=True, max_length=50,
                help_text='Nur relevant, wenn diese Firma als Lieferant geführt wird (Status "Lieferant").',
                verbose_name="Unsere Kundennummer bei diesem Lieferanten",
            ),
        ),
        migrations.AddField(
            model_name="firma",
            name="zahlungsbedingungen",
            field=models.CharField(
                blank=True, max_length=200,
                help_text=(
                    'Z. B. "14 Tage netto" oder "50% bei Auftrag, 50% bei Lieferung" - variiert '
                    "teils je Bestellung, deshalb Freitext statt fester Auswahl. Nur relevant, "
                    "wenn diese Firma als Lieferant geführt wird."
                ),
                verbose_name="Zahlungsbedingungen (Freitext)",
            ),
        ),

        # --- Artikel/Charge: altes Freitextfeld "lieferant" verlustfrei umbenennen, BEVOR der
        # Name "lieferant" für das neue FK-Feld wiederverwendet wird ---
        migrations.RenameField(
            model_name="artikel", old_name="lieferant", new_name="lieferant_freitext",
        ),
        migrations.RenameField(
            model_name="charge", old_name="lieferant", new_name="lieferant_freitext",
        ),
        migrations.AlterField(
            model_name="artikel",
            name="lieferant_freitext",
            field=models.CharField(
                blank=True, max_length=200,
                help_text=(
                    "Historisches Freitextfeld, weiterhin genutzt für Handelsware aus dem Excel-"
                    "Artikelstamm-Import (siehe import_artikelstamm.py). Für Rohmaterial/"
                    "Verpackungsmaterial/Fertigware bitte stattdessen das strukturierte Feld "
                    "'Lieferant' unten (Lieferanten-Stammdaten) nutzen."
                ),
                verbose_name="Lieferant (Freitext, Altfeld)",
            ),
        ),
        migrations.AlterField(
            model_name="charge",
            name="lieferant_freitext",
            field=models.CharField(
                blank=True, max_length=200,
                help_text="Historisches Freitextfeld. Bitte für neue Chargen stattdessen das "
                          "strukturierte Feld 'Lieferant' unten nutzen.",
                verbose_name="Lieferant (Freitext, Altfeld)",
            ),
        ),

        # --- Neues strukturiertes Lieferanten-Feld (FK auf Firma, Status "Lieferant") ---
        migrations.AddField(
            model_name="artikel",
            name="lieferant",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name="artikel_als_lieferant", to="vertrieb.firma",
                limit_choices_to={"status": "lieferant"},
                help_text=(
                    'Firma mit Status "Lieferant" (24.10.2026) - vorgesehen für Rohmaterial/'
                    "Verpackungsmaterial/Fertigware. Für Handelsware weiterhin meist über das "
                    "Altfeld 'Lieferant (Freitext, Altfeld)' aus dem Excel-Import gepflegt."
                ),
                verbose_name="Lieferant",
            ),
        ),
        migrations.AddField(
            model_name="charge",
            name="lieferant",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name="chargen_als_lieferant", to="vertrieb.firma",
                limit_choices_to={"status": "lieferant"},
                verbose_name="Lieferant",
            ),
        ),

        # --- Materialtyp um Verpackungsmaterial (Kartonage) erweitern ---
        migrations.AlterField(
            model_name="artikel",
            name="materialtyp",
            field=models.CharField(
                choices=[
                    ("handelsware", "Handelsware (zugekauft, keine eigene Produktion)"),
                    ("rohmaterial", "Rohmaterial"),
                    ("verpackungsmaterial", "Verpackungsmaterial (z. B. Kartonage)"),
                    ("fertigware", "Fertigware (Eigenproduktion)"),
                ],
                default="handelsware", max_length=20,
                help_text=(
                    "Für Rezeptur und Lagerbewegungen (Materialwirtschaft) relevant bei "
                    "Rohmaterial/Fertigware; Handelsware wird weiterhin nur über den "
                    "Lagerbestand-Wert geführt."
                ),
                verbose_name="Materialtyp",
            ),
        ),

        # --- Rezeptur.rohmaterial: auch Verpackungsmaterial zulassen ---
        migrations.AlterField(
            model_name="rezeptur",
            name="rohmaterial",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="verwendet_in_rezepturen", to="vertrieb.artikel",
                limit_choices_to=models.Q(("materialtyp__in", ["rohmaterial", "verpackungsmaterial"])),
                verbose_name="Rohmaterial/Verpackungsmaterial",
            ),
        ),
    ]
