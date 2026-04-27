from django.core.management.base import BaseCommand
from django.utils.timezone import now
from datetime import timedelta
from kyc.models import User, KYCSubmission


class Command(BaseCommand):
    help = "Seed test data for Playto KYC system"

    def handle(self, *args, **kwargs):
        self.stdout.write("🌱 Seeding test data...")

        # Create users safely
        merchant1, created1 = User.objects.update_or_create(
            username="merchant1",
            defaults={
                "role": "merchant",
                "email": "merchant1@example.com",
                "is_active": True,
            }
        )
        if created1:
            merchant1.set_password("testpass123")
            merchant1.save()
            self.stdout.write(f"  ✅ Created merchant1")

        merchant2, created2 = User.objects.update_or_create(
            username="merchant2",
            defaults={
                "role": "merchant",
                "email": "merchant2@example.com",
                "is_active": True,
            }
        )
        if created2:
            merchant2.set_password("testpass123")
            merchant2.save()
            self.stdout.write(f"  ✅ Created merchant2")

        reviewer, created3 = User.objects.update_or_create(
            username="reviewer1",
            defaults={
                "role": "reviewer",
                "email": "reviewer1@example.com",
                "is_active": True,
            }
        )
        if created3:
            reviewer.set_password("testpass123")
            reviewer.save()
            self.stdout.write(f"  ✅ Created reviewer1")

        # Create draft submission (merchant1)
        draft_submission, created = KYCSubmission.objects.update_or_create(
            merchant=merchant1,
            state="draft",
            defaults={
                "personal_details": {
                    "name": "Rahul Sharma",
                    "email": "rahul@example.com",
                    "phone": "+91-9876543210"
                },
                "business_details": {
                    "business_name": "Sharma Digital Solutions",
                    "type": "Freelancer",
                    "monthly_volume": "5000"
                }
            }
        )
        if created:
            self.stdout.write(f"  ✅ Created draft submission (ID: {draft_submission.id})")

        # Create under_review submission (merchant2) - create it 25 hours ago for SLA testing
        review_submission, created = KYCSubmission.objects.update_or_create(
            merchant=merchant2,
            state="under_review",
            defaults={
                "personal_details": {
                    "name": "Priya Patel",
                    "email": "priya@example.com",
                    "phone": "+91-9876543211"
                },
                "business_details": {
                    "business_name": "Patel Creative Agency",
                    "type": "Agency",
                    "monthly_volume": "15000"
                },
                "created_at": now() - timedelta(hours=25)  # Will be flagged as at_risk
            }
        )
        if created:
            self.stdout.write(f"  ✅ Created under_review submission (ID: {review_submission.id})")
        else:
            # Update timestamp for existing submission
            KYCSubmission.objects.filter(id=review_submission.id).update(
                created_at=now() - timedelta(hours=25)
            )
            self.stdout.write(f"  ✅ Updated under_review submission timestamp")

        self.stdout.write(self.style.SUCCESS(
            "\n✅ Seed data created successfully!\n"
            "\nTest Users:"
            "\n  Merchant 1: username='merchant1', password='testpass123'"
            "\n  Merchant 2: username='merchant2', password='testpass123'"
            "\n  Reviewer:   username='reviewer1', password='testpass123'"
            "\n"
            "\nUsage:"
            "\n  Include X-User header with the username for authentication"
            "\n  Example: curl -H 'X-User: merchant1' http://localhost:8000/api/v1/kyc/"
            "\n"
            "\nSubmissions:"
            f"\n  Draft submission ID: {draft_submission.id} (at risk - 25h old)"
            f"\n  Under review submission ID: {review_submission.id}"
        ))