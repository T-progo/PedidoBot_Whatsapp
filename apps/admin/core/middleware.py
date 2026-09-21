

# =============================================================================
# TNL-CLIENT-LIFECYCLE-MIDDLEWARE-V1
# =============================================================================

class ClientLifecycleMiddleware:
    """
    Expulsa sesiones ya existentes cuando
    cliente/operador deja de estar autorizado.

    Administración y superuser permanecen
    disponibles para reparar/renovar.
    """

    def __init__(
        self,
        get_response,
    ):
        self.get_response = get_response


    def __call__(
        self,
        request,
    ):
        from django.contrib.auth import (
            logout,
        )

        from django.contrib import messages

        from django.urls import reverse

        from core.services.client_lifecycle import (
            usuario_puede_iniciar_sesion,
        )

        user = getattr(
            request,
            "user",
            None,
        )

        if (
            user is not None
            and
            getattr(
                user,
                "is_authenticated",
                False,
            )
            and
            not usuario_puede_iniciar_sesion(
                user
            )
        ):

            login_url = reverse(
                "core:login"
            )

            logout(
                request
            )

            if request.path == login_url:

                return self.get_response(
                    request
                )

            messages.error(
                request,
                (
                    "El acceso a esta empresa "
                    "se encuentra suspendido. "
                    "Contacta a Administración "
                    "para revisar tu licencia."
                ),
            )

            from django.shortcuts import redirect

            return redirect(
                login_url
            )

        return self.get_response(
            request
        )
