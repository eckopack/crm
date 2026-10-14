from django import forms
from django.forms import inlineformset_factory

from .models import (
    Aktivitaet, Angebot, AngebotPosition, Artikel, Deal, Firma, Kontakt,
    Packschein, PackscheinPosition, Lieferschein, LieferscheinPosition,
    Rechnung, RechnungPosition,
)


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
            "erwartetes_abschlussdatum": forms.DateInput(attrs={"type": "date"}),
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
        fields = ["deal", "datum", "gueltig_bis", "status", "notizen"]
        widgets = {
            "notizen": forms.Textarea(attrs={"rows": 3}),
            "datum": forms.DateInput(attrs={"type": "date"}),
            "gueltig_bis": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bootstrapify()


class AngebotPositionForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = AngebotPosition
        fields = ["artikel", "position", "bezeichnung", "menge", "einheit", "einzelpreis"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bootstrapify()
        self.fields["artikel"].required = False
        self.fields["artikel"].widget.attrs["class"] = (
            self.fields["artikel"].widget.attrs.get("class", "") + " artikel-auswahl"
        )


AngebotPositionFormSet = inlineformset_factory(
    Angebot, AngebotPosition, form=AngebotPositionForm, extra=1, can_delete=True
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
            "datum": forms.DateInput(attrs={"type": "date"}),
            "versendet_am": forms.DateInput(attrs={"type": "date"}),
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
        widgets = {"versendet_am": forms.DateInput(attrs={"type": "date"})}

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
        self.fields["artikel"].widget.attrs["class"] = (
            self.fields["artikel"].widget.attrs.get("class", "") + " artikel-auswahl"
        )


PackscheinPositionFormSet = inlineformset_factory(
    Packschein, PackscheinPosition, form=PackscheinPositionForm, extra=1, can_delete=True
)


class LieferscheinForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Lieferschein
        fields = ["deal", "angebot", "packschein", "datum", "status", "notizen"]
        widgets = {
            "notizen": forms.Textarea(attrs={"rows": 3}),
            "datum": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bootstrapify()
        self.fields["angebot"].required = False
        self.fields["packschein"].required = False


class LieferscheinPositionForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = LieferscheinPosition
        fields = ["artikel", "position", "bezeichnung", "menge", "einheit"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bootstrapify()
        self.fields["artikel"].required = False
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
            "zahlungsziel_tage", "status", "notizen",
        ]
        widgets = {
            "notizen": forms.Textarea(attrs={"rows": 3}),
            "rechnungsdatum": forms.DateInput(attrs={"type": "date"}),
            "leistungsdatum": forms.DateInput(attrs={"type": "date"}),
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
        self.fields["artikel"].widget.attrs["class"] = (
            self.fields["artikel"].widget.attrs.get("class", "") + " artikel-auswahl"
        )


RechnungPositionFormSet = inlineformset_factory(
    Rechnung, RechnungPosition, form=RechnungPositionForm, extra=1, can_delete=True
)


class ArtikelForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Artikel
        fields = [
            "artikelnummer", "bezeichnung", "beschreibung", "geschaeftsbereich", "warengruppe",
            "einheit", "verkaufspreis", "ust_satz", "einkaufspreis", "lagerbestand_aktuell",
            "mindestbestand", "verpackungseinheit_stk", "lagerort", "lieferant", "status", "notizen",
        ]
        widgets = {
            "beschreibung": forms.Textarea(attrs={"rows": 3}),
            "notizen": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bootstrapify()
