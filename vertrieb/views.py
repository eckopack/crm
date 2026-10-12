import os

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.management import call_command
from django.db.models import Sum
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from . import nurture, pdf
from .forms import (
    AktivitaetForm, AngebotForm, AngebotPositionFormSet, DealForm, FirmaForm, KontaktForm,
    PackscheinForm, PackscheinPositionFormSet, PackscheinVersandForm,
    LieferscheinForm, LieferscheinPositionFormSet, RechnungForm, RechnungPositionFormSet,
)
from .models import (
    DEAL_PHASE_CHOICES, PHASE_STANDARD_WAHRSCHEINLICHKEIT,
    Aktivitaet, Angebot, Deal, Firma, Kontakt, Packschein, PackscheinPosition, Lieferschein, Rechnung,
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

    kontext = {
        "pipeline_wert": pipeline_wert,
        "pipeline_gewichtet": pipeline_gewichtet,
        "anzahl_offene_deals": offene_deals.count(),
        "anzahl_firmen": Firma.objects.count(),
        "anstehend": anstehend,
        "ueberfaellig": ueberfaellig,
        "phasen_uebersicht": phasen_uebersicht,
    }
    return render(request, "vertrieb/dashboard.html", kontext)


@login_required
def pipeline_kanban(request):
    spalten = []
    for key, label in DEAL_PHASE_CHOICES:
        deals = Deal.objects.filter(phase=key).select_related("firma", "zustaendiger")
        spalten.append({
            "key": key,
            "label": label,
            "deals": deals,
            "summe": deals.aggregate(s=Sum("wert"))["s"] or 0,
            "tonnen_summe": deals.aggregate(s=Sum("potenzial_tonnen"))["s"] or 0,
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
        suche = self.request.GET.get("q")
        if suche:
            qs = qs.filter(name__icontains=suche)
        return qs


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


class FirmaDeleteView(LoginRequiredMixin, DeleteView):
    model = Firma
    template_name = "vertrieb/confirm_delete.html"
    success_url = reverse_lazy("vertrieb:firma_list")


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
        suche = self.request.GET.get("q")
        if suche:
            qs = qs.filter(nachname__icontains=suche)
        return qs


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


class KontaktDeleteView(LoginRequiredMixin, DeleteView):
    model = Kontakt
    template_name = "vertrieb/confirm_delete.html"
    success_url = reverse_lazy("vertrieb:kontakt_list")


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
        return context


@login_required
def musterkarton_anfordern(request, pk):
    """Schnellaktion auf der Deal-Detailseite: legt für einen Lead einen
    Musterkarton-Packschein an (Position 'Musterkarton', 1 Stück). Der eigentliche
    Versand (Trackingnummer, Bestätigungsmail, Nachfass-Automatik) läuft über
    'Als versendet markieren' auf der Packschein-Detailseite."""
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

    packschein = Packschein.objects.create(
        deal=deal, datum=timezone.now().date(), status="offen", ist_musterversand=True,
        notizen="Automatisch angelegt über 'Musterkarton anfordern'.",
    )
    PackscheinPosition.objects.create(
        packschein=packschein, position=1, bezeichnung="Musterkarton", menge=1, einheit="stk",
    )
    messages.success(request, f"Packschein {packschein.nummer} für Musterkarton-Versand angelegt.")
    return redirect(packschein.get_absolute_url())


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
    model = Deal
    template_name = "vertrieb/confirm_delete.html"
    success_url = reverse_lazy("vertrieb:deal_list")


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
        initial = {}
        deal_id = request.GET.get("deal")
        if deal_id:
            initial["deal"] = deal_id
        form = AngebotForm(initial=initial)
        formset = AngebotPositionFormSet()
    return render(request, "vertrieb/angebot_form.html", {"form": form, "formset": formset})


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
    model = Angebot
    template_name = "vertrieb/confirm_delete.html"
    success_url = reverse_lazy("vertrieb:angebot_list")


@login_required
def angebot_pdf_download(request, pk):
    angebot = get_object_or_404(Angebot, pk=pk)
    pdf_bytes = pdf.angebot_pdf_erzeugen(angebot)
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{angebot.nummer}.pdf"'
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
            packschein = form.save()
            formset = PackscheinPositionFormSet(request.POST, instance=packschein)
            if formset.is_valid():
                formset.save()
                return redirect(packschein.get_absolute_url())
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
                {"position": p.position, "bezeichnung": p.bezeichnung, "menge": p.menge, "einheit": p.einheit}
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
    model = Packschein
    template_name = "vertrieb/confirm_delete.html"
    success_url = reverse_lazy("vertrieb:packschein_list")


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

    if request.method == "POST":
        form = LieferscheinForm(request.POST)
        if form.is_valid():
            lieferschein = form.save()
            formset = LieferscheinPositionFormSet(request.POST, instance=lieferschein)
            if formset.is_valid():
                formset.save()
                return redirect(lieferschein.get_absolute_url())
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
            }
            quelle_positionen = packschein_quelle.positionen.all()
        elif angebot_quelle:
            initial = {"deal": angebot_quelle.deal_id, "angebot": angebot_quelle.pk}
            quelle_positionen = angebot_quelle.positionen.all()
        elif deal_id:
            initial = {"deal": deal_id}
        form = LieferscheinForm(initial=initial)

        if quelle_positionen is not None and quelle_positionen.exists():
            positionen_initial = [
                {"position": p.position, "bezeichnung": p.bezeichnung, "menge": p.menge, "einheit": p.einheit}
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


class LieferscheinDeleteView(LoginRequiredMixin, DeleteView):
    model = Lieferschein
    template_name = "vertrieb/confirm_delete.html"
    success_url = reverse_lazy("vertrieb:lieferschein_list")


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
        return Rechnung.objects.all().select_related("deal", "deal__firma")


class RechnungDetailView(LoginRequiredMixin, DetailView):
    model = Rechnung
    template_name = "vertrieb/rechnung_detail.html"
    context_object_name = "rechnung"


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
            rechnung = form.save()
            formset = RechnungPositionFormSet(request.POST, instance=rechnung)
            if formset.is_valid():
                formset.save()
                return redirect(rechnung.get_absolute_url())
        else:
            formset = RechnungPositionFormSet(request.POST)
    else:
        initial = {}
        deal_id = request.GET.get("deal")
        if lieferschein_quelle:
            initial = {
                "deal": lieferschein_quelle.deal_id, "lieferschein": lieferschein_quelle.pk,
                "angebot": lieferschein_quelle.angebot_id,
            }
        elif angebot_quelle:
            initial = {"deal": angebot_quelle.deal_id, "angebot": angebot_quelle.pk}
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
                    "position": p.position, "bezeichnung": p.bezeichnung,
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
    model = Rechnung
    template_name = "vertrieb/confirm_delete.html"
    success_url = reverse_lazy("vertrieb:rechnung_list")


@login_required
def rechnung_pdf_download(request, pk):
    rechnung = get_object_or_404(Rechnung, pk=pk)
    pdf_bytes = pdf.rechnung_pdf_erzeugen(rechnung)
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{rechnung.nummer}.pdf"'
    return response
