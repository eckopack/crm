# Erstellt von Hand am 25.10.2026 als DATENMIGRATION (kein Schema-Wechsel) - auf Wunsch von
# Björn: befüllt das neue Feld Artikel.gewicht_je_stueck_g (siehe Migration 0039) für die 16
# längenspezifischen LUA-SW-*-Trinkhalmartikel mit den realen, von Björn bestätigten
# Stückgewichten aus der "Technische Übersicht - Trinkhalme"-Produktgrafik und zieht die
# daraus geänderte Rezeptur.menge_je_einheit (ARBOBLEND-Verbrauch je Gebinde, siehe Migration
# 0032) für dieselben Artikel nach.
#
# Reale Werte (von Björn im Chat am 25.10.2026 bestätigt): 15 cm = 0,8 g, 20 cm = 1,0 g,
# 23 cm = 1,2 g, 25 cm = 1,3 g. 30 cm war nicht angegeben; Björn bat ausdrücklich darum, den
# Wert selbst hochzurechnen ("30 cm bitte selber hochrechnen"). Lineare Regression über die
# vier bekannten Punkte (Gewicht = a + b * Länge, kleinste Fehlerquadrate) ergibt für 30 cm
# ca. 1,54 g, auf eine Nachkommastelle (wie die übrigen Werte) gerundet 1,5 g - diese Methode
# passt die bekannten vier Werte sichtbar enger als eine reine Proportional-Annahme
# (Gewicht/Länge = konstant), die je nach Bezugspunkt 1,5-1,6 g ergäbe. 1,5 g ist daher eine
# begründete Hochrechnung, KEINE Herstellerangabe - sollte bestätigt werden, sobald ein
# 30-cm-Trinkhalm real verwogen wird.
#
# LUA-MUSTER-STROH(-EN) bewusst NICHT aufgenommen: Musterbox mit gemischten Längen laut
# Produktbeschreibung, kein einzelnes Stückgewicht zuordenbar - deren Rezeptur-Zeile bleibt
# auf dem bisherigen pauschalen 1,0-g-Wert aus Migration 0032.
from decimal import Decimal

from django.db import migrations


GEWICHT_JE_LAENGE_CM = {
    15: Decimal("0.8"),
    20: Decimal("1.0"),
    23: Decimal("1.2"),
    25: Decimal("1.3"),
    30: Decimal("1.5"),  # Hochrechnung, siehe Migrationskopf - keine Herstellerangabe.
}

# Artikelnummer -> Länge in cm, nur für die längeneindeutigen SKUs (LUA-MUSTER-STROH(-EN)
# bewusst ausgenommen, siehe Migrationskopf).
STROH_ARTIKELNUMMER_ZU_LAENGE = {
    "LUA-SW-15-100": 15, "LUA-SW-15-100-EN": 15,
    "LUA-SW-15-500": 15, "LUA-SW-15-500-EN": 15,
    "LUA-SW-20-050": 20, "LUA-SW-20-050-EN": 20,
    "LUA-SW-20-100": 20, "LUA-SW-20-100-EN": 20,
    "LUA-SW-20-500": 20, "LUA-SW-20-500-EN": 20,
    "LUA-SW-23-500": 23, "LUA-SW-23-500-EN": 23,
    "LUA-SW-25-500": 25, "LUA-SW-25-500-EN": 25,
    "LUA-SW-30-500": 30, "LUA-SW-30-500-EN": 30,
}


def vorwaerts(apps, schema_editor):
    Artikel = apps.get_model("vertrieb", "Artikel")
    Rezeptur = apps.get_model("vertrieb", "Rezeptur")

    fehlend = []
    ohne_verpackungseinheit = []
    for nr, laenge_cm in STROH_ARTIKELNUMMER_ZU_LAENGE.items():
        try:
            artikel = Artikel.objects.get(artikelnummer=nr)
        except Artikel.DoesNotExist:
            fehlend.append(nr)
            continue

        gewicht = GEWICHT_JE_LAENGE_CM[laenge_cm]
        artikel.gewicht_je_stueck_g = gewicht
        artikel.save(update_fields=["gewicht_je_stueck_g"])

        if not artikel.verpackungseinheit_stk:
            # Migration 0032 hätte in diesem Fall bereits hart abgebrochen (siehe dort) -
            # hier nur sicherheitshalber übersprungen statt durch Null zu teilen.
            ohne_verpackungseinheit.append(nr)
            continue

        neue_menge_je_einheit = (gewicht * artikel.verpackungseinheit_stk) / Decimal("1000")
        Rezeptur.objects.filter(fertigprodukt=artikel).update(
            menge_je_einheit=neue_menge_je_einheit
        )

    if fehlend:
        raise RuntimeError(
            "Migration 0040: folgende Trinkhalm-Artikel wurden nicht gefunden, "
            "gewicht_je_stueck_g NICHT gesetzt: " + ", ".join(fehlend)
        )
    if ohne_verpackungseinheit:
        raise RuntimeError(
            "Migration 0040: folgende Trinkhalm-Artikel haben kein verpackungseinheit_stk "
            "gesetzt, Rezeptur.menge_je_einheit NICHT aktualisiert: "
            + ", ".join(ohne_verpackungseinheit)
        )


def rueckwaerts(apps, schema_editor):
    # Bewusst kein Rückbau: Datenmigration, kein Schema - siehe Migration 0032. Ein
    # Downgrade würde reale, inzwischen ggf. weiterbearbeitete Artikel-/Rezeptur-Daten
    # überschreiben bzw. löschen.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("vertrieb", "0039_artikel_gewicht_je_stueck_g"),
    ]

    operations = [
        migrations.RunPython(vorwaerts, rueckwaerts),
    ]
