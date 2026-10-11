from django import forms
from django.forms import inlineformset_factory

from .models import (
    Aktivitaet, Angebot, AngebotPosition, Deal, Firma, Kontakt,
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
        fields = ["position", "bezeichnung", "menge", "einheit", "einzelpreis"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bootstrapify()


AngebotPositionFormSet = inlineformset_factory(
    Angebot, AngebotPosition, form=AngebotPositionForm, extra=1, can_delete=True
)


class PackscheinForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Packschein
        fields = ["deal", "angebot", "datum", "kommissionierer", "status", "notizen"]
        widgets = {
            "notizen": forms.Textarea(attrs={"rows": 3}),
            "datum": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bootstrapify()
        self.fields["angebot"].required = False


class PackscheinPositionForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = PackscheinPosition
        fields = ["position", "bezeichnung", "menge", "einheit", "gepackt"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bootstrapify()


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
        fields = ["position", "bezeichnung", "menge", "einheit"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bootstrapify()


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
        fields = ["position", "bezeichnung", "menge", "einheit", "einzelpreis", "steuersatz"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bootstrapify()


RechnungPositionFormSet = inlineformset_factory(
    Rechnung, RechnungPosition, form=RechnungPositionForm, extra=1, can_delete=True
)
