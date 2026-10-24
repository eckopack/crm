from django.contrib import admin

from .models import (
    Aktivitaet, Angebot, AngebotNachfassStatus, AngebotNachfassVorlage, AngebotPosition,
    Artikel, Charge, Deal, Firma, Kontakt, Lagerbewegung, MusterboxNachfassStatus,
    MusterboxNachfassVorlage, Preisstaffel, Rechnung, RechnungZahlung, Rezeptur,
)


class KontaktInline(admin.TabularInline):
    model = Kontakt
    extra = 0


@admin.register(Firma)
class FirmaAdmin(admin.ModelAdmin):
    list_display = ("name", "geschaeftsbereich", "status", "ort", "zustaendiger", "aktualisiert_am")
    list_filter = ("geschaeftsbereich", "status")
    search_fields = ("name", "ort", "email")
    inlines = [KontaktInline]


@admin.register(Kontakt)
class KontaktAdmin(admin.ModelAdmin):
    list_display = ("nachname", "vorname", "firma", "position", "email", "telefon")
    list_filter = ("firma",)
    search_fields = ("vorname", "nachname", "email")


@admin.register(Deal)
class DealAdmin(admin.ModelAdmin):
    list_display = ("titel", "firma", "phase", "wert", "wahrscheinlichkeit", "zustaendiger", "erwartetes_abschlussdatum")
    list_filter = ("phase", "geschaeftsbereich")
    search_fields = ("titel", "firma__name")


@admin.register(Aktivitaet)
class AktivitaetAdmin(admin.ModelAdmin):
    list_display = ("betreff", "typ", "datum", "erledigt", "firma", "deal", "zustaendiger")
    list_filter = ("typ", "erledigt")
    search_fields = ("betreff", "beschreibung")


class AngebotPositionInline(admin.TabularInline):
    model = AngebotPosition
    extra = 1


@admin.register(Angebot)
class AngebotAdmin(admin.ModelAdmin):
    list_display = ("nummer", "deal", "datum", "status", "sprache", "gesamtsumme")
    list_filter = ("status", "sprache")
    search_fields = ("nummer",)
    inlines = [AngebotPositionInline]


class PreisstaffelInline(admin.TabularInline):
    model = Preisstaffel
    extra = 1
    ordering = ["-ab_menge"]


@admin.register(Artikel)
class ArtikelAdmin(admin.ModelAdmin):
    list_display = (
        "artikelnummer", "bezeichnung", "vertriebskanal", "geschaeftsbereich", "warengruppe",
        "materialtyp", "verkaufspreis", "lagerbestand_aktuell", "status", "aktualisiert_am",
    )
    list_filter = ("vertriebskanal", "geschaeftsbereich", "warengruppe", "materialtyp", "status")
    search_fields = ("artikelnummer", "bezeichnung")
    autocomplete_fields = ["lieferant"]
    inlines = [PreisstaffelInline]


# ---------------------------------------------------------------------------
# Materialwirtschaft (Phase A: Admin-Verwaltung, eigene Bedienoberfläche folgt)
#
# Lieferanten (24.10.2026) sind Firmen mit status="lieferant" - siehe FirmaAdmin oben, kein
# eigenes Admin-Modell nötig. FirmaAdmin.search_fields deckt bereits das Autocomplete für
# Artikel.lieferant/Charge.lieferant unten ab.
# ---------------------------------------------------------------------------

@admin.register(Rezeptur)
class RezepturAdmin(admin.ModelAdmin):
    list_display = ("fertigprodukt", "rohmaterial", "menge_je_einheit")
    list_filter = ("fertigprodukt", "rohmaterial")
    search_fields = ("fertigprodukt__artikelnummer", "rohmaterial__artikelnummer")
    autocomplete_fields = ["fertigprodukt", "rohmaterial"]


@admin.register(Charge)
class ChargeAdmin(admin.ModelAdmin):
    list_display = (
        "artikel", "chargennummer", "wareneingang_datum", "lieferant", "mindesthaltbarkeitsdatum",
        "menge_eingang", "bestand_aktuell", "abgelaufen",
    )
    list_filter = ("artikel", "lieferant")
    search_fields = ("artikel__artikelnummer", "chargennummer")
    readonly_fields = ("bestand_aktuell",)
    autocomplete_fields = ["artikel", "lieferant"]

    def get_readonly_fields(self, request, obj=None):
        # bestand_aktuell wird ausschliesslich ueber Lagerbewegungen fortgeschrieben (siehe
        # Lagerbewegung.save()), nie direkt im Formular - sonst drohte Doppelzaehlung, wenn
        # zusaetzlich eine Wareneingangs-Bewegung drauf gebucht wird.
        return ("bestand_aktuell",)

    def save_model(self, request, obj, form, change):
        neu = not change
        super().save_model(request, obj, form, change)
        if neu and obj.menge_eingang:
            # Eine neue Charge beginnt bei Bestand 0 (Modell-Default) - die zugehoerige
            # Wareneingangsmenge wird als eigene, sichtbare Lagerbewegung gebucht statt
            # beim Anlegen der Charge "unsichtbar" mitgesetzt zu werden. Das haelt Charge
            # und Lagerbewegung als getrennte Wahrheitsquellen auseinander (siehe Modul-
            # Docstring) und ist bis zur eigenen Wareneingang-Erfassung (Phase B) der
            # schnellste korrekte Weg, eine Charge im Admin direkt nutzbar zu machen.
            Lagerbewegung.objects.create(
                artikel=obj.artikel, charge=obj, bewegungstyp="wareneingang",
                menge=obj.menge_eingang, erstellt_von=request.user,
            )


@admin.register(MusterboxNachfassVorlage)
class MusterboxNachfassVorlageAdmin(admin.ModelAdmin):
    """Admin für die acht festen Wochen-Vorlagen der Musterbox-Nachfasskette (siehe
    Model-Doku): weder neue Zeilen hinzufügen noch bestehende löschen - die acht Wochen sind
    ein fester Rahmen, der per Datenmigration angelegt wird. Nur Betreff/Text je Woche sind
    bearbeitbar. Seit 18.10.2026 16 Zeilen (8 Wochen × 2 Sprachen) statt 8."""
    list_display = ("woche", "sprache", "betreff", "aktualisiert_am", "aktualisiert_von")
    list_filter = ("sprache",)
    ordering = ["woche", "sprache"]
    readonly_fields = ("woche", "sprache", "aktualisiert_am", "aktualisiert_von")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        obj.aktualisiert_von = request.user
        super().save_model(request, obj, form, change)


@admin.register(MusterboxNachfassStatus)
class MusterboxNachfassStatusAdmin(admin.ModelAdmin):
    """Rein informativ zur Nachverfolgung, mit der Möglichkeit, eine einzelne Kette manuell
    zu pausieren/beenden (z.B. aktiv=False setzen) - Zeilen selbst werden ausschließlich
    automatisch angelegt (siehe nurture.musterversand_abgeschlossen), daher kein manuelles
    Hinzufügen."""
    list_display = ("deal", "sprache", "naechste_woche", "naechster_versand_am", "aktiv", "beendet_grund")
    list_filter = ("aktiv", "sprache", "beendet_grund")
    search_fields = ("deal__titel", "deal__firma__name")
    readonly_fields = ("deal", "erstellt_am")

    def has_add_permission(self, request):
        return False


@admin.register(AngebotNachfassVorlage)
class AngebotNachfassVorlageAdmin(admin.ModelAdmin):
    """Admin für die sechs festen Vorlagen (3 Schritte × 2 Sprachen) der Angebot-
    Nachfasskette (siehe Model-Doku) - werden leer per Datenmigration angelegt, Björn muss
    Betreff und Text hier eintragen, bevor die Kette tatsächlich Kundenmails verschickt
    (siehe nurture.angebot_nachfass_senden)."""
    list_display = ("schritt", "sprache", "betreff", "aktualisiert_am", "aktualisiert_von")
    list_filter = ("sprache",)
    ordering = ["schritt", "sprache"]
    readonly_fields = ("schritt", "sprache", "aktualisiert_am", "aktualisiert_von")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        obj.aktualisiert_von = request.user
        super().save_model(request, obj, form, change)


@admin.register(AngebotNachfassStatus)
class AngebotNachfassStatusAdmin(admin.ModelAdmin):
    """Rein informativ zur Nachverfolgung, mit der Möglichkeit, eine einzelne Kette manuell
    zu pausieren/beenden (z.B. aktiv=False setzen) - Zeilen selbst werden ausschließlich
    automatisch angelegt (siehe signals.angebot_status_wechsel), daher kein manuelles
    Hinzufügen."""
    list_display = ("angebot", "sprache", "naechster_schritt", "naechster_versand_am", "aktiv", "beendet_grund")
    list_filter = ("aktiv", "sprache", "beendet_grund")
    search_fields = ("angebot__nummer", "angebot__deal__titel", "angebot__deal__firma__name")
    readonly_fields = ("angebot", "versendet_am", "erstellt_am")

    def has_add_permission(self, request):
        return False


@admin.register(Lagerbewegung)
class LagerbewegungAdmin(admin.ModelAdmin):
    """Reines Journal: anlegen ja, aendern/loeschen nein (siehe Lagerbewegung.delete()
    und Moduldoku in models.py) - Korrekturen laufen ueber eine neue Gegenbuchung."""
    list_display = ("datum", "artikel", "bewegungstyp", "menge", "charge", "lieferschein", "erstellt_von")
    list_filter = ("bewegungstyp", "artikel")
    search_fields = ("artikel__artikelnummer",)
    autocomplete_fields = ["artikel", "charge"]
    readonly_fields = ("datum",)

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        if not change and obj.erstellt_von_id is None:
            obj.erstellt_von = request.user
        super().save_model(request, obj, form, change)


@admin.register(RechnungZahlung)
class RechnungZahlungAdmin(admin.ModelAdmin):
    """24.10.2026, auf Wunsch von Björn (Offene-Posten-Uebersicht): hier ebenfalls
    nutzbar fuer Korrekturen - Rechnung.status wird dabei nicht hier, sondern ereignis-
    basiert per Signal aktualisiert (siehe signals.py), funktioniert also unabhaengig
    davon, ob eine Zahlung ueber views.rechnung_zahlung_erfassen oder hier im Admin
    angelegt/geaendert/geloescht wird."""
    list_display = ("rechnung", "betrag", "datum", "notiz", "erfasst_am")
    list_filter = ("datum",)
    search_fields = ("rechnung__nummer", "rechnung__deal__firma__name")
