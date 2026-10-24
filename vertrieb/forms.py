from django import forms
from django.forms import inlineformset_factory

from .models import (
    Aktivitaet, Angebot, AngebotPosition, Artikel, Bonusstaffel, Deal, Firma, Kontakt,
    Packschein, PackscheinPosition, Lieferschein, LieferscheinPosition,
    Rahmenvereinbarung, RahmenvereinbarungPosition,
    Rechnung, RechnungPosition, RechnungZahlung,
)


def _artikel_fuer_positionsauswahl():
    """Artikel-Queryset für die Positionsauswahl in Angebot/Packschein/Lieferschein/
    Rechnung - schließt vertriebskanal='amazon' aus (siehe Artikel-Model-Doku: reine
    Amazon-Zweitlistungen mit retail-typischen Preisen, die mit den Großhandelspreisen
    des identischen Produkts nichts zu tun haben und in einem echten Angebot zu einer
    um Größenordnungen falschen Position führen würden)."""
    return Artikel.objects.exclude(vertriebskanal="amazon")


class BootstrapFormMixin:
    """Fügt allen Feldern automatisch Bootstrap-CSS-Klassen hinzu."""

    def _bootstrapify(self):
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                widget.attrs.setdefault("class", "form-select")
            else:
                widget.attrs.setdefault("class", "form-control")


def date_input():
    """DateInput für <input type="date">-Felder - braucht zwingend format="%Y-%m-%d",
    sonst rendert Django den Wert im lokalisierten Format (bei LANGUAGE_CODE "de-de"
    z. B. "16.10.2026"). Das HTML5-Datumsfeld erkennt nur das ISO-Format und zeigt bei
    jedem anderen einfach gar nichts an - ein vorbelegter oder beim Bearbeiten bereits
    gespeicherter Wert erscheint dann als leeres Feld, obwohl der Wert im HTML steht
    und beim erneuten Speichern (ohne Änderung) sogar erhalten bliebe. Eine eigene
    Funktion statt einer geteilten Instanz, weil Widgets zustandsbehaftet sind und
    nicht von mehreren Feldern gleichzeitig verwendet werden sollten."""
    return forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")


class FirmaForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Firma
        fields = [
            "name", "geschaeftsbereich", "status", "branche_kunde", "website",
            "telefon", "email", "strasse", "plz", "ort", "land",
            "zustaendiger", "notizen",
        ]
        widgets = {"notizen": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bootstrapify()


class KontaktForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Kontakt
        fields = [
            "firma", "vorname", "nachname", "position", "email", "telefon",
            "mobil", "ist_hauptansprechpartner", "notizen",
        ]
        widgets = {"notizen": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bootstrapify()


class DealForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Deal
        fields = [
            "titel", "firma", "kontakt", "geschaeftsbereich", "wert", "phase",
            "wahrscheinlichkeit", "erwartetes_abschlussdatum", "zustaendiger",
            "verloren_grund", "notizen",
        ]
        widgets = {
            "notizen": forms.Textarea(attrs={"rows": 4}),
            "erwartetes_abschlussdatum": date_input(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bootstrapify()
        self.fields["kontakt"].queryset = Kontakt.objects.all().select_related("firma")


class AktivitaetForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Aktivitaet
        fields = ["typ", "betreff", "beschreibung", "datum", "erledigt", "firma", "kontakt", "deal", "zustaendiger"]
        widgets = {
            "beschreibung": forms.Textarea(attrs={"rows": 3}),
            "datum": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bootstrapify()
        self.fields["datum"].input_formats = ["%Y-%m-%dT%H:%M"]


class AngebotForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Angebot
        fields = [
            "deal", "rahmenvereinbarung", "datum", "gueltig_bis", "status", "sprache",
            "ansprechpartner", "ablehnungsgrund", "notizen",
        ]
        widgets = {
            "notizen": forms.Textarea(attrs={"rows": 3}),
            "datum": date_input(),
            "gueltig_bis": date_input(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bootstrapify()
        self.fields["rahmenvereinbarung"].required = False
        # 24.10.2026, auf Wunsch von Björn: freie Auswahl ueber ALLE Kontakte (wie beim
        # Deal-Ansprechpartner, siehe DealForm oben) statt nur die der Angebots-Firma -
        # einfacher als eine Firma-abhaengige Live-Filterung per JS, und Kontakt.__str__
        # zeigt die Firma ohnehin mit an, sodass die Auswahl eindeutig bleibt.
        self.fields["ansprechpartner"].queryset = Kontakt.objects.all().select_related("firma")
        self.fields["ansprechpartner"].required = False
        # ablehnungsgrund bewusst NICHT required hier (siehe Model-Doku bei
        # Angebot.ablehnungsgrund) - nur auf dem dedizierten "Angebot ablehnen"-Weg
        # (AngebotAblehnenForm unten) ist das Feld Pflicht.
        self.fields["ablehnungsgrund"].required = False


class AngebotAblehnenForm(BootstrapFormMixin, forms.ModelForm):
    """Dedizierter, bewusst schlanker Weg, ein Angebot als abgelehnt zu markieren (24.10.2026,
    auf Wunsch von Björn) - anders als beim generischen AngebotForm oben ist der Grund hier
    PFLICHT, weil das genau der Moment ist, in dem Björn die Ablehnung bewusst erfasst."""

    class Meta:
        model = Angebot
        fields = ["ablehnungsgrund"]
        widgets = {
            "ablehnungsgrund": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bootstrapify()
        self.fields["ablehnungsgrund"].required = True
        self.fields["ablehnungsgrund"].label = "Grund der Ablehnung"


class AngebotPositionForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = AngebotPosition
        fields = ["artikel", "position", "bezeichnung", "menge", "einheit", "einzelpreis"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bootstrapify()
        self.fields["artikel"].required = False
        self.fields["artikel"].queryset = _artikel_fuer_positionsauswahl()
        self.fields["artikel"].widget.attrs["class"] = (
            self.fields["artikel"].widget.attrs.get("class", "") + " artikel-auswahl"
        )


AngebotPositionFormSet = inlineformset_factory(
    Angebot, AngebotPosition, form=AngebotPositionForm, extra=1, can_delete=True
)


class RahmenvereinbarungForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Rahmenvereinbarung
        fields = ["deal", "sprache", "gueltig_ab", "gueltig_bis", "notizen"]
        widgets = {
            "notizen": forms.Textarea(attrs={"rows": 3}),
            "gueltig_ab": date_input(),
            "gueltig_bis": date_input(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bootstrapify()
        self.fields["gueltig_bis"].required = False


class RahmenvereinbarungPositionForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = RahmenvereinbarungPosition
        fields = ["artikel", "position", "bezeichnung", "jahresmenge", "einheit", "einzelpreis"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bootstrapify()
        self.fields["artikel"].required = False
        self.fields["artikel"].queryset = _artikel_fuer_positionsauswahl()
        self.fields["artikel"].widget.attrs["class"] = (
            self.fields["artikel"].widget.attrs.get("class", "") + " artikel-auswahl"
        )


RahmenvereinbarungPositionFormSet = inlineformset_factory(
    Rahmenvereinbarung, RahmenvereinbarungPosition, form=RahmenvereinbarungPositionForm,
    extra=1, can_delete=True,
)


class BonusstaffelForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Bonusstaffel
        fields = ["ab_menge", "bonus_prozent"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bootstrapify()


BonusstaffelFormSet = inlineformset_factory(
    Rahmenvereinbarung, Bonusstaffel, form=BonusstaffelForm, extra=1, can_delete=True,
)


class PackscheinForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Packschein
        fields = [
            "deal", "angebot", "datum", "kommissionierer", "status", "notizen",
            "ist_musterversand", "versanddienstleister", "trackingnummer", "versendet_am",
        ]
        widgets = {
            "notizen": forms.Textarea(attrs={"rows": 3}),
            "datum": date_input(),
            "versendet_am": date_input(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bootstrapify()
        self.fields["angebot"].required = False
        self.fields["versanddienstleister"].required = False
        self.fields["trackingnummer"].required = False
        self.fields["versendet_am"].required = False


class PackscheinVersandForm(BootstrapFormMixin, forms.ModelForm):
    """Schlanke Form für die Schnellaktion 'Als versendet markieren' auf der
    Packschein-Detailseite – nur die Versanddaten, nicht die ganze Bearbeiten-Form."""

    class Meta:
        model = Packschein
        fields = ["versanddienstleister", "trackingnummer", "versendet_am"]
        widgets = {"versendet_am": date_input()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bootstrapify()
        self.fields["versanddienstleister"].required = False


class PackscheinPositionForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = PackscheinPosition
        fields = ["artikel", "position", "bezeichnung", "menge", "einheit", "gepackt"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bootstrapify()
        self.fields["artikel"].required = False
        self.fields["artikel"].queryset = _artikel_fuer_positionsauswahl()
        self.fields["artikel"].widget.attrs["class"] = (
            self.fields["artikel"].widget.attrs.get("class", "") + " artikel-auswahl"
        )


PackscheinPositionFormSet = inlineformset_factory(
    Packschein, PackscheinPosition, form=PackscheinPositionForm, extra=1, can_delete=True
)


class LieferscheinForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Lieferschein
        fields = [
            "deal", "angebot", "packschein", "rahmenvereinbarung", "datum", "status",
            "sprache", "notizen",
        ]
        widgets = {
            "notizen": forms.Textarea(attrs={"rows": 3}),
            "datum": date_input(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bootstrapify()
        self.fields["angebot"].required = False
        self.fields["packschein"].required = False
        self.fields["rahmenvereinbarung"].required = False


class LieferscheinVersandForm(BootstrapFormMixin, forms.ModelForm):
    """Schlanke Form für die Schnellaktion 'Als versendet markieren' auf der
    Lieferschein-Detailseite - analog zu PackscheinVersandForm. Die Eingabe der
    Trackingnummer hier löst die Versand-Bestätigungsmail an den Kunden aus und
    schaltet die Rechnungserstellung zu diesem Lieferschein frei (siehe
    views.lieferschein_versand_bestaetigen / views.rechnung_erstellen)."""

    class Meta:
        model = Lieferschein
        fields = ["versanddienstleister", "trackingnummer", "versendet_am"]
        widgets = {"versendet_am": date_input()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bootstrapify()
        self.fields["versanddienstleister"].required = True
        self.fields["trackingnummer"].required = True


class LieferscheinPositionForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = LieferscheinPosition
        fields = ["artikel", "position", "bezeichnung", "menge", "einheit"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bootstrapify()
        self.fields["artikel"].required = False
        self.fields["artikel"].queryset = _artikel_fuer_positionsauswahl()
        self.fields["artikel"].widget.attrs["class"] = (
            self.fields["artikel"].widget.attrs.get("class", "") + " artikel-auswahl"
        )


LieferscheinPositionFormSet = inlineformset_factory(
    Lieferschein, LieferscheinPosition, form=LieferscheinPositionForm, extra=1, can_delete=True
)


class RechnungForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Rechnung
        fields = [
            "deal", "angebot", "lieferschein", "rechnungsdatum", "leistungsdatum",
            "zahlungsziel_tage", "status", "sprache", "notizen",
        ]
        widgets = {
            "notizen": forms.Textarea(attrs={"rows": 3}),
            "rechnungsdatum": date_input(),
            "leistungsdatum": date_input(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bootstrapify()
        self.fields["angebot"].required = False
        self.fields["lieferschein"].required = False


class RechnungPositionForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = RechnungPosition
        fields = ["artikel", "position", "bezeichnung", "menge", "einheit", "einzelpreis", "steuersatz"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bootstrapify()
        self.fields["artikel"].required = False
        self.fields["artikel"].queryset = _artikel_fuer_positionsauswahl()
        self.fields["artikel"].widget.attrs["class"] = (
            self.fields["artikel"].widget.attrs.get("class", "") + " artikel-auswahl"
        )


RechnungPositionFormSet = inlineformset_factory(
    Rechnung, RechnungPosition, form=RechnungPositionForm, extra=1, can_delete=True
)


class RechnungZahlungForm(BootstrapFormMixin, forms.ModelForm):
    """Erfassung eines einzelnen Zahlungseingangs (24.10.2026, auf Wunsch von Björn:
    Teilzahlungen möglich) - bewusst ein eigenes, schlankes Formular statt eines Feldes auf
    RechnungForm, weil es über einen eigenen View läuft, der nicht der GoBD-Inhaltssperre
    von rechnung_bearbeiten unterliegt (siehe views.rechnung_zahlung_erfassen)."""

    class Meta:
        model = RechnungZahlung
        fields = ["betrag", "datum", "notiz"]
        widgets = {
            "datum": date_input(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bootstrapify()


class RechnungKorrekturForm(BootstrapFormMixin, forms.ModelForm):
    """Formular fuer eine Stornorechnung/Rechnungskorrektur (24.10.2026, auf Wunsch von
    Björn - NICHT "Gutschrift": dieser Begriff ist nach §14 UStG rechtlich eine vom KAEUFER
    ausgestellte Abrechnung, nicht die hier gemeinte, vom Verkaeufer ausgestellte Korrektur
    einer eigenen Rechnung). Bewusst schlankes Feld-Set gegenueber RechnungForm: deal,
    angebot, lieferschein und status werden von rechnung_korrektur_erstellen() gesetzt
    (deal/angebot/lieferschein vom Original uebernommen, status immer "entwurf" beim
    Anlegen) und sind hier nicht frei waehlbar - eine Korrektur ohne Bezug zum Original darf
    es nicht geben."""

    class Meta:
        model = Rechnung
        fields = ["rechnungsdatum", "leistungsdatum", "sprache", "notizen"]
        widgets = {
            "notizen": forms.Textarea(attrs={"rows": 3}),
            "rechnungsdatum": date_input(),
            "leistungsdatum": date_input(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bootstrapify()


class ArtikelForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Artikel
        fields = [
            "artikelnummer", "bezeichnung", "bezeichnung_en", "beschreibung", "beschreibung_en",
            "geschaeftsbereich", "vertriebskanal", "warengruppe", "einheit", "verkaufspreis",
            "ust_satz", "einkaufspreis", "lagerbestand_aktuell", "mindestbestand",
            "verpackungseinheit_stk", "lagerort", "lieferant", "status", "notizen",
        ]
        widgets = {
            "beschreibung": forms.Textarea(attrs={"rows": 3}),
            "beschreibung_en": forms.Textarea(attrs={"rows": 3}),
            "notizen": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bootstrapify()
