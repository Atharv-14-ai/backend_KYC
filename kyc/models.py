from django.db import models
from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    ROLE_CHOICES = (
        ('merchant', 'Merchant'),
        ('reviewer', 'Reviewer'),
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)

    def __str__(self):
        return f"{self.username} ({self.role})"


class KYCSubmission(models.Model):
    STATE_CHOICES = [
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('under_review', 'Under Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('more_info_requested', 'More Info Requested'),
    ]

    merchant = models.ForeignKey(User, on_delete=models.CASCADE, related_name='kyc_submissions')
    state = models.CharField(max_length=30, choices=STATE_CHOICES, default='draft')

    personal_details = models.JSONField(default=dict)
    business_details = models.JSONField(default=dict)

    # Review tracking
    review_reason = models.TextField(blank=True, default='')
    reviewed_by = models.ForeignKey(
        User, 
        null=True, 
        blank=True, 
        on_delete=models.SET_NULL, 
        related_name='reviewed_submissions'
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['state', 'created_at']),
            models.Index(fields=['merchant', 'state']),
            models.Index(fields=['created_at']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"KYC #{self.id} - {self.merchant.username} ({self.state})"


class Document(models.Model):
    DOC_TYPES = [
        ('pan', 'PAN Card'),
        ('aadhaar', 'Aadhaar Card'),
        ('bank', 'Bank Statement'),
    ]

    submission = models.ForeignKey(
        KYCSubmission, 
        on_delete=models.CASCADE, 
        related_name='documents'
    )
    file = models.FileField(upload_to='documents/%Y/%m/%d/')
    doc_type = models.CharField(max_length=20, choices=DOC_TYPES)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f"{self.get_doc_type_display()} - {self.submission.id}"


class Notification(models.Model):
    merchant = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    event_type = models.CharField(max_length=50)
    payload = models.JSONField(default=dict)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['merchant', 'event_type']),
            models.Index(fields=['timestamp']),
        ]

    def __str__(self):
        return f"{self.event_type} - Merchant {self.merchant_id}"