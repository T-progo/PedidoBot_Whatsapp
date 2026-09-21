# ============================================================
# TNL-PROMOCIONES-IA-DUENO-SERVICE-V1
# ============================================================

from django.core.exceptions import (
    PermissionDenied,
    ValidationError,
)

from django.db import (
    IntegrityError,
    transaction,
)

from core.models import (
    PerfilUsuario,
    Producto,
    ProductoPromocionIA,
    ReglaVentaCruzadaIA,
)


MAX_TEXTO_PROMOCIONAL = 1200
MAX_PRIORIDAD = 9999


def resolver_empresa_dueno(
    user,
):
    """
    La empresa se obtiene únicamente del usuario
    autenticado.

    Nunca recibe empresa_id desde navegador.
    """

    perfil = (
        PerfilUsuario.objects
        .select_related(
            "empresa",
        )
        .filter(
            usuario=user,
            activo=True,
        )
        .first()
    )

    if perfil is None:
        raise PermissionDenied(
            "Acceso no autorizado."
        )

    if (
        perfil.rol
        !=
        PerfilUsuario.Rol.CLIENTE
    ):
        raise PermissionDenied(
            "Esta sección pertenece al Dueño del negocio."
        )

    if (
        perfil.empresa_id is None
        or
        perfil.empresa is None
    ):
        raise PermissionDenied(
            "El cliente no tiene empresa asignada."
        )

    return perfil.empresa


def productos_empresa_queryset(
    empresa,
):
    """
    Todos los productos registrados de la empresa.
    La UI puede mostrarlos todos; el runtime IA
    posteriormente filtrará disponibilidad real.
    """

    return (
        Producto.objects
        .select_related(
            "catalogo",
            "categoria",
        )
        .filter(
            catalogo__empresa_id=
                empresa.id,
        )
        .order_by(
            "nombre",
            "id",
        )
    )


def resolver_producto_empresa(
    *,
    empresa,
    producto_id,
):
    """
    Impide utilizar un producto perteneciente
    a otro tenant aunque se manipule el POST.
    """

    try:
        producto_id = int(
            str(
                producto_id
                or ""
            ).strip()
        )

    except (
        TypeError,
        ValueError,
    ):
        raise ValidationError(
            "Producto no válido."
        )

    producto = (
        productos_empresa_queryset(
            empresa
        )
        .filter(
            id=producto_id,
        )
        .first()
    )

    if producto is None:
        raise ValidationError(
            "El producto no pertenece a tu empresa."
        )

    return producto


def normalizar_texto(
    valor,
):
    texto = str(
        valor
        or ""
    ).strip()

    if (
        len(texto)
        >
        MAX_TEXTO_PROMOCIONAL
    ):
        raise ValidationError(
            (
                "El texto promocional no puede "
                f"superar {MAX_TEXTO_PROMOCIONAL} "
                "caracteres."
            )
        )

    return texto


def normalizar_prioridad(
    valor,
):
    try:
        prioridad = int(
            str(
                valor
                if valor not in (
                    None,
                    "",
                )
                else 100
            ).strip()
        )

    except (
        TypeError,
        ValueError,
    ):
        raise ValidationError(
            "Prioridad no válida."
        )

    if not (
        0
        <=
        prioridad
        <=
        MAX_PRIORIDAD
    ):
        raise ValidationError(
            "La prioridad debe estar entre 0 y 9999."
        )

    return prioridad


def guardar_promocion_producto(
    *,
    empresa,
    producto_id,
    es_estrella,
    texto_promocional,
):
    producto = (
        resolver_producto_empresa(
            empresa=empresa,
            producto_id=producto_id,
        )
    )

    texto = normalizar_texto(
        texto_promocional
    )

    with transaction.atomic():

        promocion = (
            ProductoPromocionIA.objects
            .filter(
                empresa=empresa,
                producto=producto,
            )
            .first()
        )

        if promocion is None:
            promocion = (
                ProductoPromocionIA(
                    empresa=empresa,
                    producto=producto,
                )
            )

        promocion.es_estrella = bool(
            es_estrella
        )

        promocion.texto_promocional = (
            texto
        )

        promocion.activa = True

        promocion.save()

    return promocion


def guardar_regla_crosssell(
    *,
    empresa,
    producto_origen_id,
    producto_recomendado_id,
    texto_promocional,
    prioridad=100,
    activa=True,
    regla_id=None,
):
    origen = (
        resolver_producto_empresa(
            empresa=empresa,
            producto_id=
                producto_origen_id,
        )
    )

    recomendado = (
        resolver_producto_empresa(
            empresa=empresa,
            producto_id=
                producto_recomendado_id,
        )
    )

    texto = normalizar_texto(
        texto_promocional
    )

    prioridad = normalizar_prioridad(
        prioridad
    )

    with transaction.atomic():

        if regla_id not in (
            None,
            "",
        ):
            try:
                regla_id = int(
                    regla_id
                )
            except (
                TypeError,
                ValueError,
            ):
                raise ValidationError(
                    "Regla no válida."
                )

            regla = (
                ReglaVentaCruzadaIA.objects
                .filter(
                    id=regla_id,
                    empresa=empresa,
                )
                .first()
            )

            if regla is None:
                raise ValidationError(
                    "La regla no pertenece a tu empresa."
                )

        else:
            regla = (
                ReglaVentaCruzadaIA(
                    empresa=empresa,
                )
            )

        regla.producto_origen = (
            origen
        )

        regla.producto_recomendado = (
            recomendado
        )

        regla.texto_promocional = (
            texto
        )

        regla.prioridad = (
            prioridad
        )

        regla.activa = bool(
            activa
        )

        try:
            regla.save()

        except IntegrityError as exc:
            raise ValidationError(
                (
                    "Ya existe una recomendación "
                    "igual para estos productos."
                )
            ) from exc

    return regla


def eliminar_regla_crosssell(
    *,
    empresa,
    regla_id,
):
    try:
        regla_id = int(
            str(
                regla_id
                or ""
            ).strip()
        )

    except (
        TypeError,
        ValueError,
    ):
        raise ValidationError(
            "Regla no válida."
        )

    with transaction.atomic():

        regla = (
            ReglaVentaCruzadaIA.objects
            .filter(
                id=regla_id,
                empresa=empresa,
            )
            .first()
        )

        if regla is None:
            raise ValidationError(
                "La regla no pertenece a tu empresa."
            )

        regla.delete()


def obtener_contexto_promociones(
    empresa,
):
    productos = list(
        productos_empresa_queryset(
            empresa
        )
    )

    promociones = {
        item.producto_id: item
        for item in (
            ProductoPromocionIA.objects
            .filter(
                empresa=empresa,
            )
        )
    }

    for producto in productos:
        producto.promocion_ia_ui = (
            promociones.get(
                producto.id
            )
        )

    reglas = list(
        ReglaVentaCruzadaIA.objects
        .filter(
            empresa=empresa,
        )
        .select_related(
            "producto_origen",
            "producto_recomendado",
        )
        .order_by(
            "prioridad",
            "id",
        )
    )

    estrellas = sum(
        1
        for producto in productos
        if (
            producto.promocion_ia_ui
            and
            producto.promocion_ia_ui.activa
            and
            producto.promocion_ia_ui.es_estrella
        )
    )

    return {
        "productos":
            productos,

        "reglas":
            reglas,

        "productos_estrella_count":
            estrellas,
    }
