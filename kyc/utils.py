from .models import User
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied


def get_user_from_header(request):
    """
    Extract and validate user from X-User header.
    
    Returns:
        User instance if found and valid
        
    Raises:
        AuthenticationFailed: If header is missing or user doesn't exist
    """
    username = request.headers.get("X-User")

    if not username:
        raise AuthenticationFailed(
            "Authentication required. Please provide X-User header."
        )

    try:
        user = User.objects.get(username=username, is_active=True)
        return user
    except User.DoesNotExist:
        raise AuthenticationFailed(
            f"User '{username}' not found or inactive."
        )


def require_role(user, required_role):
    """
    Check if user has the required role.
    
    Args:
        user: User instance
        required_role: String role name ('merchant' or 'reviewer')
        
    Raises:
        PermissionDenied: If user doesn't have the required role
    """
    if user.role != required_role:
        raise PermissionDenied(
            f"Access denied. This action requires '{required_role}' role. "
            f"Your role: '{user.role}'"
        )


def error_response(message, code="error", status_code=400, details=None):
    """
    Create consistent error response format.
    
    Args:
        message: Main error message
        code: Error code string
        status_code: HTTP status code
        details: Additional error details
        
    Returns:
        Response object with standardized error format
    """
    from rest_framework.response import Response
    
    error_body = {
        "error": {
            "message": str(message),
            "code": code
        }
    }
    
    if details:
        error_body["error"]["details"] = details
        
    return Response(error_body, status=status_code)