import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'playto_kyc.settings')
django.setup()

from kyc.models import KYCSubmission, User

print("🗑️  Clearing test data...")
print(f"Total submissions before: {KYCSubmission.objects.count()}")

# Delete all submissions
KYCSubmission.objects.all().delete()
print(f"Total submissions after: {KYCSubmission.objects.count()}")

# Delete test users
User.objects.filter(username__in=["merchant1", "merchant2", "reviewer1"]).delete()
print("✅ Cleared all test data")
