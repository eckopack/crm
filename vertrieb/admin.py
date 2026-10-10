from django.contrib import admin

from .models import Aktivitaet, Angebot, AngebotPosition, Deal, Firma, Kontakt


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
