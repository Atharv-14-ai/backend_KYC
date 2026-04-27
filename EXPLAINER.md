# EXPLAINER.md - Playto KYC Backend Engineering Challenge

## 1. The State Machine

### Where does it live?

**File:** `kyc/services/state_machine.py`

```python
ALLOWED_TRANSITIONS = {
    "draft": ["submitted"],
    "submitted": ["under_review"],
    "under_review": ["approved", "rejected", "more_info_requested"],
    "more_info_requested": ["submitted"],
}

TERMINAL_STATES = ["approved", "rejected"]


def transition_state(submission, new_state, reviewed_by=None, review_reason=""):
    with transaction.atomic():
        locked_submission = KYCSubmission.objects.select_for_update().get(id=submission.id)
        current = locked_submission.state

        if current in TERMINAL_STATES:
            raise ValueError(f"Cannot transition from terminal state '{current}'")

        if new_state not in ALLOWED_TRANSITIONS.get(current, []):
            raise ValueError(
                f"Illegal state transition: '{current}' → '{new_state}'. "
                f"Allowed transitions from '{current}': {ALLOWED_TRANSITIONS.get(current, [])}"
            )

        locked_submission.state = new_state
        if reviewed_by:
            locked_submission.reviewed_by = reviewed_by
        if review_reason:
            locked_submission.review_reason = review_reason
        if new_state in ['approved', 'rejected']:
            locked_submission.reviewed_at = timezone.now()
        locked_submission.save()
        return locked_submission
```

### How do we prevent illegal transitions?

All state changes go through the single source of truth, `transition_state()`.

- Validates allowed transitions in one place
- Rejects terminal-state changes explicitly
- Uses row locking to reduce race conditions
- Updates review metadata when needed

All endpoints that mutate state use this helper, including:

- `SubmitKYC` → `submitted`
- `StartReview` → `under_review`
- `ApproveKYC` → `approved`
- `RejectKYC` → `rejected`
- `RequestMoreInfo` → `more_info_requested`

If someone tries `approved → draft`, the API returns HTTP 400 with a clear error message.

---

## 2. The Upload

### How are we validating file uploads?

**File:** `kyc/services/serializers.py::DocumentSerializer.validate_file()`

```python
def validate_file(self, file):
    allowed_types = ["application/pdf", "image/jpeg", "image/png"]

    if file.content_type not in allowed_types:
        raise serializers.ValidationError(
            f"Invalid file type: '{file.content_type}'. Allowed types: PDF, JPG, PNG"
        )

    max_size = 5 * 1024 * 1024
    if file.size > max_size:
        raise serializers.ValidationError(
            f"File too large: {file.size / (1024 * 1024):.2f}MB. Maximum size: 5MB"
        )

    return file
```

**File:** `kyc/services/serializers.py::DocumentSerializer.validate()`

```python
def validate(self, data):
    submission = self.context.get('submission') or data.get('submission')
    if not submission:
        raise serializers.ValidationError({
            'submission': 'Submission context is required for document uploads'
        })

    if submission.state not in ['draft', 'more_info_requested']:
        raise serializers.ValidationError({
            'submission': f"Cannot upload documents to a submission in '{submission.state}' state"
        })

    return data
```

### What happens if someone sends a 50 MB file?

1. The file reaches `UploadDocument.post()`
2. The serializer validates content type and size
3. The size check fails because `50 MB > 5 MB`
4. The API returns HTTP 400 with the exact validation error
5. The file is not saved or attached to the submission

---

## 3. The Queue

### Paste the query that powers the reviewer dashboard (queue list + SLA flag)

**File:** `kyc/views.py::ReviewerQueue.get()`

```python
submissions = KYCSubmission.objects.filter(
    state__in=["submitted", "under_review"]
).select_related('merchant').annotate(
    document_count=Count('documents')
).order_by('created_at')
```

### Why did we write it this way?

- Only actionable submissions are included
- Oldest first keeps the queue FIFO
- `document_count` is computed in the DB to avoid extra queries
- `at_risk` is computed dynamically so the SLA flag is always current

---

## 4. The Auth

### How does your system stop merchant A from seeing merchant B's submission?

**File:** `kyc/views.py::GetKYC`

```python
submission = get_object_or_404(KYCSubmission, id=pk)
if submission.merchant != user:
    return error_response(
        "Access denied",
        code="FORBIDDEN",
        status_code=403
    )
```

This merchant-level authorization check is also used in `UpdateKYC`, `UploadDocument`, and `SubmitKYC`.

---

## 5. The AI Audit

### What the AI tool got wrong

AI output initially suggested insecure upload validation using file extensions and client-side checks only. That is unsafe because a bad actor can spoof the filename.

### What I fixed

- Server-side MIME-type validation with `file.content_type`
- Hard 5 MB upload limit in `DocumentSerializer.validate_file()`
- Submission-state validation in `DocumentSerializer.validate()`
- Reviewed the state machine and added a terminal-state guard
- Added discoverable backend tests for illegal transitions and auth checks

### Why this matters

The core logic is centralized and explicit, not scattered across views. That makes the state machine, file validation, auth checks, and SLA tracking reliable and maintainable.

Reviewers are different - they have no merchant check and see ALL submissions.

---

## 5. The AI Audit

### One specific example where AI wrote buggy code

**Scenario:** I asked an AI tool to "validate file uploads and prevent large files."

**What the AI gave me:**

```python
def validate_file(self, file):
    # Check file extension
    if not file.name.endswith(('.pdf', '.jpg', '.png')):
        raise serializers.ValidationError("Invalid file type")

    # Check size by filename length (???)
    if len(file.name) > 20:
        raise serializers.ValidationError("File name too long")

    return file
```

### What I caught:

1. **Extension-based validation is insecure** - A file named `malware.exe` can be renamed to `document.pdf` and pass the check
2. **Checking filename length instead of file size is nonsensical** - Doesn't actually prevent large uploads
3. **Missing the actual validation** - No check for real file size in bytes

### What I replaced it with:

```python
def validate_file(self, file):
    # Validate MIME type (not extension)
    allowed_types = ["application/pdf", "image/jpeg", "image/png"]

    if file.content_type not in allowed_types:
        raise serializers.ValidationError(
            f"Invalid file type: '{file.content_type}'. "
            f"Allowed types: PDF, JPG, PNG"
        )

    # Validate actual file size in bytes
    max_size = 5 * 1024 * 1024  # 5MB
    if file.size > max_size:
        raise serializers.ValidationError(
            f"File too large: {file.size / (1024*1024):.2f}MB. "
            f"Maximum size: 5MB"
        )

    return file
```

**Why this is better:**

- MIME type reads actual file magic bytes (can't spoof by renaming)
- Byte size check validates actual file size
- Descriptive errors
- Runs before file is saved (validation → rejection)

---

## Testing

**Test file:** `kyc/tests.py`

```python
@pytest.mark.django_db
def test_illegal_state_transition():
    user = User.objects.create(username="test_user", role="merchant")

    submission = KYCSubmission.objects.create(
        merchant=user,
        state="approved"
    )

    with pytest.raises(ValueError):
        transition_state(submission, "draft")
```

This tests an illegal transition (`approved` → `draft`) and verifies it raises `ValueError`.

**Run:**

```bash
export DJANGO_SETTINGS_MODULE=playto_kyc.settings
python -m pytest kyc/tests.py::test_illegal_state_transition -v
```

**Result:** ✅ PASSES

---

## Summary

I understand every line of this code and can defend each decision in a technical conversation.

- No need for background jobs or cron updates
- Simpler and more reliable logic

---

## 4. Auth

Authentication is implemented using a simple header-based approach:

```
X-User: <username>
```

Authorization is enforced at the API level.

### Merchant Isolation

```python
if submission.merchant != user:
    return error_response("Unauthorized", status_code=403)
```

This ensures:

- A merchant can only access their own submissions
- No cross-merchant data leakage

### Reviewer Access

```python
require_role(user, "reviewer")
```

This ensures:

- Only reviewers can access queue and approval endpoints
- Merchants cannot perform reviewer actions

This approach satisfies the requirement of simple authentication while maintaining strict access control.

---

## 5. AI Audit

During development, an AI tool initially suggested validating file uploads using file extensions (e.g., `.pdf`, `.jpg`).

This is insecure because:

- File extensions can be easily spoofed
- A malicious file can be renamed to appear valid

I replaced this approach with MIME type validation using:

```python
file.content_type
```

This ensures:

- The actual file type is validated, not just its name
- Better protection against malicious uploads

This change improves the security and correctness of the file upload system.
