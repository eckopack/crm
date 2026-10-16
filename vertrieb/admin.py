from django.contrib import admin

from .models import (
    Aktivitaet, Angebot, AngebotPosition, Artikel, Charge, Deal, Firma, Kontakt,
    Lagerbewegung, Preisstaffel, Rezeptur,
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
    list_display = ("nummer", "deal", "datum", "status", "gesamtsumme")
    list_filter = ("status",)
    search_fields = ("nummer",)
    inlines = [AngebotPositionInline]


class PreisstaffelInline(admin.TabularInline):
    model = Preisstaffel
    extra = 1
    ordering = ["-ab_menge"]


@admin.register(Artikel)
class ArtikelAdmin(admin.ModelAdmin):
    list_display = (
        "artikelnummer", "bezeichnung", "geschaeftsbereich", "warengruppe", "materialtyp",
        "verkaufspreis", "lagerbestand_aktuell", "status", "aktualisiert_am",
    )
    list_filter = ("geschaeftsbereich", "warengruppe", "materialtyp", "status")
    search_fields = ("artikelnummer", "bezeichnung")
    inlines = [PreisstaffelInline]


# ---------------------------------------------------------------------------
# Materialwirtschaft (Phase A: Admin-Verwaltung, eigene Bedienoberfläche folgt)
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
        "artikel", "chargennummer", "wareneingang_datum", "mindesthaltbarkeitsdatum",
        "menge_eingang", "bestand_aktuell", "abgelaufen",
    )
    list_filter = ("artikel",)
    search_fields = ("artikel__artikelnummer", "chargennummer")
    readonly_fields = ("bestand_aktuell",)
    autocomplete_fields = ["artikel"]

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
