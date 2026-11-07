"""Thamarayyath Employee Portal — Audit app views (Superadmin read-only)."""

from django.views.generic import ListView
from django.db.models import Q
from .models import AuditLog
from accounts.permissions import SuperadminRequiredMixin


class AuditLogListView(SuperadminRequiredMixin, ListView):
    model = AuditLog
    template_name = "audit/audit_log_list.html"
    context_object_name = "events"
    paginate_by = 50

    def get_queryset(self):
        qs = AuditLog.objects.select_related("actor").order_by("-timestamp")
        q = self.request.GET.get("q", "").strip()
        action = self.request.GET.get("action", "").strip()
        date_from = self.request.GET.get("date_from", "")
        date_to = self.request.GET.get("date_to", "")

        if q:
            qs = qs.filter(
                Q(actor_username__icontains=q)
                | Q(target_id__icontains=q)
                | Q(ip_address__icontains=q)
            )
        if action:
            qs = qs.filter(action=action)
        if date_from:
            qs = qs.filter(timestamp__date__gte=date_from)
        if date_to:
            qs = qs.filter(timestamp__date__lte=date_to)

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["actions"] = AuditLog.Action.choices
        ctx["selected_action"] = self.request.GET.get("action", "")
        ctx["q"] = self.request.GET.get("q", "")
        ctx["date_from"] = self.request.GET.get("date_from", "")
        ctx["date_to"] = self.request.GET.get("date_to", "")
        return ctx
