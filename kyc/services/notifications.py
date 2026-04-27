from ..models import Notification


def create_notification(merchant, event_type, payload=None):
    """
    Create a notification event for a merchant.
    
    Args:
        merchant: User instance or merchant_id
        event_type: String describing the event
        payload: Dict with additional event data
    """
    if payload is None:
        payload = {}
    
    # If merchant is an ID, use it directly
    if isinstance(merchant, int):
        merchant_id = merchant
    else:
        merchant_id = merchant.id
    
    return Notification.objects.create(
        merchant_id=merchant_id,
        event_type=event_type,
        payload=payload
    )