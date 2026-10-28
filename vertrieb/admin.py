from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin
from django.utils import timezone

from .models import (
    Aktivitaet, Angebot, AngebotNachfassStatus, AngebotNachfassVorlage, AngebotPosition,
    Artikel, Auftrag, AuftragPosition, Charge, Deal, Firma, Kontakt, Lagerbewegung,
    MitarbeiterSprache,
    MusterboxNachfassStatus, MusterboxNachfassVorlage, Preisstaffel, Produktionsbericht,
    Produktionsbuchung, Rechnung, RechnungZahlung, Rezeptur,
)


class KontaktInline(admin.TabularInline):
    model = Kontakt
    extra = 0


@admin.register(Firma)
class FirmaAdmin(admin.ModelAdmin):
    """24.10.2026, auf Wunsch von Björn: Firmen duerfen nicht mehr unwiderruflich geloescht
    werden (siehe Firma.archiviert/kann_archiviert_werden und firma_archivieren-View in der
    Oberflaeche) - Loeschen ist deshalb auch hier im Admin gesperrt, damit dieser Weg nicht
    an der Archivierungs-Sperre vorbeigeht."""

    list_display = ("name", "geschaeftsbereich", "status", "archiviert", "ort", "zustaendiger", "aktualisiert_am")
    list_filter = ("geschaeftsbereich", "status", "archiviert")
    search_fields = ("name", "ort", "email")
    inlines = [KontaktInline]

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Kontakt)
class KontaktAdmin(admin.ModelAdmin):
    """24.10.2026, auf Wunsch von Björn: siehe FirmaAdmin - dieselbe Sperre gilt hier."""

    list_display = ("nachname", "vorname", "firma", "position", "email", "telefon", "archiviert")
    list_filter = ("firma", "archiviert")
    search_fields = ("vorname", "nachname", "email")

    def has_delete_permission(self, request, obj=None):
        return False


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


class AuftragPositionInline(admin.TabularInline):
    model = AuftragPosition
    extra = 1


@admin.register(Auftrag)
class AuftragAdmin(admin.ModelAdmin):
    list_display = ("nummer", "deal", "datum", "status", "sprache", "gesamtsumme")
    list_filter = ("status", "sprache")
    search_fields = ("nummer",)
    inlines = [AuftragPositionInline]


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
    list_display = (
        "datum", "artikel", "bewegungstyp", "menge", "charge", "lieferschein",
        "produktionsbuchung", "erstellt_von",
    )
    list_filter = ("bewegungstyp", "artikel")
    search_fields = ("artikel__artikelnummer",)
    autocomplete_fields = ["artikel", "charge", "produktionsbuchung"]
    readonly_fields = ("datum",)

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        if not change and obj.erstellt_von_id is None:
            obj.erstellt_von = request.user
        super().save_model(request, obj, form, change)


@admin.register(Produktionsbuchung)
class ProduktionsbuchungAdmin(admin.ModelAdmin):
    """25.10.2026, Phase 3: rein lesend im Admin - eine Produktionsbuchung besteht immer
    aus mehreren, in einer Transaktion zusammengehörigen Lagerbewegungen plus einer neu
    angelegten Fertigware-Charge (siehe views.produktionsbuchung_erfassen) und Mengen-
    Prüfungen gegen den aktuellen Chargenbestand. Über den Admin angelegt/geändert würde
    das alles umgehen - die Bedienoberfläche unter "Lagerwirtschaft -> Produktion buchen"
    ist deshalb der einzige vorgesehene Weg, eine Produktionsbuchung zu erstellen."""
    list_display = ("datum", "fertigprodukt", "menge_ist", "menge_ausschuss", "zustaendiger", "erstellt_von")
    list_filter = ("fertigprodukt",)
    search_fields = ("fertigprodukt__artikelnummer",)
    autocomplete_fields = ["fertigprodukt", "charge", "zustaendiger"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Produktionsbericht)
class ProduktionsberichtAdmin(admin.ModelAdmin):
    """26.10.2026, Pilot Trinkhalm-L1: ebenfalls rein lesend im Admin, aus demselben Grund
    wie ProduktionsbuchungAdmin oben - Einreichen/Freigeben/Ablehnen laufen ausschließlich
    über die eigene Oberfläche (siehe views.produktionsbericht_*), damit Statuswechsel und
    die daraus entstehende Produktionsbuchung konsistent bleiben.

    AUSNAHME (26.10.2026, Björns Rückfrage "was fehlt noch..." - Datenschutz ist ihm wichtig,
    es gibt aber keinen Betriebsrat und er will die Löschfrist zunächst NICHT automatisieren,
    sondern von Fall zu Fall entscheiden): die Aktion personenbezug_entfernen unten ist die
    einzige Schreiboperation, die hier im Admin trotz has_change_permission=False möglich ist
    (Django prüft bei eigenen Actions nicht has_change_permission, siehe ModelAdmin.
    response_action) - bewusst so, weil sie unabhängig vom normalen Freigabe-Workflow sein muss
    und nur die in Produktionsbericht.personenbezug_entfernt dokumentierten Felder anfasst."""
    list_display = (
        "datum", "linie", "fertigprodukt", "status", "menge_gut_stueck",
        "eingereicht_von", "freigegeben_von", "personenbezug_entfernt",
    )
    list_filter = ("linie", "status", "fertigprodukt", "personenbezug_entfernt")
    search_fields = ("fertigprodukt__artikelnummer",)
    autocomplete_fields = ["fertigprodukt", "bediener_1", "freigegeben_von", "produktionsbuchung"]
    actions = ["personenbezug_entfernen"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description="DSGVO: Personenbezug entfernen (Bediener/Reinigung/Bemerkungen)")
    def personenbezug_entfernen(self, request, queryset):
        """Anonymisiert die ausgewählten Berichte: Bediener 1/2, Reinigungsperson und
        Bemerkungen werden geleert, Mengen/Status/Verknüpfung zur Produktionsbuchung bleiben
        für Lagerführung und Audit-Trail unverändert erhalten (siehe Moduldoku in models.py).
        Bereits anonymisierte Berichte werden übersprungen, damit personenbezug_entfernt_am
        nicht versehentlich überschrieben wird."""
        zu_bearbeiten = queryset.exclude(personenbezug_entfernt=True)
        anzahl = zu_bearbeiten.count()
        uebersprungen = queryset.count() - anzahl
        jetzt = timezone.now()
        for bericht in zu_bearbeiten:
            bericht.bediener_1 = None
            bericht.bediener_2 = ""
            bericht.reinigung_durchgefuehrt_von = ""
            bericht.bemerkungen = ""
            bericht.personenbezug_entfernt = True
            bericht.personenbezug_entfernt_am = jetzt
            bericht.save(update_fields=[
                "bediener_1", "bediener_2", "reinigung_durchgefuehrt_von", "bemerkungen",
                "personenbezug_entfernt", "personenbezug_entfernt_am",
            ])
        meldung = f"{anzahl} Produktionsbericht(e) anonymisiert."
        if uebersprungen:
            meldung += f" {uebersprungen} war(en) bereits anonymisiert und wurde(n) übersprungen."
        self.message_user(request, meldung)


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


class MitarbeiterSpracheInline(admin.StackedInline):
    """27.10.2026, auf Wunsch von Björn (zwei MA sprechen Tschechisch/Ukrainisch): direkt auf
    der Benutzer-Bearbeitungsseite im Admin sichtbar/einstellbar, statt als eigene,
    separate Admin-Liste - Björn/Bizer legen hier ohnehin schon die MA-Konten an (siehe
    Produktionsbericht-Moduldoku in models.py), die Sprache gehört inhaltlich direkt dazu.
    can_delete=False: ohne Eintrag gilt automatisch "de" (siehe
    produktion_sprachen.sprache_fuer_konto), ein Löschen hier wäre nur verwirrend."""
    model = MitarbeiterSprache
    can_delete = False
    verbose_name_plural = "Produktionsbericht-Oberflächensprache"


class ECKOPackUserAdmin(UserAdmin):
    inlines = [*UserAdmin.inlines, MitarbeiterSpracheInline]


admin.site.unregister(get_user_model())
admin.site.register(get_user_model(), ECKOPackUserAdmin)
