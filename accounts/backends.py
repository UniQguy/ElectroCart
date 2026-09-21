from django.contrib.auth import get_user_model
from .models import UserProfile

User = get_user_model()


class EmailOrPhoneBackend:

    def authenticate(
        self,
        request,
        username=None,
        password=None,
        **kwargs
    ):

        if username is None:
            username = kwargs.get("email")

        if not username or not password:
            return None

        username = username.strip()

        # Login using email
        user = User.objects.filter(
            email__iexact=username
        ).first()

        # Login using phone
        if user is None:
            profile = UserProfile.objects.filter(
                phone=username
            ).select_related("user").first()

            if profile:
                user = profile.user

        # Check password
        if user is not None:
            if user.check_password(password) and user.is_active:
                return user

        return None

    def get_user(self, user_id):

        try:
            return User.objects.get(pk=user_id)

        except User.DoesNotExist:
            return None