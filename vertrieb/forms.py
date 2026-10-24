from decimal import Decimal

from django import forms
from django.contrib.auth import get_user_model
from django.forms import inlineformset_factory
from django.utils import timezone

from .models import (
    Aktivitaet, Angebot, AngebotPosition, Artikel, Bonusstaffel, Charge, Deal, Firma,
    Kontakt, MATERIALTYPEN_MIT_CHARGENBESTAND,
    Packschein, PackscheinPosition, Lieferschein, LieferscheinPosition,
    Rahmenvereinbarung, RahmenvereinbarungPosition,
    Rechnung, RechnungPosition, RechnungZahlung, Rezeptur,
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
            "titel", "firma", "kontakt", "geschaeftsbereich", "wert",
            "potenzial_tonnen_trinkhalm", "potenzial_tonnen_besteck", "phase",
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
        # 24.10.2026, auf Wunsch von Björn ("muss bei allen immer vorhanden sein... auch bei
        # Neuanlagen... auch für bestehende Deals"): Pflichtfeld sowohl bei Neuanlage als auch
        # beim Bearbeiten. Das Modellfeld selbst bleibt null=True/blank=True, damit bestehende
        # Deals ohne Wert nicht durch eine Migration zwangsweise invalide würden - erzwungen
        # wird die Angabe stattdessen hier, sobald ein Deal angelegt oder als nächstes
        # bearbeitet wird.
        self.fields["potenzial_tonnen_trinkhalm"].required = True
        self.fields["potenzial_tonnen_besteck"].required = True


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


class WareneingangForm(BootstrapFormMixin, forms.ModelForm):
    """Bucht einen Wareneingang (Phase 2 Materialwirtschaft, 24.10.2026, auf Wunsch von
    Björn) - erzeugt eine neue Charge. Die zugehörige erste Lagerbewegung (Typ
    "Wareneingang") legt NICHT dieses Formular an, sondern der View (siehe
    views.wareneingang_erfassen) in derselben Transaktion, weil eine Charge laut Modell
    nie ohne ihre erste Bewegung entstehen soll.

    Artikelauswahl bewusst auf Rohmaterial/Verpackungsmaterial beschränkt: Handelsware
    bleibt beim bisherigen Feld, Fertigware bekommt ihren Zugang ausschließlich über die
    Produktionsbuchung (Phase 3, 25.10.2026), nicht über Wareneingang - deshalb hier
    bewusst NICHT mehr MATERIALTYPEN_MIT_CHARGENBESTAND verwendet (das umfasst seit
    Phase 3 auch "fertigware"), sondern die beiden Wareneingangs-Materialtypen explizit
    benannt."""

    class Meta:
        model = Charge
        fields = [
            "artikel", "lieferant", "chargennummer", "wareneingang_datum",
            "mindesthaltbarkeitsdatum", "menge_eingang",
        ]
        widgets = {
            "wareneingang_datum": date_input(),
            "mindesthaltbarkeitsdatum": date_input(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["artikel"].queryset = Artikel.objects.filter(
            materialtyp__in=["rohmaterial", "verpackungsmaterial"],
        ).order_by("artikelnummer")
        self._bootstrapify()

    def clean_menge_eingang(self):
        menge = self.cleaned_data["menge_eingang"]
        if menge <= 0:
            raise forms.ValidationError("Die Menge muss größer als 0 sein.")
        return menge


class ProduktionsbuchungForm(BootstrapFormMixin, forms.Form):
    """Bucht eine Produktionsbuchung (Phase 3 Materialwirtschaft, 25.10.2026, auf Wunsch
    von Björn "phase 3 starten") - bewusst ein einfaches forms.Form statt eines
    ModelForm, weil die Anzahl der Rohmaterial-Chargenfelder von der Rezeptur des
    jeweiligen Fertigprodukts abhängt und deshalb erst zur Laufzeit (in __init__)
    entstehen kann. Legt selbst weder Produktionsbuchung noch Charge/Lagerbewegung an -
    das übernimmt views.produktionsbuchung_erfassen in einer Transaktion, siehe dort.

    Pro Rezeptur-Zeile genau EIN Chargenfeld (Björns Entscheidung "erstmal nur eine
    Charge pro Buchung", 25.10.2026) - die Mengenprüfung gegen den Chargenbestand
    passiert hier in clean() (reicht nicht: Buchung wird blockiert, siehe
    Produktionsbuchung-Model-Doku) sowie sicherheitshalber ein zweites Mal mit
    select_for_update() im View unmittelbar vor dem Speichern."""

    menge_soll = forms.DecimalField(
        label="Geplante Menge (Soll)", max_digits=14, decimal_places=3, required=False,
        help_text="Optional, nur zur Dokumentation.",
    )
    menge_ist = forms.DecimalField(
        label="Produzierte Gutmenge (Ist)", max_digits=14, decimal_places=3,
        help_text="Bestimmt den Fertigware-Zugang.",
    )
    menge_ausschuss = forms.DecimalField(
        label="Ausschussmenge", max_digits=14, decimal_places=3, required=False,
        help_text="Verbraucht ebenfalls Rohmaterial, erzeugt aber keinen Fertigware-Zugang.",
    )
    datum = forms.DateTimeField(
        label="Datum/Zeit der Produktion", initial=timezone.now,
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        input_formats=["%Y-%m-%dT%H:%M"],
    )
    zustaendiger = forms.ModelChoiceField(
        label="Zuständiger Mitarbeiter", queryset=get_user_model().objects.order_by("username"),
        required=False,
    )
    chargennummer = forms.CharField(label="Chargennummer (Fertigware)", max_length=100, required=False)
    mindesthaltbarkeitsdatum = forms.DateField(
        label="Mindesthaltbarkeitsdatum (Fertigware)", required=False, widget=date_input(),
    )
    notizen = forms.CharField(label="Notizen", required=False, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, fertigprodukt, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fertigprodukt = fertigprodukt
        self.rezeptur_zeilen = list(
            Rezeptur.objects.filter(fertigprodukt=fertigprodukt).select_related("rohmaterial")
        )
        self._charge_feldnamen = {}
        for zeile in self.rezeptur_zeilen:
            feldname = f"charge_{zeile.pk}"
            self._charge_feldnamen[zeile.pk] = feldname
            self.fields[feldname] = forms.ModelChoiceField(
                label=(
                    f"Charge für {zeile.rohmaterial.artikelnummer} "
                    f"({zeile.menge_je_einheit} {zeile.rohmaterial.get_einheit_display()} je Einheit)"
                ),
                queryset=Charge.objects.filter(
                    artikel=zeile.rohmaterial, bestand_aktuell__gt=Decimal("0"),
                ).order_by("wareneingang_datum", "erstellt_am"),
                help_text="Älteste verfügbare Charge zuerst (FIFO). Reicht die gewählte Charge "
                          "nicht aus, muss eine zweite Produktionsbuchung mit der nächsten "
                          "Charge erfasst werden.",
            )
        self._bootstrapify()

    def rezeptur_zeilen_mit_feld(self):
        """Für das Template (kann dort keine Methode mit Argument aufrufen): liefert je
        Rezeptur-Zeile ein (zeile, bound_field)-Tupel des zugehörigen Chargenfelds."""
        return [(zeile, self[self._charge_feldnamen[zeile.pk]]) for zeile in self.rezeptur_zeilen]

    def clean_menge_ist(self):
        menge = self.cleaned_data["menge_ist"]
        if menge <= 0:
            raise forms.ValidationError("Die Gutmenge muss größer als 0 sein.")
        return menge

    def clean_menge_ausschuss(self):
        menge = self.cleaned_data.get("menge_ausschuss")
        if menge is None:
            return Decimal("0")
        if menge < 0:
            raise forms.ValidationError("Die Ausschussmenge darf nicht negativ sein.")
        return menge

    def clean(self):
        cleaned = super().clean()
        if not self.rezeptur_zeilen:
            raise forms.ValidationError(
                f"Für {self.fertigprodukt.artikelnummer} ist keine Rezeptur hinterlegt - "
                "bitte zuerst im Admin unter Rezeptur-Zeilen anlegen."
            )
        menge_ist = cleaned.get("menge_ist")
        menge_ausschuss = cleaned.get("menge_ausschuss") or Decimal("0")
        if menge_ist is None:
            return cleaned
        gesamtmenge = menge_ist + menge_ausschuss
        for zeile in self.rezeptur_zeilen:
            feldname = self._charge_feldnamen[zeile.pk]
            charge = cleaned.get(feldname)
            if charge is None:
                continue
            benoetigt = zeile.menge_je_einheit * gesamtmenge
            if charge.bestand_aktuell < benoetigt:
                self.add_error(
                    feldname,
                    f"Reicht nicht aus: benötigt {benoetigt} {zeile.rohmaterial.get_einheit_display()}, "
                    f"Charge hat nur noch {charge.bestand_aktuell} {zeile.rohmaterial.get_einheit_display()}.",
                )
        return cleaned


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
            "verpackungseinheit_stk", "lagerort", "lieferant_freitext", "status", "notizen",
        ]
        widgets = {
            "beschreibung": forms.Textarea(attrs={"rows": 3}),
            "beschreibung_en": forms.Textarea(attrs={"rows": 3}),
            "notizen": forms.Textarea(attrs={"rows": 3}),
        }
        # 24.10.2026: Label hier bewusst auf "Lieferant" vereinfacht (statt dem technischeren
        # Model-Label "Lieferant (Freitext, Altfeld)") - dieses Formular bedient weiterhin fast
        # ausschließlich Handelsware (materialtyp ist hier gar nicht wählbar), für die es noch
        # keine Umstellung auf Lieferanten-Stammdaten gibt. Die Unterscheidung Alt-/Neufeld ist
        # nur im Admin relevant, wo beide Felder nebeneinander auftauchen.
        labels = {"lieferant_freitext": "Lieferant"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bootstrapify()
        # Phase 2 Materialwirtschaft (24.10.2026): für Rohmaterial/Verpackungsmaterial wird
        # der Bestand seit der Wareneingang-Oberfläche aus Chargen berechnet (siehe
        # Artikel.lagerbestand_anzeige) - das Feld hier von Hand zu befüllen würde nur
        # stillschweigend ignoriert, deshalb hier gesperrt statt eine wirkungslose Eingabe
        # zuzulassen. Neue Artikel starten immer mit materialtyp="handelsware" (hier gar
        # nicht wählbar), betrifft also nur das Bearbeiten bestehender Rohmaterial-/
        # Verpackungsmaterial-Artikel.
        if self.instance.pk and self.instance.materialtyp in MATERIALTYPEN_MIT_CHARGENBESTAND:
            feld = self.fields["lagerbestand_aktuell"]
            feld.disabled = True
            feld.help_text = (
                "Wird seit der Wareneingang-Oberfläche automatisch aus den Chargen berechnet "
                "- bitte über \"Wareneingang buchen\" auf der Artikel-Seite erfassen, nicht "
                "hier von Hand eintragen."
            )
