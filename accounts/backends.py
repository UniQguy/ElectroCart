from django.contrib.auth import get_user_model
from .models import UserProfile

User = get_user_model()


class EmailOrPhoneBackend:
    def authenticate(self, request, username=None, password=None, **kwargs):
        identifier = (username or kwargs.get("email") or "").strip()
        if not identifier or not password:
            return None

        user = User.objects.filter(username__iexact=identifier).first()
        if user is None:
            user = User.objects.filter(email__iexact=identifier).first()
        if user is None:
            profile = UserProfile.objects.filter(phone=identifier).select_related("user").first()
            user = profile.user if profile else None

        if user and user.is_active and user.check_password(password):
            return user
        return None

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
