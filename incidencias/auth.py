from django.contrib.auth import get_user_model
from django.db.models import Q


def axes_whitelist_admin(_request, credentials):
    username = credentials.get("username")
    if not username:
        return False

    user_model = get_user_model()
    return user_model._default_manager.filter(username=username).filter(
        Q(is_staff=True) | Q(is_superuser=True) | Q(perfil__rol="administrador")
    ).exists()
