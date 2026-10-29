from .models import Membership, Notification
def workspace(request):
    if not request.user.is_authenticated:
        return {}
    try:
        member = Membership.objects.select_related("company").get(user=request.user)
    except Membership.DoesNotExist:
        return {}
    return {"company": member.company, "membership": member,
            "unread_notifications": Notification.objects.filter(user=request.user, read_at__isnull=True).count()}
