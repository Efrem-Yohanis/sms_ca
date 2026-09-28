"""Custom drf-spectacular authentication extension."""

from drf_spectacular.extensions import OpenApiAuthenticationExtension


class JWTAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = 'rest_framework_simplejwt.authentication.JWTAuthentication'
    name = 'jwtAuth'

    def get_security_definition(self, auto_schema):
        return {
            'type': 'http',
            'scheme': 'bearer',
            'bearerFormat': 'JWT',
            'description': (
                'JWT Bearer token. Obtain via POST /api/v1/auth/login/ '
                'and enter the access token here.'
            ),
        }
