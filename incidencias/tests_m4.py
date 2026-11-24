"""
Pruebas Automatizadas M4 — API REST de Producción, Idempotencia y OpenAPI
========================================================================
Criterios de Aceptación:
  1. Idempotencia en POST: Un cliente externo puede reintentar peticiones
     con la cabecera Idempotency-Key sin duplicar incidencias en base de datos.
  2. Aislamiento por edificio en la API: Residente de edificio B recibe 404
     al consultar incidencias de edificio A vía REST.
  3. Autenticación JWT con emisión y validación de tokens Bearer.
  4. Contrato OpenAPI 3.0 accesible y documentado para integración externa.

Uso:
    python manage.py test incidencias.tests_m4
"""

from django.test import TestCase
from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status

from incidencias.models import Edificio, Perfil, Incidencia, IdempotencyRecord


class ApiIdempotenciaTest(TestCase):
    """Verifica que la cabecera Idempotency-Key impida duplicados en reintentos de red."""

    def setUp(self):
        self.edificio = Edificio.objects.create(nombre="Torre Idempotente", direccion="Cra 10")
        self.user = User.objects.create_user(username="residente_api", password="password123")
        Perfil.objects.create(user=self.user, edificio=self.edificio, rol='residente')

        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.url = '/api/v1/incidencias/'

    def test_reintento_con_misma_idempotency_key_no_duplica_incidencias(self):
        """
        Si un cliente envía dos veces la misma petición POST con Idempotency-Key,
        la segunda devuelve la respuesta cacheada y la base de datos solo tiene 1 registro.
        """
        payload = {
            'titulo': 'Fuga urgente en tubería del piso 3',
            'descripcion': 'El agua se está filtrando hacia el ascensor.',
            'categoria': 'agua',
            'prioridad': 'alta'
        }
        idempotency_key = "transaccion-uuid-abc-12345"

        # ── 1. Primera petición (original) ──────────────────────────
        res1 = self.client.post(self.url, payload, HTTP_IDEMPOTENCY_KEY=idempotency_key, format='json')
        self.assertEqual(res1.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res1.headers.get('X-Idempotent-Replay'), 'false')
        self.assertEqual(Incidencia.objects.filter(edificio=self.edificio).count(), 1)
        incidencia_id = res1.data['id_incid']

        # ── 2. Segunda petición (reintento por fallo simulado de red) 
        res2 = self.client.post(self.url, payload, HTTP_IDEMPOTENCY_KEY=idempotency_key, format='json')
        self.assertEqual(res2.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res2.headers.get('X-Idempotent-Replay'), 'true')

        # Comprobación de oro: NO se duplicó la incidencia
        self.assertEqual(Incidencia.objects.filter(edificio=self.edificio).count(), 1)
        self.assertEqual(res2.data['id_incid'], incidencia_id)


class ApiAislamientoEdificioTest(TestCase):
    """Verifica que ningún endpoint REST permita a un usuario ver datos de otro edificio."""

    def setUp(self):
        self.edificio_a = Edificio.objects.create(nombre="Edificio Alpha", direccion="Cl 100")
        self.edificio_b = Edificio.objects.create(nombre="Edificio Beta", direccion="Cl 200")

        self.res_a = User.objects.create_user(username="residente_alpha", password="password123")
        Perfil.objects.create(user=self.res_a, edificio=self.edificio_a, rol='residente')

        self.res_b = User.objects.create_user(username="residente_beta", password="password123")
        Perfil.objects.create(user=self.res_b, edificio=self.edificio_b, rol='residente')

        self.inc_a = Incidencia.objects.create(
            edificio=self.edificio_a,
            creador=self.res_a,
            titulo="Incidencia Privada de Alpha",
            descripcion="Información de Alpha",
            estado='pendiente'
        )

        self.client = APIClient()

    def test_residente_b_recibe_404_al_consultar_incidencia_de_a_en_api(self):
        """El residente del edificio B debe recibir 404 al intentar GET /api/v1/incidencias/{id_a}/"""
        self.client.force_authenticate(user=self.res_b)
        url = f'/api/v1/incidencias/{self.inc_a.id_incid}/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_residente_a_recibe_200_en_su_propia_incidencia(self):
        """El creador en el edificio A recibe 200 con su detalle."""
        self.client.force_authenticate(user=self.res_a)
        url = f'/api/v1/incidencias/{self.inc_a.id_incid}/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id_incid'], self.inc_a.id_incid)


class ApiAutenticacionYDocumentacionTest(TestCase):
    """Verifica JWT y disponibilidad del contrato OpenAPI."""

    def setUp(self):
        self.edificio = Edificio.objects.create(nombre="Torre Central", direccion="Cl 50")
        self.user = User.objects.create_user(username="usuario_jwt", password="mi_password_seguro")
        Perfil.objects.create(user=self.user, edificio=self.edificio, rol='residente')
        self.client = APIClient()

    def test_obtener_tokens_jwt_correctamente(self):
        """POST /api/v1/auth/token/ devuelve access y refresh tokens."""
        url = '/api/v1/auth/token/'
        response = self.client.post(url, {
            'username': 'usuario_jwt',
            'password': 'mi_password_seguro'
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)

        # Probar autenticación con Bearer token
        access_token = response.data['access']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access_token}')
        res_list = self.client.get('/api/v1/incidencias/')
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)

    def test_esquema_openapi_y_swagger_disponibles(self):
        """Los endpoints de documentación /schema/ y /docs/ están activos y conformes a OpenAPI 3.0."""
        # Esquema OpenAPI JSON
        res_schema = self.client.get('/api/v1/schema/')
        self.assertEqual(res_schema.status_code, status.HTTP_200_OK)
        self.assertIn('openapi', res_schema.data)
        self.assertIn('/api/v1/incidencias/', res_schema.data['paths'])

        # UI interactiva Swagger
        res_swagger = self.client.get('/api/v1/docs/')
        self.assertEqual(res_swagger.status_code, status.HTTP_200_OK)