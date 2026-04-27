from rest_framework import serializers
from django.core.exceptions import ValidationError
from ..models import KYCSubmission, Document


class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = ['id', 'file', 'doc_type', 'uploaded_at', 'submission']
        read_only_fields = ['uploaded_at', 'submission']

    def validate_file(self, file):
        # Validate content type
        allowed_types = ["application/pdf", "image/jpeg", "image/png"]
        
        if file.content_type not in allowed_types:
            raise serializers.ValidationError(
                f"Invalid file type: '{file.content_type}'. "
                f"Allowed types: PDF, JPG, PNG"
            )

        # Validate file size (5MB limit)
        max_size = 5 * 1024 * 1024  # 5MB in bytes
        if file.size > max_size:
            raise serializers.ValidationError(
                f"File too large: {file.size / (1024*1024):.2f}MB. "
                f"Maximum size: 5MB"
            )

        return file

    def validate(self, data):
        # Ensure the submission can accept documents
        submission = self.context.get('submission') or data.get('submission')
        if not submission:
            raise serializers.ValidationError({
                "submission": "Submission context is required for document uploads"
            })

        allowed_states = ['draft', 'more_info_requested']
        if submission.state not in allowed_states:
            raise serializers.ValidationError({
                "submission": f"Cannot upload documents to a submission "
                              f"in '{submission.state}' state"
            })
        return data

    def create(self, validated_data):
        submission = self.context.get('submission') or validated_data.pop('submission')
        return Document.objects.create(submission=submission, **validated_data)


class KYCSubmissionSerializer(serializers.ModelSerializer):
    documents = DocumentSerializer(many=True, read_only=True)
    merchant_name = serializers.CharField(source='merchant.username', read_only=True)

    class Meta:
        model = KYCSubmission
        fields = [
            'id', 'merchant', 'merchant_name', 'state', 
            'personal_details', 'business_details', 
            'documents', 'review_reason', 'reviewed_by', 
            'reviewed_at', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'merchant', 'state', 'reviewed_by', 
            'reviewed_at', 'created_at', 'updated_at'
        ]

    def validate_personal_details(self, value):
        # Allow empty details for draft submissions - validation only on final submit
        if not value:
            return value or {}
        
        # Only validate if fields are provided (not empty)
        if any(value.get(f) for f in ['name', 'email', 'phone']):
            # Email validation if provided
            email = value.get('email', '')
            if email and '@' not in email:
                raise serializers.ValidationError("Invalid email format if provided")
            
            # Phone validation if provided
            phone = value.get('phone', '')
            if phone and not phone.replace('+', '').replace('-', '').replace(' ', '').isdigit():
                raise serializers.ValidationError("Invalid phone number format if provided")

        return value

    def validate_business_details(self, value):
        # Allow empty details for draft submissions - validation only on final submit
        if not value:
            return value or {}
        
        # Only validate if fields are provided (not empty)
        monthly_volume = value.get('monthly_volume')
        if monthly_volume:
            try:
                volume = float(monthly_volume)
                if volume <= 0:
                    raise serializers.ValidationError("Monthly volume must be greater than 0")
            except (ValueError, TypeError):
                raise serializers.ValidationError("Monthly volume must be a valid number")

        return value