from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from rest_framework.parsers import MultiPartParser, FormParser
from django.shortcuts import get_object_or_404
from django.utils.timezone import now
from django.db.models import Avg, Count, F, ExpressionWrapper, DurationField, Q
from datetime import timedelta

from .models import KYCSubmission
from .services.serializers import KYCSubmissionSerializer, DocumentSerializer
from .services.state_machine import transition_state
from .services.notifications import create_notification
from .utils import get_user_from_header, require_role, error_response

import re
from django.contrib.auth import get_user_model, authenticate
from rest_framework import status

User = get_user_model()


def validate_kyc_ready_for_submission(submission):
    personal = submission.personal_details or {}
    business = submission.business_details or {}
    missing = []

    for key in ['name', 'email', 'phone']:
        if not str(personal.get(key, '')).strip():
            missing.append(f'personal_details.{key}')

    for key in ['business_name', 'type', 'monthly_volume']:
        if not str(business.get(key, '')).strip():
            missing.append(f'business_details.{key}')

    return missing


# =============================
# MERCHANT ENDPOINTS
# =============================

class ListKYC(APIView):
    """List all KYC submissions for the authenticated merchant."""

    def get(self, request):
        try:
            user = get_user_from_header(request)
            require_role(user, "merchant")

            submissions = KYCSubmission.objects.filter(merchant=user).order_by('-created_at')
            serializer = KYCSubmissionSerializer(submissions, many=True)
            return Response(serializer.data)

        except (AuthenticationFailed, PermissionDenied) as e:
            return error_response(str(e), code="AUTH_ERROR", status_code=401)


class CreateKYC(APIView):
    def post(self, request):
        try:
            user = get_user_from_header(request)
            require_role(user, "merchant")

            # If request.data is empty or has empty objects, create with defaults
            data = request.data if request.data else {}
            data.setdefault('personal_details', {'name': '', 'email': '', 'phone': ''})
            data.setdefault('business_details', {'business_name': '', 'type': '', 'monthly_volume': ''})

            serializer = KYCSubmissionSerializer(data=data)
            if serializer.is_valid():
                serializer.save(merchant=user)
                return Response(serializer.data, status=201)

            return error_response("Validation failed", code="VALIDATION_ERROR", details=serializer.errors)

        except (AuthenticationFailed, PermissionDenied) as e:
            return error_response(str(e), code="AUTH_ERROR", status_code=401)


class GetKYC(APIView):
    """Get a merchant's KYC submission."""
    
    def get(self, request, pk):
        try:
            user = get_user_from_header(request)
            require_role(user, "merchant")

            submission = get_object_or_404(KYCSubmission, id=pk)

            # Authorization check
            if submission.merchant != user:
                return error_response(
                    "Access denied", 
                    code="FORBIDDEN", 
                    status_code=403
                )

            return Response(KYCSubmissionSerializer(submission).data)

        except (AuthenticationFailed, PermissionDenied) as e:
            return error_response(str(e), code="AUTH_ERROR", status_code=401)


class UpdateKYC(APIView):
    def put(self, request, pk):
        try:
            user = get_user_from_header(request)
            require_role(user, "merchant")

            submission = get_object_or_404(KYCSubmission, id=pk)

            if submission.merchant != user:
                return error_response("Access denied", code="FORBIDDEN", status_code=403)

            if submission.state != "draft":
                return error_response(
                    f"Only submissions in 'draft' state can be edited. Current state: {submission.state}",
                    code="INVALID_STATE"
                )

            # Use partial=True to allow partial updates
            serializer = KYCSubmissionSerializer(submission, data=request.data, partial=True)
            
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)

            return error_response("Validation failed", code="VALIDATION_ERROR", details=serializer.errors)

        except (AuthenticationFailed, PermissionDenied) as e:
            return error_response(str(e), code="AUTH_ERROR", status_code=401)


class UploadDocument(APIView):
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, pk):
        try:
            user = get_user_from_header(request)
            require_role(user, "merchant")

            submission = get_object_or_404(KYCSubmission, id=pk)

            if submission.merchant != user:
                return error_response("Access denied", code="FORBIDDEN", status_code=403)

            if submission.state not in ['draft', 'more_info_requested']:
                return error_response(
                    f"Cannot upload documents in '{submission.state}' state. Allowed states: draft, more_info_requested",
                    code="INVALID_STATE"
                )

            # Make sure we're handling the file correctly
            serializer = DocumentSerializer(data=request.data, context={'submission': submission})
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=201)

            return error_response("Validation failed", code="VALIDATION_ERROR", details=serializer.errors)

        except (AuthenticationFailed, PermissionDenied) as e:
            return error_response(str(e), code="AUTH_ERROR", status_code=401)


class SubmitKYC(APIView):
    """Submit a KYC submission for review."""
    
    def post(self, request, pk):
        try:
            user = get_user_from_header(request)
            require_role(user, "merchant")

            submission = get_object_or_404(KYCSubmission, id=pk)

            # Authorization check
            if submission.merchant != user:
                return error_response(
                    "Access denied", 
                    code="FORBIDDEN", 
                    status_code=403
                )

            if submission.state not in ['draft', 'more_info_requested']:
                return error_response(
                    f"Submission must be in draft or more_info_requested state to submit. Current state: {submission.state}",
                    code="INVALID_STATE"
                )

            missing_fields = validate_kyc_ready_for_submission(submission)
            if missing_fields:
                return error_response(
                    "Complete all required fields before submission",
                    code="INCOMPLETE_KYC",
                    details={"missing_fields": missing_fields}
                )

            if submission.documents.count() == 0:
                return error_response(
                    "At least one document is required before submission",
                    code="MISSING_DOCUMENTS"
                )

            # Perform state transition
            updated_submission = transition_state(submission, "submitted")

            # Log notification
            create_notification(
                updated_submission.merchant,
                "KYC_SUBMITTED",
                {
                    "submission_id": updated_submission.id,
                    "submitted_at": str(now())
                }
            )

            return Response({
                "message": "KYC submitted successfully",
                "submission": KYCSubmissionSerializer(updated_submission).data
            })

        except ValueError as e:
            return error_response(
                str(e), 
                code="INVALID_TRANSITION"
            )
        except (AuthenticationFailed, PermissionDenied) as e:
            return error_response(str(e), code="AUTH_ERROR", status_code=401)


# =============================
# REVIEWER ENDPOINTS
# =============================

class ReviewerQueue(APIView):
    """Get the reviewer queue with submissions pending review."""
    
    def get(self, request):
        try:
            user = get_user_from_header(request)
            require_role(user, "reviewer")

            # Get submissions in review queue
            submissions = KYCSubmission.objects.filter(
                state__in=["submitted", "under_review"]
            ).select_related('merchant').annotate(
                document_count=Count('documents')
            ).order_by("created_at")

            data = []
            for s in submissions:
                # Calculate time in queue
                time_in_queue = now() - s.created_at
                
                data.append({
                    "id": s.id,
                    "merchant_id": s.merchant.id,
                    "merchant_name": s.merchant.username,
                    "state": s.state,
                    "created_at": s.created_at,
                    "updated_at": s.updated_at,
                    "time_in_queue_hours": round(time_in_queue.total_seconds() / 3600, 2),
                    "at_risk": time_in_queue > timedelta(hours=24),
                    "document_count": s.document_count
                })

            return Response({
                "count": len(data),
                "results": data
            })

        except (AuthenticationFailed, PermissionDenied) as e:
            return error_response(str(e), code="AUTH_ERROR", status_code=401)


class ReviewDetail(APIView):
    """Get detailed view of a submission for review."""
    
    def get(self, request, pk):
        try:
            user = get_user_from_header(request)
            require_role(user, "reviewer")

            submission = get_object_or_404(
                KYCSubmission.objects.select_related('merchant').prefetch_related('documents'),
                id=pk
            )
            
            serializer_data = KYCSubmissionSerializer(submission).data
            
            # Add review-specific information
            time_in_queue = now() - submission.created_at
            serializer_data['time_in_queue_hours'] = round(
                time_in_queue.total_seconds() / 3600, 2
            )
            serializer_data['at_risk'] = time_in_queue > timedelta(hours=24)
            
            return Response(serializer_data)

        except (AuthenticationFailed, PermissionDenied) as e:
            return error_response(str(e), code="AUTH_ERROR", status_code=401)


class ReviewerMetrics(APIView):
    """Get reviewer dashboard metrics."""
    
    def get(self, request):
        try:
            user = get_user_from_header(request)
            require_role(user, "reviewer")

            last_7_days = now() - timedelta(days=7)

            # Get queue counts
            queue_count = KYCSubmission.objects.filter(
                state__in=["submitted", "under_review"]
            ).count()
            
            at_risk_count = KYCSubmission.objects.filter(
                state__in=["submitted", "under_review"],
                created_at__lt=now() - timedelta(hours=24)
            ).count()

            # Get 7-day metrics based on completed reviews
            recent_processed = KYCSubmission.objects.filter(
                reviewed_at__gte=last_7_days
            )
            
            total_recent = recent_processed.count()
            approved_recent = recent_processed.filter(state="approved").count()
            
            approval_rate = (approved_recent / total_recent * 100) if total_recent > 0 else 0

            # Calculate average processing time for completed reviews
            avg_time = recent_processed.filter(
                state__in=["approved", "rejected"]
            ).annotate(
                processing_time=ExpressionWrapper(
                    F("reviewed_at") - F("created_at"),
                    output_field=DurationField()
                )
            ).aggregate(avg=Avg("processing_time"))["avg"]

            # Get state-wise breakdown
            state_counts = KYCSubmission.objects.values('state').annotate(
                count=Count('id')
            )

            return Response({
                "queue_metrics": {
                    "in_queue": queue_count,
                    "at_risk": at_risk_count
                },
                "seven_day_metrics": {
                    "total_submissions": total_recent,
                    "approved": approved_recent,
                    "approval_rate": round(approval_rate, 2),
                    "avg_processing_time": str(avg_time) if avg_time else "N/A"
                },
                "state_breakdown": {
                    item['state']: item['count'] 
                    for item in state_counts
                }
            })

        except (AuthenticationFailed, PermissionDenied) as e:
            return error_response(str(e), code="AUTH_ERROR", status_code=401)


class StartReview(APIView):
    """Start reviewing a submission."""
    
    def post(self, request, pk):
        try:
            user = get_user_from_header(request)
            require_role(user, "reviewer")

            submission = get_object_or_404(KYCSubmission, id=pk)
            
            updated_submission = transition_state(submission, "under_review")

            return Response({
                "message": "Review started",
                "submission": KYCSubmissionSerializer(updated_submission).data
            })

        except ValueError as e:
            return error_response(str(e), code="INVALID_TRANSITION")
        except (AuthenticationFailed, PermissionDenied) as e:
            return error_response(str(e), code="AUTH_ERROR", status_code=401)


class ApproveKYC(APIView):
    def post(self, request, pk):
        try:
            user = get_user_from_header(request)
            require_role(user, "reviewer")

            submission = get_object_or_404(KYCSubmission, id=pk)

            # Illegal transition check first (if already terminal)
            if submission.state in ["approved", "rejected"]:
                return error_response(
                    f"Illegal state transition: submission is already {submission.state}",
                    code="INVALID_TRANSITION"
                )

            if submission.documents.count() == 0:
                return error_response(
                    "Cannot approve submission without documents",
                    code="MISSING_DOCUMENTS"
                )

            updated_submission = transition_state(
                submission,
                "approved",
                reviewed_by=user
            )

            create_notification(
                updated_submission.merchant,
                "KYC_APPROVED",
                {
                    "submission_id": updated_submission.id,
                    "approved_by": user.username,
                    "approved_at": str(now())
                }
            )

            return Response({
                "message": "KYC approved successfully",
                "submission": KYCSubmissionSerializer(updated_submission).data
            })

        except ValueError as e:
            return error_response(str(e), code="INVALID_TRANSITION")
        except (AuthenticationFailed, PermissionDenied) as e:
            return error_response(str(e), code="AUTH_ERROR", status_code=401)

class RejectKYC(APIView):
    """Reject a KYC submission."""
    
    def post(self, request, pk):
        try:
            user = get_user_from_header(request)
            require_role(user, "reviewer")

            submission = get_object_or_404(KYCSubmission, id=pk)
            reason = request.data.get("reason", "").strip()

            # Validate rejection reason
            if not reason:
                return error_response(
                    "Rejection reason is required",
                    code="MISSING_REASON"
                )

            if len(reason) < 10:
                return error_response(
                    "Rejection reason must be at least 10 characters",
                    code="INVALID_REASON"
                )

            # Perform transition
            updated_submission = transition_state(
                submission, 
                "rejected",
                reviewed_by=user,
                review_reason=reason
            )

            # Log notification
            create_notification(
                updated_submission.merchant,
                "KYC_REJECTED",
                {
                    "submission_id": updated_submission.id,
                    "rejected_by": user.username,
                    "rejected_at": str(now()),
                    "reason": reason
                }
            )

            return Response({
                "message": "KYC rejected",
                "submission": KYCSubmissionSerializer(updated_submission).data
            })

        except ValueError as e:
            return error_response(str(e), code="INVALID_TRANSITION")
        except (AuthenticationFailed, PermissionDenied) as e:
            return error_response(str(e), code="AUTH_ERROR", status_code=401)


class RequestMoreInfo(APIView):
    """Request more information from the merchant."""
    
    def post(self, request, pk):
        try:
            user = get_user_from_header(request)
            require_role(user, "reviewer")

            submission = get_object_or_404(KYCSubmission, id=pk)
            reason = request.data.get("reason", "").strip()

            # Validate reason
            if not reason:
                return error_response(
                    "Reason for requesting more information is required",
                    code="MISSING_REASON"
                )

            # Perform transition
            updated_submission = transition_state(
                submission, 
                "more_info_requested",
                reviewed_by=user,
                review_reason=reason
            )

            # Log notification
            create_notification(
                updated_submission.merchant,
                "MORE_INFO_REQUESTED",
                {
                    "submission_id": updated_submission.id,
                    "requested_by": user.username,
                    "requested_at": str(now()),
                    "reason": reason
                }
            )

            return Response({
                "message": "More information requested",
                "submission": KYCSubmissionSerializer(updated_submission).data
            })

        except ValueError as e:
            return error_response(str(e), code="INVALID_TRANSITION")
        except (AuthenticationFailed, PermissionDenied) as e:
            return error_response(str(e), code="AUTH_ERROR", status_code=401)
        
class CreateReviewerView(APIView):
    """Admin-only endpoint to create reviewer accounts"""
    
    def post(self, request):
        try:
            user = get_user_from_header(request)
            
            # Only existing reviewers or admins can create new reviewers
            if user.role not in ['reviewer', 'admin']:
                return error_response(
                    "Only reviewers can create reviewer accounts",
                    code="FORBIDDEN",
                    status_code=403
                )
            
            username = request.data.get('username', '').strip()
            email = request.data.get('email', '').strip()
            password = request.data.get('password', '').strip()
            
            errors = {}
            
            if not username:
                errors['username'] = 'Username is required'
            elif User.objects.filter(username=username).exists():
                errors['username'] = 'Username already taken'
            
            if not email:
                errors['email'] = 'Email is required'
            elif User.objects.filter(email=email).exists():
                errors['email'] = 'Email already registered'
            
            if not password or len(password) < 6:
                errors['password'] = 'Password must be at least 6 characters'
            
            if errors:
                return error_response(
                    "Validation failed",
                    code="VALIDATION_ERROR",
                    details=errors,
                    status_code=400
                )
            
            # Create reviewer account
            reviewer = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                role='reviewer'
            )
            
            return Response({
                "message": "Reviewer account created",
                "user": {
                    "id": reviewer.id,
                    "username": reviewer.username,
                    "email": reviewer.email,
                    "role": reviewer.role
                }
            }, status=status.HTTP_201_CREATED)
            
        except AuthenticationFailed as e:
            return error_response(str(e), code="AUTH_ERROR", status_code=401)
        except Exception as e:
            return error_response(str(e), code="SERVER_ERROR", status_code=500)

class SignupView(APIView):
    def post(self, request):
        try:
            username = request.data.get('username', '').strip()
            email = request.data.get('email', '').strip()
            password = request.data.get('password', '').strip()
            
            # Role is always 'merchant' for public signup
            role = 'merchant'
            
            # Validation
            errors = {}
            
            if not username:
                errors['username'] = 'Username is required'
            elif len(username) < 3:
                errors['username'] = 'Username must be at least 3 characters'
            elif User.objects.filter(username=username).exists():
                errors['username'] = 'Username already taken'
            
            if not email:
                errors['email'] = 'Email is required'
            elif not re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', email):
                errors['email'] = 'Invalid email format'
            elif User.objects.filter(email=email).exists():
                errors['email'] = 'Email already registered'
            
            if not password:
                errors['password'] = 'Password is required'
            elif len(password) < 6:
                errors['password'] = 'Password must be at least 6 characters'
            
            if errors:
                return error_response(
                    "Validation failed",
                    code="VALIDATION_ERROR",
                    details=errors,
                    status_code=400
                )
            
            # Create user with merchant role only
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                role=role
            )
            
            return Response({
                "message": "Account created successfully",
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "role": user.role
                }
            }, status=201)
            
        except Exception as e:
            # Print the actual error to console for debugging
            import traceback
            traceback.print_exc()
            return error_response(
                f"Server error: {str(e)}",
                code="SERVER_ERROR",
                status_code=500
            )


class LoginView(APIView):
    def post(self, request):
        try:
            username = request.data.get('username', '').strip()
            password = request.data.get('password', '').strip()

            if not username:
                return error_response(
                    "Username is required",
                    code="VALIDATION_ERROR",
                    details={"username": "Username is required"},
                    status_code=400
                )

            if not password:
                return error_response(
                    "Password is required",
                    code="VALIDATION_ERROR",
                    details={"password": "Password is required"},
                    status_code=400
                )

            user = authenticate(request, username=username, password=password)
            if user is None or not user.is_active:
                return error_response(
                    "Invalid username or password",
                    code="AUTH_FAILED",
                    status_code=401
                )

            return Response({
                "message": "Login successful",
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "role": user.role
                }
            })

        except Exception as e:
            import traceback
            traceback.print_exc()
            return error_response(
                f"Server error: {str(e)}",
                code="SERVER_ERROR",
                status_code=500
            )