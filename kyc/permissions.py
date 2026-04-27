from rest_framework.permissions import BasePermission


class IsMerchantOwner(BasePermission):
    """
    Permission to ensure the merchant owns the submission.
    """
    def has_object_permission(self, request, view, obj):
        # Check if the object has a 'merchant' attribute
        if hasattr(obj, 'merchant'):
            return obj.merchant == request.user
        # If checking the merchant user itself
        return obj == request.user


class IsReviewer(BasePermission):
    """
    Permission to ensure the user is a reviewer.
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == "reviewer"


class IsMerchant(BasePermission):
    """
    Permission to ensure the user is a merchant.
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == "merchant"