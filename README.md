# Playto KYC Backend

A Django REST Framework-based Know Your Customer (KYC) verification system with merchant submissions, state machine workflow, and reviewer dashboard.

## Features

- **Merchant Portal**: Create, edit, and submit KYC applications
- **Document Upload**: Secure file uploads with validation
- **State Machine**: Enforced workflow with legal state transitions
- **Reviewer Dashboard**: Queue management, metrics, and submission approval
- **Notifications**: Event logging for all state changes
- **Role-Based Access**: Merchant and Reviewer roles with strict isolation

---

## Quick Start

### Prerequisites

- Python 3.9+
- pip
- Git

### Installation

1. **Clone the repository** (if applicable):

   ```bash
   cd playto_kyc
   ```

2. **Create virtual environment**:

   ```bash
   python -m venv venv
   ```

3. **Activate virtual environment**:

   ```bash
   # Windows
   venv\Scripts\activate

   # macOS/Linux
   source venv/bin/activate
   ```

4. **Install dependencies**:

   ```bash
   pip install -r requirements.txt
   ```

5. **Run migrations**:

   ```bash
   python manage.py migrate
   ```

6. **Seed test data** (optional):

   ```bash
   python manage.py seed_data
   ```

7. **Start development server**:
   ```bash
   python manage.py runserver
   ```

Server runs at: **http://localhost:8000**

---

## API Overview

All endpoints require the `X-User` header with a username.

### Base URL

```
http://localhost:8000/api/v1
```

### Authentication

All requests must include:

```
X-User: <username>
```

Example:

```bash
curl http://localhost:8000/api/v1/kyc/ \
  -H "X-User: merchant1"
```

---

## Merchant Endpoints

### Create KYC Submission

```http
POST /kyc/
```

**Headers:**

```
X-User: merchant1
Content-Type: application/json
```

**Body:**

```json
{
  "personal_details": {
    "name": "John Doe",
    "email": "john@example.com",
    "phone": "+1234567890"
  },
  "business_details": {
    "business_name": "ABC Corp",
    "type": "LLC",
    "monthly_volume": 50000
  }
}
```

**Response:** `201 Created`

```json
{
  "id": 1,
  "merchant": 1,
  "merchant_name": "merchant1",
  "state": "draft",
  "personal_details": {...},
  "business_details": {...},
  "documents": [],
  "created_at": "2026-04-26T10:00:00Z"
}
```

---

### Get KYC Submission

```http
GET /kyc/{id}/
```

**Headers:**

```
X-User: merchant1
```

**Response:** `200 OK` - Full submission details

---

### Update KYC (Draft Only)

```http
PUT /kyc/{id}/update/
```

**Headers:**

```
X-User: merchant1
Content-Type: application/json
```

**Body:** Same structure as Create (any fields can be updated)

**Note:** Only drafts can be edited. Returns error if not in draft state.

---

### Upload Document

```http
POST /kyc/{id}/upload/
```

**Headers:**

```
X-User: merchant1
Content-Type: multipart/form-data
```

**Form Data:**

- `file` - PDF, JPG, or PNG file (max 5MB)
- `doc_type` - One of: `pan`, `aadhaar`, `bank`

**Response:** `201 Created`

```json
{
  "id": 1,
  "file": "/media/documents/file.pdf",
  "doc_type": "pan",
  "uploaded_at": "2026-04-26T10:00:00Z"
}
```

**Validation:**

- File types: PDF, JPG, PNG only
- File size: Max 5MB
- MIME type: Checked (not file extension)
- Required: At least one document before submission

---

### Submit KYC for Review

```http
POST /kyc/{id}/submit/
```

**Headers:**

```
X-User: merchant1
```

**Requirements:**

- ✅ Personal details filled (name, email, phone)
- ✅ Business details filled (business_name, type, monthly_volume)
- ✅ At least one document uploaded

**Response:** `200 OK`

```json
{
  "message": "Submitted",
  "state": "submitted"
}
```

**State Change:** `draft` → `submitted`

---

## Reviewer Endpoints

### Get Review Queue

```http
GET /review/queue/
```

**Headers:**

```
X-User: reviewer1
```

**Response:** `200 OK`

```json
[
  {
    "id": 1,
    "merchant": "merchant1",
    "state": "submitted",
    "created_at": "2026-04-26T09:00:00Z",
    "at_risk": false
  },
  {
    "id": 2,
    "merchant": "merchant2",
    "state": "under_review",
    "created_at": "2026-04-25T09:00:00Z",
    "at_risk": true
  }
]
```

**Features:**

- Sorted by oldest first (FIFO)
- `at_risk`: true if in queue > 24 hours
- Only shows `submitted` and `under_review` states

---

### Get Submission Details

```http
GET /review/{id}/
```

**Headers:**

```
X-User: reviewer1
```

**Response:** `200 OK` - Full submission with all documents

---

### Get Dashboard Metrics

```http
GET /review/metrics/
```

**Headers:**

```
X-User: reviewer1
```

**Response:** `200 OK`

```json
{
  "total_last_7_days": 10,
  "approved_last_7_days": 7,
  "approval_rate_7_days": 70.0,
  "avg_time_in_queue": "2:30:45"
}
```

---

### Start Review

```http
POST /review/{id}/start/
```

**Headers:**

```
X-User: reviewer1
```

**State Change:** `submitted` → `under_review`

**Response:** `200 OK`

```json
{
  "message": "Under review",
  "state": "under_review"
}
```

---

### Approve Submission

```http
POST /review/{id}/approve/
```

**Headers:**

```
X-User: reviewer1
```

**Requirements:**

- ✅ Not already approved
- ✅ Has at least one document

**State Change:** `under_review` → `approved`

**Response:** `200 OK`

```json
{
  "message": "Approved",
  "state": "approved"
}
```

---

### Reject Submission

```http
POST /review/{id}/reject/
```

**Headers:**

```
X-User: reviewer1
Content-Type: application/json
```

**Body:**

```json
{
  "reason": "Incomplete documentation"
}
```

**State Change:** `under_review` → `rejected`

**Response:** `200 OK`

```json
{
  "message": "Rejected",
  "state": "rejected",
  "reason": "Incomplete documentation"
}
```

---

### Request More Information

```http
POST /review/{id}/request-info/
```

**Headers:**

```
X-User: reviewer1
```

**State Change:** `under_review` → `more_info_requested`

**Response:** `200 OK`

```json
{
  "message": "More info requested",
  "state": "more_info_requested"
}
```

**Note:** Merchant can update and resubmit when in this state.

---

## State Machine

### Valid Transitions

```
draft
  ↓
submitted
  ↓
under_review
  ├→ approved ✓
  ├→ rejected ✓
  └→ more_info_requested
       ↓
    submitted (cycle back)
```

### Illegal Transitions (Return 400)

- `approved` → anything (terminal state)
- `rejected` → anything (terminal state)
- `draft` → `under_review` (must be `submitted` first)
- `reject` → `draft` (no rollback)

---

## Test Data

After running `python manage.py seed_data`:

### Users

| Username    | Role     | Status                         |
| ----------- | -------- | ------------------------------ |
| `merchant1` | Merchant | Has a draft submission         |
| `merchant2` | Merchant | Has an under_review submission |
| `reviewer1` | Reviewer | Can access all submissions     |

### Test Merchant Submission (merchant1)

- **State:** draft
- **Personal Details:** Pre-filled
- **Business Details:** Pre-filled
- **Documents:** None (add to test workflow)

---

## Running Tests

### Run All Tests

```bash
export DJANGO_SETTINGS_MODULE=playto_kyc.settings
python -m pytest kyc/tests.py -v
```

### Run Specific Test

```bash
export DJANGO_SETTINGS_MODULE=playto_kyc.settings
python -m pytest kyc/tests.py::test_illegal_state_transition -v
```

### Test Coverage

- ✅ Illegal state transition detection
- ✅ File upload validation
- ✅ JSON field validation
- ✅ Authentication & authorization

---

## Project Structure

```
playto_kyc/
├── manage.py                          # Django management
├── requirements.txt                   # Dependencies
├── db.sqlite3                         # Database (created after migrate)
├── playto_kyc/                        # Project settings
│   ├── settings.py                    # Django configuration
│   ├── urls.py                        # URL routing
│   ├── asgi.py                        # ASGI entry point
│   └── wsgi.py                        # WSGI entry point
└── kyc/                               # Main app
    ├── models.py                      # Database models
    ├── views.py                       # API endpoints
    ├── urls.py                        # App URL routing
    ├── tests.py                       # Unit tests
    ├── admin.py                       # Admin interface
    ├── apps.py                        # App configuration
    ├── services/                      # Business logic
    │   ├── state_machine.py           # State transition logic
    │   ├── notifications.py           # Event logging
    │   └── serializers.py             # Data validation
    ├── management/
    │   └── commands/
    │       └── seed_data.py           # Test data generation
    └── migrations/                    # Database migrations
```

---

## Error Handling

All errors follow a consistent format:

```json
{
  "error": {
    "message": "Error description",
    "code": "error_code"
  }
}
```

### Common Status Codes

| Code | Meaning                                      |
| ---- | -------------------------------------------- |
| 200  | Success                                      |
| 201  | Created                                      |
| 400  | Bad Request / Validation Error               |
| 401  | Unauthorized (missing/invalid X-User header) |
| 403  | Forbidden (wrong role or data access)        |
| 404  | Not Found                                    |
| 500  | Server Error                                 |

---

## Deployment

### Production Checklist

- [ ] Set `DEBUG = False` in `settings.py`
- [ ] Use PostgreSQL instead of SQLite
- [ ] Configure `ALLOWED_HOSTS`
- [ ] Use strong `SECRET_KEY`
- [ ] Set up environment variables (`.env`)
- [ ] Enable HTTPS
- [ ] Use gunicorn: `gunicorn playto_kyc.wsgi`

### Database Setup (PostgreSQL)

```python
# settings.py
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'playto_kyc',
        'USER': 'postgres',
        'PASSWORD': 'password',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}
```

---

## Support & Debugging

### Enable Debug Logging

```bash
# In settings.py
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'DEBUG',
    },
}
```

### Clear Database

```bash
rm db.sqlite3
python manage.py migrate
```

### Reset Test Data

```bash
python manage.py seed_data
```

---

## Contributing

1. Create a feature branch
2. Make changes
3. Run tests: `pytest kyc/tests.py -v`
4. Submit pull request

---

**Last Updated:** April 26, 2026  
**Django Version:** 6.0  
**Python Version:** 3.9+
