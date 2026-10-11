from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from .forms import (
    AktivitaetForm, AngebotForm, AngebotPositionFormSet, DealForm, FirmaForm, KontaktForm,
)
from .models import (
    DEAL_PHASE_CHOICES, PHASE_STANDARD_WAHRSCHEINLICHKEIT,
    Aktivitaet, Angebot, Deal, Firma, Kontakt,
)


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
