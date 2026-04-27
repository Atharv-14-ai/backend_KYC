from django.db import transaction
from ..models import KYCSubmission

ALLOWED_TRANSITIONS = {
    "draft": ["submitted"],
    "submitted": ["under_review"],
    "under_review": ["approved", "rejected", "more_info_requested"],
    "more_info_requested": ["submitted"],
}

# Terminal states - no transitions allowed from these
TERMINAL_STATES = ["approved", "rejected"]


def transition_state(submission, new_state, reviewed_by=None, review_reason=""):
    """
    Transition a KYC submission to a new state with proper locking.
    
    Args:
        submission: KYCSubmission instance
        new_state: Target state
        reviewed_by: User instance of the reviewer (optional)
        review_reason: Reason for review action (optional)
    
    Returns:
        Updated KYCSubmission instance
    
    Raises:
        ValueError: If transition is not allowed
    """
    with transaction.atomic():
        # Lock the row to prevent race conditions
        locked_submission = KYCSubmission.objects.select_for_update().get(
            id=submission.id
        )
        current = locked_submission.state

        # Check if current state is terminal
        if current in TERMINAL_STATES:
            raise ValueError(
                f"Cannot transition from terminal state '{current}'"
            )

        # Validate transition
        if new_state not in ALLOWED_TRANSITIONS.get(current, []):
            raise ValueError(
                f"Illegal state transition: '{current}' → '{new_state}'. "
                f"Allowed transitions from '{current}': {ALLOWED_TRANSITIONS.get(current, [])}"
            )

        # Perform transition
        locked_submission.state = new_state
        
        # Update review info if reviewer is provided
        if reviewed_by:
            locked_submission.reviewed_by = reviewed_by
        
        if review_reason:
            locked_submission.review_reason = review_reason
            
        if new_state in ['approved', 'rejected']:
            from django.utils import timezone
            locked_submission.reviewed_at = timezone.now()
        
        locked_submission.save()
        return locked_submission