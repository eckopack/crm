import os
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.paginator import Paginator
from django.core.validators import validate_email
from django.db import models, transaction
from django.db.models import Sum
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView, View

from . import nurture, pdf
from .forms import (
    AktivitaetForm, AngebotAblehnenForm, AngebotForm, AngebotPositionFormSet, ArtikelForm,
    BonusstaffelFormSet, DealForm, FirmaForm, KontaktForm,
    PackscheinForm, PackscheinPositionFormSet, PackscheinVersandForm,
    LieferscheinForm, LieferscheinPositionFormSet, LieferscheinVersandForm,
    RahmenvereinbarungForm, RahmenvereinbarungPositionFormSet,
    RechnungForm, RechnungKorrekturForm, RechnungPositionFormSet, RechnungZahlungForm,
    WareneingangForm,
)
from .models import (
    ANGEBOT_NACHFASS_SCHRITTE, DEAL_PHASE_CHOICES, MUSTERKARTON_ARTIKEL,
    PHASE_STANDARD_WAHRSCHEINLICHKEIT, Aktivitaet, Angebot, AngebotNachfassStatus, Artikel,
    Charge, Deal, EmailVersand, Firma, Kontakt, Lagerbewegung, MATERIALTYPEN_MIT_CHARGENBESTAND,
    MusterboxNachfassStatus, Packschein, PackscheinPosition,
    Lieferschein, Rahmenvereinbarung, Rechnung, RechnungPosition, RechnungZahlung,
)
from django.forms import inlineformset_factory


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@login_required
def dashboard(request):
    offene_deals = Deal.objects.filter(phase__in=["lead", "qualifiziert", "angebot", "verhandlung"])
    pipeline_wert = offene_deals.aggregate(s=Sum("wert"))["s"] or 0
    pipeline_gewichtet = sum(d.gewichteter_wert for d in offene_deals)

    jetzt = timezone.now()
    anstehend = (
        Aktivitaet.objects.filter(erledigt=False, datum__gte=jetzt)
        .order_by("datum")[:8]
    )
    ueberfaellig = (
        Aktivitaet.objects.filter(erledigt=False, datum__lt=jetzt)
        .order_by("datum")
    )

    phasen_uebersicht = []
    for key, label in DEAL_PHASE_CHOICES:
        qs = Deal.objects.filter(phase=key)
        phasen_uebersicht.append({
            "key": key,
            "label": label,
            "anzahl": qs.count(),
            "wert": qs.aggregate(s=Sum("wert"))["s"] or 0,
        })

    # 24.10.2026, auf Wunsch von Björn (Offene-Posten-Uebersicht, siehe
    # views.offene_posten_liste): gleiche "ueberfaellig berechnen"-Logik wie dort, hier nur
    # auf die fuers Dashboard relevanten paar neuesten/dringendsten Zeilen verkuerzt.
    offene_rechnungen = (
        Rechnung.objects.filter(status="versendet")
        .select_related("deal", "deal__firma")
        .prefetch_related("positionen", "zahlungen")
    )
    ueberfaellige_rechnungen = sorted(
        (r for r in offene_rechnungen if r.ist_ueberfaellig),
        key=lambda r: r.faelligkeitsdatum,
    )
    summe_ueberfaellige_rechnungen = sum(
        (r.offener_betrag for r in ueberfaellige_rechnungen), start=Decimal("0")
    )

    kontext = {
        "pipeline_wert": pipeline_wert,
        "pipeline_gewichtet": pipeline_gewichtet,
        "anzahl_offene_deals": offene_deals.count(),
        "anzahl_firmen": Firma.objects.count(),
        "anstehend": anstehend,
        "ueberfaellig": ueberfaellig,
        "ueberfaellige_rechnungen": ueberfaellige_rechnungen[:8],
        "anzahl_ueberfaellige_rechnungen": len(ueberfaellige_rechnungen),
        "summe_ueberfaellige_rechnungen": summe_ueberfaellige_rechnungen,
        "phasen_uebersicht": phasen_uebersicht,
    }
    return render(request, "vertrieb/dashboard.html", kontext)


@login_required
def pipeline_kanban(request):
    spalten = []
    for key, label in DEAL_PHASE_CHOICES:
        deals = Deal.objects.filter(phase=key).select_related("firma", "zustaendiger")
        # 24.10.2026, auf Wunsch von Björn: Mengenpotenzial ist jetzt nach Trinkhalm/Besteck
        # aufgeteilt (siehe Deal-Model) - die Spalten-Summe bleibt die Gesamt-Tonnage ueber
        # beide Kategorien, deshalb beide Sum()-Aggregate einzeln holen und in Python addieren
        # (ein SQL-Sum(F()+F()) wuerde bei NULL in einer der beiden Spalten NULL ergeben).
        tonnen_agg = deals.aggregate(trinkhalm=Sum("potenzial_tonnen_trinkhalm"), besteck=Sum("potenzial_tonnen_besteck"))
        spalten.append({
            "key": key,
            "label": label,
            "deals": deals,
            "summe": deals.aggregate(s=Sum("wert"))["s"] or 0,
            "tonnen_summe": (tonnen_agg["trinkhalm"] or 0) + (tonnen_agg["besteck"] or 0),
        })
    return render(request, "vertrieb/pipeline.html", {"spalten": spalten})


@login_required
def deal_phase_setzen(request, pk):
    """Schnellaktion aus der Kanban-Ansicht: Phase eines Deals per Klick ändern."""
    deal = get_object_or_404(Deal, pk=pk)
    if request.method == "POST":
        neue_phase = request.POST.get("phase")
        if neue_phase in dict(DEAL_PHASE_CHOICES):
            deal.phase = neue_phase
            deal.wahrscheinlichkeit = PHASE_STANDARD_WAHRSCHEINLICHKEIT.get(neue_phase, deal.wahrscheinlichkeit)
            deal.save()
    return redirect("vertrieb:pipeline")


@csrf_exempt
def interner_nachfass_cron(request):
    """Endpoint für den externen Render-Cron-Job (siehe render.yaml).

    Der Cron-Job selbst hat keinen Zugriff auf die SQLite-Datei auf der Disk (die ist
    nur an den Web-Service gebunden) – er ruft deshalb stattdessen diese URL per HTTPS
    auf, und die eigentliche Prüfung läuft hier, im Web-Prozess, mit normalem
    Datenbankzugriff. Schutz über ein geteiltes Secret im Header statt Login, weil hier
    kein Mensch eingeloggt ist.
    """
    erwartet = os.environ.get("NACHFASS_CRON_SECRET", "")
    erhalten = request.headers.get("X-Cron-Secret", "")
    if not erwartet or erhalten != erwartet:
        return HttpResponseForbidden("Ungueltiges oder fehlendes Secret.")
    call_command("nachfass_pruefen")
    return HttpResponse("OK")


# ---------------------------------------------------------------------------
# Firma
# ---------------------------------------------------------------------------

class FirmaListView(LoginRequiredMixin, ListView):
    model = Firma
    template_name = "vertrieb/firma_list.html"
    context_object_name = "firmen"
    paginate_by = 25

    def get_queryset(self):
        qs = Firma.objects.all().select_related("zustaendiger")
        self.zeige_archiv = self.request.GET.get("archiv") == "1"
        qs = qs.filter(archiviert=self.zeige_archiv)
        suche = self.request.GET.get("q")
        if suche:
            qs = qs.filter(name__icontains=suche)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["zeige_archiv"] = self.zeige_archiv
        return context


class FirmaDetailView(LoginRequiredMixin, DetailView):
    model = Firma
    template_name = "vertrieb/firma_detail.html"
    context_object_name = "firma"


class FirmaCreateView(LoginRequiredMixin, CreateView):
    model = Firma
    form_class = FirmaForm
    template_name = "vertrieb/firma_form.html"


class FirmaUpdateView(LoginRequiredMixin, UpdateView):
    model = Firma
    form_class = FirmaForm
    template_name = "vertrieb/firma_form.html"


@login_required
def firma_archivieren(request, pk):
    """24.10.2026, auf Wunsch von Björn: ersetzt FirmaDeleteView - Firmen duerfen nicht mehr
    unwiderruflich geloescht werden, nur noch archiviert, und auch das nur, solange nichts
    Aktives mehr daran haengt (siehe Firma.kann_archiviert_werden)."""
    firma = get_object_or_404(Firma, pk=pk)
    if request.method == "POST":
        if not firma.kann_archiviert_werden:
            messages.warning(
                request,
                f"\"{firma.name}\" ist noch mit einem offenen Deal, einer unbezahlten Rechnung "
                f"oder einer offenen Aktivität verknüpft und kann deshalb nicht archiviert werden.",
            )
            return redirect(firma.get_absolute_url())
        firma.archiviert = True
        firma.save(update_fields=["archiviert"])
        messages.success(request, f"\"{firma.name}\" wurde archiviert.")
        return redirect("vertrieb:firma_list")
    return render(request, "vertrieb/confirm_archivieren.html", {
        "object": firma, "kann_archiviert_werden": firma.kann_archiviert_werden,
    })


@login_required
def firma_reaktivieren(request, pk):
    firma = get_object_or_404(Firma, pk=pk)
    if request.method == "POST":
        firma.archiviert = False
        firma.save(update_fields=["archiviert"])
        messages.success(request, f"\"{firma.name}\" wurde reaktiviert.")
    return redirect(firma.get_absolute_url())


# ---------------------------------------------------------------------------
# Kontakt
# ---------------------------------------------------------------------------

class KontaktListView(LoginRequiredMixin, ListView):
    model = Kontakt
    template_name = "vertrieb/kontakt_list.html"
    context_object_name = "kontakte"
    paginate_by = 25

    def get_queryset(self):
        qs = Kontakt.objects.all().select_related("firma")
        self.zeige_archiv = self.request.GET.get("archiv") == "1"
        qs = qs.filter(archiviert=self.zeige_archiv)
        suche = self.request.GET.get("q")
        if suche:
            qs = qs.filter(nachname__icontains=suche)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["zeige_archiv"] = self.zeige_archiv
        return context


class KontaktDetailView(LoginRequiredMixin, DetailView):
    model = Kontakt
    template_name = "vertrieb/kontakt_detail.html"
    context_object_name = "kontakt"


class KontaktCreateView(LoginRequiredMixin, CreateView):
    model = Kontakt
    form_class = KontaktForm
    template_name = "vertrieb/kontakt_form.html"

    def get_initial(self):
        initial = super().get_initial()
        firma_id = self.request.GET.get("firma")
        if firma_id:
            initial["firma"] = firma_id
        return initial


class KontaktUpdateView(LoginRequiredMixin, UpdateView):
    model = Kontakt
    form_class = KontaktForm
    template_name = "vertrieb/kontakt_form.html"


@login_required
def kontakt_archivieren(request, pk):
    """24.10.2026, auf Wunsch von Björn: ersetzt KontaktDeleteView, siehe firma_archivieren."""
    kontakt = get_object_or_404(Kontakt, pk=pk)
    if request.method == "POST":
        if not kontakt.kann_archiviert_werden:
            messages.warning(
                request,
                f"\"{kontakt}\" ist noch mit einem offenen Deal oder einer offenen Aktivität "
                f"verknüpft und kann deshalb nicht archiviert werden.",
            )
            return redirect(kontakt.get_absolute_url())
        kontakt.archiviert = True
        kontakt.save(update_fields=["archiviert"])
        messages.success(request, f"\"{kontakt}\" wurde archiviert.")
        return redirect("vertrieb:kontakt_list")
    return render(request, "vertrieb/confirm_archivieren.html", {
        "object": kontakt, "kann_archiviert_werden": kontakt.kann_archiviert_werden,
    })


@login_required
def kontakt_reaktivieren(request, pk):
    kontakt = get_object_or_404(Kontakt, pk=pk)
    if request.method == "POST":
        kontakt.archiviert = False
        kontakt.save(update_fields=["archiviert"])
        messages.success(request, f"\"{kontakt}\" wurde reaktiviert.")
    return redirect(kontakt.get_absolute_url())


# ---------------------------------------------------------------------------
# Deal
# ---------------------------------------------------------------------------

class DealListView(LoginRequiredMixin, ListView):
    model = Deal
    template_name = "vertrieb/deal_list.html"
    context_object_name = "deals"
    paginate_by = 25

    def get_queryset(self):
        return Deal.objects.all().select_related("firma", "zustaendiger")


class DealDetailView(LoginRequiredMixin, DetailView):
    model = Deal
    template_name = "vertrieb/deal_detail.html"
    context_object_name = "deal"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["musterversand"] = (
            self.object.packscheine.filter(ist_musterversand=True).order_by("-erstellt_am").first()
        )
        # Email-Verlauf dieses Deals (20.10.2026, auf Wunsch von Björn) - siehe
        # views.EmailVersandListView für die globale Übersicht aller Deals.
        context["email_versaende"] = self.object.email_versaende.all()[:20]
        return context


# Artikelnummern-Konvention aus der Artikelstamm-Schnittstelle (siehe Doku-Dokument
# "LUAMO Artikelstamm – Abgleich Excel ↔ CRM"). Die Beileger/Flyer sind bewusst je
# Sprache getrennte Artikel (physisch unterschiedliche Druckstücke), der Musterkarton
# selbst ist ein einziger, zweisprachig bedruckter Artikel - die Sprachauswahl hier
# entscheidet nur, welcher Beileger mitgepackt wird, nicht welcher Musterkarton.
# Artikelnummern selbst kommen aus models.MUSTERKARTON_ARTIKEL (gemeinsame Quelle mit
# nurture.py - siehe dort, warum sie nicht hier liegen können).
MUSTERKARTON_ARTIKELNUMMER = {k: v["artikelnummer"] for k, v in MUSTERKARTON_ARTIKEL.items()}
BEILEGER_ARTIKELNUMMER = {
    ("besteck", "de"): "LUA-EINL-BESTECK-DE",
    ("besteck", "en"): "LUA-EINL-BESTECK-EN",
    ("trinkhalm", "de"): "LUA-FLYER-STROH-DE",
    ("trinkhalm", "en"): "LUA-FLYER-STROH-EN",
}


@login_required
def musterkarton_anfordern(request, pk):
    """Schnellaktion auf der Deal-Detailseite: legt für einen Lead einen
    Musterkarton-Packschein an - mit der gewählten Art (Besteck/Trinkhalme/Beides) als
    Musterkarton-Position(en) UND, direkt darunter, dem/den dazu passenden Beileger(n)/
    Flyer(n) in der gewählten Sprache als eigene Position, damit er beim Packen nicht
    vergessen wird. Bei "Beides" entstehen vier Positionen (Musterkarton Besteck,
    Beileger Besteck, Musterkarton Trinkhalm, Beileger Trinkhalm) in einem einzigen
    Packschein/einer Sendung. Existiert einer der Artikel noch nicht im Artikelstamm
    (z. B. weil die Beileger-Artikel noch nicht importiert sind), wird die Position
    trotzdem mit einem Hinweistext angelegt statt den Packschein gar nicht erst zu
    erstellen. Der eigentliche Versand (Trackingnummer, Bestätigungsmail,
    Nachfass-Automatik) läuft weiterhin über 'Als versendet markieren' auf der
    Packschein-Detailseite.

    Wichtig (behoben 15.10.): Die beiden Auswahlfelder im Formular hatten früher keinen
    neutralen Startwert - das erste Dropdown-Element (Besteck) war automatisch
    vorausgewählt, sodass ein Klick auf den Button ohne bewusste Auswahl immer
    "Besteck" anlegte. Die Felder haben jetzt eine deaktivierte Platzhalter-Option
    ("... wählen"), sodass eine echte Auswahl Pflicht ist."""
    deal = get_object_or_404(Deal, pk=pk)
    if request.method != "POST":
        return redirect(deal.get_absolute_url())

    offener_musterversand = deal.packscheine.filter(ist_musterversand=True).exclude(status="versendet").first()
    if offener_musterversand:
        messages.info(
            request,
            f"Für diesen Deal läuft bereits ein Musterversand ({offener_musterversand.nummer}).",
        )
        return redirect(offener_musterversand.get_absolute_url())

    art = request.POST.get("art")
    sprache = request.POST.get("sprache")
    arten = ["besteck", "trinkhalm"] if art == "beide" else [art]
    if art not in ("besteck", "trinkhalm", "beide") or sprache not in ("de", "en"):
        messages.error(request, "Bitte Art (Besteck/Trinkhalme/Beides) und Sprache (Deutsch/Englisch) auswählen.")
        return redirect(deal.get_absolute_url())

    packschein = Packschein.objects.create(
        deal=deal, datum=timezone.now().date(), status="offen", ist_musterversand=True,
        sprache=sprache,
        notizen="Automatisch angelegt über 'Musterkarton anfordern'.",
    )
    position = 1
    fehlende_artikel = False
    for einzelart in arten:
        musterkarton_nr = MUSTERKARTON_ARTIKELNUMMER[einzelart]
        beileger_nr = BEILEGER_ARTIKELNUMMER[(einzelart, sprache)]
        musterkarton_artikel = Artikel.objects.filter(artikelnummer=musterkarton_nr).first()
        beileger_artikel = Artikel.objects.filter(artikelnummer=beileger_nr).first()

        if musterkarton_artikel:
            # Sprachabhaengig wie artikel_daten_json (20.10.2026 behoben, siehe
            # nurture.py Teil 6): der Musterkarton ist EIN einziger, zweisprachig
            # bedruckter Artikel (siehe MUSTERKARTON_ARTIKEL-Kommentar in models.py) -
            # anders als der Beileger unten (eigener Artikel PRO Sprache) muss die
            # Bezeichnung hier aus bezeichnung_en gezogen werden, sonst landet bei
            # einer englischen Musterbox trotzdem die deutsche Artikelbezeichnung auf
            # Packschein, Lieferschein und im Lieferschein-PDF.
            musterkarton_bezeichnung = (
                musterkarton_artikel.bezeichnung_en
                if sprache == "en" and musterkarton_artikel.bezeichnung_en
                else musterkarton_artikel.bezeichnung
            )
        else:
            musterkarton_bezeichnung = f"Musterkarton – ACHTUNG: Artikel {musterkarton_nr} fehlt im Artikelstamm"
        PackscheinPosition.objects.create(
            packschein=packschein, artikel=musterkarton_artikel, position=position,
            bezeichnung=musterkarton_bezeichnung,
            menge=1, einheit="stk",
            musterkarton_einzelart=einzelart,
        )
        position += 1
        PackscheinPosition.objects.create(
            packschein=packschein, artikel=beileger_artikel, position=position,
            bezeichnung=(beileger_artikel.bezeichnung if beileger_artikel
                         else f"Beileger/Flyer ({sprache}) – ACHTUNG: Artikel {beileger_nr} fehlt im "
                              f"Artikelstamm, bitte manuell beilegen und Position ergänzen"),
            menge=1, einheit="stk",
        )
        position += 1
        if not musterkarton_artikel or not beileger_artikel:
            fehlende_artikel = True

    if fehlende_artikel:
        messages.warning(
            request,
            "Nicht alle Artikel sind im Artikelstamm angelegt (siehe Hinweistext in den Positionen) – "
            "Packschein bitte vor dem Versand prüfen.",
        )
    art_text = {"besteck": "Besteck", "trinkhalm": "Trinkhalme", "beide": "Besteck und Trinkhalme"}[art]
    messages.success(
        request,
        f"Packschein {packschein.nummer} für Musterkarton-Versand ({art_text}) angelegt, inkl. passendem Beileger.",
    )
    return redirect(packschein.get_absolute_url())


@login_required
def musterbox_nachfass_abbrechen(request, pk):
    """Bricht die laufende 8-wöchige Musterbox-Nachfasskette eines Deals manuell ab (20.10.2026,
    auf Wunsch von Björn: "manuell eingreifen ... evtl. Vorgang löschen" - bewusst NICHT das
    Löschen des Packscheins/Lieferscheins selbst, sondern nur das Beenden der automatischen
    Werbe-Kette an den Kunden, siehe models.MusterboxNachfassStatus). Setzt denselben
    aktiv/beendet_am/beendet_grund-Mechanismus wie management/commands/nachfass_pruefen.py,
    nur mit einem neuen Grund ('manuell') statt 'angebot'/'abgelaufen'/'verloren'."""
    deal = get_object_or_404(Deal, pk=pk)
    status = getattr(deal, "musterbox_nachfass_status", None)
    if request.method == "POST":
        if status is not None and status.aktiv:
            status.aktiv = False
            status.beendet_am = timezone.now()
            status.beendet_grund = "manuell"
            status.save(update_fields=["aktiv", "beendet_am", "beendet_grund"])
            messages.success(request, "Musterbox-Nachfasskette wurde manuell abgebrochen.")
        else:
            messages.info(request, "Für diesen Deal läuft keine aktive Musterbox-Nachfasskette.")
    return redirect(deal.get_absolute_url())


class DealCreateView(LoginRequiredMixin, CreateView):
    model = Deal
    form_class = DealForm
    template_name = "vertrieb/deal_form.html"

    def get_initial(self):
        initial = super().get_initial()
        firma_id = self.request.GET.get("firma")
        if firma_id:
            initial["firma"] = firma_id
        return initial


class DealUpdateView(LoginRequiredMixin, UpdateView):
    model = Deal
    form_class = DealForm
    template_name = "vertrieb/deal_form.html"


class DealDeleteView(LoginRequiredMixin, DeleteView):
    """24.10.2026, auf Wunsch von Björn (im Zuge der Firma/Kontakt-Archivierung): bislang gab
    es hier gar keine Sperre, obwohl ueber einen Deal gehaengte Angebote, Packscheine,
    Lieferscheine, Rahmenvereinbarungen und sogar bezahlte Rechnungen per CASCADE mitgeloescht
    wuerden. Siehe Deal.ist_loeschbar - Loeschen bleibt nur erlaubt, solange noch kein
    einziges dieser Dokumente existiert."""

    model = Deal
    template_name = "vertrieb/confirm_delete.html"
    success_url = reverse_lazy("vertrieb:deal_list")

    def form_valid(self, form):
        deal = self.get_object()
        if not deal.ist_loeschbar:
            messages.warning(
                self.request,
                f"Deal \"{deal.titel}\" hat bereits Angebote, Packscheine, Lieferscheine, "
                f"Rahmenvereinbarungen oder Rechnungen und darf deshalb nicht mehr geloescht "
                f"werden.",
            )
            return redirect(deal.get_absolute_url())
        return super().form_valid(form)


# ---------------------------------------------------------------------------
# Aktivität
# ---------------------------------------------------------------------------

class AktivitaetListView(LoginRequiredMixin, ListView):
    model = Aktivitaet
    template_name = "vertrieb/aktivitaet_list.html"
    context_object_name = "aktivitaeten"
    paginate_by = 25

    def get_queryset(self):
        qs = Aktivitaet.objects.all().select_related("firma", "kontakt", "deal", "zustaendiger")
        if self.request.GET.get("offen") == "1":
            qs = qs.filter(erledigt=False)
        return qs


class AktivitaetDetailView(LoginRequiredMixin, DetailView):
    model = Aktivitaet
    template_name = "vertrieb/aktivitaet_detail.html"
    context_object_name = "aktivitaet"


class AktivitaetCreateView(LoginRequiredMixin, CreateView):
    model = Aktivitaet
    form_class = AktivitaetForm
    template_name = "vertrieb/aktivitaet_form.html"

    def get_initial(self):
        initial = super().get_initial()
        for feld in ("firma", "kontakt", "deal"):
            wert = self.request.GET.get(feld)
            if wert:
                initial[feld] = wert
        return initial


class AktivitaetUpdateView(LoginRequiredMixin, UpdateView):
    model = Aktivitaet
    form_class = AktivitaetForm
    template_name = "vertrieb/aktivitaet_form.html"


class AktivitaetDeleteView(LoginRequiredMixin, DeleteView):
    model = Aktivitaet
    template_name = "vertrieb/confirm_delete.html"
    success_url = reverse_lazy("vertrieb:aktivitaet_list")


@login_required
def aktivitaet_erledigt_umschalten(request, pk):
    aktivitaet = get_object_or_404(Aktivitaet, pk=pk)
    if request.method == "POST":
        aktivitaet.erledigt = not aktivitaet.erledigt
        aktivitaet.save()
    return redirect(request.META.get("HTTP_REFERER", reverse_lazy("vertrieb:aktivitaet_list")))


# ---------------------------------------------------------------------------
# Angebot
# ---------------------------------------------------------------------------

class AngebotListView(LoginRequiredMixin, ListView):
    model = Angebot
    template_name = "vertrieb/angebot_list.html"
    context_object_name = "angebote"
    paginate_by = 25

    def get_queryset(self):
        return Angebot.objects.all().select_related("deal", "deal__firma")


class AngebotDetailView(LoginRequiredMixin, DetailView):
    model = Angebot
    template_name = "vertrieb/angebot_detail.html"
    context_object_name = "angebot"


@login_required
def angebot_erstellen(request):
    rahmenvereinbarung_quelle = None
    rahmenvereinbarung_id = request.GET.get("rahmenvereinbarung")
    if rahmenvereinbarung_id:
        rahmenvereinbarung_quelle = get_object_or_404(Rahmenvereinbarung, pk=rahmenvereinbarung_id)

    if request.method == "POST":
        form = AngebotForm(request.POST)
        if form.is_valid():
            angebot = form.save()
            formset = AngebotPositionFormSet(request.POST, instance=angebot)
            if formset.is_valid():
                formset.save()
                return redirect(angebot.get_absolute_url())
        else:
            formset = AngebotPositionFormSet(request.POST)
    else:
        heute = timezone.now().date()
        # Datum/Gültig-bis vorschlagen (15.10.2026, Björns Wunsch: nicht manuell
        # auswählen müssen) - Angebotsdatum = heute, Gültigkeit standardmäßig 4
        # Wochen. Reiner Vorschlag, beide Felder bleiben frei überschreibbar.
        initial = {"datum": heute, "gueltig_bis": heute + timedelta(weeks=4)}
        quelle_positionen = None
        if rahmenvereinbarung_quelle:
            # 22.10.2026, Björns Rückfrage: das Angebot ist das Dokument, das dem
            # Kunden tatsächlich zugestellt wird - hier daher bewusst MIT der vollen
            # Jahresmenge und dem eingefrorenen Preis vorbefüllt (anders als beim
            # Lieferschein-Abruf aus einer Rahmenvereinbarung, wo die Menge absichtlich
            # NICHT vorbefüllt wird, siehe lieferschein_erstellen).
            initial.update({
                "deal": rahmenvereinbarung_quelle.deal_id,
                "rahmenvereinbarung": rahmenvereinbarung_quelle.pk,
                "sprache": rahmenvereinbarung_quelle.sprache,
            })
            quelle_positionen = rahmenvereinbarung_quelle.positionen.all()
        else:
            deal_id = request.GET.get("deal")
            if deal_id:
                initial["deal"] = deal_id
        form = AngebotForm(initial=initial)

        if quelle_positionen is not None and quelle_positionen.exists():
            positionen_initial = [
                {
                    "artikel": p.artikel_id, "position": p.position, "bezeichnung": p.bezeichnung,
                    "menge": p.jahresmenge, "einheit": p.einheit, "einzelpreis": p.einzelpreis,
                }
                for p in quelle_positionen
            ]
            FormSetVorbefuellt = inlineformset_factory(
                Angebot, Angebot.positionen.rel.related_model,
                form=AngebotPositionFormSet.form, extra=len(positionen_initial), can_delete=True,
            )
            formset = FormSetVorbefuellt(initial=positionen_initial)
        else:
            formset = AngebotPositionFormSet()
    return render(request, "vertrieb/angebot_form.html", {
        "form": form, "formset": formset, "rahmenvereinbarung_quelle": rahmenvereinbarung_quelle,
    })


@login_required
def angebot_bearbeiten(request, pk):
    angebot = get_object_or_404(Angebot, pk=pk)
    if request.method == "POST":
        form = AngebotForm(request.POST, instance=angebot)
        formset = AngebotPositionFormSet(request.POST, instance=angebot)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            return redirect(angebot.get_absolute_url())
    else:
        form = AngebotForm(instance=angebot)
        formset = AngebotPositionFormSet(instance=angebot)
    return render(request, "vertrieb/angebot_form.html", {"form": form, "formset": formset, "angebot": angebot})


class AngebotDeleteView(LoginRequiredMixin, DeleteView):
    """24.10.2026, auf Wunsch von Björn (Nachzieher zum RechnungDeleteView-Fix vom selben
    Tag): dieselbe Luecke bestand unveraendert auch hier - ein Angebot liess sich loeschen,
    egal ob "entwurf" oder bereits "versendet"/"angenommen"/"abgelehnt". Fix nur fuers
    LOESCHEN (siehe Angebot.ist_loeschbar) - das Bearbeiten bleibt bewusst weiterhin in jedem
    Status moeglich, siehe Model-Doku."""

    model = Angebot
    template_name = "vertrieb/confirm_delete.html"
    success_url = reverse_lazy("vertrieb:angebot_list")

    def form_valid(self, form):
        angebot = self.get_object()
        if not angebot.ist_loeschbar:
            messages.warning(
                self.request,
                f"Angebot {angebot.nummer} wurde bereits versendet und sollte nicht mehr "
                f"geloescht werden (Status \"{angebot.get_status_display()}\").",
            )
            return redirect(angebot.get_absolute_url())
        return super().form_valid(form)


@login_required
def angebot_pdf_download(request, pk):
    angebot = get_object_or_404(Angebot, pk=pk)
    pdf_bytes = pdf.angebot_pdf_erzeugen(angebot)
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{angebot.nummer}.pdf"'
    return response


@login_required
def angebot_versand_senden_view(request, pk):
    """Verschickt ein Angebot manuell per Mail inkl. Anschreiben und PDF-Anhang an den
    Kunden (24.10.2026, auf Wunsch von Björn, siehe nurture.angebot_versand_senden) - der
    "Jetzt versenden"-Button auf der Angebots-Detailseite, analog zu
    rechnung_versand_senden_view. Setzt bei Erfolg status='versendet', was automatisch die
    bestehende Angebot-Nachfasskette startet (siehe signals.angebot_status_wechsel)."""
    angebot = get_object_or_404(Angebot, pk=pk)
    if request.method == "POST":
        if angebot.status != "entwurf":
            messages.info(request, f"Angebot {angebot.nummer} wurde bereits versendet.")
        else:
            erfolg, fehler = nurture.angebot_versand_senden(angebot)
            if erfolg:
                messages.success(request, f"Angebot {angebot.nummer} wurde per Mail an den Kunden versendet.")
            else:
                messages.warning(
                    request,
                    f"Angebot {angebot.nummer} konnte NICHT per Mail versendet werden ({fehler}).",
                )
    return redirect(angebot.get_absolute_url())


@login_required
def angebot_ablehnen(request, pk):
    """Erfasst eine Kundenablehnung zu einem versendeten Angebot, inkl. Pflichtgrund
    (24.10.2026, auf Wunsch von Björn: "aus Kundensicht" identifizierte Luecke - bisher gab
    es keinen Weg, der erfasst HAT, warum ein Angebot abgelehnt wurde, siehe Model-Doku bei
    Angebot.ablehnungsgrund). Nur aus status='versendet' moeglich - ein Entwurf wurde nie
    beim Kunden, ein bereits angenommenes/abgelaufenes/abgelehntes Angebot korrigiert man
    stattdessen ueber "Bearbeiten". Das eigentliche Beenden der Nachfasskette passiert wie
    gehabt ereignisbasiert ueber signals.angebot_status_wechsel (Status wechselt weg von
    "versendet")."""
    angebot = get_object_or_404(Angebot, pk=pk)
    if angebot.status != "versendet":
        messages.warning(
            request,
            f"Angebot {angebot.nummer} kann nicht abgelehnt werden (Status ist "
            f"\"{angebot.get_status_display()}\", nicht \"Versendet\"). Korrekturen bitte über "
            f"\"Bearbeiten\" vornehmen.",
        )
        return redirect(angebot.get_absolute_url())

    if request.method == "POST":
        form = AngebotAblehnenForm(request.POST, instance=angebot)
        if form.is_valid():
            angebot.status = "abgelehnt"
            form.save()
            messages.success(request, f"Angebot {angebot.nummer} wurde als abgelehnt erfasst.")
            return redirect(angebot.get_absolute_url())
    else:
        form = AngebotAblehnenForm(instance=angebot)
    return render(request, "vertrieb/angebot_ablehnen_form.html", {"form": form, "angebot": angebot})


# ---------------------------------------------------------------------------
# Rahmenvereinbarung (Jahresmengen-Vertrag für Großkunden, 21.10.2026 - siehe
# Model-Doku: friert pro Artikel einen Preis für die ganze Jahresmenge ein,
# unabhängig von der Größe der einzelnen Teillieferung/Charge; Bonusstaffel
# honoriert sehr hohe Gesamtabnahme über eine Rückvergütung statt über einen
# weiter abgesenkten Stückpreis)
# ---------------------------------------------------------------------------

class RahmenvereinbarungListView(LoginRequiredMixin, ListView):
    model = Rahmenvereinbarung
    template_name = "vertrieb/rahmenvereinbarung_list.html"
    context_object_name = "rahmenvereinbarungen"
    paginate_by = 25

    def get_queryset(self):
        return Rahmenvereinbarung.objects.all().select_related("deal", "deal__firma")


class RahmenvereinbarungDetailView(LoginRequiredMixin, DetailView):
    model = Rahmenvereinbarung
    template_name = "vertrieb/rahmenvereinbarung_detail.html"
    context_object_name = "rahmenvereinbarung"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["positionen"] = self.object.positionen.all().select_related("artikel")
        context["bonusstaffeln"] = self.object.bonusstaffeln.all()
        context["angebote"] = self.object.angebote.all()
        return context


@login_required
def rahmenvereinbarung_erstellen(request):
    if request.method == "POST":
        form = RahmenvereinbarungForm(request.POST)
        if form.is_valid():
            rahmenvereinbarung = form.save()
            formset = RahmenvereinbarungPositionFormSet(request.POST, instance=rahmenvereinbarung)
            bonus_formset = BonusstaffelFormSet(request.POST, instance=rahmenvereinbarung)
            if formset.is_valid() and bonus_formset.is_valid():
                formset.save()
                bonus_formset.save()
                return redirect(rahmenvereinbarung.get_absolute_url())
        else:
            formset = RahmenvereinbarungPositionFormSet(request.POST)
            bonus_formset = BonusstaffelFormSet(request.POST)
    else:
        initial = {}
        deal_id = request.GET.get("deal")
        if deal_id:
            initial["deal"] = deal_id
        form = RahmenvereinbarungForm(initial=initial)
        formset = RahmenvereinbarungPositionFormSet()
        bonus_formset = BonusstaffelFormSet()
    return render(request, "vertrieb/rahmenvereinbarung_form.html", {
        "form": form, "formset": formset, "bonus_formset": bonus_formset,
    })


@login_required
def rahmenvereinbarung_bearbeiten(request, pk):
    rahmenvereinbarung = get_object_or_404(Rahmenvereinbarung, pk=pk)
    if request.method == "POST":
        form = RahmenvereinbarungForm(request.POST, instance=rahmenvereinbarung)
        formset = RahmenvereinbarungPositionFormSet(request.POST, instance=rahmenvereinbarung)
        bonus_formset = BonusstaffelFormSet(request.POST, instance=rahmenvereinbarung)
        if form.is_valid() and formset.is_valid() and bonus_formset.is_valid():
            form.save()
            formset.save()
            bonus_formset.save()
            return redirect(rahmenvereinbarung.get_absolute_url())
    else:
        form = RahmenvereinbarungForm(instance=rahmenvereinbarung)
        formset = RahmenvereinbarungPositionFormSet(instance=rahmenvereinbarung)
        bonus_formset = BonusstaffelFormSet(instance=rahmenvereinbarung)
    return render(request, "vertrieb/rahmenvereinbarung_form.html", {
        "form": form, "formset": formset, "bonus_formset": bonus_formset,
        "rahmenvereinbarung": rahmenvereinbarung,
    })


class RahmenvereinbarungDeleteView(LoginRequiredMixin, DeleteView):
    model = Rahmenvereinbarung
    template_name = "vertrieb/confirm_delete.html"
    success_url = reverse_lazy("vertrieb:rahmenvereinbarung_list")


def rahmenvereinbarung_pdf_download(request, pk):
    """22.10.2026, Björns Anfrage nach einem "ordentlichen Vertragswerk mit Paragraphen":
    liefert das Rahmenvertrags-PDF (pdf.rahmenvertrag_pdf_erzeugen) - siehe dort und in
    vertragstexte.py den Hinweis, dass die Klauseln ein ungeprüfter Entwurf sind."""
    rahmenvereinbarung = get_object_or_404(Rahmenvereinbarung, pk=pk)
    pdf_bytes = pdf.rahmenvertrag_pdf_erzeugen(rahmenvereinbarung)
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{rahmenvereinbarung.nummer}.pdf"'
    return response


# ---------------------------------------------------------------------------
# Packschein (internes Kommissionier-/Packdokument fürs Lager)
# ---------------------------------------------------------------------------

class PackscheinListView(LoginRequiredMixin, ListView):
    model = Packschein
    template_name = "vertrieb/packschein_list.html"
    context_object_name = "packscheine"
    paginate_by = 25

    def get_queryset(self):
        return Packschein.objects.all().select_related("deal", "deal__firma")


class PackscheinDetailView(LoginRequiredMixin, DetailView):
    model = Packschein
    template_name = "vertrieb/packschein_detail.html"
    context_object_name = "packschein"


@login_required
def packschein_erstellen(request):
    angebot_quelle = None
    angebot_id = request.GET.get("angebot")
    if angebot_id:
        angebot_quelle = get_object_or_404(Angebot, pk=angebot_id)

    if request.method == "POST":
        form = PackscheinForm(request.POST)
        if form.is_valid():
            # Auftrags-Pflicht vor Packschein-Erstellung (24.10.2026, auf Wunsch von Björn:
            # "wenn wir ein Angebot anlegen, wenn es denn zum Auftrag kommt, wir dann einen
            # Packschein anlegen ... Schritt für Schritt" - vorher liess sich ein Packschein zu
            # JEDEM Angebot anlegen, auch zu einem noch nicht einmal versendeten Entwurf).
            # Musterversand-Packscheine (ist_musterversand) sind bewusst ausgenommen - das sind
            # Vorab-Musterlieferungen an Leads OHNE Angebot (siehe views.musterkarton_anfordern,
            # ein komplett eigener View, der diese Form hier gar nicht durchläuft - die Ausnahme
            # greift trotzdem defensiv, falls doch einmal über dieses Formular angelegt).
            # Bewusst nur hier bei der NEU-Erstellung geprueft (wie beim Rechnung-Pendant unten),
            # nicht in PackscheinForm.clean() oder bei packschein_bearbeiten - damit bereits
            # bestehende (vor dieser Regel angelegte) Packscheine beim Bearbeiten nicht
            # nachtraeglich blockiert werden.
            gewaehltes_angebot = form.cleaned_data.get("angebot")
            ist_musterversand = form.cleaned_data.get("ist_musterversand")
            if gewaehltes_angebot and not ist_musterversand and gewaehltes_angebot.status == "entwurf":
                form.add_error(
                    "angebot",
                    f"Angebot {gewaehltes_angebot.nummer} wurde noch nicht an den Kunden "
                    f"versendet (Status \"Entwurf\"). Ein Packschein kann erst erstellt werden, "
                    f"wenn das Angebot tatsächlich beim Kunden ist und zum Auftrag geworden ist.",
                )
                formset = PackscheinPositionFormSet(request.POST)
            else:
                packschein = form.save()
                formset = PackscheinPositionFormSet(request.POST, instance=packschein)
                if formset.is_valid():
                    formset.save()
                    # 24.10.2026, auf Wunsch von Björn: ein Packschein zu einem Angebot bedeutet,
                    # der Kunde hat das Angebot angenommen - die Nachfasskette soll dann stoppen
                    # (siehe nurture.angebot_als_angenommen_markieren).
                    if packschein.angebot_id:
                        nurture.angebot_als_angenommen_markieren(packschein.angebot)
                    return redirect(packschein.get_absolute_url())
                return render(request, "vertrieb/packschein_form.html", {
                    "form": form, "formset": formset, "angebot_quelle": angebot_quelle,
                })
        else:
            formset = PackscheinPositionFormSet(request.POST)
    else:
        initial = {}
        deal_id = request.GET.get("deal")
        if angebot_quelle:
            initial = {"deal": angebot_quelle.deal_id, "angebot": angebot_quelle.pk}
        elif deal_id:
            initial = {"deal": deal_id}
        form = PackscheinForm(initial=initial)

        if angebot_quelle and angebot_quelle.positionen.exists():
            positionen_initial = [
                {
                    "artikel": p.artikel_id, "position": p.position, "bezeichnung": p.bezeichnung,
                    "menge": p.menge, "einheit": p.einheit,
                }
                for p in angebot_quelle.positionen.all()
            ]
            FormSetVorbefuellt = inlineformset_factory(
                Packschein, Packschein.positionen.rel.related_model,
                form=PackscheinPositionFormSet.form, extra=len(positionen_initial), can_delete=True,
            )
            formset = FormSetVorbefuellt(initial=positionen_initial)
        else:
            formset = PackscheinPositionFormSet()
    return render(request, "vertrieb/packschein_form.html", {
        "form": form, "formset": formset, "angebot_quelle": angebot_quelle,
    })


@login_required
def packschein_bearbeiten(request, pk):
    packschein = get_object_or_404(Packschein, pk=pk)
    if request.method == "POST":
        form = PackscheinForm(request.POST, instance=packschein)
        formset = PackscheinPositionFormSet(request.POST, instance=packschein)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            return redirect(packschein.get_absolute_url())
    else:
        form = PackscheinForm(instance=packschein)
        formset = PackscheinPositionFormSet(instance=packschein)
    return render(request, "vertrieb/packschein_form.html", {
        "form": form, "formset": formset, "packschein": packschein,
    })


@login_required
def packschein_versand_bestaetigen(request, pk):
    """Trackingnummer eintragen und Packschein auf 'versendet' setzen. Bei einem
    Musterversand löst das zusätzlich die Bestätigungsmail an den Lead und die erste
    wöchentliche Nachfass-Aktivität aus (siehe vertrieb/nurture.py)."""
    packschein = get_object_or_404(Packschein, pk=pk)
    if request.method == "POST":
        form = PackscheinVersandForm(request.POST, instance=packschein)
        if form.is_valid():
            packschein = form.save(commit=False)
            packschein.status = "versendet"
            if not packschein.versendet_am:
                packschein.versendet_am = timezone.now().date()
            packschein.save()
            if packschein.ist_musterversand:
                nurture.musterversand_abgeschlossen(packschein)
            messages.success(request, f"Packschein {packschein.nummer} als versendet markiert.")
            return redirect(packschein.get_absolute_url())
    else:
        form = PackscheinVersandForm(instance=packschein, initial={"versendet_am": timezone.now().date()})
    return render(request, "vertrieb/packschein_versand_form.html", {"form": form, "packschein": packschein})


class PackscheinDeleteView(LoginRequiredMixin, DeleteView):
    """24.10.2026, auf Wunsch von Björn (Nachzieher zum RechnungDeleteView-Fix): siehe
    Packschein.ist_loeschbar - ein bereits versendeter Packschein (Ware raus, ggf. Grundlage
    eines Lieferscheins) soll nicht mehr loeschbar sein."""

    model = Packschein
    template_name = "vertrieb/confirm_delete.html"
    success_url = reverse_lazy("vertrieb:packschein_list")

    def form_valid(self, form):
        packschein = self.get_object()
        if not packschein.ist_loeschbar:
            messages.warning(
                self.request,
                f"Packschein {packschein.nummer} wurde bereits versendet und sollte nicht "
                f"mehr geloescht werden.",
            )
            return redirect(packschein.get_absolute_url())
        return super().form_valid(form)


@login_required
def packschein_pdf_download(request, pk):
    packschein = get_object_or_404(Packschein, pk=pk)
    pdf_bytes = pdf.packschein_pdf_erzeugen(packschein)
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{packschein.nummer}.pdf"'
    return response


# ---------------------------------------------------------------------------
# Lieferschein
# ---------------------------------------------------------------------------

class LieferscheinListView(LoginRequiredMixin, ListView):
    model = Lieferschein
    template_name = "vertrieb/lieferschein_list.html"
    context_object_name = "lieferscheine"
    paginate_by = 25

    def get_queryset(self):
        return Lieferschein.objects.all().select_related("deal", "deal__firma")


class LieferscheinDetailView(LoginRequiredMixin, DetailView):
    model = Lieferschein
    template_name = "vertrieb/lieferschein_detail.html"
    context_object_name = "lieferschein"


@login_required
def lieferschein_erstellen(request):
    angebot_quelle = None
    angebot_id = request.GET.get("angebot")
    if angebot_id:
        angebot_quelle = get_object_or_404(Angebot, pk=angebot_id)

    packschein_quelle = None
    packschein_id = request.GET.get("packschein")
    if packschein_id:
        packschein_quelle = get_object_or_404(Packschein, pk=packschein_id)

    rahmenvereinbarung_quelle = None
    rahmenvereinbarung_id = request.GET.get("rahmenvereinbarung")
    if rahmenvereinbarung_id:
        rahmenvereinbarung_quelle = get_object_or_404(Rahmenvereinbarung, pk=rahmenvereinbarung_id)

    if request.method == "POST":
        form = LieferscheinForm(request.POST)
        if form.is_valid():
            # Versand-Pflicht vor Lieferschein-Erstellung (24.10.2026, auf Wunsch von Björn:
            # "Schritt für Schritt" - Packschein vor Lieferschein, nicht parallel/alles auf
            # einmal; vorher liess sich ein Lieferschein zu JEDEM Angebot/Deal anlegen, auch
            # ganz ohne Packschein). Ausnahme: ein Abruf aus einer laufenden Rahmenvereinbarung
            # (Grosskunden-Jahresmengenvertrag, 21.10.2026) kommt bewusst OHNE eigenen
            # Packschein je Teillieferung aus (siehe Formular-Kommentar dort). Bewusst nur hier
            # bei der NEU-Erstellung geprueft (wie beim Rechnung-Pendant unten), nicht in
            # LieferscheinForm.clean() oder bei lieferschein_bearbeiten.
            gewaehlter_packschein = form.cleaned_data.get("packschein")
            gewaehlte_rahmenvereinbarung = form.cleaned_data.get("rahmenvereinbarung")
            fehler = False
            if not gewaehlte_rahmenvereinbarung:
                if not gewaehlter_packschein:
                    form.add_error(
                        "packschein",
                        "Pflichtfeld: Ein Lieferschein kann erst zu einem bereits versendeten "
                        "Packschein erzeugt werden - außer als Abruf aus einer "
                        "Rahmenvereinbarung.",
                    )
                    fehler = True
                elif gewaehlter_packschein.ist_musterversand:
                    form.add_error(
                        "packschein",
                        f"Packschein {gewaehlter_packschein.nummer} ist ein Musterversand an "
                        f"einen Lead und kann nicht zu einem Lieferschein werden.",
                    )
                    fehler = True
                elif gewaehlter_packschein.status != "versendet":
                    form.add_error(
                        "packschein",
                        f"Packschein {gewaehlter_packschein.nummer} wurde noch nicht als "
                        f"versendet markiert. Bitte zuerst dort auf der Detailseite \"Als "
                        f"versendet markieren\" ausfüllen, dann kann der Lieferschein erzeugt "
                        f"werden.",
                    )
                    fehler = True
            if fehler:
                formset = LieferscheinPositionFormSet(request.POST)
            else:
                lieferschein = form.save()
                formset = LieferscheinPositionFormSet(request.POST, instance=lieferschein)
                if formset.is_valid():
                    formset.save()
                    # 24.10.2026, auf Wunsch von Björn: wie beim Packschein (siehe dort) -
                    # Nachfasskette stoppen, sobald zu diesem Angebot ein Lieferschein angelegt
                    # wird.
                    if lieferschein.angebot_id:
                        nurture.angebot_als_angenommen_markieren(lieferschein.angebot)
                    return redirect(lieferschein.get_absolute_url())
                return render(request, "vertrieb/lieferschein_form.html", {
                    "form": form, "formset": formset,
                    "angebot_quelle": angebot_quelle, "packschein_quelle": packschein_quelle,
                    "rahmenvereinbarung_quelle": rahmenvereinbarung_quelle,
                })
        else:
            formset = LieferscheinPositionFormSet(request.POST)
    else:
        initial = {}
        deal_id = request.GET.get("deal")
        quelle_positionen = None
        if packschein_quelle:
            initial = {
                "deal": packschein_quelle.deal_id,
                "angebot": packschein_quelle.angebot_id,
                "packschein": packschein_quelle.pk,
                # Sprache wird vom Packschein übernommen (nicht vom Angebot dahinter, falls
                # eins existiert) - beim Musterkarton-Versand ist packschein.sprache die
                # verlässlichere Quelle, siehe views.musterkarton_anfordern.
                "sprache": packschein_quelle.sprache,
            }
            quelle_positionen = packschein_quelle.positionen.all()
        elif angebot_quelle:
            initial = {
                "deal": angebot_quelle.deal_id, "angebot": angebot_quelle.pk,
                "sprache": angebot_quelle.sprache,
            }
            quelle_positionen = angebot_quelle.positionen.all()
        elif rahmenvereinbarung_quelle:
            # 21.10.2026, Björns Großkunden-Jahresmengenanfrage: ein Lieferschein als
            # Abruf aus einer Rahmenvereinbarung. Artikel/Bezeichnung/Einheit werden aus
            # der vereinbarten Position übernommen, die Menge bewusst NICHT mit der
            # Jahresmenge vorbefüllt - die tatsächliche Teillieferungsmenge dieser
            # konkreten Charge ist etwas anderes und muss vom Nutzer eingetragen werden
            # (siehe Formular-Hinweis im Template).
            initial = {
                "deal": rahmenvereinbarung_quelle.deal_id,
                "rahmenvereinbarung": rahmenvereinbarung_quelle.pk,
            }
            quelle_positionen = rahmenvereinbarung_quelle.positionen.all()
        elif deal_id:
            initial = {"deal": deal_id}
        form = LieferscheinForm(initial=initial)

        if rahmenvereinbarung_quelle and quelle_positionen is not None and quelle_positionen.exists():
            positionen_initial = [
                {
                    "artikel": p.artikel_id, "position": p.position, "bezeichnung": p.bezeichnung,
                    "einheit": p.einheit,
                }
                for p in quelle_positionen
            ]
            FormSetVorbefuellt = inlineformset_factory(
                Lieferschein, Lieferschein.positionen.rel.related_model,
                form=LieferscheinPositionFormSet.form, extra=len(positionen_initial), can_delete=True,
            )
            formset = FormSetVorbefuellt(initial=positionen_initial)
        elif quelle_positionen is not None and quelle_positionen.exists():
            positionen_initial = [
                {
                    "artikel": p.artikel_id, "position": p.position, "bezeichnung": p.bezeichnung,
                    "menge": p.menge, "einheit": p.einheit,
                }
                for p in quelle_positionen
            ]
            FormSetVorbefuellt = inlineformset_factory(
                Lieferschein, Lieferschein.positionen.rel.related_model,
                form=LieferscheinPositionFormSet.form, extra=len(positionen_initial), can_delete=True,
            )
            formset = FormSetVorbefuellt(initial=positionen_initial)
        else:
            formset = LieferscheinPositionFormSet()
    return render(request, "vertrieb/lieferschein_form.html", {
        "form": form, "formset": formset,
        "angebot_quelle": angebot_quelle, "packschein_quelle": packschein_quelle,
        "rahmenvereinbarung_quelle": rahmenvereinbarung_quelle,
    })


@login_required
def lieferschein_bearbeiten(request, pk):
    lieferschein = get_object_or_404(Lieferschein, pk=pk)
    if request.method == "POST":
        form = LieferscheinForm(request.POST, instance=lieferschein)
        formset = LieferscheinPositionFormSet(request.POST, instance=lieferschein)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            return redirect(lieferschein.get_absolute_url())
    else:
        form = LieferscheinForm(instance=lieferschein)
        formset = LieferscheinPositionFormSet(instance=lieferschein)
    return render(request, "vertrieb/lieferschein_form.html", {
        "form": form, "formset": formset, "lieferschein": lieferschein,
    })


@login_required
def lieferschein_versand_bestaetigen(request, pk):
    """Trackingnummer eintragen und Lieferschein auf 'versendet' setzen (17.10.2026,
    auf Wunsch von Björn - analog zu packschein_versand_bestaetigen). Löst die
    Versand-Bestätigungsmail an den Kunden aus (siehe nurture.lieferschein_versand_abgeschlossen),
    das Ende der Nachfass-Kette des Deals (siehe management/commands/nachfass_pruefen.py) sowie
    seit 20.10.2026 (auf Wunsch von Björn, siehe nurture.py Teil 7) die automatische
    Rechnungserstellung zu diesem Lieferschein - fuer Muster UND echte Bestellungen
    gleichermassen. Hat jede Position einen ermittelbaren Preis, wird die Rechnung direkt
    mitverschickt; fehlt bei mindestens einer Position der Preis, bleibt die Rechnung als
    Entwurf liegen und muss nach manueller Preis-Korrektur ueber den "Jetzt versenden"-Button
    auf der Rechnungs-Detailseite verschickt werden (siehe rechnung_versand_senden_view).

    AENDERUNG 20.10.2026 (auf Wunsch von Björn: "wenn wir die trackingnummer beim packschein
    eingeben, braucht diese nicht nochmal beim lieferschein eingegeben werden"): Hat der
    verknuepfte Packschein bereits eine Trackingnummer (z. B. weil derselbe Versand bereits
    dort als versendet erfasst wurde) und der Lieferschein selbst noch keine eigene, wird das
    Formular damit vorbefuellt - bleibt aber ein normales, ueberschreibbares Feld fuer den
    Sonderfall, dass Packschein und Lieferschein tatsaechlich unterschiedlich versendet
    wurden (z. B. Teillieferung, oder ein Lieferschein ohne Packschein-Bezug)."""
    lieferschein = get_object_or_404(Lieferschein, pk=pk)
    if request.method == "POST":
        form = LieferscheinVersandForm(request.POST, instance=lieferschein)
        if form.is_valid():
            lieferschein = form.save(commit=False)
            lieferschein.status = "versendet"
            if not lieferschein.versendet_am:
                lieferschein.versendet_am = timezone.now().date()
            lieferschein.versand_erfasst_von = request.user
            lieferschein.save()
            erfolg, fehler = nurture.lieferschein_versand_abgeschlossen(lieferschein)
            if erfolg:
                messages.success(
                    request,
                    f"Lieferschein {lieferschein.nummer} als versendet markiert. "
                    f"Versand-Bestätigungsmail wurde an den Kunden gesendet.",
                )
            else:
                messages.warning(
                    request,
                    f"Lieferschein {lieferschein.nummer} als versendet markiert, aber die "
                    f"Versand-Bestätigungsmail an den Kunden konnte NICHT gesendet werden "
                    f"({fehler}). Rechnung kann trotzdem erstellt werden - bitte Kunden ggf. "
                    f"manuell informieren.",
                )

            rechnung, ungepreiste_positionen = nurture.rechnung_automatisch_erstellen(lieferschein)
            if ungepreiste_positionen:
                messages.warning(
                    request,
                    f"Rechnung {rechnung.nummer} wurde als Entwurf angelegt, aber NICHT automatisch "
                    f"versendet: für folgende Positionen fehlt ein Preis (kein verknüpfter Artikel "
                    f"oder Artikel ohne Verkaufspreis) - {'; '.join(ungepreiste_positionen)}. Bitte "
                    f"auf der Rechnung Preise nachtragen und dann über \"Jetzt versenden\" verschicken.",
                )
            elif rechnung.status == "entwurf":
                erfolg_re, fehler_re = nurture.rechnung_versand_senden(rechnung)
                if erfolg_re:
                    messages.success(
                        request,
                        f"Rechnung {rechnung.nummer} wurde automatisch erstellt und per Mail an den "
                        f"Kunden versendet.",
                    )
                else:
                    messages.warning(
                        request,
                        f"Rechnung {rechnung.nummer} wurde automatisch erstellt, konnte aber NICHT "
                        f"per Mail versendet werden ({fehler_re}). Bitte über \"Jetzt versenden\" auf "
                        f"der Rechnungs-Detailseite erneut versuchen.",
                    )
            return redirect(lieferschein.get_absolute_url())
    else:
        initial = {"versendet_am": timezone.now().date()}
        if lieferschein.packschein_id and not lieferschein.trackingnummer and lieferschein.packschein.trackingnummer:
            initial["versanddienstleister"] = lieferschein.packschein.versanddienstleister
            initial["trackingnummer"] = lieferschein.packschein.trackingnummer
        form = LieferscheinVersandForm(instance=lieferschein, initial=initial)
    return render(request, "vertrieb/lieferschein_versand_form.html", {"form": form, "lieferschein": lieferschein})


class LieferscheinDeleteView(LoginRequiredMixin, DeleteView):
    """24.10.2026, auf Wunsch von Björn (Nachzieher zum RechnungDeleteView-Fix): siehe
    Lieferschein.ist_loeschbar - ein bereits versendeter Lieferschein (Liefernachweis, ggf.
    bereits Grundlage einer Rechnung) soll nicht mehr loeschbar sein."""

    model = Lieferschein
    template_name = "vertrieb/confirm_delete.html"
    success_url = reverse_lazy("vertrieb:lieferschein_list")

    def form_valid(self, form):
        lieferschein = self.get_object()
        if not lieferschein.ist_loeschbar:
            messages.warning(
                self.request,
                f"Lieferschein {lieferschein.nummer} wurde bereits versendet und sollte "
                f"nicht mehr geloescht werden.",
            )
            return redirect(lieferschein.get_absolute_url())
        return super().form_valid(form)


@login_required
def lieferschein_pdf_download(request, pk):
    lieferschein = get_object_or_404(Lieferschein, pk=pk)
    pdf_bytes = pdf.lieferschein_pdf_erzeugen(lieferschein)
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{lieferschein.nummer}.pdf"'
    return response


# ---------------------------------------------------------------------------
# Rechnung
# ---------------------------------------------------------------------------

class RechnungListView(LoginRequiredMixin, ListView):
    model = Rechnung
    template_name = "vertrieb/rechnung_list.html"
    context_object_name = "rechnungen"
    paginate_by = 25

    def get_queryset(self):
        # prefetch_related("positionen", "zahlungen"): r.ist_ueberfaellig (Template)
        # braucht beides je Zeile (siehe Rechnung.bruttosumme/offener_betrag) - ohne das
        # waere das ein N+1 pro Rechnung in der Liste.
        return (
            Rechnung.objects.all()
            .select_related("deal", "deal__firma")
            .prefetch_related("positionen", "zahlungen")
        )


class RechnungDetailView(LoginRequiredMixin, DetailView):
    model = Rechnung
    template_name = "vertrieb/rechnung_detail.html"
    context_object_name = "rechnung"

    def get_context_data(self, **kwargs):
        # 20.10.2026, auf Wunsch von Björn: "ich habe aber gar keine Möglichkeit den
        # Preis zu hinterlegen" - die Moeglichkeit (ueber "Bearbeiten") gab es technisch
        # zwar schon, war aber nur als einmalige Flash-Message beim Lieferschein-Versand
        # sichtbar und verschwand danach spurlos von der Rechnung selbst. Jetzt ein
        # dauerhafter, bei jedem Aufruf neu berechneter Hinweis direkt auf der
        # Rechnungs-Detailseite, solange mindestens eine Position noch keinen Preis hat.
        context = super().get_context_data(**kwargs)
        context["ungepreiste_positionen"] = self.object.positionen.filter(einzelpreis=0)
        return context


@login_required
def rechnung_erstellen(request):
    angebot_quelle = None
    lieferschein_quelle = None
    if request.method == "GET":
        angebot_id = request.GET.get("angebot")
        lieferschein_id = request.GET.get("lieferschein")
        if lieferschein_id:
            lieferschein_quelle = get_object_or_404(Lieferschein, pk=lieferschein_id)
            angebot_quelle = lieferschein_quelle.angebot
        elif angebot_id:
            angebot_quelle = get_object_or_404(Angebot, pk=angebot_id)

    if request.method == "POST":
        form = RechnungForm(request.POST)
        if form.is_valid():
            # Versand-Pflicht vor Rechnungserstellung (17.10.2026, auf Wunsch von Björn):
            # eine Rechnung darf nur zu einem tatsaechlich versendeten Lieferschein erzeugt
            # werden (Trackingnummer gesetzt, siehe Lieferschein.tatsaechlich_versendet).
            # Bewusst nur hier bei der NEU-Erstellung geprueft, nicht in RechnungForm.clean()
            # oder bei rechnung_bearbeiten - damit bereits bestehende (vor dieser Regel
            # angelegte) Rechnungen beim Bearbeiten nicht nachtraeglich blockiert werden.
            gewaehlter_lieferschein = form.cleaned_data.get("lieferschein")
            if not gewaehlter_lieferschein:
                form.add_error(
                    "lieferschein",
                    "Pflichtfeld: Eine Rechnung kann erst nach Versand zu einem Lieferschein "
                    "erzeugt werden.",
                )
            elif not gewaehlter_lieferschein.tatsaechlich_versendet:
                form.add_error(
                    "lieferschein",
                    f"Lieferschein {gewaehlter_lieferschein.nummer} hat noch keine Trackingnummer "
                    f"hinterlegt. Bitte zuerst dort auf der Detailseite \"Als versendet markieren\" "
                    f"ausfüllen, dann kann die Rechnung erzeugt werden.",
                )
            else:
                rechnung = form.save()
                formset = RechnungPositionFormSet(request.POST, instance=rechnung)
                if formset.is_valid():
                    formset.save()
                    # 24.10.2026, auf Wunsch von Björn: wie beim Packschein/Lieferschein
                    # (siehe dort) - Nachfasskette stoppen, sobald zu diesem Angebot eine
                    # Rechnung angelegt wird.
                    if rechnung.angebot_id:
                        nurture.angebot_als_angenommen_markieren(rechnung.angebot)
                    return redirect(rechnung.get_absolute_url())
                return render(request, "vertrieb/rechnung_form.html", {
                    "form": form, "formset": formset, "angebot_quelle": angebot_quelle,
                    "lieferschein_quelle": lieferschein_quelle,
                })
        formset = RechnungPositionFormSet(request.POST)
    else:
        initial = {}
        deal_id = request.GET.get("deal")
        if lieferschein_quelle:
            initial = {
                "deal": lieferschein_quelle.deal_id, "lieferschein": lieferschein_quelle.pk,
                "angebot": lieferschein_quelle.angebot_id,
                # Sprache vom Lieferschein übernehmen (nicht nochmal vom Angebot dahinter) -
                # der Lieferschein ist das unmittelbar vorhergehende Dokument in der Kette.
                "sprache": lieferschein_quelle.sprache,
            }
        elif angebot_quelle:
            initial = {
                "deal": angebot_quelle.deal_id, "angebot": angebot_quelle.pk,
                "sprache": angebot_quelle.sprache,
            }
        elif deal_id:
            initial = {"deal": deal_id}
        form = RechnungForm(initial=initial)

        quelle_positionen = None
        if lieferschein_quelle:
            quelle_positionen = lieferschein_quelle.positionen.all()
        elif angebot_quelle:
            quelle_positionen = angebot_quelle.positionen.all()

        if quelle_positionen is not None and quelle_positionen.exists():
            positionen_initial = []
            for p in quelle_positionen:
                einzelpreis = getattr(p, "einzelpreis", 0) or 0
                positionen_initial.append({
                    "artikel": p.artikel_id, "position": p.position, "bezeichnung": p.bezeichnung,
                    "menge": p.menge, "einheit": p.einheit, "einzelpreis": einzelpreis,
                })
            FormSetVorbefuellt = inlineformset_factory(
                Rechnung, Rechnung.positionen.rel.related_model,
                form=RechnungPositionFormSet.form, extra=len(positionen_initial), can_delete=True,
            )
            formset = FormSetVorbefuellt(initial=positionen_initial)
        else:
            formset = RechnungPositionFormSet()
    return render(request, "vertrieb/rechnung_form.html", {
        "form": form, "formset": formset, "angebot_quelle": angebot_quelle, "lieferschein_quelle": lieferschein_quelle,
    })


@login_required
def rechnung_bearbeiten(request, pk):
    rechnung = get_object_or_404(Rechnung, pk=pk)
    if not rechnung.ist_bearbeitbar:
        messages.warning(
            request,
            "Diese Rechnung wurde bereits versendet und darf nach GoBD nicht mehr nachtraeglich "
            "geaendert werden. Fuer Korrekturen bitte eine Stornorechnung/Gutschrift erstellen "
            "(dieser Workflow ist noch nicht automatisiert).",
        )
        return redirect(rechnung.get_absolute_url())
    if request.method == "POST":
        form = RechnungForm(request.POST, instance=rechnung)
        formset = RechnungPositionFormSet(request.POST, instance=rechnung)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            return redirect(rechnung.get_absolute_url())
    else:
        form = RechnungForm(instance=rechnung)
        formset = RechnungPositionFormSet(instance=rechnung)
    return render(request, "vertrieb/rechnung_form.html", {
        "form": form, "formset": formset, "rechnung": rechnung,
    })


class RechnungDeleteView(LoginRequiredMixin, DeleteView):
    """24.10.2026, auf Wunsch von Björn: bislang liess sich JEDE Rechnung loeschen, unabhaengig
    vom Status - also auch eine bereits versendete oder sogar bezahlte, deren Nummer nach GoBD
    eigentlich unveraenderbar/unloeschbar sein muss (dieselbe Luecke besteht unveraendert auch
    bei AngebotDeleteView/PackscheinDeleteView/LieferscheinDeleteView, dort aber bewusst NICHT
    mit behoben - das waere eine eigene, separat zu entscheidende Aenderung). Fix: Loeschen nur
    noch erlaubt, solange die Rechnung "entwurf" ist (= rechnung.ist_bearbeitbar, dieselbe
    Grenze wie bei rechnung_bearbeiten). Die GET-Bestaetigungsseite bleibt erreichbar (sie zeigt
    dann einfach die Warnung statt eines Loeschen-Buttons), geloescht wird erst beim POST."""

    model = Rechnung
    template_name = "vertrieb/confirm_delete.html"
    success_url = reverse_lazy("vertrieb:rechnung_list")

    def form_valid(self, form):
        rechnung = self.get_object()
        if not rechnung.ist_bearbeitbar:
            messages.warning(
                self.request,
                f"Rechnung {rechnung.nummer} wurde bereits versendet und darf nach GoBD nicht "
                f"mehr geloescht werden (Status \"{rechnung.get_status_display()}\"). Für "
                f"Korrekturen bitte eine Stornorechnung erstellen.",
            )
            return redirect(rechnung.get_absolute_url())
        return super().form_valid(form)


@login_required
def rechnung_pdf_download(request, pk):
    rechnung = get_object_or_404(Rechnung, pk=pk)
    pdf_bytes = pdf.rechnung_pdf_erzeugen(rechnung)
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{rechnung.nummer}.pdf"'
    return response


@login_required
def rechnung_versand_senden_view(request, pk):
    """Verschickt eine Rechnung manuell per Mail (20.10.2026, auf Wunsch von Björn, siehe
    nurture.py Teil 7) - fuer den Fall, dass die Automatik bei Lieferschein-Versand mangels
    Positionspreisen nicht automatisch versenden konnte (rechnung bleibt dann als Entwurf
    liegen), oder um eine manuell erstellte Rechnung (views.rechnung_erstellen) ebenfalls
    per Mail zu verschicken statt nur als PDF herunterzuladen."""
    rechnung = get_object_or_404(Rechnung, pk=pk)
    if request.method == "POST":
        if rechnung.status != "entwurf":
            messages.info(request, f"Rechnung {rechnung.nummer} wurde bereits versendet.")
        else:
            erfolg, fehler = nurture.rechnung_versand_senden(rechnung)
            if erfolg:
                messages.success(request, f"Rechnung {rechnung.nummer} wurde per Mail an den Kunden versendet.")
            else:
                messages.warning(
                    request,
                    f"Rechnung {rechnung.nummer} konnte NICHT per Mail versendet werden ({fehler}).",
                )
    return redirect(rechnung.get_absolute_url())


@login_required
def rechnung_zahlung_erfassen(request, pk):
    """Erfasst einen Zahlungseingang zu einer Rechnung (24.10.2026, auf Wunsch von Björn:
    Offene-Posten-Uebersicht/Mahnwesen-Vorstufe, siehe offene_posten_liste unten) - bewusst
    ein eigener View, unabhaengig von der GoBD-Inhaltssperre in rechnung_bearbeiten (siehe
    dort), analog zu packschein_versand_bestaetigen/lieferschein_versand_bestaetigen. Mehrere
    Zahlungen pro Rechnung moeglich (Teilzahlungen). Rechnung.status wird NICHT hier,
    sondern ereignisbasiert per Signal gesetzt (siehe signals.rechnungzahlung_gespeichert),
    damit das auch bei einer Erfassung/Korrektur ueber das Admin-Interface funktioniert."""
    rechnung = get_object_or_404(Rechnung, pk=pk)
    if rechnung.status not in ("versendet", "bezahlt"):
        messages.warning(
            request,
            f"Rechnung {rechnung.nummer} ist noch nicht versendet (oder bereits storniert) - "
            f"ein Zahlungseingang kann erst danach erfasst werden.",
        )
        return redirect(rechnung.get_absolute_url())

    if request.method == "POST":
        form = RechnungZahlungForm(request.POST)
        if form.is_valid():
            zahlung = form.save(commit=False)
            zahlung.rechnung = rechnung
            zahlung.save()
            messages.success(
                request,
                f"Zahlungseingang über {zahlung.betrag} € zu Rechnung {rechnung.nummer} erfasst.",
            )
            return redirect(rechnung.get_absolute_url())
    else:
        form = RechnungZahlungForm()
    return render(request, "vertrieb/rechnung_zahlung_form.html", {"form": form, "rechnung": rechnung})


@login_required
def rechnung_zahlung_loeschen(request, pk, zahlung_pk):
    """Loescht einen fehlerhaft erfassten Zahlungseingang wieder (z.B. Zahlendreher). Der
    Rechnung-Status wird danach ueber das post_delete-Signal (siehe signals.py) automatisch
    neu bewertet - kein manuelles Zuruecksetzen noetig."""
    rechnung = get_object_or_404(Rechnung, pk=pk)
    zahlung = get_object_or_404(RechnungZahlung, pk=zahlung_pk, rechnung=rechnung)
    if request.method == "POST":
        betrag = zahlung.betrag
        zahlung.delete()
        messages.success(request, f"Zahlungseingang über {betrag} € wurde gelöscht.")
    return redirect(rechnung.get_absolute_url())


@login_required
def rechnung_korrektur_erstellen(request, pk):
    """Erstellt eine Stornorechnung/Rechnungskorrektur zu einer bereits versendeten/bezahlten
    Rechnung (24.10.2026, auf Wunsch von Björn - siehe Rechnung.storno_zu/korrektursumme/
    effektiver_bruttobetrag fuer die Hintergrund-Logik und den Kommentar bei
    RechnungKorrekturForm zur Terminologie: "Stornorechnung"/"Rechnungskorrektur", NICHT
    "Gutschrift" - dieser Begriff meint nach §14 UStG rechtlich etwas anderes).

    Deckt sowohl Vollstorno als auch Teilkorrektur ueber EINEN Mechanismus ab: die Positionen
    werden beim Anlegen als vollstaendiger, in der Menge negierter Spiegel des Originals
    vorbefuellt (= Vollstorno als editierbarer Standard) - einzelne Zeilen koennen vor dem
    Speichern geloescht oder in der Menge angepasst werden, um daraus eine Teilkorrektur zu
    machen. Die neue Rechnung bekommt automatisch ein eigenes "ST-"-Nummernpraefix (siehe
    Rechnung.save()) und startet als Entwurf - erst der tatsaechliche Versand (bestehender
    "Jetzt versenden"-Button, nurture.rechnung_versand_senden) zaehlt wirtschaftlich und loest
    die Neuberechnung des Original-Status aus (siehe signals.rechnung_korrektur_gespeichert).

    Bewusst nur fuer ORIGINALE erreichbar (original.storno_zu_id muss leer sein) - eine
    Korrektur einer Korrektur wuerde Korrekturketten erzeugen, die weder angefragt noch in der
    aktuellen Statuslogik vorgesehen sind; bei Bedarf separat zu entscheiden."""
    original = get_object_or_404(Rechnung, pk=pk)
    if original.storno_zu_id:
        messages.warning(
            request,
            f"Rechnung {original.nummer} ist selbst bereits eine Korrektur zu "
            f"{original.storno_zu.nummer}. Eine Korrektur einer Korrektur wird aktuell nicht "
            f"unterstützt.",
        )
        return redirect(original.get_absolute_url())
    if original.status not in ("versendet", "bezahlt"):
        messages.warning(
            request,
            f"Rechnung {original.nummer} kann erst korrigiert werden, wenn sie versendet oder "
            f"bezahlt ist (aktueller Status: \"{original.get_status_display()}\").",
        )
        return redirect(original.get_absolute_url())

    if request.method == "POST":
        form = RechnungKorrekturForm(request.POST)
        if form.is_valid():
            korrektur = form.save(commit=False)
            korrektur.deal_id = original.deal_id
            korrektur.angebot_id = original.angebot_id
            korrektur.lieferschein_id = original.lieferschein_id
            korrektur.storno_zu = original
            korrektur.status = "entwurf"
            korrektur.save()
            formset = RechnungPositionFormSet(request.POST, instance=korrektur)
            if formset.is_valid():
                formset.save()
                messages.success(
                    request,
                    f"Korrektur {korrektur.nummer} zu Rechnung {original.nummer} wurde als "
                    f"Entwurf angelegt. Bitte Positionen prüfen und über \"Jetzt versenden\" an "
                    f"den Kunden schicken, damit sie wirksam wird.",
                )
                return redirect(korrektur.get_absolute_url())
            return render(request, "vertrieb/rechnung_korrektur_form.html", {
                "form": form, "formset": formset, "original": original,
            })
        formset = RechnungPositionFormSet(request.POST)
    else:
        form = RechnungKorrekturForm(initial={
            "rechnungsdatum": timezone.localdate(),
            "leistungsdatum": original.leistungsdatum,
            "sprache": original.sprache,
        })
        positionen_initial = [
            {
                "artikel": p.artikel_id, "position": p.position, "bezeichnung": p.bezeichnung,
                "menge": -p.menge, "einheit": p.einheit, "einzelpreis": p.einzelpreis,
                "steuersatz": p.steuersatz,
            }
            for p in original.positionen.all()
        ]
        FormSetVorbefuellt = inlineformset_factory(
            Rechnung, RechnungPosition, form=RechnungPositionFormSet.form,
            extra=len(positionen_initial) or 1, can_delete=True,
        )
        formset = FormSetVorbefuellt(initial=positionen_initial)
    return render(request, "vertrieb/rechnung_korrektur_form.html", {
        "form": form, "formset": formset, "original": original,
    })


@login_required
def offene_posten_liste(request):
    """Interne Uebersicht ueber unbezahlte/ueberfaellige Rechnungen (24.10.2026, auf Wunsch
    von Björn: "aus kundensicht" identifizierte Luecke - es gab bisher keine Stelle im CRM,
    die ueberfaellige Zahlungen sichtbar machte; Rechnung.status "bezahlt" liess sich bis
    eben noch nicht einmal setzen, siehe Model-Doku). Bewusst OHNE automatischen
    Mahnversand an den Kunden - auf Wunsch von Björn zunaechst eine reine interne
    Arbeitsliste, aus der heraus er selbst entscheidet, wann und wie er nachfasst."""
    rechnungen = (
        Rechnung.objects.filter(status="versendet")
        .select_related("deal", "deal__firma", "deal__kontakt")
        .prefetch_related("positionen", "zahlungen")
    )
    offene = [r for r in rechnungen if r.offener_betrag > 0]
    offene.sort(key=lambda r: r.faelligkeitsdatum)
    summe_offen = sum((r.offener_betrag for r in offene), start=Decimal("0"))
    summe_ueberfaellig = sum((r.offener_betrag for r in offene if r.ist_ueberfaellig), start=Decimal("0"))
    return render(request, "vertrieb/offene_posten_list.html", {
        "rechnungen": offene,
        "summe_offen": summe_offen,
        "summe_ueberfaellig": summe_ueberfaellig,
        "anzahl_ueberfaellig": len([r for r in offene if r.ist_ueberfaellig]),
    })


# ---------------------------------------------------------------------------
# Email-Übersicht
# ---------------------------------------------------------------------------

class EmailVersandListView(LoginRequiredMixin, ListView):
    """Übersicht ALLER automatischen Kundenmails - erfolgreich und fehlgeschlagen (20.10.2026,
    auf Wunsch von Björn: "alle emailaktivitaeten sehen koennen, um einen ueberblick zu
    haben"). Siehe models.EmailVersand / nurture._mail_protokollieren."""
    model = EmailVersand
    template_name = "vertrieb/email_versand_list.html"
    context_object_name = "email_versaende"
    paginate_by = 50

    def get_queryset(self):
        qs = EmailVersand.objects.all().select_related("deal", "deal__firma")
        if self.request.GET.get("nur_fehler") == "1":
            qs = qs.filter(erfolg=False)
        return qs


class MusterboxNachfassStatusListView(LoginRequiredMixin, View):
    """Globale Übersicht aller Nachfassketten (20.10.2026, auf Wunsch von Björn, als Ergänzung
    zur Anzeige auf der Deal-/Angebots-Detailseite: "die wollte ich aber haben" - er wollte
    eine deal-übergreifende Liste, nicht nur die Einzelanzeige pro Deal).

    AENDERUNG 24.10.2026 (auf Wunsch von Björn: "ich muss das aber in der nachfass übersicht
    sehen können! nicht nur die musterboxen, sondern auch die angebote.. so war es besprochen"):
    zeigt jetzt BEIDE Nachfassketten gemeinsam in einer Liste - die 8-wöchige Musterbox-Kette
    UND die 3-stufige Angebot-Kette - sortiert nach Fälligkeitsdatum, damit auf einen Blick
    erkennbar ist, was als Nächstes fällig ist, unabhängig vom Ketten-Typ. War urspruenglich nur
    fuer Musterbox gebaut (siehe Klassenname/Template, aus Kompatibilitaetsgruenden unveraendert
    gelassen), die Angebot-Kette (23.10.2026) wurde hier versehentlich nicht ergaenzt.

    Kein ListView mehr, da zwei unterschiedliche Modelle zu einer Liste zusammengefuehrt werden
    muessen - Paginierung deshalb von Hand ueber Paginator, mit denselben Kontext-Namen
    (page_obj/is_paginated), die _pagination.html erwartet.

    Standardmäßig nur aktive Ketten, über "Alle anzeigen" auch bereits beendete Ketten mit
    Beendigungsgrund."""
    template_name = "vertrieb/musterbox_nachfass_list.html"
    EINTRAEGE_PRO_SEITE = 50

    def get(self, request):
        alle = request.GET.get("alle") == "1"

        musterbox_qs = MusterboxNachfassStatus.objects.all().select_related("deal", "deal__firma")
        if not alle:
            musterbox_qs = musterbox_qs.filter(aktiv=True)

        angebot_qs = AngebotNachfassStatus.objects.all().select_related(
            "angebot", "angebot__deal", "angebot__deal__firma",
        )
        if not alle:
            angebot_qs = angebot_qs.filter(aktiv=True)

        eintraege = []
        for status in musterbox_qs:
            eintraege.append({
                "typ": "Musterbox",
                "deal": status.deal,
                "fortschritt": f"{status.naechste_woche}/8",
                "sprache": status.get_sprache_display(),
                "naechster_versand_am": status.naechster_versand_am,
                "aktiv": status.aktiv,
                "beendet_grund": status.get_beendet_grund_display() if status.beendet_grund else "",
                "url": status.deal.get_absolute_url(),
            })
        for status in angebot_qs:
            eintraege.append({
                "typ": "Angebot",
                "deal": status.angebot.deal,
                "fortschritt": f"Schritt {status.naechster_schritt}/{ANGEBOT_NACHFASS_SCHRITTE}",
                "sprache": status.get_sprache_display(),
                "naechster_versand_am": status.naechster_versand_am,
                "aktiv": status.aktiv,
                "beendet_grund": status.get_beendet_grund_display() if status.beendet_grund else "",
                "url": status.angebot.get_absolute_url(),
                "angebot_nummer": status.angebot.nummer,
            })

        eintraege.sort(key=lambda e: (not e["aktiv"], e["naechster_versand_am"]))

        paginator = Paginator(eintraege, self.EINTRAEGE_PRO_SEITE)
        page_obj = paginator.get_page(request.GET.get("page"))

        return render(request, self.template_name, {
            "status_liste": page_obj.object_list,
            "page_obj": page_obj,
            "paginator": paginator,
            "is_paginated": page_obj.has_other_pages(),
        })


# ---------------------------------------------------------------------------
# Artikel (Artikelstamm)
# ---------------------------------------------------------------------------

class ArtikelListView(LoginRequiredMixin, ListView):
    model = Artikel
    template_name = "vertrieb/artikel_list.html"
    context_object_name = "artikel_liste"
    paginate_by = 50

    def get_queryset(self):
        qs = Artikel.objects.all()
        suche = self.request.GET.get("q")
        if suche:
            qs = qs.filter(models.Q(artikelnummer__icontains=suche) | models.Q(bezeichnung__icontains=suche))
        return qs


class ArtikelDetailView(LoginRequiredMixin, DetailView):
    model = Artikel
    template_name = "vertrieb/artikel_detail.html"
    context_object_name = "artikel"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["preisstaffeln"] = self.object.preisstaffeln.all()
        if self.object.fuehrt_chargen:
            context["chargen"] = self.object.chargen.select_related("lieferant").all()
        return context


class ArtikelCreateView(LoginRequiredMixin, CreateView):
    model = Artikel
    form_class = ArtikelForm
    template_name = "vertrieb/artikel_form.html"


class ArtikelUpdateView(LoginRequiredMixin, UpdateView):
    model = Artikel
    form_class = ArtikelForm
    template_name = "vertrieb/artikel_form.html"


class ArtikelDeleteView(LoginRequiredMixin, DeleteView):
    model = Artikel
    template_name = "vertrieb/confirm_delete.html"
    success_url = reverse_lazy("vertrieb:artikel_list")


@login_required
def wareneingang_erfassen(request):
    """Bucht einen Wareneingang für Rohmaterial/Verpackungsmaterial (Phase 2
    Materialwirtschaft, 24.10.2026, auf Wunsch von Björn - Handelsware und Fertigware
    bleiben bewusst außen vor, siehe MATERIALTYPEN_MIT_CHARGENBESTAND-Kommentar in
    models.py). Legt in EINER Transaktion eine neue Charge (Startbestand 0) UND die
    zugehörige erste Lagerbewegung vom Typ "Wareneingang" an - Lagerbewegung.save()
    schreibt den Chargenbestand dabei automatisch fort (siehe Model-Doku), damit nie eine
    Charge ohne zugehörige Bewegung entsteht, auch nicht bei einem Fehler mittendrin."""
    artikel_id = request.GET.get("artikel") or request.POST.get("artikel")
    vorausgewaehlter_artikel = None
    if artikel_id:
        vorausgewaehlter_artikel = Artikel.objects.filter(
            pk=artikel_id, materialtyp__in=MATERIALTYPEN_MIT_CHARGENBESTAND,
        ).first()

    if request.method == "POST":
        form = WareneingangForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                charge = form.save()
                Lagerbewegung.objects.create(
                    artikel=charge.artikel, charge=charge, bewegungstyp="wareneingang",
                    menge=charge.menge_eingang,
                    erstellt_von=request.user if request.user.is_authenticated else None,
                )
            messages.success(
                request,
                f"Wareneingang gebucht: {charge.menge_eingang} {charge.artikel.get_einheit_display()} "
                f"{charge.artikel.artikelnummer} (Charge {charge.chargennummer or charge.pk}).",
            )
            return redirect(charge.artikel.get_absolute_url())
    else:
        initial = {}
        if vorausgewaehlter_artikel:
            initial["artikel"] = vorausgewaehlter_artikel.pk
        form = WareneingangForm(initial=initial)
    return render(request, "vertrieb/wareneingang_form.html", {"form": form})


class LagerbewegungListView(LoginRequiredMixin, ListView):
    """Unveränderliches Bewegungsjournal (Phase 2 Materialwirtschaft, 24.10.2026) - rein
    lesend, da Lagerbewegungen laut Modell nie editiert/gelöscht werden (siehe
    Lagerbewegung.delete())."""
    model = Lagerbewegung
    template_name = "vertrieb/lagerbewegung_list.html"
    context_object_name = "bewegungen"
    paginate_by = 50

    def get_queryset(self):
        return Lagerbewegung.objects.select_related("artikel", "charge", "erstellt_von").all()


@login_required
def artikel_daten_json(request, pk):
    """Liefert Bezeichnung/Einheit/Preis/Lagerbestand eines Artikels als JSON - genutzt
    von der Artikelauswahl in den Positionsformularen (Angebot/Packschein/Lieferschein/
    Rechnung), um die übrigen Felder der Zeile per JavaScript automatisch zu befüllen,
    ohne die Seite neu zu laden. Die Felder bleiben danach für den Nutzer frei editierbar -
    das hier ist nur ein Ausfüll-Vorschlag, keine Festschreibung.

    sprache=en (18.10.2026, Angebot.sprache - siehe Model-Doku "eine Preisquelle, zwei
    Anzeigesprachen"): liefert bezeichnung_en statt bezeichnung, falls gepflegt - Preis/
    Staffeln/Lagerbestand bleiben IMMER die des angefragten Artikels, unabhängig von der
    Sprache. Fehlt bezeichnung_en (noch) für diesen Artikel, fällt die Vorbefüllung auf
    die deutsche Bezeichnung zurück, statt leer zu bleiben."""
    artikel = get_object_or_404(Artikel, pk=pk)
    menge = request.GET.get("menge")
    try:
        menge_dec = Decimal(menge) if menge not in (None, "") else None
    except InvalidOperation:
        menge_dec = None
    preis = artikel.preis_fuer_menge(menge_dec)
    staffeln = [
        {"ab_menge": s.ab_menge, "preis_netto": str(s.preis_netto)}
        for s in artikel.preisstaffeln.all()
    ]
    sprache = request.GET.get("sprache")
    bezeichnung = artikel.bezeichnung_en if sprache == "en" and artikel.bezeichnung_en else artikel.bezeichnung
    return JsonResponse({
        "bezeichnung": bezeichnung,
        "einheit": artikel.einheit,
        "einzelpreis": str(preis) if preis is not None else None,
        "steuersatz": str(artikel.ust_satz),
        "verkaufspreis_flatrate": str(artikel.verkaufspreis) if artikel.verkaufspreis is not None else None,
        "preisstaffeln": staffeln,
        "lagerbestand_aktuell": str(artikel.lagerbestand_anzeige) if artikel.lagerbestand_anzeige is not None else None,
        "mindestbestand": str(artikel.mindestbestand) if artikel.mindestbestand is not None else None,
        "unter_mindestbestand": artikel.unter_mindestbestand,
        "status": artikel.get_status_display() if artikel.status else "",
    })


# ---------------------------------------------------------------------------
# Artikel-/Preisliste erzeugen & versenden (21.10.2026, auf Wunsch von Björn: "eine
# funktion ... mit auswahl ob deutsch oder englisch, in dem ich unsere artikelliste samt
# preisstaffel mit eckopack briefpapier erzeugen und versenden kann") - bewusst KEIN
# Deal-/Firmenbezug: freie E-Mail-Eingabe statt Firma/Kontakt-Auswahl (anders als alle
# übrigen Versandfunktionen in diesem Modul), siehe nurture.artikelliste_versenden.
# Nur Großhandels-Artikel (vertriebskanal="standard") - Amazon-Zweitlistungen bleiben
# analog zur Positionsauswahl in Angebot/Packschein/Lieferschein/Rechnung aussen vor
# (siehe Artikel-Model-Doku).
# ---------------------------------------------------------------------------

def _artikelliste_standard_artikel():
    return Artikel.objects.filter(vertriebskanal="standard").order_by("artikelnummer").prefetch_related("preisstaffeln")


@login_required
def artikelliste_pdf_download(request):
    sprache = request.GET.get("sprache")
    if sprache not in ("de", "en"):
        sprache = "de"
    aufschlag_prozent, _fehler = _aufschlag_prozent_parsen(request.GET.get("aufschlag"))
    pdf_bytes = pdf.artikelliste_pdf_erzeugen(_artikelliste_standard_artikel(), sprache=sprache, aufschlag_prozent=aufschlag_prozent)
    dateiname = "ECKO-PACK_Price_List.pdf" if sprache == "en" else "ECKO-PACK_Artikel-Preisliste.pdf"
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{dateiname}"'
    return response


def _empfaenger_zeilen_aus_textarea(request):
    """Freitext-Anschriftenfeld (21.10.2026, auf Wunsch von Björn: "ich möchte aber auch
    die adresse auf der preisliste eingeben können") in einzelne, nicht-leere Zeilen
    zerlegt - wie bei der freien E-Mail-Eingabe bewusst kein Firma/Kontakt-Lookup, da die
    Preisliste (anders als Angebot & Co.) keinen Deal-/Firmenbezug hat."""
    rohtext = request.POST.get("empfaenger_adresse", "")
    return [zeile.strip() for zeile in rohtext.splitlines() if zeile.strip()]


def _aufschlag_prozent_parsen(rohwert):
    """Parst das optionale Aufschlag-Feld der Preisliste (21.10.2026, auf Wunsch von
    Björn: Preisliste mit Agenten-Provision, "ich muss in der Lage sein, die Preisliste
    so rauszugeben, dass ich ... 5% Provision aufschlage"). Deutsche Komma-Eingabe ("5,5")
    wird wie an den übrigen Zahlenfeldern dieser App akzeptiert. Leer/None bedeutet
    ausdrücklich "kein Aufschlag", nicht "0 wurde eingegeben" - beides landet aber auf
    demselben None-Rückgabewert, da 0% ohnehin keine sichtbare Auswirkung hätte.

    Gibt (Decimal|None, Fehlermeldung|None) zurück. -100% oder weniger würde Preise auf
    0 oder negativ drücken (unsinnig für einen Aufschlag), + Obergrenze bei 500% als grobe
    Tippfehler-Bremse (z. B. versehentlich "500" statt "5,00" eingegeben)."""
    rohwert = (rohwert or "").strip()
    if not rohwert:
        return None, None
    try:
        wert = Decimal(rohwert.replace(",", "."))
    except InvalidOperation:
        return None, f"„{rohwert}“ ist kein gültiger Prozentwert für den Aufschlag."
    if wert <= Decimal("-100"):
        return None, "Der Aufschlag darf nicht -100% oder weniger betragen (Preis würde 0 oder negativ)."
    if wert > Decimal("500"):
        return None, f"{wert}% erscheint unplausibel hoch für einen Aufschlag - bitte prüfen."
    if wert == 0:
        return None, None
    return wert, None


@login_required
def artikelliste_versenden(request):
    """GET zeigt das Formular (Sprachwahl + optionale Anschrift + freie E-Mail-Eingabe +
    optionaler Preisaufschlag). POST unterscheidet per "aktion"-Feld zwei Buttons
    desselben Formulars: "ansehen" liefert das PDF direkt zur Ansicht (wie zuvor
    artikelliste_pdf_download, aber jetzt inklusive der eingegebenen Anschrift fürs
    Briefpapier), "senden" verschickt die Artikel-/Preisliste direkt per Mail (ohne
    Umweg über einen Deal) - siehe nurture.artikelliste_versenden. Erfolg/Fehlschlag
    werden wie bei den übrigen Mailversand-Views über Django-Messages zurückgemeldet und
    zusätzlich zentral in EmailVersand protokolliert (deal=None, siehe
    models.EmailVersand).

    aufschlag_prozent (21.10.2026, Björns Agenten-Provisions-Anfrage): optionales
    Prozent-Eingabefeld, das auf JEDEN Preis der erzeugten Liste aufgeschlagen wird (siehe
    pdf.artikelliste_pdf_erzeugen) - z.B. um die Liste 1:1 an einen Vertriebsagenten
    weiterzugeben, der seinerseits eine Provision in dieser Höhe einbehält. Ein
    ungültiger/unplausibler Wert blockiert bewusst "ansehen" UND "senden" (statt
    stillschweigend auf 0% zurückzufallen), da ein versehentlich falscher Aufschlag auf
    einem Preisdokument, das an Dritte geht, teuer werden kann."""
    if request.method == "POST":
        sprache = request.POST.get("sprache")
        if sprache not in ("de", "en"):
            sprache = "de"
        empfaenger_zeilen = _empfaenger_zeilen_aus_textarea(request)
        aufschlag_prozent, aufschlag_fehler = _aufschlag_prozent_parsen(request.POST.get("aufschlag_prozent"))
        if aufschlag_fehler:
            messages.warning(request, aufschlag_fehler)
            return redirect("vertrieb:artikelliste_versenden")

        if request.POST.get("aktion") == "ansehen":
            pdf_bytes = pdf.artikelliste_pdf_erzeugen(
                _artikelliste_standard_artikel(), sprache=sprache, empfaenger_zeilen=empfaenger_zeilen,
                aufschlag_prozent=aufschlag_prozent,
            )
            dateiname = "ECKO-PACK_Price_List.pdf" if sprache == "en" else "ECKO-PACK_Artikel-Preisliste.pdf"
            response = HttpResponse(pdf_bytes, content_type="application/pdf")
            response["Content-Disposition"] = f'inline; filename="{dateiname}"'
            return response

        empfaenger = (request.POST.get("empfaenger") or "").strip()
        if not empfaenger:
            messages.warning(request, "Bitte eine Empfänger-E-Mail-Adresse eingeben.")
        else:
            try:
                validate_email(empfaenger)
            except ValidationError:
                messages.warning(request, f"„{empfaenger}“ ist keine gültige E-Mail-Adresse.")
                return redirect("vertrieb:artikelliste_versenden")
            erfolg, fehler = nurture.artikelliste_versenden(
                empfaenger, sprache=sprache, empfaenger_zeilen=empfaenger_zeilen, aufschlag_prozent=aufschlag_prozent,
            )
            if erfolg:
                hinweis_aufschlag = f" (mit {aufschlag_prozent}% Aufschlag)" if aufschlag_prozent else ""
                messages.success(request, f"Artikel-/Preisliste wurde an {empfaenger} versendet{hinweis_aufschlag}.")
            else:
                messages.warning(
                    request,
                    f"Artikel-/Preisliste konnte NICHT an {empfaenger} versendet werden ({fehler}).",
                )
        return redirect("vertrieb:artikelliste_versenden")

    return render(request, "vertrieb/artikelliste_versenden.html", {
        "anzahl_artikel": _artikelliste_standard_artikel().count(),
    })
