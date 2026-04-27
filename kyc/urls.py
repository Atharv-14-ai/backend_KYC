from django.urls import path
from . import views

urlpatterns = [
    # Merchant endpoints
    path('kyc/', views.ListKYC.as_view(), name='list-kyc'),
    path('kyc/create/', views.CreateKYC.as_view(), name='create-kyc'),
    path('kyc/<int:pk>/', views.GetKYC.as_view(), name='get-kyc'),
    path('kyc/<int:pk>/update/', views.UpdateKYC.as_view(), name='update-kyc'),
    path('kyc/<int:pk>/upload/', views.UploadDocument.as_view(), name='upload-document'),
    path('kyc/<int:pk>/submit/', views.SubmitKYC.as_view(), name='submit-kyc'),

    # Reviewer endpoints
    path('review/queue/', views.ReviewerQueue.as_view(), name='reviewer-queue'),
    path('review/<int:pk>/', views.ReviewDetail.as_view(), name='review-detail'),
    path('review/metrics/', views.ReviewerMetrics.as_view(), name='reviewer-metrics'),
    path('review/<int:pk>/start/', views.StartReview.as_view(), name='start-review'),
    path('review/<int:pk>/approve/', views.ApproveKYC.as_view(), name='approve-kyc'),
    path('review/<int:pk>/reject/', views.RejectKYC.as_view(), name='reject-kyc'),
    path('review/<int:pk>/request-info/', views.RequestMoreInfo.as_view(), name='request-more-info'),
    path('auth/login/', views.LoginView.as_view(), name='login'),
    path('auth/signup/', views.SignupView.as_view(), name='signup'),
    path('auth/create-reviewer/', views.CreateReviewerView.as_view(), name='create-reviewer'),
]