import json
import logging
from collections.abc import Generator

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import Http404
from django.shortcuts import redirect
from django.views.generic import TemplateView

from commcare_connect.funder_dashboard.data_access import FunderDashboardDataAccess
from commcare_connect.funder_dashboard.forms import FundForm
from commcare_connect.labs.analysis.config import (
    AnalysisPipelineConfig,
    CacheStage,
    DataSourceConfig,
    FieldComputation,
)
from commcare_connect.labs.analysis.pipeline import AnalysisPipeline
from commcare_connect.labs.analysis.sse_streaming import AnalysisPipelineSSEMixin, BaseSSEStreamView, send_sse_event

logger = logging.getLogger(__name__)


class LabsLoginRequiredMixin(LoginRequiredMixin):
    login_url = "/labs/login/"


class ManagerRequiredMixin(LabsLoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_authenticated


def _has_org_context(request):
    labs_context = getattr(request, "labs_context", {})
    return bool(labs_context.get("program_id") or labs_context.get("organization_id"))


def _get_data_access(request):
    return FunderDashboardDataAccess(request=request)


class PortfolioDashboardView(ManagerRequiredMixin, TemplateView):
    template_name = "funder_dashboard/portfolio.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["has_context"] = _has_org_context(self.request)
        if not ctx["has_context"]:
            ctx["funds"] = []
            return ctx
        try:
            da = _get_data_access(self.request)
            funds = da.get_funds()
            ctx["funds"] = funds
            ctx["active_count"] = sum(1 for f in funds if f.status == "active")
            ctx["total_programs"] = sum(len(f.program_ids) for f in funds)
        except Exception:
            logger.exception("Failed to load funds for portfolio")
            ctx["funds"] = []
            ctx["active_count"] = 0
            ctx["total_programs"] = 0
        return ctx


class FundDetailView(ManagerRequiredMixin, TemplateView):
    template_name = "funder_dashboard/fund_detail.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        pk = kwargs["pk"]
        try:
            da = _get_data_access(self.request)
            fund = da.get_fund_by_id(pk)
            if not fund:
                raise Http404("Fund not found")
            ctx["fund"] = fund
        except Http404:
            raise
        except Exception:
            logger.exception("Failed to load fund %s", pk)
            raise Http404("Fund not found")
        return ctx


class FundCreateView(ManagerRequiredMixin, TemplateView):
    template_name = "funder_dashboard/fund_form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["has_context"] = _has_org_context(self.request)
        ctx["form"] = FundForm()
        ctx["is_create"] = True
        return ctx

    def post(self, request, *args, **kwargs):
        if not _has_org_context(request):
            ctx = self.get_context_data(**kwargs)
            ctx["error"] = "Please select an organization from the context selector."
            return self.render_to_response(ctx)

        form = FundForm(request.POST)
        if form.is_valid():
            data = form.to_data_dict()
            try:
                da = _get_data_access(request)
                da.create_fund(data)
                return redirect("funder_dashboard:portfolio")
            except Exception:
                logger.exception("Failed to create fund")
                ctx = self.get_context_data(**kwargs)
                ctx["form"] = form
                ctx["error"] = "Failed to create fund. Please try again."
                return self.render_to_response(ctx)
        else:
            ctx = self.get_context_data(**kwargs)
            ctx["form"] = form
            return self.render_to_response(ctx)


class FundEditView(ManagerRequiredMixin, TemplateView):
    template_name = "funder_dashboard/fund_form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["has_context"] = _has_org_context(self.request)
        pk = kwargs["pk"]
        try:
            da = _get_data_access(self.request)
            fund = da.get_fund_by_id(pk)
            if not fund:
                raise Http404("Fund not found")
            ctx["fund"] = fund
            initial = {
                "name": fund.name,
                "description": fund.description,
                "total_budget": fund.total_budget,
                "currency": fund.currency,
                "status": fund.status,
                "program_ids_json": json.dumps(fund.program_ids),
                "delivery_types_json": json.dumps(fund.delivery_types),
                "allocations_json": json.dumps(fund.allocations),
            }
            ctx["form"] = FundForm(initial=initial)
            ctx["is_create"] = False
        except Http404:
            raise
        except Exception:
            logger.exception("Failed to load fund %s for editing", pk)
            raise Http404("Fund not found")
        return ctx

    def post(self, request, *args, **kwargs):
        pk = kwargs["pk"]
        form = FundForm(request.POST)
        if form.is_valid():
            data = form.to_data_dict()
            try:
                da = _get_data_access(request)
                da.update_fund(pk, data)
                return redirect("funder_dashboard:portfolio")
            except Exception:
                logger.exception("Failed to update fund %s", pk)
                ctx = self.get_context_data(**kwargs)
                ctx["form"] = form
                ctx["error"] = "Failed to update fund. Please try again."
                return self.render_to_response(ctx)
        else:
            ctx = self.get_context_data(**kwargs)
            ctx["form"] = form
            return self.render_to_response(ctx)


class FundPipelineDataView(BaseSSEStreamView):
    """SSE endpoint that streams visit pipeline + completed_works data for a fund's allocations."""

    login_url = "/labs/login/"

    def stream_data(self, request) -> Generator[str, None, None]:
        """Stream pipeline data for each allocation with an opportunity_id."""
        pk = self.kwargs["pk"]
        mixin = AnalysisPipelineSSEMixin()

        try:
            # Check OAuth token
            labs_oauth = request.session.get("labs_oauth", {})
            access_token = labs_oauth.get("access_token")
            if not access_token:
                yield send_sse_event("Error", error="No OAuth token found. Please log in to Connect.")
                return

            # Load the fund and its allocations
            da = _get_data_access(request)
            fund = da.get_fund_by_id(pk)
            if not fund:
                yield send_sse_event("Error", error=f"Fund {pk} not found")
                return

            allocations = fund.allocations
            opp_allocations = [a for a in allocations if a.get("opportunity_id")]
            if not opp_allocations:
                yield send_sse_event("No allocations with opportunity IDs", data={"visits": [], "payments": []})
                return

            yield send_sse_event(f"Processing {len(opp_allocations)} allocations...")

            # Create pipeline once before the loop
            pipeline = AnalysisPipeline(request)

            all_visits = []
            all_payments = []

            for alloc in opp_allocations:
                opp_id = int(alloc["opportunity_id"])
                opp_name = alloc.get("opportunity_name", f"Opportunity {opp_id}")
                country = alloc.get("country", "")
                delivery_type = alloc.get("delivery_type", "")

                yield send_sse_event(f"Loading visits for {opp_name}...")

                # Build pipeline config for visit-level data
                config = AnalysisPipelineConfig(
                    grouping_key="username",
                    terminal_stage=CacheStage.VISIT_LEVEL,
                    data_source=DataSourceConfig(type="connect_csv"),
                    experiment=f"funder_visits_{opp_id}",
                    fields=[
                        FieldComputation(name="visit_date", path="visit_date", aggregation="first"),
                        FieldComputation(
                            name="status",
                            path="status",
                            aggregation="first",
                            transform=lambda v: str(v) if v else "",
                        ),
                        FieldComputation(
                            name="location",
                            path="location",
                            aggregation="first",
                            transform=lambda v: str(v) if v else "",
                        ),
                        FieldComputation(
                            name="entity_name",
                            path="entity_name",
                            aggregation="first",
                            transform=lambda v: str(v) if v else "",
                        ),
                    ],
                )

                # Execute pipeline with streaming
                try:
                    pipeline_stream = pipeline.stream_analysis(config, opportunity_id=opp_id)
                    yield from mixin.stream_pipeline_events(pipeline_stream)

                    result = mixin._pipeline_result
                    if result:

                        def format_date(d):
                            if d and hasattr(d, "isoformat"):
                                return d.isoformat()
                            return d

                        opp_visits = []
                        for row in result.rows:
                            computed = getattr(row, "computed", {}) or {}
                            opp_visits.append(
                                {
                                    "visit_date": format_date(row.visit_date),
                                    "username": row.username,
                                    "entity_name": row.entity_name or computed.get("entity_name", ""),
                                    "status": row.status or computed.get("status", ""),
                                    "location": computed.get("location", ""),
                                    "opp_id": opp_id,
                                    "opp_name": opp_name,
                                    "country": country,
                                    "delivery_type": delivery_type,
                                }
                            )
                        all_visits.extend(opp_visits)

                        yield send_sse_event(f"Got {len(opp_visits)} visits for {opp_name}")
                except Exception as e:
                    logger.warning("Pipeline failed for opp %s: %s", opp_id, e)
                    yield send_sse_event(f"Skipping visits for {opp_name}: {e}")

                # Fetch completed_works CSV for payment data
                try:
                    yield send_sse_event(f"Fetching payments for {opp_name}...")
                    completed_works = da.fetch_completed_works(opp_id)

                    # Filter to approved rows only
                    approved_works = [w for w in completed_works if w.get("status") == "approved"]

                    opp_payments = []
                    for w in approved_works:
                        opp_payments.append(
                            {
                                "status_modified_date": w.get("status_modified_date", ""),
                                "payment_date": w.get("payment_date", ""),
                                "usd_flw": float(w.get("payment_accrued", 0) or 0),
                                "usd_org": float(w.get("org_pay", 0) or 0),
                                "opp_id": opp_id,
                                "opp_name": opp_name,
                                "country": country,
                                "delivery_type": delivery_type,
                            }
                        )
                    all_payments.extend(opp_payments)

                    yield send_sse_event(f"Got {len(opp_payments)} payments for {opp_name}")
                except Exception as e:
                    logger.warning("Completed works fetch failed for opp %s: %s", opp_id, e)
                    yield send_sse_event(f"Skipping payments for {opp_name}: {e}")

            # Send final SSE event with all data
            yield send_sse_event(
                f"Loaded {len(all_visits)} visits, {len(all_payments)} payments",
                data={"visits": all_visits, "payments": all_payments},
            )

        except Exception as e:
            logger.error("FundPipelineDataView error: %s", e, exc_info=True)
            yield send_sse_event("Error", error=str(e))
