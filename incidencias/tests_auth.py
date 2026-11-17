from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from incidencias.models import Edificio, Perfil


@override_settings(AXES_FAILURE_LIMIT=2)
class AdminLoginLockoutTests(TestCase):
    def setUp(self):
        self.edificio = Edificio.objects.create(
            nombre="Torre de prueba",
            direccion="Calle 1",
        )
        self.admin = User.objects.create_user(
            username="admin_login",
            password="ClaveSegura123!",
        )
        Perfil.objects.create(
            user=self.admin,
            edificio=self.edificio,
            rol="administrador",
        )
        self.residente = User.objects.create_user(
            username="residente_login",
            password="ClaveSegura123!",
        )
        Perfil.objects.create(
            user=self.residente,
            edificio=self.edificio,
            rol="residente",
        )
        self.login_url = reverse("login")

    def _post_login(self, username, password):
        return self.client.post(
            self.login_url,
            {"username": username, "password": password},
            REMOTE_ADDR="192.0.2.1",
        )

    def test_administrador_no_se_bloquea_por_intentos_fallidos(self):
        for _ in range(3):
            self._post_login("admin_login", "clave_incorrecta")

        response = self._post_login("admin_login", "ClaveSegura123!")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.wsgi_request.user, self.admin)

    def test_residente_sigue_bloqueandose_al_superar_el_limite(self):
        for _ in range(2):
            self._post_login("residente_login", "clave_incorrecta")

        response = self._post_login("residente_login", "ClaveSegura123!")

        self.assertEqual(response.status_code, 429)
        self.assertFalse(response.wsgi_request.user.is_authenticated)
