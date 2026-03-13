import json
import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import Http404
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.views.generic import DetailView, ListView, TemplateView, UpdateView
from django_tables2 import SingleTableView

from .data_access import SolicitationDataAccess
from .forms import SolicitationForm, SolicitationResponseForm, SolicitationReviewForm
from .models import DeliveryTypeDescriptionRecord, ResponseRecord, ReviewRecord, SolicitationRecord

# =============================================================================
# Permission Mixins (following established patterns)
# =============================================================================


class SolicitationAccessMixin(LoginRequiredMixin, UserPassesTestMixin):
    """
    Handles organization membership requirements for solicitation access.

    Following the OrganizationUserMixin pattern from opportunity/views.py.
    Users must have organization membership to access solicitation features.
    For labs environment, authenticated labs users have access.
    """

    def test_func(self):
        return self.request.user.is_authenticated


class SolicitationManagerMixin(LoginRequiredMixin, UserPassesTestMixin):
    """
    Handles program manager permissions for solicitation management.

    Following the ProgramManagerMixin pattern from program/views.py exactly.
    Users must be organization admins with program manager role.
    For labs environment, authenticated labs users have access.
    """

    def test_func(self):
        return self.request.user.is_authenticated


class SolicitationResponseViewAccessMixin(LoginRequiredMixin, UserPassesTestMixin):
    """
    Handles access permissions for viewing solicitation responses.
    For labs environment, authenticated labs users have access.
    """

    def test_func(self):
        return self.request.user.is_authenticated


# =============================================================================
# Data Access Helper Function
# =============================================================================
# Note: Following audit/tasks pattern - instantiate directly in views rather
# than using a mixin. This is simpler and more explicit.


# =============================================================================
# Custom Decorators (following established patterns from opportunity/program apps)
# =============================================================================
def solicitation_access_required(view_func):
    """
    Decorator equivalent of SolicitationAccessMixin for function-based views.
    Ensures user has organization membership (following established patterns).
    For labs environment, authenticated labs users have access.
    """
    from functools import wraps

    from django.core.exceptions import PermissionDenied

    @login_required
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            raise PermissionDenied("Authentication required")
        return view_func(request, *args, **kwargs)

    return wrapper


# =============================================================================
# Admin Overview Views - REPLACED BY UnifiedSolicitationDashboard
# =============================================================================

# AdminSolicitationOverview, ProgramSolicitationDashboard, and UserSolicitationDashboard
# have been consolidated into UnifiedSolicitationDashboard (see bottom of file)


# =============================================================================
# New LocalLabsRecord-based Views
# =============================================================================


class LabsHomeView(TemplateView):
    """
    Landing page for the solicitations lab explaining the project and providing navigation.
    """

    template_name = "solicitations/labs_home.html"


class ManageSolicitationsListView(ListView):
    """
    List view of solicitations created by the current user.
    """

    model = SolicitationRecord
    template_name = "solicitations/manage_list.html"
    context_object_name = "solicitations"
    paginate_by = 20

    def get_queryset(self):
        # Check if required context is present (organization or program)
        labs_context = getattr(self.request, "labs_context", {})
        if not labs_context.get("organization_id") and not labs_context.get("program_id"):
            # No organization or program selected, return empty list
            return []

        # Use data access layer to filter by user's username
        data_access = SolicitationDataAccess(request=self.request)
        return data_access.get_solicitations()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        labs_context = getattr(self.request, "labs_context", {})
        context["has_context"] = bool(labs_context.get("organization_id") or labs_context.get("program_id"))
        return context


class MyResponsesListView(ListView):
    """
    List view of responses created by the current user's organization.
    Requires program context selection.
    """

    model = ResponseRecord
    template_name = "solicitations/my_responses.html"
    context_object_name = "responses"
    paginate_by = 20

    def dispatch(self, request, *args, **kwargs):
        # Verify program context is selected
        labs_context = getattr(request, "labs_context", {})
        if not labs_context.get("program_id"):
            messages.error(request, "Please select a program context to view your responses.")
            return redirect("solicitations:home")

        self.data_access = SolicitationDataAccess(request=request)
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        # Get user's organization slug from labs_context
        labs_context = getattr(self.request, "labs_context", {})
        org_slug = labs_context.get("organization_slug")

        if org_slug:
            return self.data_access.get_responses_for_organization(organization_id=org_slug)
        return []


class SolicitationResponsesListView(SingleTableView):
    """
    List view of all responses to a specific solicitation (for solicitation authors).
    Uses django-tables2 for display.
    """

    model = ResponseRecord
    template_name = "solicitations/solicitation_responses.html"
    context_object_name = "responses"
    paginate_by = 20

    def dispatch(self, request, *args, **kwargs):
        # Verify program context is selected
        labs_context = getattr(request, "labs_context", {})
        if not labs_context.get("program_id"):
            messages.error(request, "Please select a program context to view responses.")
            return redirect("solicitations:manage_list")

        # Store data_access as instance variable for use in multiple methods
        self.data_access = SolicitationDataAccess(request=request)

        # Get the solicitation
        solicitation_pk = self.kwargs.get("solicitation_pk")
        self.solicitation = self.data_access.get_solicitation_by_id(solicitation_pk)

        if not self.solicitation:
            raise Http404("Solicitation not found")

        # Check if user has access to the solicitation's program
        # If solicitation has a program_id, verify user is in that program
        if self.solicitation.program_id:
            user_program_ids = []
            if hasattr(request.user, "programs"):
                user_program_ids = [prog.get("id") for prog in request.user.programs if prog.get("id")]

            if self.solicitation.program_id not in user_program_ids:
                raise Http404("You don't have access to this solicitation's program")

        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return self.data_access.get_responses_for_solicitation(solicitation_record=self.solicitation)

    def get_table_class(self):
        from .tables import ResponseRecordTable

        return ResponseRecordTable

    def get_table_kwargs(self):
        """Pass data_access to table for API queries."""
        kwargs = super().get_table_kwargs()
        kwargs["data_access"] = self.data_access
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["solicitation"] = self.solicitation
        return context


class SolicitationListView(LoginRequiredMixin, ListView):
    """
    Public list view of all publicly listed solicitations using LocalLabsRecords.
    Any authenticated user can view public solicitations.
    """

    model = SolicitationRecord
    template_name = "solicitations/solicitation_list.html"
    context_object_name = "solicitations"
    paginate_by = 12

    def get_queryset(self):
        try:
            data_access = SolicitationDataAccess(request=self.request)
            solicitation_type = self.kwargs.get("type")
            delivery_type_slug = self.request.GET.get("delivery_type")

            # Get public solicitations
            solicitations = data_access.get_public_solicitations(
                status="active",
                delivery_type_slug=delivery_type_slug,
            )

            # Filter by solicitation type if specified
            if solicitation_type and solicitation_type != "all":
                solicitations = [s for s in solicitations if s.solicitation_type == solicitation_type]

            return solicitations
        except Exception:
            # If API fails, return empty list
            return []

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["current_type"] = self.kwargs.get("type", "all")
        context["coming_soon"] = False
        context["delivery_type_filter"] = self.request.GET.get("delivery_type", "")

        # Count totals
        solicitations = context.get("solicitations", [])
        if isinstance(solicitations, list):
            context["total_active"] = len(solicitations)
            context["eoi_count"] = len([s for s in solicitations if s.solicitation_type == "eoi"])
            context["rfp_count"] = len([s for s in solicitations if s.solicitation_type == "rfp"])
        else:
            context["total_active"] = 0
            context["eoi_count"] = 0
            context["rfp_count"] = 0

        return context


class SolicitationDetailView(DetailView):
    """
    Public detail view of a specific solicitation using LocalLabsRecords.
    """

    model = SolicitationRecord
    template_name = "solicitations/solicitation_detail.html"
    context_object_name = "solicitation"

    def get_object(self, queryset=None):
        pk = self.kwargs.get("pk")

        # For public viewing, we need to bypass context filtering
        # Create data_access without context restrictions for ID lookup
        data_access = SolicitationDataAccess(request=self.request)
        solicitation = data_access.get_solicitation_by_id(pk)

        if not solicitation:
            raise Http404("Solicitation not found")

        # Allow viewing if:
        # 1. Solicitation is active and publicly listed (public access - no context needed)
        # 2. User is authenticated and is the owner (can view their own drafts/closed)
        is_public = solicitation.status == "active" and solicitation.is_publicly_listed
        is_owner = self.request.user.is_authenticated and solicitation.username == self.request.user.username

        if not (is_public or is_owner):
            raise Http404("Solicitation not found")

        return solicitation

    def get_context_data(self, **kwargs):
        data_access = SolicitationDataAccess(request=self.request)
        context = super().get_context_data(**kwargs)
        solicitation = self.object
        today = timezone.now().date()

        # Add deadline information
        if solicitation.application_deadline:
            from datetime import datetime

            if isinstance(solicitation.application_deadline, str):
                deadline = datetime.fromisoformat(solicitation.application_deadline).date()
            else:
                deadline = solicitation.application_deadline
            days_remaining = (deadline - today).days
            context["days_remaining"] = max(0, days_remaining)
            context["deadline_passed"] = days_remaining < 0

        # Add questions
        context["questions"] = solicitation.questions

        # Check for existing response if user is authenticated
        context["has_draft"] = False
        context["has_submitted_response"] = False

        if self.request.user.is_authenticated and self.request.user.memberships.exists():
            user_org = self.request.user.memberships.first().organization

            # Check for draft
            draft = data_access.get_response_for_solicitation(
                solicitation_record=solicitation, organization_id=user_org.slug, status="draft"
            )
            if draft:
                context["has_draft"] = True
                context["draft"] = draft

            # Check for submitted response
            submitted = data_access.get_response_for_solicitation(
                solicitation_record=solicitation, organization_id=user_org.slug, status="submitted"
            )
            if submitted:
                context["has_submitted_response"] = True
                context["submitted_response"] = submitted

        return context


class SolicitationResponseCreateOrUpdate(SolicitationAccessMixin, UpdateView):
    """
    Create or update a solicitation response using LocalLabsRecords.
    Simplified version that works directly with JSON data.
    """

    model = ResponseRecord
    form_class = SolicitationResponseForm
    template_name = "solicitations/response_form.html"

    def get_object(self, queryset=None):
        data_access = SolicitationDataAccess(request=self.request)
        response_pk = self.kwargs.get("pk")
        if response_pk:
            # Edit mode - explicit PK provided
            response = data_access.get_response_by_id(response_pk)
            if not response:
                raise Http404("Response not found")

            # Verify user can edit - Labs uses OAuth organizations (slugs)
            user_org_slugs = []
            if hasattr(self.request.user, "organizations"):
                user_org_slugs = [org.get("slug") for org in self.request.user.organizations if org.get("slug")]

            if response.organization_id not in user_org_slugs:
                raise Http404("You can only edit your organization's responses")

            return response

        # Check if an organization was specified in POST/GET to load existing response
        org_slug = self.request.POST.get("organization_id") or self.request.GET.get("org")
        if org_slug:
            solicitation_pk = self.kwargs.get("solicitation_pk")
            if solicitation_pk:
                # Try to find existing response for this org+solicitation
                solicitation = data_access.get_solicitation_by_id(solicitation_pk)
                if solicitation:
                    response = data_access.get_response_for_solicitation(
                        solicitation_record=solicitation, organization_id=org_slug, username=self.request.user.username
                    )
                    if response:
                        return response

        return None

    def dispatch(self, request, *args, **kwargs):
        # Verify organization context is selected for responding
        labs_context = getattr(request, "labs_context", {})
        if not labs_context.get("organization_id"):
            # Check if user has organizations from OAuth
            has_orgs = hasattr(request.user, "organizations") and request.user.organizations
            if not has_orgs:
                messages.error(request, "You need to be part of an organization to respond to solicitations.")
            else:
                messages.error(request, "Please select an organization context to respond to solicitations.")
            return redirect("solicitations:list")

        data_access = SolicitationDataAccess(request=request)

        # Get solicitation
        if self.kwargs.get("pk"):
            response = self.get_object()
            self.solicitation = data_access.get_solicitation_by_id(response.labs_record_id)
        else:
            solicitation_pk = self.kwargs.get("solicitation_pk")
            self.solicitation = data_access.get_solicitation_by_id(solicitation_pk)

        if not self.solicitation:
            raise Http404("Solicitation not found")

        # Check if user can respond
        if not self.solicitation.can_accept_responses():
            messages.warning(request, "This solicitation is no longer accepting responses")
            return redirect("solicitations:detail", pk=self.solicitation.pk)

        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        data_access = SolicitationDataAccess(request=self.request)
        kwargs = super().get_form_kwargs()
        kwargs["solicitation"] = self.solicitation
        kwargs["user"] = self.request.user
        kwargs["data_access"] = data_access
        # Pass instance if we have one (for editing existing responses)
        if self.object:
            kwargs["instance"] = self.object
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["solicitation"] = self.solicitation
        context["questions"] = self.solicitation.questions
        context["is_editing"] = self.kwargs.get("pk") is not None
        return context

    def form_valid(self, form):
        data_access = SolicitationDataAccess(request=self.request)

        # Get organization slug from form (user selected it)
        org_slug = form.cleaned_data.get("organization_id")

        is_draft = self.request.POST.get("action") == "save_draft"

        # Prepare response data (exclude organization_id from responses)
        response_answers = {k: v for k, v in form.cleaned_data.items() if k != "organization_id"}
        response_data = {
            "status": "draft" if is_draft else "submitted",
            "responses": response_answers,
            "attachments": [],  # TODO: Handle attachments
            "submitted_by": {
                "id": self.request.user.id,
                "username": self.request.user.username,
                "email": self.request.user.email,
                "full_name": self.request.user.get_full_name()
                if hasattr(self.request.user, "get_full_name")
                else f"{self.request.user.first_name} {self.request.user.last_name}".strip(),
            },
        }

        # Create or update response
        if self.object:
            # Update existing via API
            response = data_access.update_response(
                record_id=self.object.id, data_dict=response_data, organization_id=org_slug
            )
        else:
            # Create new
            response = data_access.create_response(
                solicitation_record=self.solicitation,
                organization_id=org_slug,  # Pass slug (not int ID)
                username=self.request.user.username,
                data_dict=response_data,
            )

        if is_draft:
            messages.success(self.request, "Draft saved successfully")
            return redirect("solicitations:response_edit", pk=response.id)
        else:
            messages.success(self.request, "Response submitted successfully")
            return redirect("solicitations:response_detail", pk=response.id)


class SolicitationResponseDetailView(SolicitationResponseViewAccessMixin, DetailView):
    """
    View response details using LocalLabsRecords.
    """

    model = ResponseRecord
    template_name = "solicitations/response_detail.html"
    context_object_name = "response"

    def get_object(self, queryset=None):
        data_access = SolicitationDataAccess(request=self.request)
        pk = self.kwargs.get("pk")
        response = data_access.get_response_by_id(pk)
        if not response:
            raise Http404("Response not found")
        return response

    def get_context_data(self, **kwargs):
        data_access = SolicitationDataAccess(request=self.request)
        context = super().get_context_data(**kwargs)
        response = self.object
        solicitation = data_access.get_solicitation_by_id(response.labs_record_id)
        context["solicitation"] = solicitation

        # Get reviews
        # Note: This would need a method in data_access to fetch reviews for a response
        context["reviews"] = []  # TODO: Implement get_reviews_for_response

        # Build questions_with_answers for template
        questions_with_answers = []
        if solicitation and solicitation.questions:
            response_answers = response.responses  # Dict from JSON data
            for question in solicitation.questions:
                q_id = question.get("id")
                q_text = question.get("question_text")
                q_required = question.get("is_required", False)
                answer = response_answers.get(f"question_{q_id}", "")

                questions_with_answers.append(
                    {
                        "question": {
                            "question_text": q_text,
                            "is_required": q_required,
                        },
                        "answer": answer,
                    }
                )

        context["questions_with_answers"] = questions_with_answers
        return context


class SolicitationResponseReviewCreateOrUpdate(SolicitationManagerMixin, UpdateView):
    """
    Create or update a review for a response using LocalLabsRecords.
    """

    model = ReviewRecord
    form_class = SolicitationReviewForm
    template_name = "solicitations/review_form.html"

    def get_object(self, queryset=None):
        data_access = SolicitationDataAccess(request=self.request)
        response_pk = self.kwargs.get("response_pk")
        response = data_access.get_response_by_id(response_pk)

        if not response:
            raise Http404("Response not found")

        # Check if review already exists for this user
        review = data_access.get_review_by_user(response_record=response, username=self.request.user.username)
        return review

    def dispatch(self, request, *args, **kwargs):
        data_access = SolicitationDataAccess(request=request)
        response_pk = self.kwargs.get("response_pk")
        self.response = data_access.get_response_by_id(response_pk)

        if not self.response:
            raise Http404("Response not found")

        self.solicitation = data_access.get_solicitation_by_id(self.response.labs_record_id)

        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["response"] = self.response
        context["solicitation"] = self.solicitation
        context["is_editing"] = self.object is not None

        # Add questions_with_answers for template
        questions_with_answers = []
        if self.solicitation and self.solicitation.questions:
            response_answers = self.response.responses
            for question in self.solicitation.questions:
                q_id = question.get("id")
                q_text = question.get("question_text")
                q_required = question.get("is_required", False)
                answer = response_answers.get(f"question_{q_id}", "")

                questions_with_answers.append(
                    {
                        "question": {
                            "question_text": q_text,
                            "is_required": q_required,
                        },
                        "answer": answer,
                    }
                )

        context["questions_with_answers"] = questions_with_answers
        return context

    def form_valid(self, form):
        data_access = SolicitationDataAccess(request=self.request)
        review_data = {
            "score": form.cleaned_data.get("score"),
            "recommendation": form.cleaned_data.get("recommendation"),
            "notes": form.cleaned_data.get("notes"),
            "tags": form.cleaned_data.get("tags", ""),
        }

        if self.object:
            # Update existing review via API
            data_access.update_review(record_id=self.object.id, data_dict=review_data)
            messages.success(self.request, "Review updated successfully")
        else:
            # Create new review
            data_access.create_review(
                response_record=self.response, username=self.request.user.username, data_dict=review_data
            )
            messages.success(self.request, "Review submitted successfully")

        return redirect("solicitations:response_detail", pk=self.response.id)


class SolicitationCreateOrUpdate(SolicitationManagerMixin, UpdateView):
    """
    Create or edit solicitations using LocalLabsRecords.
    Simplified version that stores data in JSON.
    """

    model = SolicitationRecord
    form_class = SolicitationForm
    template_name = "solicitations/solicitation_form.html"

    def get_object(self, queryset=None):
        pk = self.kwargs.get("pk")
        if pk:
            data_access = SolicitationDataAccess(request=self.request)
            # Edit mode - return existing solicitation
            solicitation = data_access.get_solicitation_by_id(pk)
            if not solicitation:
                raise Http404("Solicitation not found")
            # For labs: permissions already checked by SolicitationManagerMixin
            return solicitation
        return None

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()

        # Remove instance since we're using LocalLabsRecords, not Solicitation model
        kwargs.pop("instance", None)

        # Pass user for form setup (even though program field is removed)
        kwargs["user"] = self.request.user

        # Pass data_access for dynamic delivery type choices
        kwargs["data_access"] = SolicitationDataAccess(request=self.request)

        # For labs: populate form with JSON data for editing
        if self.object:
            # Populate form with JSON data for editing
            initial_data = self.object.data.copy()
            # Map delivery_type_slug to delivery_type field
            if "delivery_type_slug" in initial_data:
                initial_data["delivery_type"] = initial_data["delivery_type_slug"]
            kwargs["initial"] = initial_data

        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get program context from labs_context
        labs_context = getattr(self.request, "labs_context", {})
        program_id = labs_context.get("program_id")

        # For labs: get production program info from labs_context or OAuth data
        if program_id and hasattr(self.request.user, "programs"):
            # Find program in user's OAuth data
            for prog in self.request.user.programs:
                if prog.get("id") == program_id:
                    context["program"] = prog
                    break

        # Check if program context is required for this view
        context["has_program_context"] = bool(program_id)

        # Build question context inline (no helper needed)
        # JSON serialize for JavaScript consumption in template
        if self.object and hasattr(self.object, "questions"):
            # Edit mode - load existing questions from JSON
            context["existing_questions"] = json.dumps(self.object.questions or [])
        else:
            # Create mode - empty questions
            context["existing_questions"] = json.dumps([])

        # Add simple breadcrumb navigation for labs
        action_title = "Edit Solicitation" if self.object else "Create Solicitation"
        context["path"] = [
            {"title": "Solicitations Home", "url": reverse("solicitations:home")},
            {"title": "Manage Solicitations", "url": reverse("solicitations:manage_list")},
            {"title": action_title, "url": "#"},
        ]

        return context

    def form_valid(self, form):
        # Validate that program context is selected
        labs_context = getattr(self.request, "labs_context", {})
        program_pk = labs_context.get("program_id")

        if not program_pk:
            messages.error(
                self.request, "Please select a program context from the header before creating a solicitation."
            )
            return redirect("solicitations:manage_list")

        data_access = SolicitationDataAccess(request=self.request)
        is_edit = self.object is not None

        # Get program ID and name from labs_context
        program_name = None
        if hasattr(self.request.user, "programs") and program_pk:
            for prog in self.request.user.programs:
                if str(prog.get("id")) == str(program_pk):
                    program_name = prog.get("name")
                    break

        # For labs: we don't use organization_id for solicitation creation
        # (only for responses).

        # Parse questions data
        questions_data = self.request.POST.get("questions_data", "[]")
        try:
            questions = json.loads(questions_data) if questions_data else []
        except json.JSONDecodeError:
            questions = []

        # Assign IDs to questions that don't have them
        for question in questions:
            if not question.get("id"):
                question["id"] = str(uuid.uuid4())[:8]  # Use short UUID for readability

        # Prepare data for JSON storage
        solicitation_data = {
            "title": form.cleaned_data.get("title", ""),
            "description": form.cleaned_data.get("description", ""),
            "scope_of_work": form.cleaned_data.get("scope_of_work", ""),
            "solicitation_type": form.cleaned_data.get("solicitation_type", "eoi"),
            "status": form.cleaned_data.get("status", "draft"),
            "is_publicly_listed": form.cleaned_data.get("is_publicly_listed", True),
            "delivery_type_slug": form.cleaned_data.get("delivery_type", ""),
            "application_deadline": str(form.cleaned_data.get("application_deadline", "")),
            "expected_start_date": str(form.cleaned_data.get("expected_start_date", ""))
            if form.cleaned_data.get("expected_start_date")
            else "",
            "expected_end_date": str(form.cleaned_data.get("expected_end_date", ""))
            if form.cleaned_data.get("expected_end_date")
            else "",
            "estimated_scale": form.cleaned_data.get("estimated_scale", ""),
            "program_name": program_name,  # Store program name from OAuth data
            "questions": questions,
        }

        if is_edit:
            # Update existing record via API
            self.object = data_access.update_solicitation(
                record_id=self.object.id, data_dict=solicitation_data, program_id=program_pk
            )
            messages.success(
                self.request, f'Solicitation "{solicitation_data["title"]}" has been updated successfully.'
            )
        else:
            # Create new record with production IDs
            self.object = data_access.create_solicitation(
                program_id=program_pk,
                username=self.request.user.username,
                data_dict=solicitation_data,
            )
            messages.success(
                self.request, f'Solicitation "{solicitation_data["title"]}" has been created successfully.'
            )

        return redirect(self.get_success_url())

    def get_success_url(self):
        # Redirect to manage list after creating/editing solicitation
        return reverse("solicitations:manage_list")


# =============================================================================
# Delivery Type Views (Public)
# =============================================================================


class DeliveryTypesListView(LoginRequiredMixin, ListView):
    """
    Public list view of all delivery types with solicitation and program counts.
    Any authenticated user can view delivery types.

    URL Parameters:
        min_visits: Minimum visit threshold for counting programs (default: 0)
    """

    model = DeliveryTypeDescriptionRecord
    template_name = "solicitations/delivery_types_list.html"
    context_object_name = "delivery_types"

    def get_queryset(self):
        try:
            data_access = SolicitationDataAccess(request=self.request)
            return data_access.get_delivery_types(active_only=True)
        except Exception:
            return []

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get min_visits from URL params
        min_visits = int(self.request.GET.get("min_visits", 0))
        context["min_visits"] = min_visits

        try:
            data_access = SolicitationDataAccess(request=self.request)

            # Get solicitation counts per delivery type
            all_solicitations = data_access.get_public_solicitations(status="active")
            solicitation_counts = {}
            for sol in all_solicitations:
                slug = sol.delivery_type_slug
                if slug:
                    solicitation_counts[slug] = solicitation_counts.get(slug, 0) + 1

            # Get opportunity counts per delivery type
            opp_counts = data_access.get_opportunity_counts_by_delivery_type(min_visits=min_visits)

            # Add counts to each delivery type for template access
            delivery_types = context.get("delivery_types", [])
            total_active_opps = 0
            total_completed_opps = 0

            for dt in delivery_types:
                dt.solicitation_count = solicitation_counts.get(dt.slug, 0)

                # Add opportunity counts
                opp_data = opp_counts.get(dt.slug, {"active": 0, "completed": 0, "total": 0})
                dt.active_opportunities = opp_data["active"]
                dt.completed_opportunities = opp_data["completed"]
                dt.total_opportunities = opp_data["total"]

                total_active_opps += opp_data["active"]
                total_completed_opps += opp_data["completed"]

            context["total_solicitations"] = len(all_solicitations)
            context["total_active_opportunities"] = total_active_opps
            context["total_completed_opportunities"] = total_completed_opps

        except Exception:
            context["total_solicitations"] = 0
            context["total_active_opportunities"] = 0
            context["total_completed_opportunities"] = 0

        return context


class DeliveryTypeDetailView(LoginRequiredMixin, DetailView):
    """
    Public detail view of a delivery type with its solicitations and programs.
    Any authenticated user can view delivery type details.

    URL Parameters:
        min_visits: Minimum visit threshold for showing programs (default: 0)
        include_inactive: Include inactive/ended programs (default: false)
    """

    model = DeliveryTypeDescriptionRecord
    template_name = "solicitations/delivery_type_detail.html"
    context_object_name = "delivery_type"

    def get_object(self, queryset=None):
        slug = self.kwargs.get("slug")
        try:
            data_access = SolicitationDataAccess(request=self.request)
            delivery_type = data_access.get_delivery_type_by_slug(slug)
            if not delivery_type:
                raise Http404("Delivery type not found")
            return delivery_type
        except Http404:
            raise
        except Exception:
            raise Http404("Delivery type not found")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get URL params
        min_visits = int(self.request.GET.get("min_visits", 0))
        include_inactive = self.request.GET.get("include_inactive", "").lower() == "true"
        context["min_visits"] = min_visits
        context["include_inactive"] = include_inactive

        try:
            data_access = SolicitationDataAccess(request=self.request)

            # Get solicitations for this delivery type
            context["solicitations"] = data_access.get_solicitations_by_delivery_type(
                delivery_type_slug=self.object.slug,
                status="active",
            )

            # Get opportunities/programs for this delivery type
            opportunities = data_access.get_opportunities_by_delivery_type(
                delivery_type_slug=self.object.slug,
                min_visits=min_visits,
                include_inactive=include_inactive,
            )

            # Group opportunities by organization for summary
            org_summaries = {}
            for opp in opportunities:
                org_slug = opp.get("organization", "unknown")
                if org_slug not in org_summaries:
                    org_summaries[org_slug] = {
                        "organization": org_slug,
                        "opportunities": [],
                        "total_visits": 0,
                        "active_count": 0,
                        "completed_count": 0,
                    }

                org_summaries[org_slug]["opportunities"].append(opp)
                org_summaries[org_slug]["total_visits"] += opp.get("visit_count", 0)
                if opp.get("is_active", False):
                    org_summaries[org_slug]["active_count"] += 1
                else:
                    org_summaries[org_slug]["completed_count"] += 1

            context["opportunities"] = opportunities
            context["org_summaries"] = list(org_summaries.values())
            context["total_opportunities"] = len(opportunities)
            context["total_visits"] = sum(opp.get("visit_count", 0) for opp in opportunities)

        except Exception:
            context["solicitations"] = []
            context["opportunities"] = []
            context["org_summaries"] = []
            context["total_opportunities"] = 0
            context["total_visits"] = 0

        return context


class OpportunityDetailView(LoginRequiredMixin, TemplateView):
    """
    Detail view for a single opportunity.
    Shows all available information about the opportunity in a nice layout.
    """

    template_name = "solicitations/opportunity_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        opp_id = self.kwargs.get("opp_id")

        try:
            data_access = SolicitationDataAccess(request=self.request)
            opportunity = data_access.get_opportunity_by_id(opp_id)

            if not opportunity:
                raise Http404("Opportunity not found")

            context["opportunity"] = opportunity

            # Get delivery type info for breadcrumb
            delivery_type_slug = opportunity.get("delivery_type_slug")
            if delivery_type_slug:
                delivery_type = data_access.get_delivery_type_by_slug(delivery_type_slug)
                context["delivery_type"] = delivery_type

        except Http404:
            raise
        except Exception:
            raise Http404("Opportunity not found")

        return context
