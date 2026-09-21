"""
Reglas locales de ocupación de citas.

TNL-CITA-LOCAL-LOCK-V1

Una cita bloquea horario cuando:

1. Está programada; o
2. Está pendiente de confirmación y conserva
   una retención de pago vigente.

Las retenciones vencidas no bloquean.
"""

from django.db.models import Q
from django.utils import timezone

from core.models import Cita


def citas_bloqueantes_queryset(
    *,
    empresa,
    inicio,
    fin,
    ahora=None,
    excluir_cita_id=None,
):
    """
    QuerySet de citas locales que se traslapan con
    el rango solicitado y deben bloquearlo.
    """

    if ahora is None:
        ahora = timezone.now()


    query_estado = (
        Q(
            estado=
                Cita.ESTADO_PROGRAMADA
        )
        |
        Q(
            estado=
                Cita.ESTADO_PENDIENTE_CONFIRMACION,
            retencion_pago_hasta__gt=
                ahora,
        )
    )


    qs = (
        Cita.objects
        .filter(
            empresa=empresa,
            inicio__lt=fin,
            fin__gt=inicio,
        )
        .filter(
            query_estado
        )
    )


    if excluir_cita_id is not None:

        qs = qs.exclude(
            pk=excluir_cita_id
        )


    return qs


def hay_bloqueo_local_cita(
    *,
    empresa,
    inicio,
    fin,
    ahora=None,
    excluir_cita_id=None,
) -> bool:
    """
    Devuelve True cuando existe al menos una cita
    local que debe impedir reservar ese horario.
    """

    return (
        citas_bloqueantes_queryset(
            empresa=empresa,
            inicio=inicio,
            fin=fin,
            ahora=ahora,
            excluir_cita_id=
                excluir_cita_id,
        )
        .exists()
    )


# TNL-CITA-PAYMENT-RESOLVER-V1
def resolver_pago_cita(
    *,
    empresa,
    servicio_producto=None,
):
    """
    Resuelve los valores monetarios autoritativos
    que deben quedar congelados en una Cita.

    Nunca recibe precio, moneda o importe desde
    Typebot o desde el cliente.
    """

    from datetime import timedelta
    from decimal import (
        Decimal,
        ROUND_HALF_UP,
    )

    from django.utils import timezone

    from core.models import (
        ConfiguracionAgenda,
        Producto,
    )


    agenda = (
        ConfiguracionAgenda.objects
        .filter(
            empresa=empresa
        )
        .first()
    )

    if agenda is None:
        agenda = ConfiguracionAgenda(
            empresa=empresa
        )


    politica = (
        str(
            agenda.politica_pago_cita
            or
            ConfiguracionAgenda.POLITICA_SIN_PAGO
        )
        .strip()
    )


    if politica not in {
        ConfiguracionAgenda.POLITICA_SIN_PAGO,
        ConfiguracionAgenda.POLITICA_ANTICIPO,
        ConfiguracionAgenda.POLITICA_PAGO_COMPLETO,
    }:
        raise ValueError(
            "Política de pago de cita inválida."
        )


    requiere_pago = (
        politica
        !=
        ConfiguracionAgenda.POLITICA_SIN_PAGO
    )


    producto = None
    importe_total = Decimal("0.00")
    moneda = ""


    if servicio_producto is not None:

        producto_id = getattr(
            servicio_producto,
            "pk",
            servicio_producto,
        )

        producto = (
            Producto.objects
            .select_related(
                "catalogo"
            )
            .filter(
                pk=producto_id,
            )
            .first()
        )

        if producto is None:
            raise ValueError(
                "El servicio seleccionado no existe."
            )

        if (
            producto.catalogo.empresa_id
            !=
            empresa.pk
        ):
            raise ValueError(
                "El servicio no pertenece a esta empresa."
            )

        if not producto.catalogo.activo:
            raise ValueError(
                "El catálogo del servicio está inactivo."
            )

        if not producto.activo:
            raise ValueError(
                "El servicio seleccionado está inactivo."
            )


        precio = Decimal(
            str(producto.precio)
        )

        if precio <= 0:
            raise ValueError(
                "El servicio debe tener un precio mayor a cero."
            )


        importe_total = precio.quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )


        moneda = str(
            producto.catalogo.moneda
            or ""
        ).strip().upper()


        if len(moneda) != 3:
            raise ValueError(
                "La moneda del catálogo es inválida."
            )


    if requiere_pago and producto is None:
        raise ValueError(
            "La política de pago requiere un servicio del catálogo."
        )


    if (
        politica
        ==
        ConfiguracionAgenda.POLITICA_ANTICIPO
    ):

        porcentaje = Decimal(
            str(
                agenda.porcentaje_anticipo
            )
        )

        if (
            porcentaje <= 0
            or
            porcentaje >= 100
        ):
            raise ValueError(
                "El porcentaje de anticipo debe ser mayor a 0 y menor a 100."
            )

    elif (
        politica
        ==
        ConfiguracionAgenda.POLITICA_PAGO_COMPLETO
    ):
        porcentaje = Decimal("100.00")

    else:
        porcentaje = Decimal("0.00")


    if requiere_pago:

        importe_requerido = (
            importe_total
            *
            porcentaje
            /
            Decimal("100")
        ).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )

        if importe_requerido <= 0:
            raise ValueError(
                "El importe requerido para la cita es inválido."
            )


        retencion_minutos = int(
            agenda.retencion_pago_minutos
        )

        if not (
            5
            <=
            retencion_minutos
            <=
            60
        ):
            raise ValueError(
                "El tiempo de retención debe estar entre 5 y 60 minutos."
            )


        retencion_hasta = (
            timezone.now()
            +
            timedelta(
                minutes=retencion_minutos
            )
        )

    else:

        importe_requerido = Decimal("0.00")
        retencion_minutos = 0
        retencion_hasta = None


    return {
        "politica":
            politica,

        "requiere_pago":
            requiere_pago,

        "servicio_producto":
            producto,

        "servicio":
            (
                str(producto.nombre).strip()
                if producto is not None
                else ""
            ),

        "importe_total":
            importe_total,

        "moneda":
            moneda,

        "porcentaje_pago_requerido":
            porcentaje.quantize(
                Decimal("0.01")
            ),

        "importe_pago_requerido":
            importe_requerido,

        "retencion_pago_minutos":
            retencion_minutos,

        "retencion_pago_hasta":
            retencion_hasta,
    }
