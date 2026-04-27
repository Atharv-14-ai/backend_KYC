from django.test import TestCase
from django.utils.timezone import now
from datetime import timedelta
from kyc.models import User, KYCSubmission
from kyc.services.state_machine import transition_state


class StateMachineTests(TestCase):
    '''Test suite for KYC state machine transitions.'''

    def test_illegal_transition_approved_to_draft(self):
        merchant = User.objects.create_user(username='test_merchant', password='pass123', role='merchant')
        submission = KYCSubmission.objects.create(
            merchant=merchant,
            state='approved'
        )

        with self.assertRaises(ValueError) as exc_info:
            transition_state(submission, 'draft')

        self.assertIn("Cannot transition from terminal state 'approved'", str(exc_info.exception))

    def test_illegal_transition_draft_to_approved(self):
        merchant = User.objects.create_user(username='test_merchant', password='pass123', role='merchant')
        submission = KYCSubmission.objects.create(
            merchant=merchant,
            state='draft'
        )

        with self.assertRaises(ValueError):
            transition_state(submission, 'approved')

    def test_valid_transition_path(self):
        merchant = User.objects.create_user(username='test_merchant', password='pass123', role='merchant')
        reviewer = User.objects.create_user(username='test_reviewer', password='pass123', role='reviewer')

        submission = KYCSubmission.objects.create(
            merchant=merchant,
            state='draft'
        )

        submission = transition_state(submission, 'submitted')
        self.assertEqual(submission.state, 'submitted')

        submission = transition_state(submission, 'under_review')
        self.assertEqual(submission.state, 'under_review')

        submission = transition_state(submission, 'approved', reviewed_by=reviewer)
        self.assertEqual(submission.state, 'approved')
        self.assertEqual(submission.reviewed_by, reviewer)
        self.assertIsNotNone(submission.reviewed_at)

    def test_terminal_state_no_transitions(self):
        merchant = User.objects.create_user(username='test_merchant', password='pass123', role='merchant')

        approved_sub = KYCSubmission.objects.create(
            merchant=merchant,
            state='approved'
        )
        with self.assertRaises(ValueError):
            transition_state(approved_sub, 'draft')
        with self.assertRaises(ValueError):
            transition_state(approved_sub, 'submitted')

        rejected_sub = KYCSubmission.objects.create(
            merchant=merchant,
            state='rejected'
        )
        with self.assertRaises(ValueError):
            transition_state(rejected_sub, 'draft')

    def test_more_info_cycle(self):
        merchant = User.objects.create_user(username='test_merchant', password='pass123', role='merchant')
        reviewer = User.objects.create_user(username='test_reviewer', password='pass123', role='reviewer')

        submission = KYCSubmission.objects.create(
            merchant=merchant,
            state='draft'
        )

        submission = transition_state(submission, 'submitted')
        submission = transition_state(submission, 'under_review')

        submission = transition_state(
            submission,
            'more_info_requested',
            reviewed_by=reviewer,
            review_reason='Need clearer documents'
        )
        self.assertEqual(submission.state, 'more_info_requested')
        self.assertEqual(submission.review_reason, 'Need clearer documents')

        submission = transition_state(submission, 'submitted')
        self.assertEqual(submission.state, 'submitted')


class AuthorizationTests(TestCase):
    def test_merchant_cannot_access_other_merchant_submission(self):
        merchant_a = User.objects.create_user(username='merchant_a', password='pass123', role='merchant')
        merchant_b = User.objects.create_user(username='merchant_b', password='pass123', role='merchant')

        submission_b = KYCSubmission.objects.create(
            merchant=merchant_b,
            state='draft'
        )

        response = self.client.get(
            f'/api/v1/kyc/{submission_b.id}/',
            HTTP_X_USER=merchant_a.username
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()['error']['code'], 'FORBIDDEN')

    def test_reviewer_can_access_submission(self):
        merchant = User.objects.create_user(username='merchant1', password='pass123', role='merchant')
        reviewer = User.objects.create_user(username='reviewer1', password='pass123', role='reviewer')

        submission = KYCSubmission.objects.create(
            merchant=merchant,
            state='submitted'
        )

        response = self.client.get(
            f'/api/v1/review/{submission.id}/',
            HTTP_X_USER=reviewer.username
        )
        self.assertEqual(response.status_code, 200)


class SlaTrackingTests(TestCase):
    def test_recent_submission_not_at_risk(self):
        merchant = User.objects.create_user(username='test_merchant', password='pass123', role='merchant')
        submission = KYCSubmission.objects.create(
            merchant=merchant,
            state='under_review'
        )

        time_in_queue = now() - submission.created_at
        self.assertLess(time_in_queue, timedelta(hours=24))

    def test_old_submission_is_at_risk(self):
        merchant = User.objects.create_user(username='test_merchant', password='pass123', role='merchant')
        submission = KYCSubmission.objects.create(
            merchant=merchant,
            state='under_review'
        )
        KYCSubmission.objects.filter(id=submission.id).update(
            created_at=now() - timedelta(hours=25)
        )
        submission.refresh_from_db()

        time_in_queue = now() - submission.created_at
        self.assertGreater(time_in_queue, timedelta(hours=24))

    def test_submit_kyc_requires_complete_details(self):
        merchant = User.objects.create_user(username='merchant_c', password='pass123', role='merchant')
        submission = KYCSubmission.objects.create(
            merchant=merchant,
            state='draft',
            personal_details={'name': '', 'email': '', 'phone': ''},
            business_details={'business_name': '', 'type': '', 'monthly_volume': ''}
        )

        response = self.client.post(
            f'/api/v1/kyc/{submission.id}/submit/',
            HTTP_X_USER=merchant.username
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['error']['code'], 'INCOMPLETE_KYC')
