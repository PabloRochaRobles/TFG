"""
Endpoints de autenticación: register, login, refresh.

Identificador único de usuario: el **email**. Internamente se guarda
también como `username` (porque el User model por defecto de Django
exige ese campo), pero el cliente móvil sólo conoce `email + password`.

  POST /api/auth/register/   → {email, password}            → {access, refresh}
  POST /api/auth/login/      → {email, password}            → {access, refresh}
  POST /api/auth/refresh/    → {refresh}                    → {access}
"""

from django.contrib.auth import get_user_model
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from rest_framework import permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView


User = get_user_model()


def _tokens_for_user(user) -> dict:
    """Genera el par de tokens para un usuario."""
    refresh = RefreshToken.for_user(user)
    return {
        'access':  str(refresh.access_token),
        'refresh': str(refresh),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Registro
# ─────────────────────────────────────────────────────────────────────────────

class RegisterSerializer(serializers.Serializer):
    email    = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)

    def validate_email(self, value):
        # Normalizamos a minúsculas para que "Foo@bar.com" == "foo@bar.com".
        value = value.lower().strip()
        try:
            validate_email(value)
        except ValidationError:
            raise serializers.ValidationError('Email no válido.')
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError('Ya existe un usuario con este email.')
        return value

    def create(self, validated_data):
        # username = email para que el login con email funcione directo.
        return User.objects.create_user(
            username=validated_data['email'],
            email=validated_data['email'],
            password=validated_data['password'],
        )


class RegisterView(APIView):
    """POST /api/auth/register/ — crea usuario y devuelve tokens (login auto)."""
    permission_classes = [permissions.AllowAny]
    authentication_classes = []  # no se requiere token para registrarse

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        user = serializer.save()
        tokens = _tokens_for_user(user)
        return Response(
            {
                'email':  user.email,
                'access': tokens['access'],
                'refresh': tokens['refresh'],
            },
            status=status.HTTP_201_CREATED,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Login (acepta `email` en lugar de `username`)
# ─────────────────────────────────────────────────────────────────────────────

class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Renombra el campo `username` → `email` en la API pública.

    Importante: NO sobreescribimos `username_field`. Si lo cambiásemos a
    `'email'`, SimpleJWT llamaría a `authenticate(email=..., password=...)`
    y `ModelBackend` (el backend por defecto de Django) ignora ese kwarg —
    el login fallaría con "No active account found".

    En lugar de eso: aceptamos `email` en el body, y antes de delegar al
    `super().validate()` movemos el valor a `attrs['username']`. Como al
    registrarse guardamos `username = email`, la autenticación encuentra
    al usuario correctamente.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Reemplazamos el campo `username` (creado por la clase padre) por `email`.
        self.fields['email'] = serializers.EmailField(write_only=True)
        self.fields.pop('username', None)

    def validate(self, attrs):
        email = attrs.pop('email', '').lower().strip()
        attrs['username'] = email   # super().validate() lee attrs['username']
        return super().validate(attrs)


class EmailTokenObtainPairView(TokenObtainPairView):
    """POST /api/auth/login/ — autentica con email + password."""
    serializer_class = EmailTokenObtainPairSerializer
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
