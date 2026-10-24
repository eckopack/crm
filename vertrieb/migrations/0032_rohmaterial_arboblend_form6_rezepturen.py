# Erstellt von Hand am 24.10.2026 als DATENMIGRATION (kein Schema-Wechsel) - auf Wunsch von
# Björn: legt die beiden konkreten Rohmaterial-Artikel ARBOBLEND 5953 M (TECNARO) und FORM 6
# (traceless) an, schaltet die betroffenen LUAMO-Fertigprodukte von "handelsware" (Default) auf
# materialtyp="fertigware" um und legt für jedes davon die passende Rezeptur-Zeile an.
#
# Mengen-Herleitung (Angaben Björn, 24.10.2026, im Chat): ca. 1 g ARBOBLEND je Trinkhalm,
# ca. 2,5 g FORM 6 je Kleinbesteck-Teil, ca. 6 g FORM 6 je Großbesteck-Teil. Das ist ein
# Durchschnittswert je Kategorie (nicht je einzelne Artikelvariante) - siehe PR-Beschreibung.
# Die Menge je Gebinde (Rezeptur.menge_je_einheit) wird NICHT hier hart codiert, sondern bei
# jedem Artikel live aus dessen eigenem Feld verpackungseinheit_stk berechnet
# (Gramm je Stück * Stück je Gebinde / 1000 = kg je Gebinde), damit die Migration auch dann
# noch korrekt rechnet, wenn sich verpackungseinheit_stk zwischenzeitlich geändert hat.
#
# Neuer Artikelnummern-Nummernkreis für Rohmaterial (ab sofort fortzuführen):
#   ROH-<Lieferanten-Kürzel>-<Produktkurzname>
#   TEC = TECNARO GmbH, TRL = traceless materials GmbH, TOP = topac GmbH (für künftige
#   Kartonage-Artikel vorgesehen, hier noch nicht verwendet).
#
# Bewusst NICHT aufgenommen (siehe PR-Beschreibung):
#   - LUA-FLYER-STROH(-EN): Werbe-Flyer, kein physisches Produkt aus ARBOBLEND.
#   - LUA-EINL-BESTECK(-EN): Beileger/Einlage, kein eigenständiges Besteckteil.
#   - LUA-MUSTER-BESTECK(-EN): Zusammensetzung (welche Teile/wie viele) nicht bekannt -
#     hier bewusst kein Rezeptur-Eintrag geraten, sondern offen gelassen.
from decimal import Decimal

from django.db import migrations


STROH_ARTIKELNUMMERN = [
    "LUA-SW-15-100", "LUA-SW-15-100-EN",
    "LUA-SW-15-500", "LUA-SW-15-500-EN",
    "LUA-SW-20-050", "LUA-SW-20-050-EN",
    "LUA-SW-20-100", "LUA-SW-20-100-EN",
    "LUA-SW-20-500", "LUA-SW-20-500-EN",
    "LUA-SW-23-500", "LUA-SW-23-500-EN",
    "LUA-SW-25-500", "LUA-SW-25-500-EN",
    "LUA-SW-30-500", "LUA-SW-30-500-EN",
    "LUA-MUSTER-STROH", "LUA-MUSTER-STROH-EN",
]
KLEINBESTECK_ARTIKELNUMMERN = [
    "LUA-KB-EIS-500", "LUA-KB-EIS-500-EN",
    "LUA-KB-POMMES-500", "LUA-KB-POMMES-500-EN",
]
GROSSBESTECK_ARTIKELNUMMERN = [
    "LUA-GB-GABEL-150", "LUA-GB-GABEL-150-EN",
    "LUA-GB-LOEFFEL-150", "LUA-GB-LOEFFEL-150-EN",
    "LUA-GB-MESSER-150", "LUA-GB-MESSER-150-EN",
    "LUA-GB-MIX-150", "LUA-GB-MIX-150-EN",
]

GRAMM_JE_STUECK_STROH = Decimal("1.0")
GRAMM_JE_STUECK_KLEINBESTECK = Decimal("2.5")
GRAMM_JE_STUECK_GROSSBESTECK = Decimal("6.0")


def vorwaerts(apps, schema_editor):
    Firma = apps.get_model("vertrieb", "Firma")
    Artikel = apps.get_model("vertrieb", "Artikel")
    Rezeptur = apps.get_model("vertrieb", "Rezeptur")

    tecnaro = Firma.objects.get(name="TECNARO GmbH")
    traceless = Firma.objects.get(name="traceless materials GmbH")

    arboblend, _ = Artikel.objects.update_or_create(
        artikelnummer="ROH-TEC-5953M",
        defaults=dict(
            bezeichnung="ARBOBLEND 5953 M",
            geschaeftsbereich="nachhaltige_verpackung",
            vertriebskanal="standard",
            warengruppe="Rohmaterial",
            einheit="kg",
            materialtyp="rohmaterial",
            einkaufspreis=Decimal("8.74"),
            lieferant_id=tecnaro.pk,
            status="aktiv",
            notizen=(
                "Angelegt 24.10.2026 aus Rechnung TECNARO Nr. 42623004 (8,74 EUR/kg netto, "
                "Zolltarif-Nr. 3907 99 80). Rohmaterial fuer LUAMO-Trinkhalme, ca. 1 g je "
                "Stueck (Angabe Bjoern, 24.10.2026, im Chat)."
            ),
        ),
    )
    form6, _ = Artikel.objects.update_or_create(
        artikelnummer="ROH-TRL-FORM6",
        defaults=dict(
            bezeichnung="FORM 6",
            geschaeftsbereich="nachhaltige_verpackung",
            vertriebskanal="standard",
            warengruppe="Rohmaterial",
            einheit="kg",
            materialtyp="rohmaterial",
            einkaufspreis=Decimal("6.40"),
            lieferant_id=traceless.pk,
            status="aktiv",
            notizen=(
                "Angelegt 24.10.2026, Preis 6,40 EUR/kg laut Angabe Bjoern (24.10.2026, im "
                "Chat) - NICHT aus der zuvor hochgeladenen Auftragsbestaetigung 32-25-00064 "
                "(dort: IM-025 Spritzguss Granulat, 15,00 EUR/kg, vermutlich ein frueherer "
                "Muster-/Testauftrag vom 22.10.2025 - IM-025 wurde deshalb bewusst NICHT als "
                "eigener Artikel angelegt). Rohmaterial fuer LUAMO-Besteck, ca. 2,5 g je "
                "Kleinbesteck-Teil bzw. 6 g je Grossbesteck-Teil."
            ),
        ),
    )

    # LUA-MUSTER-STROH(-EN) haben verpackungseinheit_stk NICHT gesetzt (Excel-Import hat das
    # Feld hier leer gelassen), obwohl die Bezeichnung/Notizen eindeutig "50 Stück"/"50 pcs"
    # ausweisen (geprüft 24.10.2026 gegen die Live-Daten). Wird hier nachgetragen, damit diese
    # zwei Artikel nicht grundlos von der Rezeptur-Zuordnung ausgeschlossen werden.
    for nr in ("LUA-MUSTER-STROH", "LUA-MUSTER-STROH-EN"):
        Artikel.objects.filter(
            artikelnummer=nr, verpackungseinheit_stk__isnull=True
        ).update(verpackungseinheit_stk=50)

    fehlende_verpackungseinheit = []

    def rezeptur_anlegen(artikelnummern, rohmaterial, gramm_je_stueck):
        for nr in artikelnummern:
            fertigprodukt = Artikel.objects.get(artikelnummer=nr)
            if not fertigprodukt.verpackungseinheit_stk:
                fehlende_verpackungseinheit.append(nr)
                continue
            fertigprodukt.materialtyp = "fertigware"
            fertigprodukt.save(update_fields=["materialtyp"])
            menge_je_einheit = (
                gramm_je_stueck * fertigprodukt.verpackungseinheit_stk
            ) / Decimal("1000")
            Rezeptur.objects.update_or_create(
                fertigprodukt=fertigprodukt, rohmaterial=rohmaterial,
                defaults={"menge_je_einheit": menge_je_einheit},
            )

    rezeptur_anlegen(STROH_ARTIKELNUMMERN, arboblend, GRAMM_JE_STUECK_STROH)
    rezeptur_anlegen(KLEINBESTECK_ARTIKELNUMMERN, form6, GRAMM_JE_STUECK_KLEINBESTECK)
    rezeptur_anlegen(GROSSBESTECK_ARTIKELNUMMERN, form6, GRAMM_JE_STUECK_GROSSBESTECK)

    if fehlende_verpackungseinheit:
        # Bewusst ein harter Fehler (bricht die Migration und damit den Deploy ab), statt
        # stillschweigend mit einer geratenen Menge weiterzumachen: eine falsche Rezeptur-Menge
        # wäre im Betrieb viel schwerer zu entdecken als ein fehlgeschlagener Deploy im
        # Render-Build-Log. Stand 24.10.2026 geprüft: betrifft aktuell keinen der oben
        # gelisteten Artikel (alle haben verpackungseinheit_stk gesetzt, LUA-MUSTER-STROH(-EN)
        # wird oben nachgetragen) - dies ist ein Sicherheitsnetz für künftige Änderungen.
        raise RuntimeError(
            "Migration 0032: folgende Artikel haben kein verpackungseinheit_stk gesetzt, "
            "Rezeptur wurde NICHT angelegt, materialtyp NICHT geändert: "
            + ", ".join(fehlende_verpackungseinheit)
        )


def rueckwaerts(apps, schema_editor):
    # Bewusst kein Rückbau: Datenmigration, kein Schema. Ein Downgrade würde echte
    # Rezeptur-/Artikel-Stammdaten löschen, die inzwischen ggf. weiterbearbeitet wurden.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("vertrieb", "0031_lieferanten_materialtyp_verpackungsmaterial"),
    ]

    operations = [
        migrations.RunPython(vorwaerts, rueckwaerts),
    ]
