# Erstellt von Hand am 29.10.2026 als DATENMIGRATION (kein Schema-Wechsel) - Bugfix, auf
# Wunsch von Björn ("rezepturen noch ein thema?" -> "bitte fixen", im Zuge der Rückfrage zu
# den GUTOM-Chargennummern für Trinkhalme).
#
# FEHLER (gefunden 29.10.2026 beim Nachprüfen der Rezeptur-Zeilen für ROH-TEC-5953M):
# Migration 0032 hat Rezeptur.menge_je_einheit für alle 30 Fertigware-Rezeptur-Zeilen als
# "Gramm je Stück * Stück je Gebinde (verpackungseinheit_stk) / 1000" angelegt - im eigenen
# Migrationskommentar wörtlich als "kg je Gebinde" bezeichnet. Migration 0040 hat für die 16
# längenspezifischen Trinkhalm-Artikel dieselbe (fehlerhafte) Formel erneut angewendet, nur
# mit genaueren Gramm-Werten je Länge statt des pauschalen 1,0-g-Werts.
#
# Das Modell (Rezeptur.menge_je_einheit, siehe Model-Doku) verlangt aber "je EINER Einheit
# des Fertigprodukts" (Einheit = Stück), und genau so multipliziert
# views._produktionsbuchung_anlegen() auch: `zeile.menge_je_einheit * gesamtmenge`, wobei
# gesamtmenge die produzierte STÜCKZAHL ist (menge_ist + menge_ausschuss). Jede reale
# Produktionsbuchung hätte also bisher das 50- bis 500-fache (= jeweilige
# verpackungseinheit_stk) des tatsächlich benötigten Rohmaterials verbraucht und wäre bei
# jeder realistischen Stückzahl sofort an der Chargenbestand-Prüfung gescheitert ("Charge
# reicht nicht mehr aus").
#
# FIX: menge_je_einheit je Zeile durch die verpackungseinheit_stk des zugehörigen
# Fertigprodukts teilen - das kehrt exakt die ursprüngliche (fehlerhafte) Multiplikation aus
# 0032/0040 um und ergibt wieder den schon damals bekannten Gramm-je-Stück-Wert (1,0 g
# Rohware pauschal bzw. 0,8/1,0/1,2/1,3/1,5 g je Trinkhalm-Länge, 2,5 g je Kleinbesteck-Teil,
# 6,0 g je Großbesteck-Teil - siehe Migrationen 0032/0040), ohne diese Werte hier erneut
# hart zu codieren: der aktuell gespeicherte (falsche) Wert enthält sie bereits, es muss nur
# durch den Gebinde-Faktor zurückgerechnet werden.
#
# Zusätzliche Prüfung für die 16 längenspezifischen Trinkhalm-Artikel (die seit Migration
# 0040 ihr Gewicht je Stück zusätzlich UNABHÄNGIG in Artikel.gewicht_je_stueck_g tragen):
# das zurückgerechnete Ergebnis muss exakt mit gewicht_je_stueck_g / 1000 übereinstimmen -
# andernfalls bricht die Migration hart ab, statt eine ggf. seitdem von Hand geänderte
# Rezeptur-Zeile stillschweigend zu überschreiben (siehe Migration 0032/0040, dieselbe
# Vorsicht: lieber ein fehlgeschlagener Deploy als eine unbemerkt falsche Materialmenge).
#
# NACHTRAG 30.10.2026 (erster Deploy-Versuch ist mit genau diesem Sicherheitscheck
# gescheitert und hat den App-Start blockiert, bis Render automatisch auf den vorherigen
# Stand zurückgefallen ist - kein Datenschaden, aber kurzzeitig nicht ausgerollt): LUA-
# MUSTER-STROH(-EN) hatten in der Live-DB tatsächlich KEIN verpackungseinheit_stk gesetzt,
# obwohl Migration 0032 es dort einmalig auf 50 gesetzt hatte ("Z. B. 500 bei einem 500er-
# Schlauchbeutel... LUA-MUSTER-STROH(-EN) haben verpackungseinheit_stk NICHT gesetzt...").
# Vermutung [Wahrscheinlich]: der bei jedem Deploy laufende Befehl import_artikelstamm
# überschreibt Artikel-Felder aus der Excel-Stammdatei, die für dieses Feld bei diesen
# beiden Mustervarianten keinen Wert trägt, und setzt es dadurch bei jedem Neustart
# stillschweigend wieder auf leer zurück - eine eigene, von dieser Migration unabhängige
# Baustelle (siehe PR-Beschreibung), die hier NICHT mitbehoben wird. Diese Migration setzt
# das Feld deshalb direkt vor der eigentlichen Korrektur erneut auf den aus Migration 0032
# bekannten Wert (50 Stück, siehe Artikel-Bezeichnung "50 Stück"/"50 pcs"), statt erneut
# hart abzubrechen - ein für diese beiden Artikel bereits einmal korrekt gesetzter und seit
# dem erstmaligen Produktiv-Einsatz nur durch den Import wieder verlorener Wert ist kein
# Fall für "bitte manuell prüfen", sondern eine bekannte, dokumentierte Korrektur.
from decimal import Decimal

from django.db import migrations

MUSTERKARTON_VERPACKUNGSEINHEIT_NACHTRAG = {
    "LUA-MUSTER-STROH": 50,
    "LUA-MUSTER-STROH-EN": 50,
}


def vorwaerts(apps, schema_editor):
    Artikel = apps.get_model("vertrieb", "Artikel")
    Rezeptur = apps.get_model("vertrieb", "Rezeptur")

    for nr, stk in MUSTERKARTON_VERPACKUNGSEINHEIT_NACHTRAG.items():
        Artikel.objects.filter(
            artikelnummer=nr, verpackungseinheit_stk__isnull=True,
        ).update(verpackungseinheit_stk=stk)

    ohne_verpackungseinheit = []
    abweichend = []
    korrigiert = []

    for zeile in Rezeptur.objects.select_related("fertigprodukt", "rohmaterial").all():
        fertigprodukt = zeile.fertigprodukt
        stk_je_gebinde = fertigprodukt.verpackungseinheit_stk
        if not stk_je_gebinde:
            ohne_verpackungseinheit.append(fertigprodukt.artikelnummer)
            continue

        alte_menge = zeile.menge_je_einheit
        neue_menge = (alte_menge / Decimal(stk_je_gebinde)).quantize(Decimal("0.00001"))

        if fertigprodukt.gewicht_je_stueck_g is not None:
            erwartet = (fertigprodukt.gewicht_je_stueck_g / Decimal("1000")).quantize(Decimal("0.00001"))
            if erwartet != neue_menge:
                abweichend.append(
                    f"{fertigprodukt.artikelnummer}: zurückgerechnet {neue_menge} kg/Stück, "
                    f"aber gewicht_je_stueck_g ergibt {erwartet} kg/Stück"
                )
                continue

        zeile.menge_je_einheit = neue_menge
        zeile.save(update_fields=["menge_je_einheit"])
        korrigiert.append(f"{fertigprodukt.artikelnummer}: {alte_menge} -> {neue_menge} kg/Stück")

    if ohne_verpackungseinheit:
        raise RuntimeError(
            "Migration 0048: folgende Fertigprodukte haben kein verpackungseinheit_stk "
            "gesetzt, Rezeptur.menge_je_einheit NICHT korrigiert: "
            + ", ".join(ohne_verpackungseinheit)
        )
    if abweichend:
        raise RuntimeError(
            "Migration 0048: zurückgerechneter Wert weicht von Artikel.gewicht_je_stueck_g "
            "ab (vermutlich wurde eine der beiden Zahlen seit Migration 0040 von Hand "
            "geändert) - bitte manuell prüfen statt automatisch zu korrigieren: "
            + "; ".join(abweichend)
        )


def rueckwaerts(apps, schema_editor):
    # Bewusst kein Rückbau: Datenmigration, kein Schema - siehe Migration 0032/0040. Ein
    # Downgrade würde reale, inzwischen ggf. weiterbearbeitete Rezeptur-Daten (oder seitdem
    # gebuchte Produktionsbuchungen, die bereits auf Basis der korrigierten Menge liefen)
    # wieder auf die fehlerhaften Gebinde-Werte zurücksetzen.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("vertrieb", "0047_fracht_verpackung_palette"),
    ]

    operations = [
        migrations.RunPython(vorwaerts, rueckwaerts),
    ]
