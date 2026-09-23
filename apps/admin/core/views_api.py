from decimal import Decimal
from hmac import compare_digest
from pathlib import Path

from django.db.models import Q
from django.http import JsonResponse

from .models import Bot, Producto


CLAVE_API_PATH = Path(
    "/opt/tunegociolisto/infrastructure/secrets/typebot_catalog_api_key"
)


# =============================================================================
# TNL-CLIENT-LIFECYCLE-API-GUARD-V1
# =============================================================================

def _nl_api_empresa_operativa_error(
    empresa,
):
    """
    Guard comercial central para APIs Typebot.

    El webhook de Mercado Pago queda fuera
    deliberadamente para mantener consistencia
    de pagos ya iniciados.
    """

    from core.services.client_lifecycle import (
        empresa_operativa,
    )

    if empresa_operativa(
        empresa
    ):
        return None

    return JsonResponse(
        {
            "ok": False,
            "error": (
                "El servicio de esta empresa "
                "se encuentra temporalmente "
                "suspendido."
            ),
            "codigo":
                "EMPRESA_SUSPENDIDA",
        },
        status=423,
    )


def _leer_clave_api():
    try:
        return CLAVE_API_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


# TNL-TYPEBOT-BEARER-AUTH-V2
def _autorizacion_typebot_valida(
    autorizacion,
    clave_esperada,
):
    """
    Valida exclusivamente la credencial
    Bearer principal vigente.
    """

    if not clave_esperada:
        return False

    return compare_digest(
        autorizacion,
        f"Bearer {clave_esperada}",
    )





# TNL-PRODUCT-API-IMAGES-V1
def _producto_media_url(field):
    """
    Devuelve URL HTTPS pública de un ImageField.
    No modifica ni lee el archivo físico.
    """
    from django.conf import settings

    if not field:
        return ""

    relative_url = str(
        field.url
    )

    base = str(
        getattr(
            settings,
            "NEGOCIOLISTO_PUBLIC_MEDIA_BASE_URL",
            "https://admin.negociolisto.com.mx",
        )
    ).rstrip("/")

    if not relative_url.startswith("/"):
        relative_url = (
            "/"
            + relative_url
        )

    return (
        base
        + relative_url
    )


def _producto_galeria_urls(producto):

    return [
        _producto_media_url(
            imagen.imagen
        )
        for imagen in (
            producto.galeria.all()
        )
        if (
            imagen.activa
            and imagen.imagen
        )
    ]


def producto_buscar(request):
    if request.method != "GET":
        return JsonResponse(
            {"ok": False, "error": "Método no permitido."},
            status=405,
        )

    clave_esperada = _leer_clave_api()

    if not clave_esperada:
        return JsonResponse(
            {"ok": False, "error": "Servicio no configurado."},
            status=503,
        )

    autorizacion = request.headers.get("Authorization", "")

    if not _autorizacion_typebot_valida(
        autorizacion,
        clave_esperada,
    ):
        respuesta = JsonResponse(
            {"ok": False, "error": "No autorizado."},
            status=401,
        )
        respuesta["WWW-Authenticate"] = "Bearer"
        return respuesta

    consulta = request.GET.get("q", "").strip()
    bot_id = request.GET.get("bot_id", "").strip()

    if not bot_id:
        return JsonResponse(
            {"ok": False, "error": "El parámetro bot_id es obligatorio."},
            status=400,
        )

    if len(consulta) < 2:
        return JsonResponse(
            {
                "ok": False,
                "error": "La búsqueda debe contener al menos 2 caracteres.",
            },
            status=400,
        )

    try:
        bot_id = int(bot_id)
    except (TypeError, ValueError):
        return JsonResponse(
            {"ok": False, "error": "bot_id no es válido."},
            status=400,
        )

    bot = (
        Bot.objects
        .select_related("empresa", "plantilla")
        .filter(id=bot_id, activo=True)
        .first()
    )

    if bot is None:
        return JsonResponse(
            {"ok": False, "error": "Bot no encontrado o inactivo."},
            status=404,
        )

    lifecycle_error = (
        _nl_api_empresa_operativa_error(
            bot.empresa
        )
    )

    if lifecycle_error is not None:
        return lifecycle_error


    if bot.plantilla_id is None:
        return JsonResponse(
            {
                "ok": False,
                "error": "El bot no tiene una plantilla asociada.",
            },
            status=409,
        )

    # ========================================================
    # TNL-PRODUCTO-BUSCAR-SERVICIOS-V2
    #
    # La infraestructura interna sigue utilizando Producto,
    # pero una plantilla clínica representa servicios.
    #
    # Para clínica:
    # - no se usa stock como criterio de disponibilidad;
    # - la tarjeta visible no muestra inventario.
    #
    # Las demás verticales conservan exactamente el
    # comportamiento histórico stock__gt=0.
    # ========================================================

    modo_servicios = (
        str(
            bot.plantilla.tipo
            or ""
        ).strip()
        in {
            "clinica",
            "estetica",
        }
    )


    productos_qs = (
        Producto.objects
        .select_related("catalogo")
        .prefetch_related("galeria")
        .filter(
            catalogo__empresa_id=bot.empresa_id,
            catalogo__plantilla_id=bot.plantilla_id,
            catalogo__activo=True,
            activo=True,
        )
    )


    if not modo_servicios:

        productos_qs = (
            productos_qs.filter(
                stock__gt=0,
            )
        )


    productos = list(
        productos_qs
        .filter(
            Q(nombre__icontains=consulta)
            | Q(descripcion__icontains=consulta)
            | Q(sku__icontains=consulta)
        )
        .order_by("nombre")[:10]
    )

    resultados = [
        {
            "id": producto.id,
            "sku": producto.sku,
            "nombre": producto.nombre,
            "descripcion": producto.descripcion,
            # TNL-PRODUCTO-DECIMAL-OUTPUT-V1
"precio": format(
                producto.precio.quantize(
                    Decimal("0.01"),
                    rounding="ROUND_HALF_UP",
                ),
                ".2f",
            ),
            "stock": format(
                producto.stock.quantize(
                    Decimal("0.01"),
                    rounding="ROUND_HALF_UP",
                ),
                ".2f",
            ),
            "unidad": producto.unidad,
            "moneda": producto.catalogo.moneda,
            "imagen_principal_url": (
                _producto_media_url(
                    producto.imagen_principal
                )
            ),
            "galeria_urls": (
                _producto_galeria_urls(
                    producto
                )
            ),
        }
        for producto in productos
    ]


    tarjeta_descripciones = []


    for item in resultados:

        if modo_servicios:

            descripcion = str(
                item["descripcion"]
                or ""
            ).strip()


            partes = []


            if descripcion:

                partes.append(
                    descripcion
                )


            partes.append(
                (
                    f"💰 Precio: {item['moneda']} "
                    f"${item['precio']}"
                )
            )


            tarjeta_descripciones.append(
                "\n".join(
                    partes
                )
            )

            continue


        # Comportamiento histórico para inventario físico.
        tarjeta_descripciones.append(
            (
                f"💰 Precio: {item['moneda']} "
                f"${item['precio']}\n"
                f"📦 Disponible: {item['stock']} "
                f"{item['unidad']}"
            )
        )


    return JsonResponse(
        {
            "ok": True,
            "consulta": consulta,
            "cantidad": len(resultados),
            "empresa": bot.empresa.nombre,
            "productos": resultados,
            "producto_ids": [item["id"] for item in resultados],
            "skus": [item["sku"] for item in resultados],
            "nombres": [item["nombre"] for item in resultados],
            "descripciones": [item["descripcion"] for item in resultados],
            "precios": [item["precio"] for item in resultados],
            "stocks": [item["stock"] for item in resultados],
            "unidades": [item["unidad"] for item in resultados],
            "monedas": [item["moneda"] for item in resultados],
            "imagenes_principales": [
                item["imagen_principal_url"]
                for item in resultados
            ],
            "galerias": [
                item["galeria_urls"]
                for item in resultados
            ],
        "tarjeta_descripciones": tarjeta_descripciones,
        },
        json_dumps_params={"ensure_ascii": False},
    )


# === VALIDACION DE PRODUCTO PARA TYPEBOT ===
def producto_validar(request):
    """Valida producto, cantidad y stock sin modificar inventario."""
    from decimal import Decimal, InvalidOperation

    if request.method != "GET":
        return JsonResponse(
            {"ok": False, "error": "Método no permitido."},
            status=405,
        )

    clave_esperada = _leer_clave_api()
    if not clave_esperada:
        return JsonResponse(
            {"ok": False, "error": "Servicio no configurado."},
            status=503,
        )

    autorizacion = request.headers.get("Authorization", "")
    if not _autorizacion_typebot_valida(
        autorizacion,
        clave_esperada,
    ):
        respuesta = JsonResponse(
            {"ok": False, "error": "No autorizado."},
            status=401,
        )
        respuesta["WWW-Authenticate"] = "Bearer"
        return respuesta

    bot_id_texto = request.GET.get("bot_id", "").strip()
    producto_id_texto = request.GET.get("producto_id", "").strip()
    cantidad_texto = request.GET.get("cantidad", "").strip()

    if not bot_id_texto or not producto_id_texto or not cantidad_texto:
        return JsonResponse(
            {
                "ok": False,
                "error": (
                    "bot_id, producto_id y cantidad son obligatorios."
                ),
            },
            status=400,
        )

    try:
        bot_id = int(bot_id_texto)
        producto_id = int(producto_id_texto)
        cantidad = Decimal(cantidad_texto)
    except (TypeError, ValueError, InvalidOperation):
        return JsonResponse(
            {"ok": False, "error": "Parámetros no válidos."},
            status=400,
        )

    if cantidad <= 0:
        return JsonResponse(
            {"ok": False, "error": "La cantidad debe ser mayor que cero."},
            status=400,
        )

    bot = (
        Bot.objects.select_related("empresa", "plantilla")
        .filter(id=bot_id, activo=True)
        .first()
    )
    if not bot:
        return JsonResponse(
            {"ok": False, "error": "Bot no encontrado."},
            status=404,
        )

    lifecycle_error = (
        _nl_api_empresa_operativa_error(
            bot.empresa
        )
    )

    if lifecycle_error is not None:
        return lifecycle_error


    productos = Producto.objects.select_related("catalogo").filter(
        id=producto_id,
        activo=True,
        catalogo__activo=True,
        catalogo__empresa=bot.empresa,
    )

    if bot.plantilla_id:
        productos = productos.filter(
            catalogo__plantilla_id=bot.plantilla_id,
        )
    else:
        productos = productos.filter(
            catalogo__plantilla__isnull=True,
        )

    producto = productos.first()
    if not producto:
        return JsonResponse(
            {
                "ok": False,
                "error": "Producto no encontrado para este bot.",
            },
            status=404,
        )

    disponible = producto.stock >= cantidad
    subtotal = (producto.precio * cantidad).quantize(Decimal("0.01"))
    moneda = producto.catalogo.moneda

    return JsonResponse(
        {
            "ok": True,
            "bot_id": bot.id,
            "empresa": bot.empresa.nombre,
            "producto_id": producto.id,
            "sku": producto.sku,
            "nombre": producto.nombre,
            "precio": format(
                producto.precio.quantize(
                    Decimal("0.01"),
                    rounding="ROUND_HALF_UP",
                ),
                ".2f",
            ),
            "cantidad": str(cantidad),
            "stock": format(
                producto.stock.quantize(
                    Decimal("0.01"),
                    rounding="ROUND_HALF_UP",
                ),
                ".2f",
            ),
            "unidad": producto.unidad,
            "moneda": moneda,
            "disponible": disponible,
            "subtotal": str(subtotal),
            "resumen": (
                f"{producto.nombre}\n"
                f"Cantidad: {cantidad} {producto.unidad}\n"
                f"Subtotal: {moneda} ${subtotal}"
            ),
        }
    )


# === CARRITO DE TYPEBOT ===
from django.views.decorators.csrf import csrf_exempt


@csrf_exempt
# ============================================================
# TNL-TYPEBOT-PEDIDO-WHATSAPP-CANAL-V1
# ============================================================

def _resolver_canal_whatsapp_pedido_typebot(
    bot,
):
    """
    Asocia un pedido Typebot únicamente cuando existe
    exactamente un canal WhatsApp activo y compatible
    para el mismo Bot.

    Prioridad:
    - Conserva el comportamiento histórico cuando existe
      exactamente un canal activo con identificador.
    - Si no existe ninguno con identificador, permite como
      fallback exactamente un único canal WhatsApp activo.
    - Nunca elige entre múltiples canales ambiguos.

    Nunca usa empresa_id enviado por Typebot.
    """

    from .models import Canal


    canales_configurados = list(
        Canal.objects
        .filter(
            bot_id=bot.pk,
            tipo="whatsapp",
            activo=True,
        )
        .exclude(
            identificador=""
        )
        .order_by(
            "id"
        )[:2]
    )


    if len(
        canales_configurados
    ) == 1:

        return canales_configurados[0]


    if len(
        canales_configurados
    ) > 1:

        return None


    canales_activos = list(
        Canal.objects
        .filter(
            bot_id=bot.pk,
            tipo="whatsapp",
            activo=True,
        )
        .order_by(
            "id"
        )[:2]
    )


    if len(
        canales_activos
    ) != 1:

        return None


    return canales_activos[0]


# TNL-TYPEBOT-CARRITO-AGREGAR-CSRF-V1
@csrf_exempt
def carrito_producto_agregar(request):
    """Crea o actualiza un carrito de Typebot sin confirmar inventario."""
    from decimal import Decimal, InvalidOperation
    import json
    from uuid import uuid4

    from django.db import transaction

    from .models import Pedido, PedidoDetalle

    if request.method != "POST":
        return JsonResponse(
            {"ok": False, "error": "Método no permitido."},
            status=405,
        )

    clave_esperada = _leer_clave_api()
    if not clave_esperada:
        return JsonResponse(
            {"ok": False, "error": "Servicio no configurado."},
            status=503,
        )

    autorizacion = request.headers.get("Authorization", "")
    if not _autorizacion_typebot_valida(
        autorizacion,
        clave_esperada,
    ):
        respuesta = JsonResponse(
            {"ok": False, "error": "No autorizado."},
            status=401,
        )
        respuesta["WWW-Authenticate"] = "Bearer"
        return respuesta

    try:
        if request.content_type == "application/json":
            datos = json.loads(request.body.decode("utf-8"))
        else:
            datos = request.POST.dict()
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse(
            {"ok": False, "error": "El cuerpo JSON no es válido."},
            status=400,
        )

    if not isinstance(datos, dict):
        return JsonResponse(
            {"ok": False, "error": "El cuerpo debe ser un objeto JSON."},
            status=400,
        )

    bot_id_texto = str(datos.get("bot_id", "")).strip()
    producto_id_texto = str(datos.get("producto_id", "")).strip()
    cantidad_texto = str(datos.get("cantidad", "")).strip()
    carrito_token = str(datos.get("carrito_token", "")).strip()

    if not bot_id_texto or not producto_id_texto or not cantidad_texto:
        return JsonResponse(
            {
                "ok": False,
                "error": "bot_id, producto_id y cantidad son obligatorios.",
            },
            status=400,
        )

    if len(carrito_token) > 64:
        return JsonResponse(
            {"ok": False, "error": "carrito_token no es válido."},
            status=400,
        )

    try:
        bot_id = int(bot_id_texto)
        producto_id = int(producto_id_texto)
        cantidad = Decimal(cantidad_texto)
    except (TypeError, ValueError, InvalidOperation):
        return JsonResponse(
            {"ok": False, "error": "Parámetros no válidos."},
            status=400,
        )

    if cantidad <= 0:
        return JsonResponse(
            {"ok": False, "error": "La cantidad debe ser mayor que cero."},
            status=400,
        )

    bot = (
        Bot.objects.select_related("empresa", "plantilla")
        .filter(id=bot_id, activo=True)
        .first()
    )
    if not bot:
        return JsonResponse(
            {"ok": False, "error": "Bot no encontrado."},
            status=404,
        )

    lifecycle_error = (
        _nl_api_empresa_operativa_error(
            bot.empresa
        )
    )

    if lifecycle_error is not None:
        return lifecycle_error


    try:
        with transaction.atomic():
            productos = (
                Producto.objects.select_for_update()
                .select_related("catalogo")
                .filter(
                    id=producto_id,
                    activo=True,
                    catalogo__activo=True,
                    catalogo__empresa=bot.empresa,
                )
            )

            if bot.plantilla_id:
                productos = productos.filter(
                    catalogo__plantilla_id=bot.plantilla_id,
                )
            else:
                productos = productos.filter(
                    catalogo__plantilla__isnull=True,
                )

            producto = productos.first()
            if not producto:
                return JsonResponse(
                    {
                        "ok": False,
                        "error": "Producto no encontrado para este bot.",
                    },
                    status=404,
                )

            moneda = producto.catalogo.moneda
            carrito_creado = False

            canal_typebot = (
                _resolver_canal_whatsapp_pedido_typebot(
                    bot
                )
            )

            if carrito_token:
                pedido = (
                    Pedido.objects.select_for_update()
                    .filter(
                        empresa=bot.empresa,
                        identificador_externo=f"typebot:{carrito_token}",
                        estado="carrito",
                    )
                    .first()
                )
                if not pedido:
                    return JsonResponse(
                        {
                            "ok": False,
                            "error": "El carrito no existe o ya fue procesado.",
                        },
                        status=404,
                    )
                if (
                    pedido.canal_id is None
                    and
                    canal_typebot is not None
                ):
                    pedido.canal = canal_typebot
                    pedido.save(
                        update_fields=[
                            "canal",
                            "actualizado_en",
                        ]
                    )

                if pedido.moneda != moneda:
                    return JsonResponse(
                        {
                            "ok": False,
                            "error": "El producto usa una moneda diferente.",
                        },
                        status=400,
                    )
            else:
                carrito_token = uuid4().hex
                pedido = Pedido.objects.create(
                    empresa=bot.empresa,
                    canal=canal_typebot,
                    numero=f"TB-{uuid4().hex[:12].upper()}",
                    estado="carrito",
                    cliente_nombre="",
                    cliente_telefono="",
                    cliente_email="",
                    direccion_entrega="",
                    notas="",
                    moneda=moneda,
                    subtotal=Decimal("0"),
                    descuento=Decimal("0"),
                    total=Decimal("0"),
                    identificador_externo=f"typebot:{carrito_token}",
                )
                carrito_creado = True

            detalle = (
                PedidoDetalle.objects.select_for_update()
                .filter(pedido=pedido, producto=producto)
                .first()
            )
            cantidad_total = cantidad
            if detalle:
                cantidad_total += detalle.cantidad

            if cantidad_total > producto.stock:
                return JsonResponse(
                    {
                        "ok": False,
                        "error": "Existencia insuficiente.",
                        "producto_id": producto.id,
                        "nombre": producto.nombre,
                        "solicitado": str(cantidad_total),
                        "stock": format(
                producto.stock.quantize(
                    Decimal("0.01"),
                    rounding="ROUND_HALF_UP",
                ),
                ".2f",
            ),
                        "unidad": producto.unidad,
                    },
                    status=409,
                )

            precio = producto.precio
            importe = (precio * cantidad_total).quantize(Decimal("0.01"))

            if detalle:
                detalle.sku = producto.sku
                detalle.nombre_producto = producto.nombre
                detalle.cantidad = cantidad_total
                detalle.precio_unitario = precio
                detalle.descuento = Decimal("0")
                detalle.importe = importe
                detalle.save(
                    update_fields=[
                        "sku",
                        "nombre_producto",
                        "cantidad",
                        "precio_unitario",
                        "descuento",
                        "importe",
                    ]
                )
            else:
                PedidoDetalle.objects.create(
                    pedido=pedido,
                    producto=producto,
                    sku=producto.sku,
                    nombre_producto=producto.nombre,
                    cantidad=cantidad_total,
                    precio_unitario=precio,
                    descuento=Decimal("0"),
                    importe=importe,
                )

            detalles = list(
                PedidoDetalle.objects.filter(pedido=pedido)
                .select_related("producto")
                .order_by("id")
            )
            subtotal = sum(
                (item.importe for item in detalles),
                Decimal("0"),
            ).quantize(Decimal("0.01"))
            total = max(
                subtotal - pedido.descuento,
                Decimal("0"),
            ).quantize(Decimal("0.01"))

            pedido.subtotal = subtotal
            pedido.total = total
            pedido.save(update_fields=["subtotal", "total", "actualizado_en"])

            lineas = [
                {
                    "producto_id": item.producto_id,
                    "sku": item.sku,
                    "nombre": item.nombre_producto,
                    "cantidad": str(item.cantidad),
                    "precio_unitario": str(item.precio_unitario),
                    "importe": str(item.importe),
                }
                for item in detalles
            ]

    except Exception:
        return JsonResponse(
            {
                "ok": False,
                "error": "No fue posible actualizar el carrito.",
            },
            status=500,
        )

    return JsonResponse(
        {
            "ok": True,
            "carrito_creado": carrito_creado,
            "carrito_token": carrito_token,
            "pedido_id": pedido.id,
            "pedido_numero": pedido.numero,
            "estado": pedido.estado,
            "empresa": bot.empresa.nombre,
            "moneda": pedido.moneda,
            "subtotal": str(pedido.subtotal),
            "descuento": str(pedido.descuento),
            "total": str(pedido.total),
            "cantidad_productos": len(lineas),
            "lineas": lineas,
            "mensaje": f"{producto.nombre} fue agregado al pedido.",
        }
    )


# === DATOS DE CLIENTE PARA CARRITO TYPEBOT ===
@csrf_exempt
def carrito_datos_guardar(request):
    """Guarda datos del cliente en un carrito sin confirmarlo."""
    import json

    from django.core.exceptions import ValidationError
    from django.core.validators import validate_email
    from django.db import transaction

    from .models import Pedido

    if request.method != "POST":
        return JsonResponse(
            {"ok": False, "error": "Método no permitido."},
            status=405,
        )

    clave_esperada = _leer_clave_api()
    if not clave_esperada:
        return JsonResponse(
            {"ok": False, "error": "Servicio no configurado."},
            status=503,
        )

    autorizacion = request.headers.get("Authorization", "")
    if not _autorizacion_typebot_valida(
        autorizacion,
        clave_esperada,
    ):
        respuesta = JsonResponse(
            {"ok": False, "error": "No autorizado."},
            status=401,
        )
        respuesta["WWW-Authenticate"] = "Bearer"
        return respuesta

    try:
        if request.content_type == "application/json":
            datos = json.loads(request.body.decode("utf-8"))
        else:
            datos = request.POST.dict()
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse(
            {"ok": False, "error": "El cuerpo JSON no es válido."},
            status=400,
        )

    if not isinstance(datos, dict):
        return JsonResponse(
            {"ok": False, "error": "El cuerpo debe ser un objeto JSON."},
            status=400,
        )

    bot_id_texto = str(datos.get("bot_id", "")).strip()
    carrito_token = str(datos.get("carrito_token", "")).strip()
    cliente_nombre = str(datos.get("cliente_nombre", "")).strip()
    cliente_telefono = str(datos.get("cliente_telefono", "")).strip()
    cliente_email = str(datos.get("cliente_email", "")).strip()
    direccion_entrega = str(datos.get("direccion_entrega", "")).strip()
    notas = str(datos.get("notas", "")).strip()

    if cliente_email.casefold() in {"omitir", "ninguno", "ninguna", "no"}:
        cliente_email = ""
    if notas.casefold() in {"ninguno", "ninguna", "no"}:
        notas = ""

    if not bot_id_texto or not carrito_token:
        return JsonResponse(
            {
                "ok": False,
                "error": "bot_id y carrito_token son obligatorios.",
            },
            status=400,
        )

    if not cliente_nombre or not cliente_telefono or not direccion_entrega:
        return JsonResponse(
            {
                "ok": False,
                "error": (
                    "Nombre, teléfono y dirección de entrega son obligatorios."
                ),
            },
            status=400,
        )

    if len(carrito_token) > 64:
        return JsonResponse(
            {"ok": False, "error": "carrito_token no es válido."},
            status=400,
        )

    if len(cliente_nombre) > 200:
        return JsonResponse(
            {"ok": False, "error": "El nombre es demasiado largo."},
            status=400,
        )

    if len(cliente_telefono) > 50:
        return JsonResponse(
            {"ok": False, "error": "El teléfono es demasiado largo."},
            status=400,
        )

    if cliente_email:
        try:
            validate_email(cliente_email)
        except ValidationError:
            return JsonResponse(
                {"ok": False, "error": "El correo electrónico no es válido."},
                status=400,
            )

    try:
        bot_id = int(bot_id_texto)
    except (TypeError, ValueError):
        return JsonResponse(
            {"ok": False, "error": "bot_id no es válido."},
            status=400,
        )

    bot = (
        Bot.objects.select_related("empresa")
        .filter(id=bot_id, activo=True)
        .first()
    )
    if not bot:
        return JsonResponse(
            {"ok": False, "error": "Bot no encontrado."},
            status=404,
        )

    lifecycle_error = (
        _nl_api_empresa_operativa_error(
            bot.empresa
        )
    )

    if lifecycle_error is not None:
        return lifecycle_error


    with transaction.atomic():
        pedido = (
            Pedido.objects.select_for_update()
            .filter(
                empresa=bot.empresa,
                identificador_externo=f"typebot:{carrito_token}",
                estado="carrito",
            )
            .first()
        )
        if not pedido:
            return JsonResponse(
                {
                    "ok": False,
                    "error": "El carrito no existe o ya fue procesado.",
                },
                status=404,
            )

        if not pedido.detalles.exists():
            return JsonResponse(
                {"ok": False, "error": "El carrito está vacío."},
                status=400,
            )

        pedido.cliente_nombre = cliente_nombre
        pedido.cliente_telefono = cliente_telefono
        pedido.cliente_email = cliente_email
        pedido.direccion_entrega = direccion_entrega
        pedido.notas = notas
        pedido.save(
            update_fields=[
                "cliente_nombre",
                "cliente_telefono",
                "cliente_email",
                "direccion_entrega",
                "notas",
                "actualizado_en",
            ]
        )

    return JsonResponse(
        {
            "ok": True,
            "datos_guardados": True,
            "carrito_token": carrito_token,
            "pedido_id": pedido.id,
            "pedido_numero": pedido.numero,
            "estado": pedido.estado,
            "cliente_nombre": pedido.cliente_nombre,
            "cliente_telefono": pedido.cliente_telefono,
            "cliente_email": pedido.cliente_email,
            "direccion_entrega": pedido.direccion_entrega,
            "notas": pedido.notas,
            "moneda": pedido.moneda,
            "total": str(pedido.total),
            "mensaje": "Datos del pedido guardados correctamente.",
        }
    )


# === CONFIRMACION DE PEDIDO PARA TYPEBOT ===
@csrf_exempt
def carrito_confirmar(request):
    """Confirma un carrito usando el motor transaccional existente."""
    import json

    from django.core.exceptions import ValidationError

    from .models import Pedido
    from .services.pedidos import confirmar_pedido

    if request.method != "POST":
        return JsonResponse(
            {"ok": False, "error": "Método no permitido."},
            status=405,
        )

    clave_esperada = _leer_clave_api()
    if not clave_esperada:
        return JsonResponse(
            {"ok": False, "error": "Servicio no configurado."},
            status=503,
        )

    autorizacion = request.headers.get("Authorization", "")
    if not _autorizacion_typebot_valida(
        autorizacion,
        clave_esperada,
    ):
        respuesta = JsonResponse(
            {"ok": False, "error": "No autorizado."},
            status=401,
        )
        respuesta["WWW-Authenticate"] = "Bearer"
        return respuesta

    try:
        if request.content_type == "application/json":
            datos = json.loads(request.body.decode("utf-8"))
        else:
            datos = request.POST.dict()
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse(
            {"ok": False, "error": "El cuerpo JSON no es válido."},
            status=400,
        )

    if not isinstance(datos, dict):
        return JsonResponse(
            {"ok": False, "error": "El cuerpo debe ser un objeto JSON."},
            status=400,
        )

    bot_id_texto = str(datos.get("bot_id", "")).strip()
    carrito_token = str(datos.get("carrito_token", "")).strip()

    if not bot_id_texto or not carrito_token:
        return JsonResponse(
            {
                "ok": False,
                "error": "bot_id y carrito_token son obligatorios.",
            },
            status=400,
        )

    if len(carrito_token) > 64:
        return JsonResponse(
            {"ok": False, "error": "carrito_token no es válido."},
            status=400,
        )

    try:
        bot_id = int(bot_id_texto)
    except (TypeError, ValueError):
        return JsonResponse(
            {"ok": False, "error": "bot_id no es válido."},
            status=400,
        )

    bot = (
        Bot.objects.select_related("empresa")
        .filter(id=bot_id, activo=True)
        .first()
    )
    if not bot:
        return JsonResponse(
            {"ok": False, "error": "Bot no encontrado."},
            status=404,
        )

    lifecycle_error = (
        _nl_api_empresa_operativa_error(
            bot.empresa
        )
    )

    if lifecycle_error is not None:
        return lifecycle_error


    pedido = (
        Pedido.objects.filter(
            empresa=bot.empresa,
            identificador_externo=f"typebot:{carrito_token}",
        )
        .first()
    )
    if not pedido:
        return JsonResponse(
            {"ok": False, "error": "Pedido no encontrado."},
            status=404,
        )

    if pedido.estado != "carrito":
        return JsonResponse(
            {
                "ok": False,
                "error": "El pedido ya no está disponible para confirmar.",
                "pedido_numero": pedido.numero,
                "estado": pedido.estado,
            },
            status=409,
        )

    if not (
        pedido.cliente_nombre.strip()
        and pedido.cliente_telefono.strip()
        and pedido.direccion_entrega.strip()
    ):
        return JsonResponse(
            {
                "ok": False,
                "error": "Faltan datos obligatorios del cliente.",
            },
            status=400,
        )

    try:
        pedido = confirmar_pedido(pedido_id=pedido.id)
    except ValidationError as error:
        mensajes = getattr(error, "messages", None) or [str(error)]
        return JsonResponse(
            {
                "ok": False,
                "error": mensajes[0],
                "errores": mensajes,
                "pedido_numero": pedido.numero,
            },
            status=409,
        )

    return JsonResponse(
        {
            "ok": True,
            "pedido_confirmado": True,
            "pedido_id": pedido.id,
            "pedido_numero": pedido.numero,
            "estado": pedido.estado,
            "confirmado_en": (
                pedido.confirmado_en.isoformat()
                if pedido.confirmado_en
                else None
            ),
            "empresa": pedido.empresa.nombre,
            "cliente_nombre": pedido.cliente_nombre,
            "moneda": pedido.moneda,
            "subtotal": str(pedido.subtotal),
            "descuento": str(pedido.descuento),
            "total": str(pedido.total),
            "mensaje": f"Pedido {pedido.numero} confirmado correctamente.",
        }
    )


# === CANCELACION DE PEDIDO PARA TYPEBOT ===
@csrf_exempt
def carrito_cancelar(request):
    """Cancela un pedido de Typebot sin modificar inventario."""
    import json

    from django.core.exceptions import ValidationError

    from .models import Pedido
    from .services.pedidos import cancelar_pedido_cliente

    if request.method != "POST":
        return JsonResponse(
            {"ok": False, "error": "Método no permitido."},
            status=405,
        )

    clave_esperada = _leer_clave_api()
    if not clave_esperada:
        return JsonResponse(
            {"ok": False, "error": "Servicio no configurado."},
            status=503,
        )

    autorizacion = request.headers.get("Authorization", "")
    if not _autorizacion_typebot_valida(
        autorizacion,
        clave_esperada,
    ):
        respuesta = JsonResponse(
            {"ok": False, "error": "No autorizado."},
            status=401,
        )
        respuesta["WWW-Authenticate"] = "Bearer"
        return respuesta

    try:
        if request.content_type == "application/json":
            datos = json.loads(request.body.decode("utf-8"))
        else:
            datos = request.POST.dict()
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse(
            {"ok": False, "error": "El cuerpo JSON no es válido."},
            status=400,
        )

    if not isinstance(datos, dict):
        return JsonResponse(
            {"ok": False, "error": "El cuerpo debe ser un objeto JSON."},
            status=400,
        )

    bot_id_texto = str(datos.get("bot_id", "")).strip()
    carrito_token = str(datos.get("carrito_token", "")).strip()

    if not bot_id_texto or not carrito_token:
        return JsonResponse(
            {"ok": False, "error": "bot_id y carrito_token son obligatorios."},
            status=400,
        )

    if len(carrito_token) > 64:
        return JsonResponse(
            {"ok": False, "error": "carrito_token no es válido."},
            status=400,
        )

    try:
        bot_id = int(bot_id_texto)
    except (TypeError, ValueError):
        return JsonResponse(
            {"ok": False, "error": "bot_id no es válido."},
            status=400,
        )

    bot = (
        Bot.objects.select_related("empresa")
        .filter(id=bot_id, activo=True)
        .first()
    )
    if not bot:
        return JsonResponse(
            {"ok": False, "error": "Bot no encontrado."},
            status=404,
        )

    lifecycle_error = (
        _nl_api_empresa_operativa_error(
            bot.empresa
        )
    )

    if lifecycle_error is not None:
        return lifecycle_error


    pedido = (
        Pedido.objects.filter(
            empresa=bot.empresa,
            identificador_externo=f"typebot:{carrito_token}",
        )
        .first()
    )
    if not pedido:
        return JsonResponse(
            {"ok": False, "error": "Pedido no encontrado."},
            status=404,
        )

    # TNL-CANCELACION-CLIENTE-V1
    # La regla de cancelación vive únicamente en
    # services.pedidos.cancelar_pedido_cliente, que bloquea
    # el pedido y vuelve a leer su estado.
    try:
        resultado = cancelar_pedido_cliente(pedido_id=pedido.id)
    except Pedido.DoesNotExist:
        return JsonResponse(
            {"ok": False, "error": "Pedido no encontrado."},
            status=404,
        )
    except ValidationError as exc:
        pedido.refresh_from_db(fields=["estado"])
        return JsonResponse(
            {
                "ok": False,
                "error": exc.messages[0],
                "pedido_numero": pedido.numero,
                "estado": pedido.estado,
            },
            status=409,
        )

    pedido = resultado["pedido"]

    if not resultado["cambio_real"]:
        return JsonResponse(
            {
                "ok": True,
                "pedido_cancelado": True,
                "pedido_id": pedido.id,
                "pedido_numero": pedido.numero,
                "estado": pedido.estado,
                "mensaje": f"El pedido {pedido.numero} ya estaba cancelado.",
            }
        )

    return JsonResponse(
        {
            "ok": True,
            "pedido_cancelado": True,
            "pedido_id": pedido.id,
            "pedido_numero": pedido.numero,
            "estado": pedido.estado,
            "total": str(pedido.total),
            "mensaje": f"Pedido {pedido.numero} cancelado correctamente.",
        }
    )


# === CONSULTA DE PEDIDO PARA TYPEBOT ===
def pedido_consultar(request):
    """Consulta un pedido del bot validando número y teléfono del cliente."""
    if request.method != "GET":
        return JsonResponse(
            {"ok": False, "error": "Método no permitido."}, status=405
        )

    clave_esperada = _leer_clave_api()
    if not clave_esperada:
        return JsonResponse(
            {"ok": False, "error": "Servicio no configurado."}, status=503
        )

    autorizacion = request.headers.get("Authorization", "")
    if not _autorizacion_typebot_valida(
        autorizacion,
        clave_esperada,
    ):
        respuesta = JsonResponse(
            {"ok": False, "error": "No autorizado."}, status=401
        )
        respuesta["WWW-Authenticate"] = "Bearer"
        return respuesta

    bot_id_texto = request.GET.get("bot_id", "").strip()
    numero = request.GET.get("numero", "").strip().upper()
    telefono = "".join(
        caracter
        for caracter in request.GET.get("telefono", "")
        if caracter.isdigit()
    )

    if not bot_id_texto or not numero or not telefono:
        return JsonResponse(
            {
                "ok": False,
                "encontrado": False,
                "error": "bot_id, numero y telefono son obligatorios.",
            },
            status=400,
        )

    try:
        bot_id = int(bot_id_texto)
    except (TypeError, ValueError):
        return JsonResponse(
            {"ok": False, "encontrado": False, "error": "bot_id no es válido."},
            status=400,
        )

    bot = (
        Bot.objects.select_related("empresa")
        .filter(id=bot_id, activo=True)
        .first()
    )
    if not bot:
        return JsonResponse(
            {"ok": False, "encontrado": False, "error": "Bot no encontrado."},
            status=404,
        )

    lifecycle_error = (
        _nl_api_empresa_operativa_error(
            bot.empresa
        )
    )

    if lifecycle_error is not None:
        return lifecycle_error


    from .models import Pedido

    pedido = (
        Pedido.objects.prefetch_related("detalles")
        .filter(empresa=bot.empresa, numero__iexact=numero)
        .first()
    )
    telefono_guardado = ""
    if pedido:
        telefono_guardado = "".join(
            caracter
            for caracter in pedido.cliente_telefono
            if caracter.isdigit()
        )

    # Misma respuesta para pedido inexistente o teléfono incorrecto.
    if not pedido or not compare_digest(telefono, telefono_guardado):
        return JsonResponse(
            {
                "ok": True,
                "encontrado": False,
                "cantidad_productos": 0,
                "mensaje": "No encontramos un pedido con esos datos.",
            }
        )

    lineas = [
        {
            "sku": detalle.sku,
            "nombre": detalle.nombre_producto,
            "cantidad": str(detalle.cantidad),
            "precio_unitario": str(detalle.precio_unitario),
            "importe": str(detalle.importe),
        }
        for detalle in pedido.detalles.all()
    ]
    productos_resumen = "\n".join(
        f"• {linea['nombre']} — {linea['cantidad']}"
        for linea in lineas
    )

    return JsonResponse(
        {
            "ok": True,
            "encontrado": True,
            "pedido_numero": pedido.numero,
            "estado": pedido.estado,
            "cliente_nombre": pedido.cliente_nombre,
            "moneda": pedido.moneda,
            "total": str(pedido.total),
            "cantidad_productos": len(lineas),
            "lineas": lineas,
            "productos_resumen": productos_resumen,
            "mensaje": f"Pedido {pedido.numero}: {pedido.estado}.",
        }
    )


# =============================================================================
# TNL-TYPEBOT-CITAS-API-V1
# API de agenda para Typebot.
#
# Seguridad:
#   Bearer compartido de la API Typebot existente.
#   bot_id determina exclusivamente la empresa.
# =============================================================================


def _citas_api_error_auth(
    request,
):

    clave_esperada = (
        _leer_clave_api()
    )

    if not clave_esperada:

        return JsonResponse(
            {
                "ok": False,
                "error":
                    "Servicio no configurado.",
                "codigo":
                    "API_NO_CONFIGURADA",
            },
            status=503,
        )


    autorizacion = (
        request.headers.get(
            "Authorization",
            "",
        )
    )


    if not _autorizacion_typebot_valida(
        autorizacion,
        clave_esperada,
    ):

        respuesta = JsonResponse(
            {
                "ok": False,
                "error":
                    "No autorizado.",
                "codigo":
                    "NO_AUTORIZADO",
            },
            status=401,
        )

        respuesta[
            "WWW-Authenticate"
        ] = "Bearer"

        return respuesta


    return None


def _citas_api_leer_datos(
    request,
):

    import json


    try:

        content_type = str(
            request.content_type
            or
            ""
        ).lower()


        if content_type.startswith(
            "application/json"
        ):

            raw = (
                request.body.decode(
                    "utf-8"
                )
            )

            datos = (
                json.loads(raw)
                if raw
                else {}
            )

        else:

            datos = (
                request.POST.dict()
            )


    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
    ):

        return (
            None,
            JsonResponse(
                {
                    "ok": False,
                    "error":
                        "El cuerpo JSON no es válido.",
                    "codigo":
                        "JSON_INVALIDO",
                },
                status=400,
            ),
        )


    if not isinstance(
        datos,
        dict,
    ):

        return (
            None,
            JsonResponse(
                {
                    "ok": False,
                    "error":
                        "El cuerpo debe ser un objeto JSON.",
                    "codigo":
                        "JSON_OBJETO_REQUERIDO",
                },
                status=400,
            ),
        )


    return (
        datos,
        None,
    )


def _citas_api_resolver_bot(
    bot_id_value,
):

    bot_id_texto = str(
        bot_id_value
        or
        ""
    ).strip()


    if not bot_id_texto:

        return (
            None,
            JsonResponse(
                {
                    "ok": False,
                    "error":
                        "bot_id es obligatorio.",
                    "codigo":
                        "BOT_ID_REQUERIDO",
                },
                status=400,
            ),
        )


    try:

        bot_id = int(
            bot_id_texto
        )

    except (
        TypeError,
        ValueError,
    ):

        return (
            None,
            JsonResponse(
                {
                    "ok": False,
                    "error":
                        "bot_id no es válido.",
                    "codigo":
                        "BOT_ID_INVALIDO",
                },
                status=400,
            ),
        )


    bot = (
        Bot.objects
        .select_related(
            "empresa"
        )
        .filter(
            id=bot_id,
            activo=True,
        )
        .first()
    )


    if bot is None:

        return (
            None,
            JsonResponse(
                {
                    "ok": False,
                    "error":
                        "Bot no encontrado o inactivo.",
                    "codigo":
                        "BOT_NO_ENCONTRADO",
                },
                status=404,
            ),
        )

    lifecycle_error = (
        _nl_api_empresa_operativa_error(
            bot.empresa
        )
    )

    if lifecycle_error is not None:

        return (
            None,
            lifecycle_error,
        )



    return (
        bot,
        None,
    )


def _citas_api_datetime(
    value,
    nombre,
):

    from datetime import (
        datetime,
    )

    from django.utils import (
        timezone,
    )


    texto = str(
        value
        or
        ""
    ).strip()


    if not texto:

        raise ValueError(
            f"{nombre} es obligatorio."
        )


    # Compatibilidad ISO-8601 con Z.
    if texto.endswith(
        "Z"
    ):

        texto = (
            texto[:-1]
            +
            "+00:00"
        )


    try:

        value_dt = (
            datetime.fromisoformat(
                texto
            )
        )

    except ValueError as exc:

        raise ValueError(
            (
                f"{nombre} debe usar "
                "formato ISO-8601."
            )
        ) from exc


    if timezone.is_naive(
        value_dt
    ):

        raise ValueError(
            (
                f"{nombre} debe incluir "
                "zona horaria."
            )
        )


    return value_dt


# TNL-CITAS-FECHA-HORA-V1
def _citas_api_resolver_horario(
    datos,
    empresa,
):
    """
    Resuelve el horario de una cita usando uno
    de dos contratos compatibles:

    1. inicio + fin ISO-8601 con zona horaria.
    2. fecha + hora + duracion_minutos.

    Para el contrato amigable la zona horaria
    se obtiene de ConfiguracionGoogleCalendar
    de la empresa correspondiente.
    """

    from datetime import (
        datetime,
        timedelta,
        timezone as datetime_timezone,
    )

    from zoneinfo import (
        ZoneInfo,
        ZoneInfoNotFoundError,
    )

    from core.models import (
        ConfiguracionAgenda,
        ConfiguracionGoogleCalendar,
    )


    inicio_raw = str(
        datos.get(
            "inicio"
        )
        or
        ""
    ).strip()

    fin_raw = str(
        datos.get(
            "fin"
        )
        or
        ""
    ).strip()


    # --------------------------------------------------------
    # CONTRATO ORIGINAL.
    #
    # Si existe inicio o fin, conservamos exactamente
    # el comportamiento previo y exigimos ambos.
    # --------------------------------------------------------

    if (
        inicio_raw
        or
        fin_raw
    ):

        inicio = (
            _citas_api_datetime(
                inicio_raw,
                "inicio",
            )
        )

        fin = (
            _citas_api_datetime(
                fin_raw,
                "fin",
            )
        )


        if fin <= inicio:

            raise ValueError(
                (
                    "fin debe ser posterior "
                    "a inicio."
                )
            )


        return (
            inicio,
            fin,
        )


    # --------------------------------------------------------
    # CONTRATO AMIGABLE PARA TYPEBOT.
    # --------------------------------------------------------

    fecha_texto = str(
        datos.get(
            "fecha"
        )
        or
        ""
    ).strip()

    hora_texto = str(
        datos.get(
            "hora"
        )
        or
        ""
    ).strip()

    # TNL-CITAS-DURACION-ZERO-FIX-V1
    duracion_raw = datos.get(
        "duracion_minutos"
    )


    # bool es subtipo de int en Python.
    # No aceptamos true/false como duración.
    if isinstance(
        duracion_raw,
        bool,
    ):

        raise ValueError(
            (
                "duracion_minutos debe "
                "ser un número entero."
            )
        )


    duracion_texto = (
        ""
        if duracion_raw is None
        else str(
            duracion_raw
        ).strip()
    )


    if not fecha_texto:

        raise ValueError(
            "fecha es obligatoria."
        )


    if not hora_texto:

        raise ValueError(
            "hora es obligatoria."
        )


    try:

        fecha = (
            datetime.strptime(
                fecha_texto,
                "%Y-%m-%d",
            )
            .date()
        )

    except ValueError as exc:

        raise ValueError(
            (
                "fecha debe usar formato "
                "AAAA-MM-DD."
            )
        ) from exc


    try:

        hora = (
            datetime.strptime(
                hora_texto,
                "%H:%M",
            )
            .time()
        )

    except ValueError as exc:

        raise ValueError(
            (
                "hora debe usar formato "
                "HH:MM de 24 horas."
            )
        ) from exc


    if duracion_texto:

        try:

            duracion_minutos = int(
                duracion_texto
            )

        except (
            TypeError,
            ValueError,
        ) as exc:

            raise ValueError(
                (
                    "duracion_minutos debe "
                    "ser un número entero."
                )
            ) from exc

    else:

        configuracion_agenda = (
            ConfiguracionAgenda.objects
            .filter(
                empresa=empresa
            )
            .only(
                "duracion_predeterminada_minutos"
            )
            .first()
        )

        if configuracion_agenda is not None:

            duracion_minutos = int(
                configuracion_agenda
                .duracion_predeterminada_minutos
            )

        else:

            # Compatibilidad histórica para una
            # empresa que todavía no tenga la nueva
            # configuración de agenda.
            duracion_minutos = 30


    if not (
        1
        <=
        duracion_minutos
        <=
        1440
    ):

        raise ValueError(
            (
                "duracion_minutos debe estar "
                "entre 1 y 1440."
            )
        )


    configuracion = (
        ConfiguracionGoogleCalendar.objects
        .filter(
            empresa=empresa
        )
        .only(
            "zona_horaria"
        )
        .first()
    )


    zona_horaria = str(
        (
            configuracion.zona_horaria
            if configuracion
            else ""
        )
        or
        ""
    ).strip()


    if not zona_horaria:

        raise ValueError(
            (
                "La empresa no tiene una "
                "zona horaria de Google Calendar "
                "configurada."
            )
        )


    try:

        zona = ZoneInfo(
            zona_horaria
        )

    except ZoneInfoNotFoundError as exc:

        raise ValueError(
            (
                "La zona horaria configurada "
                "no es válida."
            )
        ) from exc


    naive = datetime.combine(
        fecha,
        hora,
    )


    # --------------------------------------------------------
    # Validación DST genérica.
    #
    # Evita aceptar horas inexistentes o ambiguas en
    # empresas cuya zona horaria tenga cambios estacionales.
    # --------------------------------------------------------

    candidatos = []


    for fold in (
        0,
        1,
    ):

        aware = naive.replace(
            tzinfo=zona,
            fold=fold,
        )

        roundtrip = (
            aware
            .astimezone(
                datetime_timezone.utc
            )
            .astimezone(
                zona
            )
        )


        if (
            roundtrip.replace(
                tzinfo=None
            )
            ==
            naive
        ):

            candidatos.append(
                aware
            )


    if not candidatos:

        raise ValueError(
            (
                "La hora indicada no existe "
                "en la zona horaria configurada."
            )
        )


    offsets = {
        candidato.utcoffset()
        for candidato in candidatos
    }


    if len(offsets) > 1:

        raise ValueError(
            (
                "La hora indicada es ambigua "
                "por un cambio de horario."
            )
        )


    inicio = candidatos[0]

    fin = (
        inicio
        +
        timedelta(
            minutes=
                duracion_minutos
        )
    )


    return (
        inicio,
        fin,
    )



def _citas_api_validar_longitud(
    value,
    *,
    nombre,
    max_length,
):

    texto = str(
        value
        or
        ""
    ).strip()


    if len(texto) > max_length:

        raise ValueError(
            (
                f"{nombre} supera "
                f"{max_length} caracteres."
            )
        )


    return texto


def _citas_api_error_servicio(
    exc,
):

    from core.services.google_calendar_citas import (
        GoogleCalendarCitaNoEncontradaError,
        GoogleCalendarCitasError,
        GoogleCalendarHorarioOcupadoError,
        GoogleCalendarNoConectadoError,
    )


    if isinstance(
        exc,
        GoogleCalendarHorarioOcupadoError,
    ):

        return JsonResponse(
            {
                "ok": False,
                "disponible": False,
                "error":
                    "El horario solicitado ya está ocupado.",
                "codigo":
                    "HORARIO_OCUPADO",
            },
            status=409,
        )


    if isinstance(
        exc,
        GoogleCalendarNoConectadoError,
    ):

        return JsonResponse(
            {
                "ok": False,
                "error":
                    "Google Calendar no está conectado para esta empresa.",
                "codigo":
                    "GOOGLE_CALENDAR_NO_CONECTADO",
            },
            status=409,
        )


    if isinstance(
        exc,
        GoogleCalendarCitaNoEncontradaError,
    ):

        return JsonResponse(
            {
                "ok": False,
                "error":
                    "Cita no encontrada.",
                "codigo":
                    "CITA_NO_ENCONTRADA",
            },
            status=404,
        )


    if isinstance(
        exc,
        GoogleCalendarCitasError,
    ):

        return JsonResponse(
            {
                "ok": False,
                "error":
                    "No fue posible procesar la operación de agenda.",
                "codigo":
                    "GOOGLE_CALENDAR_ERROR",
            },
            status=502,
        )


    return None


# -----------------------------------------------------------------------------
# DISPONIBILIDAD
# -----------------------------------------------------------------------------


# TNL-TYPEBOT-CITAS-ESTADO-V1
@csrf_exempt
def cita_estado(
    request,
):
    """
    Estado funcional de la agenda para un bot.

    No consulta Google Calendar y no modifica
    datos. Su objetivo es permitir que Typebot
    determine si debe mostrar el flujo de citas
    para la empresa correspondiente.
    """

    from core.models import (
        ConfiguracionGoogleCalendar,
    )


    if request.method != "POST":

        return JsonResponse(
            {
                "ok": False,
                "error":
                    "Método no permitido.",
            },
            status=405,
        )


    auth_error = (
        _citas_api_error_auth(
            request
        )
    )

    if auth_error is not None:
        return auth_error


    datos, datos_error = (
        _citas_api_leer_datos(
            request
        )
    )

    if datos_error is not None:
        return datos_error


    bot, bot_error = (
        _citas_api_resolver_bot(
            datos.get(
                "bot_id"
            )
        )
    )

    if bot_error is not None:
        return bot_error


    configuracion = (
        ConfiguracionGoogleCalendar.objects
        .filter(
            empresa=bot.empresa
        )
        .first()
    )


    agenda_disponible = False
    zona_horaria = ""


    if configuracion is not None:

        calendar_id = str(
            configuracion.calendar_id
            or
            ""
        ).strip()

        zona = str(
            configuracion.zona_horaria
            or
            ""
        ).strip()


        agenda_disponible = bool(
            configuracion.habilitada
            and
            configuracion.estado_conexion
            ==
            ConfiguracionGoogleCalendar
            .ESTADO_CONECTADA
            and
            calendar_id
            and
            zona
        )


        if agenda_disponible:

            zona_horaria = zona


    mensaje = (
        "La agenda está disponible."
        if agenda_disponible
        else
        "La agenda aún no está disponible."
    )


    return JsonResponse(
        {
            "ok": True,

            "agenda_disponible":
                agenda_disponible,

            "bot_id":
                bot.pk,

            "empresa":
                bot.empresa.nombre,

            "zona_horaria":
                zona_horaria,

            "mensaje":
                mensaje,

            # TNL-TYPEBOT-CITAS-RESPONSE-DATA-V1
            # Compatibilidad Typebot:
            # responseVariableMapping usa data.* y
            # las Conditions comparan texto "true".
            "data": {
                "agenda_disponible":
                    (
                        "true"
                        if agenda_disponible
                        else "false"
                    ),

                "zona_horaria":
                    zona_horaria,

                "mensaje":
                    mensaje,
            },
        },
        json_dumps_params={
            "ensure_ascii": False
        },
    )


@csrf_exempt
def cita_disponibilidad(
    request,
):

    from core.services.google_calendar_citas import (
        GoogleCalendarCitasError,
        consultar_slot_agenda,
    )


    if request.method != "POST":

        return JsonResponse(
            {
                "ok": False,
                "error":
                    "Método no permitido.",
            },
            status=405,
        )


    auth_error = (
        _citas_api_error_auth(
            request
        )
    )

    if auth_error is not None:
        return auth_error


    datos, datos_error = (
        _citas_api_leer_datos(
            request
        )
    )

    if datos_error is not None:
        return datos_error


    bot, bot_error = (
        _citas_api_resolver_bot(
            datos.get(
                "bot_id"
            )
        )
    )

    if bot_error is not None:
        return bot_error


    try:

        inicio, fin = (
            _citas_api_resolver_horario(
                datos,
                bot.empresa,
            )
        )


    except ValueError as exc:

        return JsonResponse(
            {
                "ok": False,
                "error":
                    str(exc),
                "codigo":
                    "HORARIO_INVALIDO",
            },
            status=400,
        )


    try:

        resultado = (
            consultar_slot_agenda(
                empresa=bot.empresa,
                inicio=inicio,
                fin=fin,
            )
        )


    except GoogleCalendarCitasError as exc:

        response = (
            _citas_api_error_servicio(
                exc
            )
        )

        if response is not None:
            return response

        raise


    ocupados = (
        resultado.get(
            "ocupados",
            []
        )
        or []
    )


    return JsonResponse(
        {
            "ok": True,

            "disponible":
                bool(
                    resultado[
                        "disponible"
                    ]
                ),

            "bot_id":
                bot.pk,

            "empresa":
                bot.empresa.nombre,

            "inicio":
                inicio.isoformat(),

            "fin":
                fin.isoformat(),

            "zona_horaria":
                resultado[
                    "zona_horaria"
                ],

            "bloques_ocupados":
                len(
                    ocupados
                ),

            "ocupados":
                ocupados,

            "data": {
                "disponible":
                    (
                        "true"
                        if bool(
                            resultado[
                                "disponible"
                            ]
                        )
                        else "false"
                    ),

                "inicio":
                    inicio.isoformat(),

                "fin":
                    fin.isoformat(),

                "zona_horaria":
                    resultado[
                        "zona_horaria"
                    ],
            },
        },
        json_dumps_params={
            "ensure_ascii": False
        },
    )


# -----------------------------------------------------------------------------
# CREAR CITA
# -----------------------------------------------------------------------------

@csrf_exempt
def cita_crear(
    request,
):

    from django.core.validators import (
        validate_email,
    )

    from django.core.exceptions import (
        ValidationError,
    )

    from core.models import (
        Cita,
    )

    from core.services.google_calendar_citas import (
        GoogleCalendarCitasError,
        crear_cita,
    )


    if request.method != "POST":

        return JsonResponse(
            {
                "ok": False,
                "error":
                    "Método no permitido.",
            },
            status=405,
        )


    auth_error = (
        _citas_api_error_auth(
            request
        )
    )

    if auth_error is not None:
        return auth_error


    datos, datos_error = (
        _citas_api_leer_datos(
            request
        )
    )

    if datos_error is not None:
        return datos_error


    bot, bot_error = (
        _citas_api_resolver_bot(
            datos.get(
                "bot_id"
            )
        )
    )

    if bot_error is not None:
        return bot_error


    try:

        inicio, fin = (
            _citas_api_resolver_horario(
                datos,
                bot.empresa,
            )
        )


        titulo = (
            _citas_api_validar_longitud(
                datos.get(
                    "titulo"
                ),
                nombre="titulo",
                max_length=255,
            )
        )


        if not titulo:

            raise ValueError(
                "titulo es obligatorio."
            )


        nombre_cliente = (
            _citas_api_validar_longitud(
                datos.get(
                    "nombre_cliente"
                ),
                nombre=
                    "nombre_cliente",
                max_length=200,
            )
        )


        telefono_cliente = (
            _citas_api_validar_longitud(
                datos.get(
                    "telefono_cliente"
                ),
                nombre=
                    "telefono_cliente",
                max_length=50,
            )
        )


        email_cliente = (
            _citas_api_validar_longitud(
                datos.get(
                    "email_cliente"
                ),
                nombre=
                    "email_cliente",
                max_length=254,
            )
        )


        servicio = (
            _citas_api_validar_longitud(
                datos.get(
                    "servicio"
                ),
                nombre="servicio",
                max_length=255,
            )
        )


        # TNL-CITA-SERVICIO-PRODUCTO-API-V1
        servicio_producto_id = (
            datos.get(
                "servicio_producto_id"
            )
        )

        if servicio_producto_id in (
            "",
            None,
        ):
            servicio_producto_id = None

        else:
            try:
                servicio_producto_id = int(
                    servicio_producto_id
                )
            except (
                TypeError,
                ValueError,
            ) as exc:
                raise ValueError(
                    "servicio_producto_id no es válido."
                ) from exc

            if servicio_producto_id <= 0:
                raise ValueError(
                    "servicio_producto_id no es válido."
                )


        referencia = (
            _citas_api_validar_longitud(
                datos.get(
                    "referencia_conversacion"
                ),
                nombre=
                    "referencia_conversacion",
                max_length=255,
            )
        )


        descripcion = str(
            datos.get(
                "descripcion"
            )
            or
            ""
        ).strip()


        if len(descripcion) > 5000:

            raise ValueError(
                (
                    "descripcion supera "
                    "5000 caracteres."
                )
            )


        if email_cliente:

            try:

                validate_email(
                    email_cliente
                )

            except ValidationError as exc:

                raise ValueError(
                    (
                        "email_cliente "
                        "no es válido."
                    )
                ) from exc


    except ValueError as exc:

        return JsonResponse(
            {
                "ok": False,
                "error":
                    str(exc),
                "codigo":
                    "DATOS_CITA_INVALIDOS",
            },
            status=400,
        )


    try:

        cita = (
            crear_cita(
                empresa=
                    bot.empresa,

                bot=
                    bot,

                inicio=
                    inicio,

                fin=
                    fin,

                titulo=
                    titulo,

                nombre_cliente=
                    nombre_cliente,

                telefono_cliente=
                    telefono_cliente,

                email_cliente=
                    email_cliente,

                servicio=
                    servicio,

                descripcion=
                    descripcion,

                referencia_conversacion=
                    referencia,

                origen=
                    Cita.ORIGEN_CHATBOT,
            
                servicio_producto=
                    servicio_producto_id,
            )
        )


    except GoogleCalendarCitasError as exc:

        response = (
            _citas_api_error_servicio(
                exc
            )
        )

        if response is not None:
            return response

        raise


    # TNL-CITA-PAYMENT-RESPONSE-V1
    requiere_pago = (
        cita.importe_pago_requerido
        is not None
        and
        cita.importe_pago_requerido > 0
    )

    if requiere_pago:
        mensaje_cita = (
            "Horario reservado temporalmente. "
            "Pago pendiente."
        )
    else:
        mensaje_cita = (
            "Cita programada correctamente."
        )


    retencion_iso = (
        cita.retencion_pago_hasta.isoformat()
        if cita.retencion_pago_hasta
        else None
    )


    return JsonResponse(
        {
            "ok": True,

            "cita_creada": True,

            "cita_id":
                cita.pk,

            "estado":
                cita.estado,

            "requiere_pago":
                requiere_pago,

            "politica_pago_aplicada":
                cita.politica_pago_aplicada,

            "servicio_producto_id":
                cita.servicio_producto_id,

            "importe_total":
                str(cita.importe_total),

            "porcentaje_pago_requerido":
                str(
                    cita.porcentaje_pago_requerido
                ),

            "importe_pago_requerido":
                str(
                    cita.importe_pago_requerido
                ),

            "moneda":
                cita.moneda,

            "retencion_pago_hasta":
                retencion_iso,

            "bot_id":
                bot.pk,

            "empresa":
                bot.empresa.nombre,

            "titulo":
                cita.titulo,

            "servicio":
                cita.servicio,

            "nombre_cliente":
                cita.nombre_cliente,

            "inicio":
                cita.inicio.isoformat(),

            "fin":
                cita.fin.isoformat(),

            "zona_horaria":
                cita.zona_horaria,

            "referencia_conversacion":
                cita.referencia_conversacion,

            "mensaje":
                mensaje_cita,

            "data": {
                "cita_id":
                    cita.pk,

                "estado":
                    cita.estado,

                "requiere_pago":
                    requiere_pago,

                "politica_pago_aplicada":
                    cita.politica_pago_aplicada,

                "servicio_producto_id":
                    cita.servicio_producto_id,

                "importe_total":
                    str(cita.importe_total),

                "porcentaje_pago_requerido":
                    str(
                        cita.porcentaje_pago_requerido
                    ),

                "importe_pago_requerido":
                    str(
                        cita.importe_pago_requerido
                    ),

                "moneda":
                    cita.moneda,

                "retencion_pago_hasta":
                    retencion_iso,

                "mensaje":
                    mensaje_cita,
            },
        },
        status=201,
        json_dumps_params={
            "ensure_ascii": False
        },
    )


# -----------------------------------------------------------------------------
# CONSULTAR CITA
# -----------------------------------------------------------------------------

@csrf_exempt
def cita_consultar(
    request,
):

    from core.models import (
        Cita,
    )


    if request.method != "POST":

        return JsonResponse(
            {
                "ok": False,
                "error":
                    "Método no permitido.",
            },
            status=405,
        )


    auth_error = (
        _citas_api_error_auth(
            request
        )
    )

    if auth_error is not None:
        return auth_error


    datos, datos_error = (
        _citas_api_leer_datos(
            request
        )
    )

    if datos_error is not None:
        return datos_error


    bot, bot_error = (
        _citas_api_resolver_bot(
            datos.get(
                "bot_id"
            )
        )
    )

    if bot_error is not None:
        return bot_error


    cita_id_texto = str(
        datos.get(
            "cita_id"
        )
        or
        ""
    ).strip()


    if not cita_id_texto:

        return JsonResponse(
            {
                "ok": False,
                "encontrada": False,
                "error":
                    "cita_id es obligatorio.",
                "codigo":
                    "CITA_ID_REQUERIDO",
            },
            status=400,
        )


    try:

        cita_id = int(
            cita_id_texto
        )

    except (
        TypeError,
        ValueError,
    ):

        return JsonResponse(
            {
                "ok": False,
                "encontrada": False,
                "error":
                    "cita_id no es válido.",
                "codigo":
                    "CITA_ID_INVALIDO",
            },
            status=400,
        )


    # Aislamiento obligatorio:
    # nunca se consulta sólo por PK.
    cita = (
        Cita.objects
        .filter(
            pk=cita_id,
            empresa=bot.empresa,
        )
        .first()
    )


    if cita is None:

        return JsonResponse(
            {
                "ok": True,
                "encontrada": False,
                "cita_id":
                    cita_id,
                "mensaje":
                    "Cita no encontrada.",
            },
            status=200,
        )


    return JsonResponse(
        {
            "ok": True,
            "encontrada": True,

            "cita_id":
                cita.pk,

            "estado":
                cita.estado,

            "bot_id":
                bot.pk,

            "empresa":
                bot.empresa.nombre,

            "titulo":
                cita.titulo,

            "servicio":
                cita.servicio,

            "nombre_cliente":
                cita.nombre_cliente,

            "inicio":
                cita.inicio.isoformat(),

            "fin":
                cita.fin.isoformat(),

            "zona_horaria":
                cita.zona_horaria,

            "referencia_conversacion":
                cita.referencia_conversacion,

            "confirmada":
                cita.confirmada_en
                is not None,

            "cancelada":
                cita.estado
                ==
                Cita.ESTADO_CANCELADA,
        },
        json_dumps_params={
            "ensure_ascii": False
        },
    )


# -----------------------------------------------------------------------------
# CANCELAR CITA
# -----------------------------------------------------------------------------

@csrf_exempt
def cita_cancelar(
    request,
):

    from core.models import (
        Cita,
    )

    from core.services.google_calendar_citas import (
        GoogleCalendarCitasError,
        cancelar_cita,
    )


    if request.method != "POST":

        return JsonResponse(
            {
                "ok": False,
                "error":
                    "Método no permitido.",
            },
            status=405,
        )


    auth_error = (
        _citas_api_error_auth(
            request
        )
    )

    if auth_error is not None:
        return auth_error


    datos, datos_error = (
        _citas_api_leer_datos(
            request
        )
    )

    if datos_error is not None:
        return datos_error


    bot, bot_error = (
        _citas_api_resolver_bot(
            datos.get(
                "bot_id"
            )
        )
    )

    if bot_error is not None:
        return bot_error


    cita_id_texto = str(
        datos.get(
            "cita_id"
        )
        or
        ""
    ).strip()


    if not cita_id_texto:

        return JsonResponse(
            {
                "ok": False,
                "error":
                    "cita_id es obligatorio.",
                "codigo":
                    "CITA_ID_REQUERIDO",
            },
            status=400,
        )


    try:

        cita_id = int(
            cita_id_texto
        )

    except (
        TypeError,
        ValueError,
    ):

        return JsonResponse(
            {
                "ok": False,
                "error":
                    "cita_id no es válido.",
                "codigo":
                    "CITA_ID_INVALIDO",
            },
            status=400,
        )


    # Comprobación de pertenencia ANTES de
    # invocar el servicio Google.
    cita_previa = (
        Cita.objects
        .filter(
            pk=cita_id,
            empresa=bot.empresa,
        )
        .first()
    )


    if cita_previa is None:

        return JsonResponse(
            {
                "ok": False,
                "error":
                    "Cita no encontrada.",
                "codigo":
                    "CITA_NO_ENCONTRADA",
            },
            status=404,
        )


    ya_cancelada = (
        cita_previa.estado
        ==
        Cita.ESTADO_CANCELADA
    )


    try:

        cita = (
            cancelar_cita(
                empresa=
                    bot.empresa,

                cita_id=
                    cita_id,
            )
        )


    except GoogleCalendarCitasError as exc:

        response = (
            _citas_api_error_servicio(
                exc
            )
        )

        if response is not None:
            return response

        raise


    return JsonResponse(
        {
            "ok": True,

            "cita_cancelada": True,

            "ya_estaba_cancelada":
                ya_cancelada,

            "cita_id":
                cita.pk,

            "estado":
                cita.estado,

            "bot_id":
                bot.pk,

            "empresa":
                bot.empresa.nombre,

            "cancelada_en":
                (
                    cita.cancelada_en
                    .isoformat()
                    if cita.cancelada_en
                    else None
                ),

            "mensaje":
                (
                    "La cita ya estaba cancelada."
                    if ya_cancelada
                    else
                    "Cita cancelada correctamente."
                ),
        },
        json_dumps_params={
            "ensure_ascii": False
        },
    )


# =============================================================================
# TNL-MERCADOPAGO-WEBHOOK-V1
# Webhook público firmado Mercado Pago.
# =============================================================================

def mercadopago_webhook(
    request,
):

    import json
    import logging
    import uuid

    from decimal import (
        Decimal,
        InvalidOperation,
    )

    from django.db import transaction

    from django.http import (
        HttpResponse,
        HttpResponseNotAllowed,
    )

    from django.utils import timezone
    from django.utils.dateparse import parse_datetime
    from django.views.decorators.csrf import csrf_exempt

    from core.models import (
        Cita,
        ConfiguracionMercadoPago,
        Pago,
        Pedido,
        PedidoEstadoEvento,
    )

    from core.services.mercadopago import (
        consultar_pago_mercadopago,
        obtener_access_token_configuracion,
        validar_firma_webhook,
    )

    # TNL-MERCADOPAGO-CITA-WEBHOOK-V1
    from core.services.google_calendar_citas import (
        GoogleCalendarHorarioOcupadoError,
        programar_cita_pagada_en_google,
    )

    from core.services.pedido_notificaciones import (
        notificar_evento_pedido_whatsapp,
    )


    # ---------------------------------------------------------
    # Sólo POST.
    # Se hace manual para mantener el decorador csrf_exempt
    # completamente localizado en este endpoint.
    # ---------------------------------------------------------

    if request.method != "POST":

        return HttpResponseNotAllowed(
            [
                "POST"
            ]
        )


    logger = logging.getLogger(
        "negociolisto.mercadopago"
    )


    # ---------------------------------------------------------
    # Firma Mercado Pago.
    # data.id utilizado para la firma proviene de query string.
    # ---------------------------------------------------------

    x_signature = (
        request.headers.get(
            "x-signature",
            "",
        )
    )

    x_request_id = (
        request.headers.get(
            "x-request-id",
            "",
        )
    )

    data_id_url = str(
        request.GET.get(
            "data.id",
            ""
        )
        or
        request.GET.get(
            "data_id",
            ""
        )
        or
        ""
    ).strip()


    if not validar_firma_webhook(
        x_signature=x_signature,
        x_request_id=x_request_id,
        data_id=data_id_url,
    ):

        logger.warning(
            "TNL_MP_WEBHOOK_INVALID_SIGNATURE"
        )

        return HttpResponse(
            status=401
        )


    # ---------------------------------------------------------
    # El contenido sólo se procesa DESPUÉS de validar firma.
    # ---------------------------------------------------------

    try:

        body = json.loads(
            request.body.decode(
                "utf-8"
            )
            or
            "{}"
        )

    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
    ):

        logger.warning(
            "TNL_MP_WEBHOOK_INVALID_JSON"
        )

        return HttpResponse(
            status=400
        )


    if not isinstance(
        body,
        dict,
    ):

        return HttpResponse(
            status=400
        )


    event_type = str(
        body.get(
            "type"
        )
        or
        request.GET.get(
            "type"
        )
        or
        ""
    ).strip().lower()


    # La URL está preparada exclusivamente
    # para Payments. Otros eventos se reconocen
    # pero no se procesan.
    if event_type not in {
        "payment",
        "payments",
    }:

        return HttpResponse(
            status=200
        )


    data = (
        body.get(
            "data"
        )
        or
        {}
    )

    if not isinstance(
        data,
        dict,
    ):

        return HttpResponse(
            status=400
        )


    payment_id_body = str(
        data.get(
            "id"
        )
        or
        ""
    ).strip()


    # Si ambas fuentes contienen ID,
    # tienen que coincidir.
    if (
        data_id_url
        and
        payment_id_body
        and
        data_id_url.lower()
        !=
        payment_id_body.lower()
    ):

        logger.warning(
            "TNL_MP_WEBHOOK_ID_MISMATCH"
        )

        return HttpResponse(
            status=400
        )


    payment_id = (
        payment_id_body
        or
        data_id_url
    )


    if not payment_id:

        return HttpResponse(
            status=400
        )


    mp_user_id = str(
        body.get(
            "user_id"
        )
        or
        ""
    ).strip()


    if not mp_user_id:

        logger.warning(
            "TNL_MP_WEBHOOK_USER_ID_MISSING"
        )

        return HttpResponse(
            status=400
        )


    # ---------------------------------------------------------
    # Aislamiento multiempresa:
    # localizar exclusivamente la configuración cuyo
    # mp_user_id coincide con el vendedor notificado.
    # ---------------------------------------------------------

    config = (
        ConfiguracionMercadoPago.objects
        .select_related(
            "empresa"
        )
        .filter(
            mp_user_id=
                mp_user_id,

            habilitada=True,

            estado_conexion=(
                ConfiguracionMercadoPago
                .EstadoConexion
                .CONECTADA
            ),
        )
        .first()
    )


    if config is None:

        logger.warning(
            (
                "TNL_MP_WEBHOOK_UNKNOWN_SELLER "
                "mp_user_id_present=1"
            )
        )

        # Firma válida pero vendedor no administrado
        # por esta instalación. No provocar reintentos.
        return HttpResponse(
            status=200
        )


    # ---------------------------------------------------------
    # Consultar Mercado Pago.
    # Nunca confiar sólo en el cuerpo del Webhook.
    # ---------------------------------------------------------

    try:

        # TNL-MERCADOPAGO-WEBHOOK-AUTOREFRESH-V1
        access_token = (
            obtener_access_token_configuracion(
                config.id
            )
        )

        remote = (
            consultar_pago_mercadopago(
                access_token=
                    access_token,

                payment_id=
                    payment_id,
            )
        )

    except Exception as exc:

        logger.error(
            (
                "TNL_MP_WEBHOOK_PAYMENT_QUERY_FAIL "
                "empresa=%s exception=%s"
            ),
            config.empresa_id,
            type(exc).__name__,
        )

        # 503 provoca reintento del Webhook.
        return HttpResponse(
            status=503
        )


    # ---------------------------------------------------------
    # Validaciones críticas del pago remoto.
    # ---------------------------------------------------------

    remote_payment_id = str(
        remote.get(
            "id"
        )
        or
        ""
    ).strip()

    collector_id = str(
        remote.get(
            "collector_id"
        )
        or
        ""
    ).strip()

    external_reference = str(
        remote.get(
            "external_reference"
        )
        or
        ""
    ).strip()

    currency_id = str(
        remote.get(
            "currency_id"
        )
        or
        ""
    ).strip().upper()

    status = str(
        remote.get(
            "status"
        )
        or
        ""
    ).strip().lower()

    status_detail = str(
        remote.get(
            "status_detail"
        )
        or
        ""
    ).strip()


    if (
        not remote_payment_id
        or
        remote_payment_id
        !=
        str(payment_id)
    ):

        logger.warning(
            "TNL_MP_WEBHOOK_REMOTE_ID_INVALID"
        )

        return HttpResponse(
            status=400
        )


    if (
        not collector_id
        or
        collector_id
        !=
        str(config.mp_user_id)
    ):

        logger.warning(
            (
                "TNL_MP_WEBHOOK_COLLECTOR_MISMATCH "
                "empresa=%s"
            ),
            config.empresa_id,
        )

        return HttpResponse(
            status=400
        )


    # external_reference deberá ser nuestro UUID Pago.referencia.
    try:

        pago_uuid = uuid.UUID(
            external_reference
        )

    except (
        ValueError,
        TypeError,
        AttributeError,
    ):

        logger.warning(
            "TNL_MP_WEBHOOK_EXTERNAL_REFERENCE_INVALID"
        )

        return HttpResponse(
            status=400
        )


    pago = (
        Pago.objects
        .select_related(
            "pedido",
            "pedido__empresa",
            "cita",
            "cita__empresa",
        )
        .filter(
            referencia=
                pago_uuid,

            proveedor=
                Pago.Proveedor
                .MERCADOPAGO,
        )
        .first()
    )


    # Aislamiento multiempresa para ambos destinos.
    if pago is not None:

        if pago.pedido_id:

            pago_empresa_id = (
                pago.pedido.empresa_id
            )

        elif pago.cita_id:

            pago_empresa_id = (
                pago.cita.empresa_id
            )

        else:

            pago_empresa_id = None


        if (
            pago_empresa_id
            !=
            config.empresa_id
        ):
            pago = None


    if pago is None:

        logger.warning(
            (
                "TNL_MP_WEBHOOK_LOCAL_PAYMENT_NOT_FOUND "
                "empresa=%s"
            ),
            config.empresa_id,
        )

        return HttpResponse(
            status=200
        )


    try:

        remote_amount = Decimal(
            str(
                remote.get(
                    "transaction_amount"
                )
            )
        )

    except (
        InvalidOperation,
        TypeError,
        ValueError,
    ):

        return HttpResponse(
            status=400
        )


    local_amount = Decimal(
        pago.monto
    )


    if remote_amount != local_amount:

        logger.warning(
            (
                "TNL_MP_WEBHOOK_AMOUNT_MISMATCH "
                "empresa=%s pago=%s"
            ),
            config.empresa_id,
            pago.pk,
        )

        return HttpResponse(
            status=400
        )


    if (
        currency_id
        !=
        str(
            pago.moneda
        ).upper()
    ):

        logger.warning(
            (
                "TNL_MP_WEBHOOK_CURRENCY_MISMATCH "
                "empresa=%s pago=%s"
            ),
            config.empresa_id,
            pago.pk,
        )

        return HttpResponse(
            status=400
        )


    # ---------------------------------------------------------
    # Mapeo de estados.
    # ---------------------------------------------------------

    status_map = {
        "approved":
            Pago.Estado.APROBADO,

        "pending":
            Pago.Estado.PENDIENTE,

        "in_process":
            Pago.Estado.PENDIENTE,

        "authorized":
            Pago.Estado.PENDIENTE,

        "in_mediation":
            Pago.Estado.PENDIENTE,

        "rejected":
            Pago.Estado.RECHAZADO,

        "cancelled":
            Pago.Estado.CANCELADO,

        "refunded":
            Pago.Estado.REEMBOLSADO,

        "charged_back":
            Pago.Estado.CONTRACARGO,
    }


    local_status = status_map.get(
        status
    )


    if local_status is None:

        # Estado remoto desconocido:
        # conservar información de proveedor,
        # pero no inventar una transición interna.
        local_status = Pago.Estado.PENDIENTE


    # ---------------------------------------------------------
    # Merchant order.
    # ---------------------------------------------------------

    order = (
        remote.get(
            "order"
        )
        or
        {}
    )

    if not isinstance(
        order,
        dict,
    ):
        order = {}


    merchant_order_id = str(
        order.get(
            "id"
        )
        or
        ""
    ).strip()


    # ---------------------------------------------------------
    # Fecha aprobada.
    # ---------------------------------------------------------

    aprobado_en = None

    if status == "approved":

        date_approved = str(
            remote.get(
                "date_approved"
            )
            or
            ""
        ).strip()

        if date_approved:

            aprobado_en = (
                parse_datetime(
                    date_approved
                )
            )

        if aprobado_en is None:

            aprobado_en = (
                timezone.now()
            )


    # ---------------------------------------------------------
    # Guardado transaccional e idempotente.
    # ---------------------------------------------------------

    # Sólo se asigna para un Pago aprobado cuyo destino es Cita.
    # Se consume DESPUÉS de salir de transaction.atomic().
    cita_finalizar_id = None

    # TNL-CHANGO-MP-PAGADO-WHATSAPP-V1
    #
    # Evento persistente únicamente cuando un pedido CHANGO
    # transiciona realmente a pagado.
    # El envío WhatsApp ocurre después del COMMIT.
    pedido_pagado_evento_id = None

    try:

        with transaction.atomic():

            locked = (
                Pago.objects
                .select_for_update()
                .get(
                    pk=pago.pk
                )
            )


            conflict = (
                Pago.objects
                .filter(
                    payment_id=
                        remote_payment_id
                )
                .exclude(
                    pk=locked.pk
                )
                .exists()
            )


            if conflict:

                logger.error(
                    (
                        "TNL_MP_WEBHOOK_PAYMENT_ID_CONFLICT "
                        "empresa=%s"
                    ),
                    config.empresa_id,
                )

                return HttpResponse(
                    status=409
                )


            locked.payment_id = (
                remote_payment_id
            )

            if merchant_order_id:

                locked.merchant_order_id = (
                    merchant_order_id
                )

            locked.estado_proveedor = (
                status
            )

            locked.detalle_estado_proveedor = (
                status_detail
            )

            locked.estado = (
                local_status
            )

            locked.ultima_notificacion_en = (
                timezone.now()
            )

            if (
                aprobado_en is not None
                and
                locked.aprobado_en is None
            ):

                locked.aprobado_en = (
                    aprobado_en
                )

            locked.save()

            # -------------------------------------------------
            # TNL-MERCADOPAGO-PEDIDO-PAGADO-V1
            #
            # Sólo una confirmación REAL de Mercado Pago
            # puede llevar el pedido a "pagado".
            #
            # Nunca degradamos estados operativos posteriores
            # ni reactivamos pedidos cancelados.
            # -------------------------------------------------

            if (
                local_status
                ==
                Pago.Estado.APROBADO
            ):

                if locked.pedido_id:

                    # ---------------------------------------------
                    # FLUJO HISTORICO DE PEDIDO.
                    # No cambiar transiciones ni semántica.
                    # ---------------------------------------------

                    pedido_locked = (
                        Pedido.objects
                        .select_for_update()
                        .get(
                            pk=
                                locked.pedido_id
                        )
                    )

                    if pedido_locked.estado in {
                        "confirmado",
                        "pendiente",
                    }:

                        estado_anterior_pedido = (
                            pedido_locked.estado
                        )

                        pedido_locked.estado = (
                            "pagado"
                        )

                        pedido_locked.save(
                            update_fields=[
                                "estado",
                                "actualizado_en",
                            ]
                        )

                        # TNL-RESTAURANTE-MP-PAGADO-WHATSAPP-V1
                        #
                        # El evento de pago automático aplica
                        # únicamente a pedidos Restaurante.
                        if (
                            str(
                                pedido_locked.tipo_orden
                                or ""
                            ).strip().lower()
                            in {
                                "comedor",
                                "para_llevar",
                                "domicilio",
                            }
                        ):

                            evento_pagado = (
                                PedidoEstadoEvento.objects.create(
                                    pedido=
                                        pedido_locked,

                                    estado_anterior=
                                        estado_anterior_pedido,

                                    estado_nuevo=
                                        "pagado",

                                    usuario=
                                        None,
                                )
                            )

                            pedido_pagado_evento_id = (
                                evento_pagado.pk
                            )

                    elif (
                        pedido_locked.estado
                        ==
                        "pagado"
                    ):

                        # Webhook repetido:
                        # transición ya aplicada.
                        pass

                    else:

                        logger.warning(
                            (
                                "TNL_MP_PAYMENT_APPROVED_"
                                "ORDER_STATE_PRESERVED "
                                "empresa=%s pedido=%s "
                                "estado=%s"
                            ),
                            config.empresa_id,
                            pedido_locked.pk,
                            pedido_locked.estado,
                        )


                elif locked.cita_id:

                    # ---------------------------------------------
                    # NUEVO DESTINO: CITA.
                    #
                    # Sólo registramos aquí el hecho financiero.
                    # Google se ejecutará después del COMMIT.
                    # ---------------------------------------------

                    cita_locked = (
                        Cita.objects
                        .select_for_update()
                        .get(
                            pk=
                                locked.cita_id,
                            empresa=
                                config.empresa,
                        )
                    )

                    cita_locked.importe_pagado = (
                        remote_amount
                    )

                    if (
                        cita_locked.pago_confirmado_en
                        is None
                    ):

                        cita_locked.pago_confirmado_en = (
                            aprobado_en
                        )

                    cita_locked.save(
                        update_fields=[
                            "importe_pagado",
                            "pago_confirmado_en",
                            "actualizado_en",
                        ]
                    )

                    cita_finalizar_id = (
                        cita_locked.pk
                    )


                else:

                    # La constraint core_pago_destino_xor debería
                    # hacer imposible este estado.
                    raise RuntimeError(
                        "Pago sin destino Pedido/Cita."
                    )


    except Exception as exc:

        logger.error(
            (
                "TNL_MP_WEBHOOK_DB_FAIL "
                "empresa=%s pago=%s exception=%s"
            ),
            config.empresa_id,
            pago.pk,
            type(exc).__name__,
        )

        return HttpResponse(
            status=503
        )


    # ---------------------------------------------------------
    # TNL-CHANGO-MP-PAGADO-WHATSAPP-V1
    #
    # El hecho financiero ya hizo COMMIT.
    # Un fallo de WhatsApp nunca revierte Pago ni Pedido.
    # PedidoEstadoEvento aporta claim idempotente at-most-once.
    # ---------------------------------------------------------
    if pedido_pagado_evento_id is not None:

        try:

            resultado_notificacion = (
                notificar_evento_pedido_whatsapp(
                    evento_id=
                        pedido_pagado_evento_id
                )
            )

            if not resultado_notificacion.get(
                "enviado",
                False,
            ):

                logger.warning(
                    (
                        "TNL_MP_ORDER_PAID_WHATSAPP_NOT_SENT "
                        "empresa=%s evento=%s aplicable=%s"
                    ),
                    config.empresa_id,
                    pedido_pagado_evento_id,
                    resultado_notificacion.get(
                        "aplicable",
                        False,
                    ),
                )

        except Exception as exc:

            logger.error(
                (
                    "TNL_MP_ORDER_PAID_WHATSAPP_FAIL "
                    "empresa=%s evento=%s exception=%s"
                ),
                config.empresa_id,
                pedido_pagado_evento_id,
                type(exc).__name__,
            )


    # ---------------------------------------------------------
    # CITA PAGADA: FINALIZAR GOOGLE FUERA DEL ATOMIC.
    #
    # En este punto Pago y Cita.pago_confirmado_en ya hicieron
    # COMMIT. Un fallo Google jamás revierte el hecho financiero.
    # ---------------------------------------------------------
    if cita_finalizar_id is not None:

        try:

            programar_cita_pagada_en_google(
                cita_finalizar_id
            )

        except GoogleCalendarHorarioOcupadoError as exc:

            logger.warning(
                (
                    "TNL_MP_CITA_APPROVED_SLOT_UNAVAILABLE "
                    "empresa=%s cita=%s exception=%s"
                ),
                config.empresa_id,
                cita_finalizar_id,
                type(exc).__name__,
            )

            # Pago confirmado, pero el horario ya no está libre.
            # El helper deja la Cita en estado error.
            # No provocar reintentos infinitos de Mercado Pago.
            return HttpResponse(
                status=200
            )

        except Exception as exc:

            logger.error(
                (
                    "TNL_MP_CITA_GOOGLE_FINALIZE_FAIL "
                    "empresa=%s cita=%s exception=%s"
                ),
                config.empresa_id,
                cita_finalizar_id,
                type(exc).__name__,
            )

            # El pago ya quedó confirmado.
            # 503 sólo solicita reintentar la finalización técnica;
            # el helper Google es idempotente.
            return HttpResponse(
                status=503
            )


    return HttpResponse(
        status=200
    )

# Aplicamos csrf_exempt de manera explícita
# sólo a esta función pública.
mercadopago_webhook = csrf_exempt(
    mercadopago_webhook
)


# =============================================================================
# TNL-MERCADOPAGO-TYPEBOT-CHECKOUT-V1
# Generación segura de enlace Checkout Pro para un pedido confirmado.
# =============================================================================

@csrf_exempt
def carrito_mercadopago_checkout(
    request,
):

    import json
    import logging

    from decimal import (
        Decimal,
    )

    from django.db import (
        transaction,
    )

    from django.http import (
        JsonResponse,
    )

    from django.utils import (
        timezone,
    )

    from core.models import (
        Bot,
        ConfiguracionMercadoPago,
        Pago,
        Pedido,
    )

    from core.services.mercadopago import (
        crear_preferencia_checkout_pro,
        obtener_access_token_configuracion,
    )


    # TNL-MERCADOPAGO-TYPEBOT-GRACEFUL-V1
    def _checkout_no_disponible(
        *,
        mensaje,
        pedido=None,
    ):
        """
        Respuesta controlada para situaciones donde
        el pedido ya está confirmado correctamente
        pero Checkout Pro no está disponible.

        Es HTTP 200 deliberadamente para que Typebot
        pueda continuar por su rama fallback.
        """

        payload = {
            "ok": True,
            "checkout_disponible":
                False,
            "checkout_url":
                "",
            "checkout_mensaje":
                str(
                    mensaje
                    or
                    (
                        "Pago con Mercado Pago "
                        "no disponible por el momento."
                    )
                ),
        }

        if pedido is not None:

            payload[
                "pedido_id"
            ] = pedido.id

            payload[
                "pedido_numero"
            ] = pedido.numero

        return JsonResponse(
            payload
        )


    if request.method != "POST":

        return JsonResponse(
            {
                "ok": False,
                "error":
                    "Método no permitido.",
            },
            status=405,
        )


    # ---------------------------------------------------------
    # Autenticación Typebot ya existente.
    # ---------------------------------------------------------

    clave_esperada = (
        _leer_clave_api()
    )

    if not clave_esperada:

        return JsonResponse(
            {
                "ok": False,
                "error":
                    "Servicio no configurado.",
            },
            status=503,
        )


    autorizacion = (
        request.headers.get(
            "Authorization",
            "",
        )
    )

    if not _autorizacion_typebot_valida(
        autorizacion,
        clave_esperada,
    ):

        response = JsonResponse(
            {
                "ok": False,
                "error":
                    "No autorizado.",
            },
            status=401,
        )

        response[
            "WWW-Authenticate"
        ] = "Bearer"

        return response


    # ---------------------------------------------------------
    # Body.
    # ---------------------------------------------------------

    try:

        if (
            request.content_type
            ==
            "application/json"
        ):

            datos = json.loads(
                request.body.decode(
                    "utf-8"
                )
            )

        else:

            datos = (
                request.POST.dict()
            )

    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
    ):

        return JsonResponse(
            {
                "ok": False,
                "error":
                    "El cuerpo JSON no es válido.",
            },
            status=400,
        )


    if not isinstance(
        datos,
        dict,
    ):

        return JsonResponse(
            {
                "ok": False,
                "error":
                    "El cuerpo debe ser un objeto JSON.",
            },
            status=400,
        )


    bot_id_texto = str(
        datos.get(
            "bot_id",
            ""
        )
        or
        ""
    ).strip()

    carrito_token = str(
        datos.get(
            "carrito_token",
            ""
        )
        or
        ""
    ).strip()


    if (
        not bot_id_texto
        or
        not carrito_token
    ):

        return JsonResponse(
            {
                "ok": False,
                "error":
                    "bot_id y carrito_token "
                    "son obligatorios.",
            },
            status=400,
        )


    if len(
        carrito_token
    ) > 64:

        return JsonResponse(
            {
                "ok": False,
                "error":
                    "carrito_token no es válido.",
            },
            status=400,
        )


    try:

        bot_id = int(
            bot_id_texto
        )

    except (
        TypeError,
        ValueError,
    ):

        return JsonResponse(
            {
                "ok": False,
                "error":
                    "bot_id no es válido.",
            },
            status=400,
        )


    bot = (
        Bot.objects
        .select_related(
            "empresa"
        )
        .filter(
            id=bot_id,
            activo=True,
        )
        .first()
    )


    if not bot:

        return JsonResponse(
            {
                "ok": False,
                "error":
                    "Bot no encontrado.",
            },
            status=404,
        )

    lifecycle_error = (
        _nl_api_empresa_operativa_error(
            bot.empresa
        )
    )

    if lifecycle_error is not None:
        return lifecycle_error



    # ---------------------------------------------------------
    # Preparar Pago local bajo bloqueo.
    # Ningún monto se acepta desde Typebot.
    # ---------------------------------------------------------

    with transaction.atomic():

        pedido = (
            Pedido.objects
            .select_for_update()
            .filter(
                empresa=
                    bot.empresa,

                identificador_externo=
                    (
                        "typebot:"
                        +
                        carrito_token
                    ),
            )
            .first()
        )


        if pedido is None:

            return JsonResponse(
                {
                    "ok": False,
                    "error":
                        "Pedido no encontrado.",
                },
                status=404,
            )


        if (
            pedido.estado
            !=
            "confirmado"
        ):

            return JsonResponse(
                {
                    "ok": False,
                    "error":
                        (
                            "Sólo un pedido confirmado "
                            "puede generar un enlace "
                            "de Mercado Pago."
                        ),
                    "pedido_numero":
                        pedido.numero,
                    "estado":
                        pedido.estado,
                },
                status=409,
            )


        total_real = Decimal(
            pedido.total
        )

        total_2 = total_real.quantize(
            Decimal(
                "0.01"
            )
        )


        if total_real <= 0:

            return JsonResponse(
                {
                    "ok": False,
                    "error":
                        "El total del pedido "
                        "debe ser mayor que cero.",
                },
                status=409,
            )


        if total_real != total_2:

            return JsonResponse(
                {
                    "ok": False,
                    "error":
                        (
                            "El total del pedido tiene "
                            "una precisión monetaria "
                            "no compatible."
                        ),
                },
                status=409,
            )


        # -----------------------------------------------------
        # TNL-RESTAURANTE-PAGO-DIRECTO-P2-V1
        #
        # Si ya se eligió efectivo / contra entrega,
        # no generar posteriormente un Checkout Pro.
        #
        # Esta función ya bloquea Pedido con select_for_update(),
        # igual que pago-directo, por lo que ambas rutas quedan
        # serializadas bajo concurrencia.
        # -----------------------------------------------------

        pago_directo = (
            Pago.objects
            .filter(
                pedido=
                    pedido,

                proveedor=
                    Pago.Proveedor
                    .NEGOCIO,

                estado__in=[
                    Pago.Estado.PENDIENTE,
                    Pago.Estado.APROBADO,
                ],
            )
            .first()
        )

        if pago_directo is not None:

            return _checkout_no_disponible(
                mensaje=(
                    "Este pedido ya fue registrado "
                    "para pago en efectivo "
                    "o contra entrega."
                ),
                pedido=pedido,
            )


        config = (
            ConfiguracionMercadoPago.objects
            .filter(
                empresa=
                    pedido.empresa,

                habilitada=True,

                estado_conexion=(
                    ConfiguracionMercadoPago
                    .EstadoConexion
                    .CONECTADA
                ),
            )
            .first()
        )


        if (
            config is None
            or
            not config.access_token_cifrado
            or
            not config.mp_user_id
        ):

            return _checkout_no_disponible(
                mensaje=(
                    "Mercado Pago no está "
                    "disponible para este pedido."
                ),
                pedido=pedido,
            )


        # -----------------------------------------------------
        # Reutilización idempotente de una preferencia activa.
        # -----------------------------------------------------

        existente = (
            Pago.objects
            .filter(
                pedido=pedido,
                proveedor=(
                    Pago.Proveedor
                    .MERCADOPAGO
                ),
                estado__in=[
                    Pago.Estado.CREADO,
                    Pago.Estado.PENDIENTE,
                ],
            )
            .order_by(
                "-id"
            )
            .first()
        )


        if existente is not None:

            if (
                existente.preference_id
                and
                existente.checkout_url
            ):

                return JsonResponse(
                    {
                        "ok": True,
                        "checkout_disponible":
                            True,
                        "checkout_mensaje":
                            (
                                "Puedes pagar este pedido "
                                "con Mercado Pago usando "
                                "el siguiente enlace:"
                            ),
                        "reutilizado":
                            True,
                        "pedido_id":
                            pedido.id,
                        "pedido_numero":
                            pedido.numero,
                        "pago_id":
                            existente.id,
                        "pago_referencia":
                            str(
                                existente.referencia
                            ),
                        "estado_pago":
                            existente.estado,
                        "checkout_url":
                            existente.checkout_url,
                    }
                )


            # Otro proceso podría estar creando
            # actualmente la preferencia.
            return _checkout_no_disponible(
                mensaje=(
                    "El enlace de Mercado Pago "
                    "todavía se está procesando. "
                    "El pedido ya quedó confirmado."
                ),
                pedido=pedido,
            )


        pago = Pago.objects.create(
            pedido=pedido,
            proveedor=(
                Pago.Proveedor
                .MERCADOPAGO
            ),
            estado=(
                Pago.Estado
                .CREADO
            ),
            monto=
                total_2,
            moneda=
                str(
                    pedido.moneda
                ).upper(),
        )


        # Copiamos únicamente los valores
        # necesarios antes de liberar el lock.
        config_id = config.id
        mp_user_id = str(
            config.mp_user_id
        )

        pago_id = pago.id
        referencia = str(
            pago.referencia
        )

        pedido_id = pedido.id
        pedido_numero = (
            pedido.numero
        )

        moneda = str(
            pedido.moneda
        ).upper()

        monto = total_2


    # ---------------------------------------------------------
    # Llamada remota FUERA de la transacción larga.
    # ---------------------------------------------------------

    logger = logging.getLogger(
        "negociolisto.mercadopago"
    )


    try:

        # TNL-MERCADOPAGO-CHECKOUT-AUTOREFRESH-V1
        access_token = (
            obtener_access_token_configuracion(
                config_id
            )
        )

        resultado = (
            crear_preferencia_checkout_pro(
                access_token=
                    access_token,

                external_reference=
                    referencia,

                pedido_numero=
                    pedido_numero,

                monto=
                    monto,

                moneda=
                    moneda,

                expected_collector_id=
                    mp_user_id,
            )
        )

        preference_id = str(
            resultado[
                "preference_id"
            ]
        )

        checkout_url = str(
            resultado[
                "checkout_url"
            ]
        )


        with transaction.atomic():

            locked = (
                Pago.objects
                .select_for_update()
                .get(
                    pk=pago_id
                )
            )

            locked.preference_id = (
                preference_id
            )

            locked.checkout_url = (
                checkout_url
            )

            locked.estado = (
                Pago.Estado
                .PENDIENTE
            )

            locked.estado_proveedor = (
                "preference_created"
            )

            locked.detalle_estado_proveedor = ""

            locked.save()


        return JsonResponse(
            {
                "ok": True,
                "checkout_disponible":
                    True,
                "checkout_mensaje":
                    (
                        "Puedes pagar este pedido "
                        "con Mercado Pago usando "
                        "el siguiente enlace:"
                    ),
                "reutilizado":
                    False,
                "pedido_id":
                    pedido_id,
                "pedido_numero":
                    pedido_numero,
                "pago_id":
                    pago_id,
                "pago_referencia":
                    referencia,
                "estado_pago":
                    Pago.Estado.PENDIENTE,
                "checkout_url":
                    checkout_url,
            }
        )


    except Exception as exc:

        logger.error(
            (
                "TNL_MP_PREFERENCE_FAIL "
                "empresa=%s pedido=%s "
                "pago=%s exception=%s"
            ),
            bot.empresa_id,
            pedido_id,
            pago_id,
            type(exc).__name__,
        )


        try:

            with transaction.atomic():

                locked = (
                    Pago.objects
                    .select_for_update()
                    .get(
                        pk=pago_id
                    )
                )

                if (
                    locked.estado
                    ==
                    Pago.Estado.CREADO
                ):

                    locked.estado = (
                        Pago.Estado.ERROR
                    )

                    locked.estado_proveedor = (
                        "preference_error"
                    )

                    locked.detalle_estado_proveedor = (
                        "No fue posible crear "
                        "la preferencia."
                    )

                    locked.save()

        except Exception as db_exc:

            logger.error(
                (
                    "TNL_MP_PREFERENCE_ERROR_SAVE_FAIL "
                    "empresa=%s pago=%s "
                    "exception=%s"
                ),
                bot.empresa_id,
                pago_id,
                type(db_exc).__name__,
            )


        return _checkout_no_disponible(
            mensaje=(
                "Mercado Pago no está disponible "
                "por el momento. "
                "El pedido ya quedó confirmado."
            ),
            pedido=pedido,
        )


# =============================================================================
# TNL-IA-TYPEBOT-ENDPOINT-V1
# =============================================================================

from django.views.decorators.csrf import csrf_exempt


# ============================================================================
# TNL-IA-PRODUCT-VISUALS-V1
# ============================================================================
#
# Convierte exclusivamente productos REALES del tenant
# mencionados por la respuesta conversacional en un
# contrato visual consumible por Typebot.
#
# La IA:
# - NO elige IDs;
# - NO genera URLs;
# - NO inventa precios.
#
# Todos esos datos vuelven a resolverse en Django.
# ============================================================================

def _ia_productos_visuales_respuesta(
    *,
    bot,
    respuesta,
    limite=6,
):

    vacio = {
        "productos_cantidad": 0,
        "producto_ids": [],
        "producto_nombres": [],
        "producto_precios": [],
        "imagenes_principales": [],
    }


    plantilla = getattr(
        bot,
        "plantilla",
        None,
    )

    tipo = str(
        getattr(
            plantilla,
            "tipo",
            "",
        )
        or
        ""
    ).strip().casefold()


    if tipo != "restaurante":
        return vacio


    try:
        limite = int(
            limite
        )
    except (
        TypeError,
        ValueError,
    ):
        limite = 6


    limite = max(
        1,
        min(
            limite,
            10,
        ),
    )


    import re
    import unicodedata


    def normalizar(value):

        value = str(
            value
            or
            ""
        ).casefold()

        value = (
            unicodedata
            .normalize(
                "NFKD",
                value,
            )
        )

        value = "".join(
            char
            for char in value
            if not unicodedata.combining(
                char
            )
        )

        return " ".join(
            re.findall(
                r"[a-z0-9]+",
                value,
            )
        )


    texto = normalizar(
        respuesta
    )


    def normalizar_sku_literal(value):

        value = str(
            value
            or
            ""
        ).casefold()

        value = (
            unicodedata
            .normalize(
                "NFKD",
                value,
            )
        )

        value = "".join(
            char
            for char in value
            if not unicodedata.combining(
                char
            )
        )

        return re.sub(
            r"\s+",
            " ",
            value,
        ).strip()


    texto_sku_literal = (
        normalizar_sku_literal(
            respuesta
        )
    )


    if not texto:
        return vacio


    tokens_texto = set(
        texto.split()
    )


    stopwords = {
        "a",
        "al",
        "con",
        "de",
        "del",
        "el",
        "en",
        "la",
        "las",
        "los",
        "o",
        "para",
        "por",
        "un",
        "una",
        "y",
    }


    try:
        from core.models import Producto
        from core.services.catalogo import (
            productos_vendibles,
        )

        # TNL-CATALOGO-REGLAS-V1
        # Mismas reglas que el menú: sólo lo que el
        # carrito aceptaría.
        productos = list(
            productos_vendibles(
                empresa_id=bot.empresa_id,
                plantilla_id=bot.plantilla_id,
                restaurante=True,
                queryset=(
                    Producto.objects
                    .select_related(
                        "catalogo",
                    )
                ),
            )
            .exclude(
                imagen_principal=""
            )
            .order_by(
                "nombre",
                "id",
            )[
                :200
            ]
        )

    except Exception:

        # La capa visual es complementaria.
        # Nunca debe derribar la respuesta IA.
        return vacio


    productos.sort(
        key=lambda producto: (
            -len(
                normalizar(
                    producto.nombre
                )
            ),
            producto.id,
        )
    )


    sku_literal_repeticiones = {}

    for producto in productos:

        sku_literal = (
            normalizar_sku_literal(
                producto.sku
            )
        )

        if not sku_literal:
            continue

        sku_literal_repeticiones[
            sku_literal
        ] = (
            sku_literal_repeticiones.get(
                sku_literal,
                0,
            )
            +
            1
        )


    def coincidencia_fuerte_nombre(
        producto,
    ):

        nombre_normalizado = normalizar(
            producto.nombre
        )

        if not nombre_normalizado:
            return False

        if (
            (
                " "
                + nombre_normalizado
                + " "
            )
            in
            (
                " "
                + texto
                + " "
            )
        ):
            return True

        tokens_nombre = [
            token
            for token
            in nombre_normalizado.split()
            if token
            not in stopwords
        ]

        return (
            bool(
                tokens_nombre
            )
            and
            all(
                token
                in
                tokens_texto
                for token
                in
                tokens_nombre
            )
        )


    hay_coincidencia_fuerte_nombre = any(
        coincidencia_fuerte_nombre(
            producto
        )
        for producto
        in productos
    )


    encontrados = []


    for producto in productos:

        nombre_normalizado = (
            normalizar(
                producto.nombre
            )
        )

        sku_literal = (
            normalizar_sku_literal(
                producto.sku
            )
        )


        tokens_nombre = [
            token
            for token
            in nombre_normalizado.split()
            if token
            not in stopwords
        ]


        coincidencia = False


        if nombre_normalizado:

            coincidencia = (
                (
                    " "
                    + nombre_normalizado
                    + " "
                )
                in
                (
                    " "
                    + texto
                    + " "
                )
            )


        if (
            not coincidencia
            and
            not hay_coincidencia_fuerte_nombre
            and
            sku_literal
            and
            len(
                sku_literal
            )
            >=
            3
            and
            sku_literal_repeticiones.get(
                sku_literal,
                0,
            )
            ==
            1
        ):

            coincidencia = (
                re.search(
                    (
                        r"(?<!\w)"
                        + re.escape(
                            sku_literal
                        )
                        + r"(?!\w)"
                    ),
                    texto_sku_literal,
                )
                is not None
            )


        if (
            not coincidencia
            and
            tokens_nombre
        ):

            coincidencia = all(
                token
                in
                tokens_texto
                for token
                in
                tokens_nombre
            )


        if not coincidencia:
            continue


        try:

            imagen = (
                _producto_media_url(
                    producto.imagen_principal
                )
            )

            if not imagen:
                continue


            precio = (
                _restaurante_api_dinero(
                    producto.precio,
                    etiqueta=(
                        "El precio del producto "
                        f"'{producto.nombre}' "
                        "para respuesta IA visual"
                    ),
                )
            )

        except Exception:

            continue


        encontrados.append(
            {
                "id":
                    producto.id,

                "nombre":
                    producto.nombre,

                "precio":
                    precio,

                "imagen":
                    imagen,
            }
        )


        if (
            len(
                encontrados
            )
            >=
            limite
        ):
            break


    if not encontrados:
        return vacio


    return {
        "productos_cantidad":
            len(
                encontrados
            ),

        "producto_ids": [
            item["id"]
            for item
            in encontrados
        ],

        "producto_nombres": [
            item["nombre"]
            for item
            in encontrados
        ],

        "producto_precios": [
            item["precio"]
            for item
            in encontrados
        ],

        "imagenes_principales": [
            item["imagen"]
            for item
            in encontrados
        ],
    }



# =============================================================================
# TNL-IA-CATALOGO-INTENT-V1
# =============================================================================
#
# Solicitudes GENERALES de menu / catalogo / productos / servicios
# para restaurantes se resuelven deterministicamente.
#
# No consume proveedor IA.
# Recomendaciones especificas continúan por IA.
#
# =============================================================================

def _ia_intencion_catalogo_restaurante(
    *,
    bot,
    mensaje,
):
    import re
    import unicodedata


    plantilla = getattr(
        bot,
        "plantilla",
        None,
    )


    tipo = str(
        getattr(
            plantilla,
            "tipo",
            "",
        )
        or
        ""
    ).strip().casefold()


    if tipo != "restaurante":
        return False


    texto = str(
        mensaje
        or
        ""
    ).casefold()


    texto = unicodedata.normalize(
        "NFKD",
        texto,
    )


    texto = "".join(
        char
        for char in texto
        if not unicodedata.combining(
            char
        )
    )


    texto = re.sub(
        r"[^a-z0-9]+",
        " ",
        texto,
    )


    texto = re.sub(
        r"\s+",
        " ",
        texto,
    ).strip()


    if not texto:
        return False


    exclusiones = (
        "recomiend",
        "recomendacion",
        "sugier",
        "sugerencia",
        "cual es mejor",
        "cuales son mejores",
        "cual me conviene",
        "mejor opcion",
        "mejores opciones",
    )


    if any(
        token in texto
        for token in exclusiones
    ):
        return False


    exactos = {
        "menu",
        "ver menu",
        "mostrar menu",
        "muestrame el menu",
        "dame el menu",
        "quiero ver el menu",
        "quiero conocer el menu",

        "carta",
        "ver carta",
        "mostrar carta",
        "muestrame la carta",

        "catalogo",
        "ver catalogo",
        "mostrar catalogo",
        "muestrame el catalogo",

        "categorias",
        "ver categorias",
        "mostrar categorias",

        "productos",
        "ver productos",
        "mostrar productos",
        "muestrame los productos",
        "muestrame sus productos",

        "servicios",
        "ver servicios",
        "mostrar servicios",
        "muestrame los servicios",
        "muestrame sus servicios",

        "productos y servicios",
        "productos o servicios",
        "productos y o servicios",

        "servicios y productos",
        "servicios o productos",
        "servicios y o productos",
    }


    if texto in exactos:
        return True


    objeto = (
        r"(?:"
        r"productos?|"
        r"servicios?|"
        r"productos?\s+(?:y|o|y o)\s+servicios?|"
        r"servicios?\s+(?:y|o|y o)\s+productos?|"
        r"menu|"
        r"catalogo|"
        r"carta|"
        r"categorias?|"
        r"platillos?|"
        r"opciones?"
        r")"
    )


    patrones = (
        rf"\bque\s+{objeto}\s+"
        r"(?:tienen|manejan|ofrecen|venden|hay)\b",

        rf"\b(?:cuales|que)\s+son\s+"
        rf"(?:sus|los|las)?\s*{objeto}\b",

        r"\bque\s+(?:venden|ofrecen|manejan)\b",

        r"\b(?:ver|mostrar|muestrame|ensename|dame|consultar)\b"
        r".*\b(?:menu|catalogo|carta|categorias?|productos?|servicios?)\b",

        r"\b(?:quiero|quisiera|me gustaria)\s+"
        r"(?:ver|conocer|consultar)\b"
        r".*\b(?:menu|catalogo|carta|categorias?|productos?|servicios?|"
        r"lo que venden)\b",

        r"\b(?:tienen|manejan|ofrecen)\s+"
        r"(?:menu|catalogo|carta)\b",

        r"\b(?:cual|cuales)\s+es\s+"
        r"(?:su|el|la)\s+"
        r"(?:menu|catalogo|carta)\b",

        r"\bque\s+hay\s+en\s+"
        r"(?:el|su|la)\s+"
        r"(?:menu|catalogo|carta)\b",

        r"\bque\s+(?:tienen|hay)\s+"
        r"(?:para\s+)?"
        r"(?:comer|cenar|almorzar|tomar)\b",
    )



    #
    # TNL-CHANGO-CATALOGO-NATURAL-V1
    #
    # Extensiones lingüísticas habilitadas
    # exclusivamente para CHANGO durante
    # su fase de certificación.
    #
    # No altera ALITAS ni otros restaurantes.
    #
    patrones_chango = ()


    plantilla_tipo = str(
        getattr(
            getattr(
                bot,
                "plantilla",
                None,
            ),
            "tipo",
            "",
        )
        or ""
    ).strip()

    if plantilla_tipo == "restaurante":

        patrones_chango = (

            rf"\bque\s+{objeto}\s+tienes\b",

            rf"\b(?:cuales|que)\s+son\s+"
            rf"tus\s+{objeto}\b",

            r"\b(?:muestra\s+me|me\s+muestras?)\b"
            r".*\b(?:menu|catalogo|carta|categorias?|"
            r"productos?|servicios?)\b",

            r"\bque\s+hay\s+de\s+"
            r"(?:comer|cenar|almorzar|tomar)\b",

                #
                # TNL-CHANGO-NEW-ORDER-CATALOG-V1
                #
                # Nuevo pedido GENERICO → catálogo real.
                # Sólo CHANGO. No absorbe productos concretos.
                #
                r"^(?:quiero|quisiera|deseo|me\s+gustaria)\s+"
                r"(?:(?:hacer|realizar|iniciar|levantar)\s+)?"
                r"(?:un\s+nuevo|un|otro|nuevo)\s+pedido"
                r"(?:\s+por\s+favor)?$",

                r"^(?:quiero|quisiera|deseo|me\s+gustaria)\s+"
                r"(?:pedir|ordenar)"
                r"(?:\s+algo)?"
                r"(?:\s+por\s+favor)?$",

                r"^(?:hacer|realizar|iniciar|levantar)\s+"
                r"(?:un\s+nuevo|un|otro|nuevo)\s+pedido"
                r"(?:\s+por\s+favor)?$",

        )


    return any(
        re.search(
            patron,
            texto,
        )
        is not None
        for patron in (patrones + patrones_chango)
    )

def _ia_intencion_recomendacion_producto_restaurante(
    *,
    bot,
    mensaje,
):
    """
    Determina si el mensaje original del usuario
    debe habilitar productos visuales.

    Acepta:
    - recomendación explícita;
    - compra/pedido directo;
    - sustitución explícita de producto.

    Excluye:
    - consultas informativas;
    - cancelación/anulación;
    - negación de producto sin sustitución positiva.
    """
    import re
    import unicodedata

    plantilla = getattr(
        bot,
        "plantilla",
        None,
    )

    tipo = str(
        getattr(
            plantilla,
            "tipo",
            "",
        )
        or
        ""
    ).strip().casefold()

    if tipo != "restaurante":
        return False

    texto = str(
        mensaje
        or
        ""
    ).casefold()

    texto = unicodedata.normalize(
        "NFKD",
        texto,
    )

    texto = "".join(
        char
        for char in texto
        if not unicodedata.combining(
            char
        )
    )

    texto = re.sub(
        r"[^a-z0-9]+",
        " ",
        texto,
    )

    texto = re.sub(
        r"\s+",
        " ",
        texto,
    ).strip()

    if not texto:
        return False


    senales_recomendacion = (
        "recomiend",
        "recomendacion",
        "sugier",
        "sugerencia",
        "cual es mejor",
        "cuales son mejores",
        "cual me conviene",
        "mejor opcion",
        "mejores opciones",
    )

    if any(
        senal in texto
        for senal
        in senales_recomendacion
    ):
        return True


    #
    # Sustitución positiva explícita.
    #
    # Se evalúa ANTES de la negación para aceptar:
    #
    # "no quiero hamburguesa mejor quiero papas"
    #
    senales_reemplazo = (
        "mejor quiero ",
        "mejor quisiera ",
        "mejor deseo ",
        "mejor dame ",
        "mejor deme ",
        "mejor ponme ",
        "mejor agregame ",
        "mejor agrega ",
        "mejor anademe ",
        "mejor anade ",
        "mejor me llevo ",
    )

    if any(
        senal in texto
        for senal
        in senales_reemplazo
    ):
        return True


    #
    # Intención informativa.
    #
    if re.search(
        (
            r"\b"
            r"(?:quiero|quisiera|deseo)"
            r"\s+"
            r"(?:saber|conocer|preguntar|consultar)"
            r"\b"
        ),
        texto,
    ):
        return False


    #
    # Cancelación/anulación explícita.
    #
    if re.search(
        (
            r"\b"
            r"(?:cancelar|cancela|cancelame|"
            r"anular|anula|anulame)"
            r"\b"
        ),
        texto,
    ):
        return False


    #
    # Negación de producto sin sustitución positiva.
    #
    if re.search(
        (
            r"\b"
            r"(?:ya\s+)?"
            r"no\s+"
            r"(?:quiero|quisiera|deseo)"
            r"\b"
        ),
        texto,
    ):
        return False


    #
    # Compra / pedido directo.
    #
    if re.search(
        (
            r"\b"
            r"(?:quiero|quisiera|deseo)"
            r"\s+"
            r"(?!"
            r"saber\b|"
            r"conocer\b|"
            r"preguntar\b|"
            r"consultar\b|"
            r"cancelar\b|"
            r"anular\b"
            r")"
        ),
        texto,
    ):
        return True


    if re.search(
        (
            r"\b"
            r"(?:"
            r"dame|"
            r"deme|"
            r"ponme|"
            r"agregame|"
            r"agrega|"
            r"anademe|"
            r"anade"
            r")"
            r"\b"
        ),
        texto,
    ):
        return True


    if (
        "me llevo "
        in texto
    ):
        return True


    return False





# TNL-CHANGO-IA-DIRECT-PRODUCT-HANDOFF-V1
def _ia_handoff_producto_directo_chango(
    *,
    bot,
    mensaje,
    productos_visuales,
):
    """
    CHANGO únicamente.

    Si una intención de compra ya resolvió exactamente
    un producto real, entrega el control al flujo
    estructurado de producto.

    Las recomendaciones explícitas siguen usando
    el flujo visual existente.
    """

    plantilla_tipo = str(
        getattr(
            getattr(
                bot,
                "plantilla",
                None,
            ),
            "tipo",
            "",
        )
        or ""
    ).strip()

    if plantilla_tipo != "restaurante":
        return productos_visuales

    if not isinstance(
        productos_visuales,
        dict,
    ):
        return productos_visuales

    try:
        cantidad = int(
            productos_visuales.get(
                "productos_cantidad"
            )
            or
            0
        )

    except (
        TypeError,
        ValueError,
    ):
        return productos_visuales

    if cantidad != 1:
        return productos_visuales

    import unicodedata

    texto = " ".join(
        str(
            mensaje
            or
            ""
        )
        .casefold()
        .split()
    )

    texto = "".join(
        ch
        for ch
        in unicodedata.normalize(
            "NFD",
            texto,
        )
        if not unicodedata.combining(
            ch
        )
    )

    senales_recomendacion = (
        "recomiend",
        "recomendacion",
        "suger",
        "cual es mejor",
        "cuales son mejores",
        "cual me conviene",
        "mejor opcion",
        "mejores opciones",
    )

    if any(
        senal in texto
        for senal
        in senales_recomendacion
    ):
        return productos_visuales

    def primero(valor):

        if isinstance(
            valor,
            (list, tuple),
        ):
            if not valor:
                return ""

            return valor[0]

        return valor

    producto_id = primero(
        productos_visuales.get(
            "producto_ids"
        )
    )

    producto_nombre = primero(
        productos_visuales.get(
            "producto_nombres"
        )
    )

    producto_id = str(
        producto_id
        or
        ""
    ).strip()

    producto_nombre = str(
        producto_nombre
        or
        ""
    ).strip()

    if not producto_id:
        return productos_visuales

    resultado = dict(
        productos_visuales
    )

    resultado.update(
        {
            "ia_accion":
                "mostrar_producto",
            "producto_id":
                producto_id,
            "producto_nombre":
                producto_nombre,
        }
    )

    return resultado




# TNL-CHANGO-IA-CURRENT-TRANSACTION-HANDOFF-V1
# TNL-CHANGO-IA-CURRENT-FINALIZE-HANDOFF-V1
def _ia_prehandoff_transaccion_actual_chango(
    *,
    bot,
    mensaje,
    carrito_token,
):
    """
    CHANGO únicamente.

    Convierte únicamente intenciones transaccionales
    del carrito ACTUAL en acciones estructuradas.

    Nunca busca pedidos históricos por pedido_id,
    teléfono, número de pedido ni memoria IA.
    """

    plantilla_tipo = str(
        getattr(
            getattr(
                bot,
                "plantilla",
                None,
            ),
            "tipo",
            "",
        )
        or ""
    ).strip()

    if plantilla_tipo != "restaurante":
        return None

    token = str(
        carrito_token
        or
        ""
    ).strip()

    if not token:
        return None

    import re
    import unicodedata

    texto = " ".join(
        str(
            mensaje
            or
            ""
        )
        .casefold()
        .split()
    )

    texto = "".join(
        char
        for char
        in unicodedata.normalize(
            "NFD",
            texto,
        )
        if not unicodedata.combining(
            char
        )
    )

    texto = re.sub(
        r"[¿?¡!.,;:]+",
        " ",
        texto,
    )

    texto = " ".join(
        texto.split()
    )


    consultas_pago = (
        "aceptan tarjeta",
        "aceptan tarjetas",
        "que tarjetas aceptan",
        "cuales tarjetas aceptan",
        "que metodos de pago",
        "cuales metodos de pago",
        "formas de pago",
        "tienen mercado pago",
        "manejan mercado pago",
        "como funciona mercado pago",
    )

    es_consulta_pago = any(
        consulta in texto
        for consulta
        in consultas_pago
    )


    selecciones_mp_exactas = {
        "tarjeta",
        "con tarjeta",
        "tarjeta de credito",
        "tarjeta de debito",
        "mercado pago",
        "pago con tarjeta",
        "pagar con tarjeta",
        "pago por tarjeta",
        "pagar por tarjeta",
        "pago con mercado pago",
        "pagar con mercado pago",
    }

    senales_mp = (
        "quiero pagar con tarjeta",
        "quisiera pagar con tarjeta",
        "deseo pagar con tarjeta",
        "prefiero pagar con tarjeta",
        "quiero pagar con mercado pago",
        "quisiera pagar con mercado pago",
        "deseo pagar con mercado pago",
        "prefiero pagar con mercado pago",
        "si quiero pagar con mercado pago",
        "si pago con mercado pago",
        "pago con mercado pago",
        "pagar con mercado pago",
        "pago con tarjeta",
        "pagar con tarjeta",
    )

    negaciones_mp = (
        "no quiero pagar con mercado pago",
        "no deseo pagar con mercado pago",
        "no quisiera pagar con mercado pago",
        "no pago con mercado pago",
    )

    es_negacion_mp = any(
        senal in texto
        for senal
        in negaciones_mp
    )


    es_pago_mp = (
        not es_consulta_pago
        and
        not es_negacion_mp
        and
        (
            texto
            in
            selecciones_mp_exactas
            or
            any(
                senal in texto
                for senal
                in senales_mp
            )
        )
    )


    selecciones_efectivo_exactas = {
        "efectivo",
        "en efectivo",
        "pago en efectivo",
        "pagar en efectivo",
        "contra entrega",
        "pago contra entrega",
        "pagar contra entrega",
        "efectivo contra entrega",
    }

    senales_efectivo = (
        "quiero pagar en efectivo",
        "quisiera pagar en efectivo",
        "deseo pagar en efectivo",
        "prefiero pagar en efectivo",
        "quiero pagar contra entrega",
        "quisiera pagar contra entrega",
        "deseo pagar contra entrega",
        "prefiero pagar contra entrega",
    )

    es_pago_efectivo = (
        texto
        in
        selecciones_efectivo_exactas
        or
        any(
            senal in texto
            for senal
            in senales_efectivo
        )
    )


    confirmaciones_exactas = {
        "confirmo",
        "si confirmo",
        "confirmar",
        "confirmar pedido",
        "confirmar mi pedido",
        "todo correcto",
        "todo esta correcto",
        "esta correcto",
        "si esta correcto",
        "si todo esta correcto",
    }

    senales_confirmacion = (
        "todo esta correcto confirmo",
        "todo correcto confirmo",
        "esta correcto confirmo",
        "si confirmo el pedido",
        "confirmo el pedido",
        "confirmar el pedido",
        "si todo correcto",
        "si todo esta correcto",
    )

    es_confirmacion = (
        texto
        in
        confirmaciones_exactas
        or
        any(
            senal in texto
            for senal
            in senales_confirmacion
        )
    )


    # --------------------------------------------------------------
    # TNL-CHANGO-IA-PAYMENT-CANONICAL-HANDOFF-V1
    #
    # Mientras el pedido siga en carrito, cualquier consulta o
    # selección de método de pago abandona la respuesta generativa
    # y continúa por el flujo canónico de finalización.
    #
    # Mercado Pago directo se conserva únicamente para un pedido
    # que YA esté confirmado.
    # --------------------------------------------------------------

    if (
        es_consulta_pago
        or
        es_pago_mp
        or
        es_pago_efectivo
        or
        es_negacion_mp
    ):

        pedido, pedido_error = (
            _restaurante_api_resolver_pedido(
                bot=bot,
                carrito_token=
                    token,
                solo_carrito=False,
            )
        )

        if (
            pedido_error is not None
            or
            pedido is None
        ):
            return None

        estado_pedido = (
            str(
                getattr(
                    pedido,
                    "estado",
                    "",
                )
                or
                ""
            )
            .strip()
            .lower()
        )

        if estado_pedido == "confirmado":

            if es_pago_mp:

                return {
                    "ia_accion":
                        "pagar_mercadopago",
                }

            return None

        if estado_pedido == "carrito":

            return {
                "ia_accion":
                    "finalizar_pedido_actual",
            }

        return None


    if es_confirmacion:

        pedido, pedido_error = (
            _restaurante_api_resolver_pedido(
                bot=bot,
                carrito_token=
                    token,
                solo_carrito=True,
            )
        )

        if (
            pedido_error is not None
            or
            pedido is None
        ):
            return None

        return {
            "ia_accion":
                "finalizar_pedido_actual",
        }


    return None


# TNL-CHANGO-PRE-IA-CURRENT-MESSAGE-HANDOFF-V1
def _ia_guardrail_salida_pago_chango(
    *,
    bot,
    respuesta,
    carrito_token,
):
    """
    CHANGO únicamente.

    Impide que una respuesta generativa tome control
    sobre los métodos de pago.

    Si existe un carrito ACTUAL y la salida IA intenta
    preguntar, sugerir o describir pagos, el control
    regresa al flujo canónico de finalización.

    TNL-IA-SIN-CARRITO-GUARD-V1

    Si NO existe carrito y la salida IA habla de pagos, de
    métodos que el negocio no tiene (transferencia, enlaces
    de pago) o da por tomado un pedido, esa salida se
    descarta: se responde con un texto corto y se manda al
    menú real (ia_accion=mostrar_categorias). La IA no toma
    pedidos.
    """

    plantilla_tipo = str(
        getattr(
            getattr(
                bot,
                "plantilla",
                None,
            ),
            "tipo",
            "",
        )
        or ""
    ).strip()

    if plantilla_tipo != "restaurante":
        return None

    token = str(
        carrito_token
        or
        ""
    ).strip()

    import re
    import unicodedata

    texto = " ".join(
        str(
            respuesta
            or
            ""
        )
        .casefold()
        .split()
    )

    texto = "".join(
        char
        for char
        in unicodedata.normalize(
            "NFD",
            texto,
        )
        if not unicodedata.combining(
            char
        )
    )

    texto = re.sub(
        r"[¿?¡!.,;:]+",
        " ",
        texto,
    )

    texto = " ".join(
        texto.split()
    )

    # --------------------------------------------------------------
    # TNL-CHANGO-IA-PAYMENT-OUTPUT-GUARD-V1
    # --------------------------------------------------------------

    senales_pago_salida = (
        "metodo de pago",
        "metodos de pago",
        "mercado pago",
        "tarjeta",
        "efectivo",
        "contra entrega",
        "transferencia",
    )

    # Sin carrito no basta con vigilar el pago: también hay
    # que impedir que la IA dé por tomado un pedido u ofrezca
    # métodos que el negocio no tiene.
    senales_sin_carrito = senales_pago_salida + (
        "enlace de pago",
        "link de pago",
        "liga de pago",
        "deposito",
        "clabe",
        "spei",
        "paypal",
        "pedido registrado",
        "pedido confirmado",
        "pedido quedo",
        "quedo registrado",
        "orden registrada",
        "tomar tu pedido",
        "tomo tu pedido",
        "anoto tu pedido",
        "tu pedido",
        "subtotal",
    )

    hay_senal_pago = any(
        senal in texto
        for senal
        in senales_pago_salida
    )

    pedido = None

    if token:

        pedido, pedido_error = (
            _restaurante_api_resolver_pedido(
                bot=bot,
                carrito_token=
                    token,
                solo_carrito=True,
            )
        )

        if pedido_error is not None:
            pedido = None

    if pedido is not None:

        # Comportamiento vigente: con carrito real el control
        # vuelve al cierre canónico.
        if not hay_senal_pago:
            return None

        return {
            "ia_accion":
                "finalizar_pedido_actual",
        }

    if not any(
        senal in texto
        for senal
        in senales_sin_carrito
    ):
        return None

    return {
        "ia_accion":
            "mostrar_categorias",

        "respuesta":
            (
                "Para tomar tu pedido y cobrarlo necesito "
                "que lo hagas desde el menú: ahí eliges "
                "productos y el pago disponible. Te muestro "
                "las categorías."
            ),
    }


def _ia_guardrail_salida_tipo_orden_chango(
    *,
    bot,
    respuesta,
    carrito_token,
):
    """
    CHANGO únicamente.

    Si una respuesta generativa intenta preguntar
    recoger / para llevar vs domicilio cuando existe
    un carrito ACTUAL, conserva únicamente el texto
    previo y entrega la selección al menú canónico.
    """

    plantilla_tipo = str(
        getattr(
            getattr(
                bot,
                "plantilla",
                None,
            ),
            "tipo",
            "",
        )
        or ""
    ).strip()

    if plantilla_tipo != "restaurante":
        return None

    token = str(
        carrito_token
        or
        ""
    ).strip()

    if not token:
        return None

    respuesta_original = str(
        respuesta
        or
        ""
    ).strip()

    if not respuesta_original:
        return None

    import re
    import unicodedata

    def normalizar(value):

        texto = " ".join(
            str(
                value
                or
                ""
            )
            .casefold()
            .split()
        )

        texto = "".join(
            char
            for char
            in unicodedata.normalize(
                "NFD",
                texto,
            )
            if not unicodedata.combining(
                char
            )
        )

        texto = re.sub(
            r"[¿?¡!.,;:]+",
            " ",
            texto,
        )

        return " ".join(
            texto.split()
        )

    texto = normalizar(
        respuesta_original
    )

    tiene_domicilio = (
        "domicilio"
        in texto
    )

    tiene_recoleccion = (
        "recoger"
        in texto
        or
        "para llevar"
        in texto
    )

    if not (
        tiene_domicilio
        and
        tiene_recoleccion
    ):
        return None

    # No intervenir mientras la IA todavía esté
    # preguntando cantidad.
    if any(
        señal in texto
        for señal in (
            "cuantas",
            "cuantos",
            "cantidad",
        )
    ):
        return None

    pedido, pedido_error = (
        _restaurante_api_resolver_pedido(
            bot=bot,
            carrito_token=
                token,
            solo_carrito=True,
        )
    )

    if (
        pedido_error is not None
        or
        pedido is None
    ):
        return None

    # --------------------------------------------------------------
    # TNL-CHANGO-IA-TIPO-ORDEN-OUTPUT-GUARD-V1
    # --------------------------------------------------------------

    respuesta_limpia = (
        respuesta_original
    )

    encontrada = False
    cursor = 0

    while True:

        indice = respuesta_original.find(
            "¿",
            cursor,
        )

        if indice < 0:
            break

        cola = normalizar(
            respuesta_original[
                indice:
            ]
        )

        if (
            "domicilio"
            in cola
            and
            (
                "recoger"
                in cola
                or
                "para llevar"
                in cola
            )
        ):
            respuesta_limpia = (
                respuesta_original[
                    :indice
                ]
                .rstrip()
            )

            encontrada = True
            break

        cursor = indice + 1

    if not encontrada:

        lineas = []

        for linea in (
            respuesta_original
            .splitlines()
        ):

            linea_normalizada = (
                normalizar(
                    linea
                )
            )

            if (
                "domicilio"
                in linea_normalizada
                and
                (
                    "recoger"
                    in linea_normalizada
                    or
                    "para llevar"
                    in linea_normalizada
                )
            ):
                continue

            lineas.append(
                linea
            )

        respuesta_limpia = (
            "\n".join(
                lineas
            )
            .strip()
        )

    return {
        "ia_accion":
            "seleccionar_tipo_orden_actual",

        "respuesta":
            respuesta_limpia,
    }


def _ia_prehandoff_producto_mensaje_chango(
    *,
    bot,
    mensaje,
):
    """
    CHANGO únicamente.

    Resuelve compras singulares usando exclusivamente
    el mensaje ACTUAL antes de consultar a la IA.

    Esto evita mezclar productos de pedidos anteriores
    conservados en la memoria conversacional.
    """

    plantilla_tipo = str(
        getattr(
            getattr(
                bot,
                "plantilla",
                None,
            ),
            "tipo",
            "",
        )
        or ""
    ).strip()

    if plantilla_tipo != "restaurante":
        return None

    import unicodedata

    texto = " ".join(
        str(
            mensaje
            or
            ""
        )
        .casefold()
        .split()
    )

    texto = "".join(
        ch
        for ch in unicodedata.normalize(
            "NFD",
            texto,
        )
        if not unicodedata.combining(ch)
    )

    #
    # El clasificador existente cubre:
    # quiero / también quiero / ahora quiero /
    # dame / agregame / sustituciones ya conocidas.
    #
    intencion_existente = bool(
        _ia_intencion_recomendacion_producto_restaurante(
            bot=bot,
            mensaje=mensaje,
        )
    )

    # ============================================================
    # TNL-RESTAURANTE-IA-DIRECT-CATALOG-SELECTION-V1
    # ============================================================
    #
    # Una respuesta corta que coincide EXACTAMENTE con el nombre
    # o SKU de un único producto real se interpreta como selección
    # directa del catálogo.
    #
    # Ejemplos:
    #   "Boneless" -> nombre exacto
    #   "Extras"   -> SKU exacto "EXTRAS"
    #
    # No interpreta frases parciales ni preguntas como selección.
    #
    palabras_directas = texto.split()

    if (
        palabras_directas
        and
        len(
            palabras_directas
        )
        <=
        4
    ):

        productos_directos = (
            _ia_productos_visuales_respuesta(
                bot=bot,
                respuesta=mensaje,
            )
        )

        try:

            cantidad_directa = int(
                productos_directos.get(
                    "productos_cantidad"
                )
                or
                0
            )

        except (
            TypeError,
            ValueError,
        ):

            cantidad_directa = 0

        if cantidad_directa == 1:

            def primero_directo(
                valor,
            ):

                if isinstance(
                    valor,
                    (
                        list,
                        tuple,
                    ),
                ):

                    if not valor:
                        return ""

                    return valor[0]

                return valor

            producto_id_directo = str(
                primero_directo(
                    productos_directos.get(
                        "producto_ids"
                    )
                )
                or
                ""
            ).strip()

            try:

                producto_id_directo_int = int(
                    producto_id_directo
                )

            except (
                TypeError,
                ValueError,
            ):

                producto_id_directo_int = 0

            if producto_id_directo_int > 0:

                from core.services.catalogo import (
                    productos_vendibles,
                )

                # TNL-CATALOGO-REGLAS-V1
                producto_directo = (
                    productos_vendibles(
                        empresa_id=bot.empresa_id,
                        plantilla_id=bot.plantilla_id,
                        restaurante=True,
                    )
                    .filter(
                        id=
                            producto_id_directo_int,
                    )
                    .only(
                        "id",
                        "nombre",
                        "sku",
                    )
                    .first()
                )

                if producto_directo is not None:

                    def normalizar_catalogo_directo(
                        valor,
                    ):

                        valor = " ".join(
                            str(
                                valor
                                or
                                ""
                            )
                            .casefold()
                            .split()
                        )

                        return "".join(
                            ch
                            for ch
                            in unicodedata.normalize(
                                "NFD",
                                valor,
                            )
                            if not unicodedata.combining(
                                ch
                            )
                        )

                    coincidencias_directas = {
                        normalizar_catalogo_directo(
                            producto_directo.nombre
                        ),
                        normalizar_catalogo_directo(
                            producto_directo.sku
                        ),
                    }

                    coincidencias_directas.discard(
                        ""
                    )

                    if texto in coincidencias_directas:

                        resultado_directo = (
                            _ia_handoff_producto_directo_chango(
                                bot=bot,
                                mensaje=mensaje,
                                productos_visuales=
                                    productos_directos,
                            )
                        )

                        if (
                            isinstance(
                                resultado_directo,
                                dict,
                            )
                            and
                            resultado_directo.get(
                                "ia_accion"
                            )
                            ==
                            "mostrar_producto"
                        ):

                            return resultado_directo

    # ============================================================
    # TNL-RESTAURANTE-IA-QUANTITY-LED-PRODUCT-V1
    # ============================================================
    #
    # Frases naturales iniciadas por una cantidad positiva pueden
    # representar directamente un producto real del catálogo:
    #
    #   "10 alitas"
    #   "10 alitas con buffalo rams"
    #   "10 alitas con salsa búfalo rams"
    #
    # Sólo hay handoff cuando el resolver certificado encuentra
    # exactamente UN producto real. No se infiere cantidad del
    # Pedido aquí: Typebot conserva su flujo de cantidad canónico.
    #
    palabras_cantidad = texto.split()

    if palabras_cantidad:

        primer_token_cantidad = (
            palabras_cantidad[0]
            .strip(
                "¿?¡!.,;:"
            )
        )

        if (
            primer_token_cantidad.isdigit()
            and
            int(
                primer_token_cantidad
            )
            >
            0
        ):

            productos_cantidad = (
                _ia_productos_visuales_respuesta(
                    bot=bot,
                    respuesta=mensaje,
                )
            )

            try:

                cantidad_resuelta = int(
                    productos_cantidad.get(
                        "productos_cantidad"
                    )
                    or
                    0
                )

            except (
                TypeError,
                ValueError,
            ):

                cantidad_resuelta = 0

            if cantidad_resuelta == 1:

                resultado_cantidad = (
                    _ia_handoff_producto_directo_chango(
                        bot=bot,
                        mensaje=mensaje,
                        productos_visuales=
                            productos_cantidad,
                    )
                )

                if (
                    isinstance(
                        resultado_cantidad,
                        dict,
                    )
                    and
                    resultado_cantidad.get(
                        "ia_accion"
                    )
                    ==
                    "mostrar_producto"
                ):

                    return resultado_cantidad

    #
    # Caso natural que el clasificador existente
    # no captura:
    #
    #   "Mejor una hamburguesa doble"
    #   "Mejor la hamburguesa doble"
    #
    # Deliberadamente NO incluye:
    #   "cual es mejor"
    #   "mejor opcion"
    #   "que me recomiendas"
    #
    reemplazo_mejor_directo = (
        texto.startswith(
            (
                "mejor un ",
                "mejor una ",
                "mejor unos ",
                "mejor unas ",
                "mejor el ",
                "mejor la ",
                "mejor los ",
                "mejor las ",
            )
        )
    )

    if not (
        intencion_existente
        or
        reemplazo_mejor_directo
    ):
        return None

    productos_mensaje = (
        _ia_productos_visuales_respuesta(
            bot=bot,
            respuesta=mensaje,
        )
    )

    resultado = (
        _ia_handoff_producto_directo_chango(
            bot=bot,
            mensaje=mensaje,
            productos_visuales=
                productos_mensaje,
        )
    )

    if not isinstance(
        resultado,
        dict,
    ):
        return None

    if (
        resultado.get("ia_accion")
        !=
        "mostrar_producto"
    ):
        return None

    return resultado


# ------------------------------------------------------------------
# TNL-RESTAURANTE-IA-MULTITURN-POSTGEN-V2
# ------------------------------------------------------------------
def _ia_continuacion_compra_multiturno_restaurante(
    *,
    bot,
    mensaje,
    historial,
    respuesta_ia,
):
    """
    Permite que una aclaración breve continúe una intención
    de compra del intercambio inmediatamente anterior.

    La salida actual de la IA debe resolver exactamente
    un producto real del catálogo.

    No crea pedidos.
    No busca pedidos históricos.
    No modifica memoria.
    No decide métodos de pago.
    """

    plantilla_tipo = str(
        getattr(
            getattr(
                bot,
                "plantilla",
                None,
            ),
            "tipo",
            "",
        )
        or
        ""
    ).strip().casefold()

    if plantilla_tipo != "restaurante":
        return False

    if not isinstance(
        historial,
        list,
    ):
        return False

    mensajes = []

    for item in historial:

        if not isinstance(
            item,
            dict,
        ):
            continue

        role = str(
            item.get(
                "role"
            )
            or
            ""
        ).strip()

        content = str(
            item.get(
                "content"
            )
            or
            ""
        ).strip()

        if (
            role
            not in {
                "user",
                "assistant",
            }
            or
            not content
        ):
            continue

        mensajes.append(
            {
                "role":
                    role,

                "content":
                    content,
            }
        )

    if len(
        mensajes
    ) < 2:
        return False

    anterior_usuario = mensajes[-2]
    anterior_asistente = mensajes[-1]

    if (
        anterior_usuario["role"]
        !=
        "user"
        or
        anterior_asistente["role"]
        !=
        "assistant"
    ):
        return False

    mensaje_anterior = str(
        anterior_usuario[
            "content"
        ]
        or
        ""
    ).strip()

    respuesta_anterior = str(
        anterior_asistente[
            "content"
        ]
        or
        ""
    ).strip()

    actual = str(
        mensaje
        or
        ""
    ).strip()

    respuesta_actual = str(
        respuesta_ia
        or
        ""
    ).strip()

    if (
        not mensaje_anterior
        or
        not respuesta_anterior
        or
        not actual
        or
        not respuesta_actual
    ):
        return False

    if (
        _ia_intencion_recomendacion_producto_restaurante(
            bot=bot,
            mensaje=actual,
        )
    ):
        return False

    if not (
        _ia_intencion_recomendacion_producto_restaurante(
            bot=bot,
            mensaje=mensaje_anterior,
        )
    ):
        return False

    import re
    import unicodedata

    def normalizar(
        valor,
    ):

        texto = " ".join(
            str(
                valor
                or
                ""
            )
            .casefold()
            .split()
        )

        texto = "".join(
            char
            for char
            in unicodedata.normalize(
                "NFD",
                texto,
            )
            if not unicodedata.combining(
                char
            )
        )

        return texto

    actual_normalizado = (
        normalizar(
            actual
        )
    )

    if not actual_normalizado:
        return False

    if len(
        actual_normalizado.split()
    ) > 8:
        return False

    if actual_normalizado in {
        "no",
        "no gracias",
        "ninguno",
        "ninguna",
        "cancelar",
    }:
        return False

    bloqueados = (
        r"\b(?:"
        r"pagar\w*|"
        r"pago\w*|"
        r"mercado|"
        r"tarjeta\w*|"
        r"efectivo|"
        r"transferencia\w*|"
        r"contra\s+entrega|"
        r"confirm\w*|"
        r"cancel\w*|"
        r"anul\w*|"
        r"menu|"
        r"catalogo|"
        r"categorias?|"
        r"productos?|"
        r"domicilio|"
        r"recoger|"
        r"recojo|"
        r"para\s+llevar|"
        r"comedor|"
        r"direccion"
        r")\b"
    )

    if re.search(
        bloqueados,
        actual_normalizado,
    ):
        return False

    productos_anterior_usuario = (
        _ia_productos_visuales_respuesta(
            bot=bot,
            respuesta=
                mensaje_anterior,
        )
    )

    productos_anterior_asistente = (
        _ia_productos_visuales_respuesta(
            bot=bot,
            respuesta=
                respuesta_anterior,
        )
    )

    try:

        cantidad_anterior_usuario = int(
            productos_anterior_usuario.get(
                "productos_cantidad"
            )
            or
            0
        )

        cantidad_anterior_asistente = int(
            productos_anterior_asistente.get(
                "productos_cantidad"
            )
            or
            0
        )

    except (
        TypeError,
        ValueError,
    ):
        return False

    if cantidad_anterior_usuario == 1:
        return False

    if cantidad_anterior_asistente == 1:
        return False

    productos_actuales = (
        _ia_productos_visuales_respuesta(
            bot=bot,
            respuesta=
                respuesta_actual,
        )
    )

    try:

        cantidad_actual = int(
            productos_actuales.get(
                "productos_cantidad"
            )
            or
            0
        )

    except (
        TypeError,
        ValueError,
    ):
        return False

    return cantidad_actual == 1


# =============================================================================
# TNL-IA-CANCELACION-CLIENTE-V1
#
# Cancelación EXPLÍCITA del pedido actual escrita como texto libre.
#
# Es determinista: sólo mensajes completos de una lista cerrada,
# nunca similitud ni criterio del modelo. Usa la misma regla que el
# botón de Typebot (cancelar_pedido_cliente) y responde con el
# resultado real de la base de datos.
# =============================================================================

_IA_FRASES_CANCELACION_EXPLICITA = frozenset(
    {
        "cancelar",
        "cancela",
        "cancelar pedido",
        "cancelar el pedido",
        "cancelar mi pedido",
        "cancela el pedido",
        "cancela mi pedido",
        "quiero cancelar",
        "quiero cancelar el pedido",
        "quiero cancelar mi pedido",
    }
)

_IA_CORTESIAS_CANCELACION = (
    "por favor",
    "porfavor",
    "porfa",
)


def _ia_es_cancelacion_explicita(
    mensaje,
):
    """
    True sólo si el mensaje completo es una petición
    explícita de cancelación (mayúsculas, acentos,
    espacios, signos y emojis no importan).
    """

    import re
    import unicodedata

    texto = unicodedata.normalize(
        "NFD",
        str(
            mensaje
            or
            ""
        ).casefold(),
    )

    texto = "".join(
        char
        for char
        in texto
        if not unicodedata.combining(
            char
        )
    )

    # "❌ Cancelar pedido", "¡Cancelar!" -> "cancelar ..."
    texto = re.sub(
        r"[^a-z0-9 ]+",
        " ",
        texto,
    )

    texto = " ".join(
        texto.split()
    )

    for cortesia in _IA_CORTESIAS_CANCELACION:

        if texto.startswith(
            cortesia + " "
        ):
            texto = texto[
                len(cortesia) + 1:
            ]

        if texto.endswith(
            " " + cortesia
        ):
            texto = texto[
                :-(len(cortesia) + 1)
            ]

    return (
        texto
        in
        _IA_FRASES_CANCELACION_EXPLICITA
    )


def _ia_cancelacion_explicita_pedido_actual(
    *,
    bot,
    mensaje,
    carrito_token,
):
    """
    Devuelve la respuesta HTTP de una cancelación explícita
    del pedido ACTUAL, o None para seguir el flujo IA normal.

    Sólo actúa con un carrito_token válido de este Bot
    Restaurante; nunca busca pedidos por teléfono ni historial.
    """

    from django.core.exceptions import (
        ValidationError,
    )

    from core.models import (
        Pedido,
    )

    from core.services.pedidos import (
        cancelar_pedido_cliente,
    )

    plantilla_tipo = str(
        getattr(
            getattr(
                bot,
                "plantilla",
                None,
            ),
            "tipo",
            "",
        )
        or ""
    ).strip()

    if plantilla_tipo != "restaurante":
        return None

    token = str(
        carrito_token
        or
        ""
    ).strip()

    if not token:
        return None

    if not _ia_es_cancelacion_explicita(
        mensaje
    ):
        return None

    # Mismas reglas de formato, alcance del Bot y
    # ambigüedad que el botón "Cancelar pedido".
    pedido, pedido_error = (
        _restaurante_api_resolver_pedido(
            bot=bot,
            carrito_token=token,
            solo_carrito=False,
        )
    )

    if pedido_error is not None:
        return None

    try:

        resultado = cancelar_pedido_cliente(
            pedido_id=pedido.id,
        )

    except Pedido.DoesNotExist:
        return None

    except ValidationError as exc:

        pedido.refresh_from_db(
            fields=["estado"]
        )

        pedido_cancelado = False

        respuesta = exc.messages[0]

    else:

        pedido = resultado["pedido"]

        pedido_cancelado = True

        if resultado["cambio_real"]:
            respuesta = (
                f"Listo, tu pedido {pedido.numero} "
                "fue cancelado."
            )
        else:
            respuesta = (
                f"Tu pedido {pedido.numero} "
                "ya estaba cancelado."
            )

    productos_vacios = {
        "productos_cantidad": 0,
        "producto_ids": [],
        "producto_nombres": [],
        "producto_precios": [],
        "imagenes_principales": [],
    }

    texto_bool = {
        True: "true",
        False: "false",
    }

    return JsonResponse(
        {
            "ok": True,

            "ia_disponible": True,

            "respuesta": respuesta,
            "ia_mensaje": "",
            "modelo": "",
            "palabras_salida": 0,
            "palabras_disponibles": 0,

            "ia_accion": "",

            "pedido_cancelado":
                pedido_cancelado,

            "pedido_numero":
                pedido.numero,

            "estado":
                pedido.estado,

            # Typebot sólo debe olvidar el carrito cuando
            # el pedido quedó realmente cancelado.
            "clear_carrito_token":
                pedido_cancelado,

            **productos_vacios,

            "data": {
                "ia_disponible":
                    "true",

                "respuesta":
                    respuesta,

                "ia_mensaje":
                    "",

                "palabras_disponibles":
                    0,

                "ia_accion":
                    "",

                "pedido_cancelado":
                    texto_bool[pedido_cancelado],

                "clear_carrito_token":
                    texto_bool[pedido_cancelado],

                **productos_vacios,
            },
        },
        status=200,
    )


@csrf_exempt
def typebot_ia_responder(request):
    """
    Endpoint protegido para IA desde Typebot.

    La empresa se deriva exclusivamente de:

        bot_id -> Bot -> Empresa

    Typebot nunca controla empresa_id ni llama
    directamente a OpenAI.
    """

    import json

    from django.http import JsonResponse

    from core.models import Bot

    from core.services.ia_bolsa import (
        BolsaIAAgotadaError,
        IAInactivaError,
        obtener_estado_ia,
    )

    from core.services.ia_generacion import (
        EntradaIAInvalidaError,
        ProveedorIAError,
        generar_respuesta_ia,
    )


    # --------------------------------------------------------------
    # METHOD
    # --------------------------------------------------------------

    if request.method != "POST":

        return JsonResponse(
            {
                "ok": False,
                "error": "METHOD_NOT_ALLOWED",
                "mensaje": "Método no permitido.",
            },
            status=405,
        )


    # --------------------------------------------------------------
    # AUTH TYPEBOT EXISTENTE
    # --------------------------------------------------------------

    clave_esperada = _leer_clave_api()

    autorizacion = (
        request.headers.get(
            "Authorization",
            "",
        )
        or ""
    )


    if not _autorizacion_typebot_valida(
        autorizacion,
        clave_esperada,
    ):

        return JsonResponse(
            {
                "ok": False,
                "error": "UNAUTHORIZED",
                "mensaje": "Autorización inválida.",
            },
            status=401,
        )


    # --------------------------------------------------------------
    # JSON
    # --------------------------------------------------------------

    try:

        payload = json.loads(
            request.body.decode("utf-8")
            or
            "{}"
        )

    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
    ):

        return JsonResponse(
            {
                "ok": False,
                "error": "INVALID_JSON",
                "mensaje":
                    "El cuerpo JSON no es válido.",
            },
            status=400,
        )


    if not isinstance(
        payload,
        dict,
    ):

        return JsonResponse(
            {
                "ok": False,
                "error": "INVALID_BODY",
                "mensaje":
                    "El cuerpo debe ser un objeto JSON.",
            },
            status=400,
        )


    # --------------------------------------------------------------
    # BOT
    # --------------------------------------------------------------

    try:

        bot_id = int(
            payload.get("bot_id")
            or
            0
        )

    except (
        TypeError,
        ValueError,
    ):

        bot_id = 0


    if bot_id <= 0:

        return JsonResponse(
            {
                "ok": False,
                "error": "INVALID_BOT_ID",
                "mensaje": "bot_id es requerido.",
            },
            status=400,
        )


    bot = (
        Bot.objects
        .select_related(
            "empresa",
            "plantilla",
            "plantilla__instalacion_maestra",
            "plantilla__instalacion_maestra__plantilla_maestra",
        )
        .filter(
            pk=bot_id,
            activo=True,
        )
        .first()
    )


    if bot is None:

        return JsonResponse(
            {
                "ok": False,
                "error": "BOT_NOT_FOUND",
                "mensaje": "Bot no disponible.",
            },
            status=404,
        )

    lifecycle_error = (
        _nl_api_empresa_operativa_error(
            bot.empresa
        )
    )

    if lifecycle_error is not None:
        return lifecycle_error



    # --------------------------------------------------------------
    # MENSAJE
    # --------------------------------------------------------------

    mensaje = str(
        payload.get("mensaje")
        or
        payload.get("entrada")
        or
        ""
    ).strip()


    if not mensaje:

        return JsonResponse(
            {
                "ok": False,
                "error": "EMPTY_MESSAGE",
                "mensaje": "El mensaje está vacío.",
            },
            status=400,
        )


    if len(mensaje) > 4000:

        return JsonResponse(
            {
                "ok": False,
                "error": "MESSAGE_TOO_LONG",
                "mensaje":
                    "El mensaje excede el tamaño permitido.",
            },
            status=400,
        )


    # --------------------------------------------------------------
    # TNL-CHANGO-IA-CURRENT-TRANSACTION-HANDOFF-V1
    #
    # Únicamente contexto del carrito ACTUAL.
    # No se recibe pedido_id ni se buscan pedidos históricos.
    # --------------------------------------------------------------

    carrito_token_ia = str(
        payload.get(
            "carrito_token"
        )
        or
        ""
    ).strip()


    # --------------------------------------------------------------
    # TNL-IA-CANCELACION-CLIENTE-V1
    #
    # Antes de cualquier respuesta IA: una cancelación explícita
    # del carrito ACTUAL se ejecuta con la regla autorizada y se
    # responde con el resultado real. Todo lo demás sigue igual.
    # --------------------------------------------------------------

    respuesta_cancelacion = (
        _ia_cancelacion_explicita_pedido_actual(
            bot=bot,
            mensaje=mensaje,
            carrito_token=carrito_token_ia,
        )
    )

    if respuesta_cancelacion is not None:
        return respuesta_cancelacion


    # --------------------------------------------------------------
    # TNL-IA-CATALOGO-INTENT-V1
    # --------------------------------------------------------------

    if _ia_intencion_catalogo_restaurante(
        bot=bot,
        mensaje=mensaje,
    ):

        productos_vacios = {
            "productos_cantidad": 0,
            "producto_ids": [],
            "producto_nombres": [],
            "producto_precios": [],
            "imagenes_principales": [],
        }


        return JsonResponse(
            {
                "ok": True,

                "ia_disponible": True,

                "respuesta": "",
                "ia_mensaje": "",
                "modelo": "",
                "palabras_salida": 0,
                "palabras_disponibles": 0,

                "ia_accion":
                    "mostrar_categorias",

                **productos_vacios,

                "data": {
                    "ia_disponible":
                        "true",

                    "respuesta":
                        "",

                    "ia_mensaje":
                        "",

                    "palabras_disponibles":
                        0,

                    "ia_accion":
                        "mostrar_categorias",

                    **productos_vacios,
                },
            },
            status=200,
        )


    # --------------------------------------------------------------
    # TNL-IA-CONVERSATION-IDENTITY-V1
    #
    # La referencia conversacional jamás es controlada
    # directamente por Typebot.
    #
    # Se deriva exclusivamente de:
    #
    #   Bot/Empresa Django
    #   + instalación administrada
    #   + instanceName Evolution
    #   + remoteJid Evolution
    #
    # El remoteJid no se persiste en claro.
    # --------------------------------------------------------------

    remote_jid = str(
        payload.get(
            "remote_jid"
        )
        or
        ""
    ).strip()

    instance_name = str(
        payload.get(
            "instance_name"
        )
        or
        ""
    ).strip()


    from core.services.ia_contexto import (
        resolver_referencia_typebot,
    )


    referencia = (
        resolver_referencia_typebot(
            bot=bot,
            remote_jid=remote_jid,
            instance_name=
                instance_name,
        )
    )


    # --------------------------------------------------------------
    # TNL-IA-BOT-SYSTEM-PROMPT-V1
    #
    # Prioridad:
    #   Bot.system_prompt
    #   -> PlantillaMaestra.configuracion["system_prompt"]
    #   -> prompt base NegocioListo.
    #
    # Las instrucciones técnicas de agenda permanecen
    # separadas y no son editables desde Bots.
    # --------------------------------------------------------------

    from core.services.ia_prompt import (
        resolver_instrucciones_bot,
    )


    instrucciones = (
        resolver_instrucciones_bot(
            bot=bot,
            max_palabras=120,
        )
    )


    # --------------------------------------------------------------
    # GENERACION CENTRALIZADA
    # --------------------------------------------------------------

    try:

        # TNL-IA-AGENDA-ORCHESTRATION-V1
        #
        # Las consultas naturales de disponibilidad se
        # interpretan con IA, pero la disponibilidad real
        # proviene exclusivamente del backend + Google.
        # TNL-IA-AGENDA-RESERVA-ORCHESTRATION-V1
        #
        # Reserva tiene prioridad sobre consulta:
        # - "Agéndame..." -> previsualiza y pide confirmación.
        # - "Confirmar cita..." -> revalida y crea.
        #
        # Un mensaje que no corresponde a reserva continúa
        # hacia el orquestador de disponibilidad existente.
        from core.services.ia_agenda_reserva import (
            responder_reserva_agenda_ia,
        )

        from core.services.ia_agenda import (
            responder_disponibilidad_agenda_ia,
        )


        agenda_resultado = (
            responder_reserva_agenda_ia(
                empresa=bot.empresa,
                bot=bot,
                mensaje=mensaje,
                referencia_conversacion=
                    referencia,
            )
        )


        if not agenda_resultado.get(
            "manejado"
        ):

            agenda_resultado = (
                responder_disponibilidad_agenda_ia(
                    empresa=bot.empresa,
                    mensaje=mensaje,
                    referencia_conversacion=
                        referencia,
                )
            )


        if agenda_resultado.get(
            "manejado"
        ):

            estado_ia = obtener_estado_ia(
                bot.empresa_id
            )


            palabras_disponibles = (
                agenda_resultado.get(
                    "palabras_disponibles"
                )
            )


            if palabras_disponibles is None:

                palabras_disponibles = (
                    estado_ia.get(
                        "palabras_disponibles",
                        0,
                    )
                )


            respuesta_agenda = str(
                agenda_resultado.get(
                    "respuesta"
                )
                or
                ""
            ).strip()


            return JsonResponse(
                {
                    "ok": True,
                    "ia_disponible": True,

                    "respuesta":
                        respuesta_agenda,

                    "ia_mensaje": "",

                    "modelo":
                        agenda_resultado.get(
                            "modelo"
                        )
                        or
                        "",

                    "palabras_salida":
                        agenda_resultado.get(
                            "palabras_salida"
                        )
                        or
                        0,

                    "palabras_disponibles":
                        palabras_disponibles,

                    "ia_accion":
                        agenda_resultado.get(
                            "accion"
                        )
                        or
                        "",

                    "agenda_fecha":
                        agenda_resultado.get(
                            "fecha"
                        )
                        or
                        "",

                    "agenda_total_disponibles":
                        agenda_resultado.get(
                            "total_disponibles"
                        )
                        or
                        0,

                    "agenda_horarios":
                        agenda_resultado.get(
                            "horarios"
                        )
                        or
                        "",

                    "agenda_cita_id":
                        agenda_resultado.get(
                            "cita_id"
                        ),

                    "agenda_estado":
                        agenda_resultado.get(
                            "estado"
                        )
                        or
                        "",

                    "data": {
                        "ia_disponible":
                            "true",

                        "respuesta":
                            respuesta_agenda,

                        "ia_mensaje":
                            "",

                        "palabras_disponibles":
                            palabras_disponibles,

                        "agenda_accion":
                            agenda_resultado.get(
                                "accion"
                            )
                            or
                            "",

                        "agenda_cita_id":
                            agenda_resultado.get(
                                "cita_id"
                            ),

                        "agenda_estado":
                            agenda_resultado.get(
                                "estado"
                            )
                            or
                            "",
                    },
                },
                status=200,
            )


        # TNL-IA-CONVERSATION-MEMORY-V1
        #
        # Sólo la respuesta conversacional general utiliza
        # memoria. Los NLU técnicos de agenda permanecen
        # completamente aislados de este historial.
        #
        # Redis es fail-open: si no está disponible,
        # historial será [] y la IA continúa stateless.
        from core.services.ia_memoria import (
            guardar_intercambio,
            obtener_historial,
        )


        historial = (
            obtener_historial(
                referencia
            )
            if referencia
            else []
        )



        # ----------------------------------------------------------
        # TNL-CHANGO-IA-CURRENT-TRANSACTION-HANDOFF-V1
        #
        # Confirmación y pago sólo pueden usar el
        # carrito_token ACTUAL.
        # ----------------------------------------------------------

        pre_handoff_transaccion = (
            _ia_prehandoff_transaccion_actual_chango(
                bot=bot,
                mensaje=mensaje,
                carrito_token=
                    carrito_token_ia,
            )
        )

        if pre_handoff_transaccion is not None:

            accion_transaccion = str(
                pre_handoff_transaccion.get(
                    "ia_accion"
                )
                or
                ""
            ).strip()

            respuesta_transaccion = {
                "ia_disponible":
                    "true",

                "respuesta":
                    "",

                "ia_mensaje":
                    "",

                "palabras_disponibles":
                    "",

                "productos_cantidad":
                    0,

                "producto_ids":
                    [],

                "producto_nombres":
                    [],

                "producto_precios":
                    [],

                "imagenes_principales":
                    [],

                "ia_accion":
                    accion_transaccion,

                "producto_id":
                    "",

                "producto_nombre":
                    "",
            }

            return JsonResponse(
                {
                    "ok": True,
                    **respuesta_transaccion,
                    "data":
                        dict(
                            respuesta_transaccion
                        ),
                }
            )


        pre_handoff_producto = (
            _ia_prehandoff_producto_mensaje_chango(
                bot=bot,
                mensaje=mensaje,
            )
        )

        if pre_handoff_producto is not None:

            respuesta_directa = {
                "ia_disponible":
                    "true",

                "respuesta":
                    "",

                "ia_mensaje":
                    "",

                "palabras_disponibles":
                    "",

                "productos_cantidad":
                    pre_handoff_producto.get(
                        "productos_cantidad",
                        0,
                    ),

                "producto_ids":
                    pre_handoff_producto.get(
                        "producto_ids",
                        [],
                    ),

                "producto_nombres":
                    pre_handoff_producto.get(
                        "producto_nombres",
                        [],
                    ),

                "producto_precios":
                    pre_handoff_producto.get(
                        "producto_precios",
                        [],
                    ),

                "imagenes_principales":
                    pre_handoff_producto.get(
                        "imagenes_principales",
                        [],
                    ),

                "ia_accion":
                    "mostrar_producto",

                "producto_id":
                    pre_handoff_producto.get(
                        "producto_id",
                        "",
                    ),

                "producto_nombre":
                    pre_handoff_producto.get(
                        "producto_nombre",
                        "",
                    ),
            }

            return JsonResponse(
                {
                    "ok": True,
                    **respuesta_directa,
                    "data":
                        dict(
                            respuesta_directa
                        ),
                }
            )

        resultado = generar_respuesta_ia(
            empresa_id=bot.empresa_id,
            entrada=mensaje,
            instrucciones=instrucciones,
            referencia_conversacion=referencia,
            origen="typebot",
            historial=historial,
            max_palabras=120,
        )


        post_handoff_pago = (
            _ia_guardrail_salida_pago_chango(
                bot=bot,
                respuesta=
                    resultado.get(
                        "respuesta"
                    )
                    or
                    "",
                carrito_token=
                    carrito_token_ia,
            )
        )

        if post_handoff_pago is not None:

            accion_post_pago = str(
                post_handoff_pago.get(
                    "ia_accion"
                )
                or
                ""
            ).strip()

            texto_post_pago = str(
                post_handoff_pago.get(
                    "respuesta"
                )
                or
                ""
            ).strip()

            respuesta_post_pago = {
                "ia_disponible":
                    "true",

                "respuesta":
                    texto_post_pago,

                "ia_mensaje":
                    "",

                "palabras_disponibles":
                    resultado.get(
                        "palabras_disponibles",
                        0,
                    ),

                "productos_cantidad":
                    0,

                "producto_ids":
                    [],

                "producto_nombres":
                    [],

                "producto_precios":
                    [],

                "imagenes_principales":
                    [],

                "ia_accion":
                    accion_post_pago,

                "producto_id":
                    "",

                "producto_nombre":
                    "",
            }

            return JsonResponse(
                {
                    "ok": True,
                    **respuesta_post_pago,
                    "data":
                        dict(
                            respuesta_post_pago
                        ),
                }
            )


        post_handoff_tipo_orden = (
            _ia_guardrail_salida_tipo_orden_chango(
                bot=bot,
                respuesta=
                    resultado.get(
                        "respuesta"
                    )
                    or
                    "",
                carrito_token=
                    carrito_token_ia,
            )
        )

        if post_handoff_tipo_orden is not None:

            accion_tipo_orden = str(
                post_handoff_tipo_orden.get(
                    "ia_accion"
                )
                or
                ""
            ).strip()

            texto_tipo_orden = str(
                post_handoff_tipo_orden.get(
                    "respuesta"
                )
                or
                ""
            ).strip()

            respuesta_tipo_orden = {
                "ia_disponible":
                    "true",

                "respuesta":
                    texto_tipo_orden,

                "ia_mensaje":
                    "",

                "palabras_disponibles":
                    resultado.get(
                        "palabras_disponibles",
                        0,
                    ),

                "productos_cantidad":
                    0,

                "producto_ids":
                    [],

                "producto_nombres":
                    [],

                "producto_precios":
                    [],

                "imagenes_principales":
                    [],

                "ia_accion":
                    accion_tipo_orden,

                "producto_id":
                    "",

                "producto_nombre":
                    "",
            }

            return JsonResponse(
                {
                    "ok": True,
                    **respuesta_tipo_orden,
                    "data":
                        dict(
                            respuesta_tipo_orden
                        ),
                }
            )


        # La memoria se escribe únicamente DESPUÉS de que
        # generar_respuesta_ia haya:
        #
        # 1. obtenido respuesta válida;
        # 2. aplicado el límite comercial;
        # 3. registrado correctamente el consumo.
        #
        # Un fallo Redis nunca invalida la respuesta.
        if referencia:

            guardar_intercambio(
                referencia,
                mensaje_usuario=
                    mensaje,
                respuesta_asistente=
                    resultado[
                        "respuesta"
                    ],
            )


    except (
        BolsaIAAgotadaError,
        IAInactivaError,
    ):

        estado = obtener_estado_ia(
            bot.empresa_id
        )

        return JsonResponse(
            {
                "ok": True,
                "ia_disponible": False,
                "respuesta": "",
                "ia_mensaje":
                    "La asistencia con inteligencia artificial "
                    "no está disponible en este momento.",
                "palabras_disponibles":
                    estado.get(
                        "palabras_disponibles",
                        0,
                    ),
                "data": {
                    "ia_disponible": "false",
                    "respuesta": "",
                    "ia_mensaje":
                        "La asistencia con inteligencia artificial "
                        "no está disponible en este momento.",
                    "palabras_disponibles":
                        estado.get(
                            "palabras_disponibles",
                            0,
                        ),
                },
            },
            status=200,
        )


    except EntradaIAInvalidaError:

        return JsonResponse(
            {
                "ok": False,
                "error": "INVALID_AI_INPUT",
                "mensaje":
                    "La entrada para IA no es válida.",
            },
            status=400,
        )


    except ProveedorIAError:

        return JsonResponse(
            {
                "ok": True,
                "ia_disponible": False,
                "respuesta": "",
                "ia_mensaje":
                    "La asistencia con inteligencia artificial "
                    "no está disponible temporalmente.",
                "data": {
                    "ia_disponible": "false",
                    "respuesta": "",
                    "ia_mensaje":
                        "La asistencia con inteligencia artificial "
                        "no está disponible temporalmente.",
                    "palabras_disponibles": 0,
                },
            },
            status=200,
        )


    intencion_producto_actual = bool(
        _ia_intencion_recomendacion_producto_restaurante(
            bot=bot,
            mensaje=mensaje,
        )
    )

    continuacion_producto_multiturno = False

    if not intencion_producto_actual:

        continuacion_producto_multiturno = (
            _ia_continuacion_compra_multiturno_restaurante(
                bot=bot,
                mensaje=mensaje,
                historial=historial,
                respuesta_ia=
                    resultado["respuesta"],
            )
        )

    if (
        intencion_producto_actual
        or
        continuacion_producto_multiturno
    ):

        productos_visuales = (
            _ia_productos_visuales_respuesta(
                bot=bot,
                respuesta=
                    resultado["respuesta"],
            )
        )

    else:

        productos_visuales = {
            "productos_cantidad": 0,
            "producto_ids": [],
            "producto_nombres": [],
            "producto_precios": [],
            "imagenes_principales": [],
        }

    productos_visuales = (
        _ia_handoff_producto_directo_chango(
            bot=bot,
            mensaje=mensaje,
            productos_visuales=
                productos_visuales,
        )
    )



    return JsonResponse(
        {
            # TNL-IA-TYPEBOT-RESPONSE-DATA-V1
            "ok": True,
            "ia_disponible": True,

            "respuesta":
                resultado["respuesta"],

            "ia_mensaje": "",

            "modelo":
                resultado["modelo"],

            "palabras_salida":
                resultado["palabras_salida"],

            "palabras_disponibles":
                resultado["palabras_disponibles"],

            # TNL-IA-PRODUCT-VISUALS-ROOT-V1
            # Typebot evalua bodyPath "data.*" contra
            # response.data, es decir, contra la raiz
            # del body HTTP. Se conservan tambien dentro
            # de "data" por compatibilidad.
            **productos_visuales,

            # Contrato estable para Typebot.
            # ia_disponible se entrega como texto porque
            # el bloque Condition compara contra "true".
            "data": {
                "ia_disponible": "true",
                "respuesta":
                    resultado["respuesta"],
                "ia_mensaje": "",
                "palabras_disponibles":
                    resultado["palabras_disponibles"],

                # TNL-IA-PRODUCT-VISUALS-V1
                **productos_visuales,
            },
        },
        status=200,
    )



# =============================================================================
# TNL-TYPEBOT-CITAS-SLOTS-API-V1
#
# Lista los horarios realmente ofertables para una empresa.
#
# Resuelve empresa exclusivamente mediante bot_id.
# Combina:
#   - horario comercial;
#   - duración;
#   - intervalo;
#   - anticipación mínima;
#   - Google Calendar FreeBusy.
#
# No crea citas ni eventos.
# =============================================================================


@csrf_exempt
def cita_horarios_disponibles(
    request,
):

    from datetime import (
        datetime,
    )

    from core.services.google_calendar_citas import (
        GoogleCalendarCitasError,
        listar_slots_disponibles,
    )


    if request.method != "POST":

        return JsonResponse(
            {
                "ok": False,
                "error":
                    "Método no permitido.",
            },
            status=405,
        )


    auth_error = (
        _citas_api_error_auth(
            request
        )
    )

    if auth_error is not None:
        return auth_error


    datos, datos_error = (
        _citas_api_leer_datos(
            request
        )
    )

    if datos_error is not None:
        return datos_error


    bot, bot_error = (
        _citas_api_resolver_bot(
            datos.get(
                "bot_id"
            )
        )
    )

    if bot_error is not None:
        return bot_error


    try:

        fecha_texto = str(
            datos.get(
                "fecha"
            )
            or
            ""
        ).strip()


        if not fecha_texto:

            raise ValueError(
                "fecha es obligatoria."
            )


        try:

            fecha = (
                datetime.strptime(
                    fecha_texto,
                    "%Y-%m-%d",
                )
                .date()
            )

        except ValueError as exc:

            raise ValueError(
                (
                    "fecha debe usar formato "
                    "AAAA-MM-DD."
                )
            ) from exc


        def parse_hora_opcional(
            nombre,
        ):

            valor = str(
                datos.get(
                    nombre
                )
                or
                ""
            ).strip()


            if not valor:
                return None


            try:

                return (
                    datetime.strptime(
                        valor,
                        "%H:%M",
                    )
                    .time()
                )

            except ValueError as exc:

                raise ValueError(
                    (
                        f"{nombre} debe usar "
                        "formato HH:MM de 24 horas."
                    )
                ) from exc


        hora_desde = (
            parse_hora_opcional(
                "hora_desde"
            )
        )

        hora_hasta = (
            parse_hora_opcional(
                "hora_hasta"
            )
        )


        duracion_raw = datos.get(
            "duracion_minutos"
        )


        if isinstance(
            duracion_raw,
            bool,
        ):

            raise ValueError(
                (
                    "duracion_minutos debe ser "
                    "un número entero."
                )
            )


        if (
            duracion_raw is None
            or
            str(
                duracion_raw
            ).strip()
            ==
            ""
        ):

            duracion_minutos = None

        else:

            try:

                duracion_minutos = int(
                    str(
                        duracion_raw
                    ).strip()
                )

            except (
                TypeError,
                ValueError,
            ) as exc:

                raise ValueError(
                    (
                        "duracion_minutos debe ser "
                        "un número entero."
                    )
                ) from exc


            if not (
                1
                <=
                duracion_minutos
                <=
                1440
            ):

                raise ValueError(
                    (
                        "duracion_minutos debe estar "
                        "entre 1 y 1440."
                    )
                )


    except ValueError as exc:

        return JsonResponse(
            {
                "ok": False,
                "error":
                    str(exc),
                "codigo":
                    "DATOS_SLOTS_INVALIDOS",
            },
            status=400,
            json_dumps_params={
                "ensure_ascii": False
            },
        )


    try:

        resultado = (
            listar_slots_disponibles(
                empresa=
                    bot.empresa,

                fecha=
                    fecha,

                duracion_minutos=
                    duracion_minutos,

                hora_desde=
                    hora_desde,

                hora_hasta=
                    hora_hasta,
            )
        )


    except GoogleCalendarCitasError as exc:

        response = (
            _citas_api_error_servicio(
                exc
            )
        )

        if response is not None:
            return response

        return JsonResponse(
            {
                "ok": False,
                "error":
                    (
                        "No fue posible consultar "
                        "los horarios disponibles."
                    ),
                "codigo":
                    "AGENDA_NO_DISPONIBLE",
            },
            status=503,
            json_dumps_params={
                "ensure_ascii": False
            },
        )


    slots = (
        resultado.get(
            "slots"
        )
        or []
    )


    total_disponibles = len(
        slots
    )


    hay_disponibilidad = (
        total_disponibles
        >
        0
    )


    horarios_texto = ", ".join(
        str(
            slot.get(
                "hora"
            )
            or
            ""
        ).strip()
        for slot in slots
        if str(
            slot.get(
                "hora"
            )
            or
            ""
        ).strip()
    )


    if resultado[
        "dia_cerrado"
    ]:

        mensaje = (
            "La empresa no ofrece citas "
            "en ese día."
        )

    elif hay_disponibilidad:

        mensaje = (
            "Horarios disponibles: "
            +
            horarios_texto
        )

    else:

        mensaje = (
            "No hay horarios disponibles "
            "para los criterios solicitados."
        )


    return JsonResponse(
        {
            "ok": True,

            "bot_id":
                bot.pk,

            "empresa":
                bot.empresa.nombre,

            "fecha":
                resultado[
                    "fecha"
                ],

            "dia_cerrado":
                bool(
                    resultado[
                        "dia_cerrado"
                    ]
                ),

            "hay_disponibilidad":
                hay_disponibilidad,

            "zona_horaria":
                resultado[
                    "zona_horaria"
                ],

            "duracion_minutos":
                resultado[
                    "duracion_minutos"
                ],

            "intervalo_minutos":
                resultado[
                    "intervalo_minutos"
                ],

            "anticipacion_minima_minutos":
                resultado[
                    "anticipacion_minima_minutos"
                ],

            "bloques_atencion":
                resultado[
                    "bloques_atencion"
                ],

            "bloques_ocupados_google":
                resultado[
                    "bloques_ocupados_google"
                ],

            "total_candidatos":
                resultado[
                    "total_candidatos"
                ],

            "descartados_anticipacion":
                resultado[
                    "descartados_anticipacion"
                ],

            "descartados_google":
                resultado[
                    "descartados_google"
                ],

            "total_disponibles":
                total_disponibles,

            "slots":
                slots,

            "mensaje":
                mensaje,

            # Contrato amigable para Typebot.
            "data": {

                "hay_disponibilidad":
                    (
                        "true"
                        if hay_disponibilidad
                        else
                        "false"
                    ),

                "dia_cerrado":
                    (
                        "true"
                        if resultado[
                            "dia_cerrado"
                        ]
                        else
                        "false"
                    ),

                "fecha":
                    resultado[
                        "fecha"
                    ],

                "horarios":
                    horarios_texto,

                "total_disponibles":
                    str(
                        total_disponibles
                    ),

                "duracion_minutos":
                    str(
                        resultado[
                            "duracion_minutos"
                        ]
                    ),

                "mensaje":
                    mensaje,
            },
        },
        json_dumps_params={
            "ensure_ascii": False
        },
    )


# =============================================================================
# TNL-CITA-MERCADOPAGO-CHECKOUT-V1
# =============================================================================

# TNL-CITA-MP-CHECKOUT-CSRF-EXEMPT-V1
@csrf_exempt
def cita_mercadopago_checkout(request):

    import logging

    from decimal import Decimal

    from django.db import transaction
    from django.http import JsonResponse
    from django.utils import timezone

    from core.models import (
        Cita,
        ConfiguracionMercadoPago,
        Pago,
    )

    from core.services.mercadopago import (
        crear_preferencia_checkout_pro,
        obtener_access_token_configuracion,
    )


    def no_disponible(
        mensaje,
        *,
        cita=None,
        motivo="mercadopago_no_disponible",
        status=200,
    ):
        payload = {
            "ok": True,
            "checkout_disponible": False,
            "checkout_url": "",
            "motivo": motivo,
            "checkout_mensaje": str(
                mensaje or
                "No fue posible generar el enlace de pago."
            ),
        }

        if cita is not None:
            payload["cita_id"] = cita.pk
            payload["estado"] = cita.estado
            payload["retencion_pago_hasta"] = (
                cita.retencion_pago_hasta.isoformat()
                if cita.retencion_pago_hasta
                else None
            )

        return JsonResponse(
            payload,
            status=status,
        )


    if request.method != "POST":
        return JsonResponse(
            {
                "ok": False,
                "error": "Método no permitido.",
            },
            status=405,
        )


    auth_error = _citas_api_error_auth(
        request
    )

    if auth_error is not None:
        return auth_error


    datos, datos_error = _citas_api_leer_datos(
        request
    )

    if datos_error is not None:
        return datos_error


    bot, bot_error = _citas_api_resolver_bot(
        datos.get("bot_id")
    )

    if bot_error is not None:
        return bot_error


    lifecycle_error = _nl_api_empresa_operativa_error(
        bot.empresa
    )

    if lifecycle_error is not None:
        return lifecycle_error


    try:
        cita_id = int(
            datos.get("cita_id")
        )

        if cita_id <= 0:
            raise ValueError

    except (TypeError, ValueError):
        return JsonResponse(
            {
                "ok": False,
                "error": "cita_id no es válido.",
            },
            status=400,
        )


    with transaction.atomic():

        cita = (
            Cita.objects
            .select_for_update()
            .filter(
                pk=cita_id,
                empresa=bot.empresa,
            )
            .first()
        )

        if cita is None:
            return JsonResponse(
                {
                    "ok": False,
                    "error": "Cita no encontrada.",
                },
                status=404,
            )


        if (
            cita.estado
            !=
            Cita.ESTADO_PENDIENTE_CONFIRMACION
        ):
            return JsonResponse(
                {
                    "ok": False,
                    "error":
                        "La cita no está pendiente de pago.",
                    "estado":
                        cita.estado,
                },
                status=409,
            )


        if (
            cita.politica_pago_aplicada
            ==
            "sin_pago"
        ):
            return JsonResponse(
                {
                    "ok": False,
                    "error":
                        "Esta cita no requiere pago.",
                },
                status=409,
            )


        monto = Decimal(
            cita.importe_pago_requerido
        )

        moneda = str(
            cita.moneda or ""
        ).strip().upper()


        if monto <= 0:
            return JsonResponse(
                {
                    "ok": False,
                    "error":
                        "El importe de pago de la cita es inválido.",
                },
                status=409,
            )


        if len(moneda) != 3:
            return JsonResponse(
                {
                    "ok": False,
                    "error":
                        "La moneda de la cita es inválida.",
                },
                status=409,
            )


        ahora = timezone.now()

        if (
            cita.retencion_pago_hasta is None
            or
            cita.retencion_pago_hasta <= ahora
        ):
            return no_disponible(
                "La retención del horario ya venció.",
                cita=cita,
                motivo="retencion_vencida",
                status=409,
            )


        aprobado = (
            Pago.objects
            .filter(
                cita=cita,
                proveedor=Pago.Proveedor.MERCADOPAGO,
                estado=Pago.Estado.APROBADO,
            )
            .exists()
        )

        if aprobado:
            return no_disponible(
                "El pago de esta cita ya fue aprobado.",
                cita=cita,
                motivo="pago_ya_aprobado",
                status=409,
            )


        existente = (
            Pago.objects
            .filter(
                cita=cita,
                proveedor=Pago.Proveedor.MERCADOPAGO,
                estado__in=[
                    Pago.Estado.CREADO,
                    Pago.Estado.PENDIENTE,
                ],
            )
            .order_by("-id")
            .first()
        )


        if existente is not None:

            if (
                existente.preference_id
                and
                existente.checkout_url
            ):
                return JsonResponse(
                    {
                        "ok": True,
                        "checkout_disponible": True,
                        "reutilizado": True,
                        "cita_id": cita.pk,
                        "pago_id": existente.pk,
                        "pago_referencia":
                            str(existente.referencia),
                        "estado_pago":
                            existente.estado,
                        "checkout_url":
                            existente.checkout_url,
                        "retencion_pago_hasta":
                            cita.retencion_pago_hasta.isoformat(),
                    }
                )

            return no_disponible(
                "El enlace de pago se está generando.",
                cita=cita,
                motivo="checkout_en_proceso",
            )


        config = (
            ConfiguracionMercadoPago.objects
            .filter(
                empresa=cita.empresa,
                habilitada=True,
                estado_conexion=(
                    ConfiguracionMercadoPago
                    .EstadoConexion
                    .CONECTADA
                ),
            )
            .first()
        )


        if (
            config is None
            or
            not config.mp_user_id
        ):
            return no_disponible(
                "Mercado Pago no está disponible para esta cita.",
                cita=cita,
            )


        pago = Pago.objects.create(
            pedido=None,
            cita=cita,
            proveedor=Pago.Proveedor.MERCADOPAGO,
            estado=Pago.Estado.CREADO,
            monto=monto,
            moneda=moneda,
        )


        pago_id = pago.pk
        referencia = str(
            pago.referencia
        )

        config_id = config.pk
        mp_user_id = str(
            config.mp_user_id
        )

        cita_id_local = cita.pk
        servicio = str(
            cita.servicio or ""
        ).strip()

        retencion_hasta = (
            cita.retencion_pago_hasta
        )


    # -------------------------------------------------------------
    # Mercado Pago FUERA de la transacción.
    # -------------------------------------------------------------

    logger = logging.getLogger(
        "negociolisto.mercadopago"
    )


    try:

        access_token = (
            obtener_access_token_configuracion(
                config_id
            )
        )


        ahora_mp = timezone.now()

        if retencion_hasta <= ahora_mp:
            raise RuntimeError(
                "La retención venció antes de crear la preferencia."
            )


        prefijo = (
            "Anticipo de cita"
            if
            cita.politica_pago_aplicada
            ==
            "anticipo"
            else
            "Pago de cita"
        )

        titulo_item = (
            prefijo
            +
            (
                " - " + servicio
                if servicio
                else ""
            )
        )


        resultado = crear_preferencia_checkout_pro(
            access_token=access_token,
            external_reference=referencia,
            pedido_numero=
                f"CITA-{cita_id_local}",
            monto=monto,
            moneda=moneda,
            expected_collector_id=
                mp_user_id,
            titulo_item=
                titulo_item,
            expiration_date_from=
                ahora_mp.isoformat(
                    timespec="seconds"
                ),
            expiration_date_to=
                retencion_hasta.isoformat(
                    timespec="seconds"
                ),
        )


        preference_id = str(
            resultado["preference_id"]
        )

        checkout_url = str(
            resultado["checkout_url"]
        )


        with transaction.atomic():

            locked_pago = (
                Pago.objects
                .select_for_update()
                .get(
                    pk=pago_id
                )
            )

            locked_cita = (
                Cita.objects
                .select_for_update()
                .get(
                    pk=cita_id_local
                )
            )


            if (
                locked_cita.estado
                !=
                Cita.ESTADO_PENDIENTE_CONFIRMACION
                or
                locked_cita.retencion_pago_hasta is None
                or
                locked_cita.retencion_pago_hasta
                <=
                timezone.now()
            ):

                if (
                    locked_pago.estado
                    ==
                    Pago.Estado.CREADO
                ):
                    locked_pago.estado = (
                        Pago.Estado.EXPIRADO
                    )
                    locked_pago.estado_proveedor = (
                        "local_retention_expired"
                    )
                    locked_pago.save()

                return no_disponible(
                    "La retención del horario ya venció.",
                    cita=locked_cita,
                    motivo="retencion_vencida",
                    status=409,
                )


            if (
                locked_pago.estado
                ==
                Pago.Estado.CREADO
            ):
                locked_pago.preference_id = (
                    preference_id
                )
                locked_pago.checkout_url = (
                    checkout_url
                )
                locked_pago.estado = (
                    Pago.Estado.PENDIENTE
                )
                locked_pago.estado_proveedor = (
                    "preference_created"
                )
                locked_pago.detalle_estado_proveedor = ""
                locked_pago.save()


        return JsonResponse(
            {
                "ok": True,
                "checkout_disponible": True,
                "reutilizado": False,
                "cita_id": cita_id_local,
                "pago_id": pago_id,
                "pago_referencia": referencia,
                "estado_pago":
                    Pago.Estado.PENDIENTE,
                "checkout_url":
                    checkout_url,
                "importe_pago_requerido":
                    str(monto),
                "moneda":
                    moneda,
                "retencion_pago_hasta":
                    retencion_hasta.isoformat(),
            }
        )


    except Exception as exc:

        logger.error(
            (
                "TNL_MP_CITA_PREFERENCE_FAIL "
                "empresa=%s cita=%s pago=%s exception=%s"
            ),
            bot.empresa_id,
            cita_id_local,
            pago_id,
            type(exc).__name__,
        )


        try:

            with transaction.atomic():

                locked = (
                    Pago.objects
                    .select_for_update()
                    .get(
                        pk=pago_id
                    )
                )

                if (
                    locked.estado
                    ==
                    Pago.Estado.CREADO
                ):
                    locked.estado = (
                        Pago.Estado.ERROR
                    )
                    locked.estado_proveedor = (
                        "preference_error"
                    )
                    locked.detalle_estado_proveedor = (
                        "No fue posible crear la preferencia."
                    )
                    locked.save()

        except Exception as db_exc:

            logger.error(
                (
                    "TNL_MP_CITA_PREFERENCE_ERROR_SAVE_FAIL "
                    "empresa=%s pago=%s exception=%s"
                ),
                bot.empresa_id,
                pago_id,
                type(db_exc).__name__,
            )


        return no_disponible(
            "No fue posible generar el enlace de pago.",
            cita=cita,
            motivo="mercadopago_no_disponible",
        )


# =============================================================================
# TNL-RESTAURANTE-API-MENU-V1
#
# APIs GET exclusivas para el menú Restaurante.
#
# Seguridad:
# - Bearer interno existente.
# - bot_id resuelve Empresa + Plantilla en servidor.
# - nunca acepta empresa_id desde Typebot.
#
# Economía:
# - no calcula pedidos.
# - no redondea precios incompatibles.
#
# Datos:
# - no modifica Pedido / PedidoDetalle / inventario.
# =============================================================================


def _restaurante_api_auth_error(
    request,
):

    clave_esperada = (
        _leer_clave_api()
    )

    if not clave_esperada:

        return JsonResponse(
            {
                "ok": False,
                "error":
                    "Servicio no configurado.",
            },
            status=503,
        )

    autorizacion = (
        request.headers.get(
            "Authorization",
            "",
        )
    )

    if not _autorizacion_typebot_valida(
        autorizacion,
        clave_esperada,
    ):

        respuesta = JsonResponse(
            {
                "ok": False,
                "error":
                    "No autorizado.",
            },
            status=401,
        )

        respuesta[
            "WWW-Authenticate"
        ] = "Bearer"

        return respuesta

    return None


def _restaurante_api_resolver_bot(
    bot_id_texto,
):

    from core.models import (
        Bot,
    )

    texto = str(
        bot_id_texto
        or ""
    ).strip()

    if not texto:

        return (
            None,
            JsonResponse(
                {
                    "ok": False,
                    "error":
                        "El parámetro bot_id "
                        "es obligatorio.",
                },
                status=400,
            ),
        )

    try:

        bot_id = int(
            texto
        )

    except (
        TypeError,
        ValueError,
    ):

        return (
            None,
            JsonResponse(
                {
                    "ok": False,
                    "error":
                        "bot_id no es válido.",
                },
                status=400,
            ),
        )

    if bot_id <= 0:

        return (
            None,
            JsonResponse(
                {
                    "ok": False,
                    "error":
                        "bot_id no es válido.",
                },
                status=400,
            ),
        )

    bot = (
        Bot.objects
        .select_related(
            "empresa",
            "plantilla",
        )
        .filter(
            id=bot_id,
            activo=True,
        )
        .first()
    )

    if bot is None:

        return (
            None,
            JsonResponse(
                {
                    "ok": False,
                    "error":
                        "Bot no encontrado "
                        "o inactivo.",
                },
                status=404,
            ),
        )

    lifecycle_error = (
        _nl_api_empresa_operativa_error(
            bot.empresa
        )
    )

    if lifecycle_error is not None:

        return (
            None,
            lifecycle_error,
        )

    plantilla = bot.plantilla

    if plantilla is None:

        return (
            None,
            JsonResponse(
                {
                    "ok": False,
                    "error":
                        "El bot no tiene una "
                        "plantilla asociada.",
                },
                status=409,
            ),
        )

    if not plantilla.activa:

        return (
            None,
            JsonResponse(
                {
                    "ok": False,
                    "error":
                        "La plantilla del bot "
                        "está inactiva.",
                },
                status=409,
            ),
        )

    if (
        str(
            plantilla.tipo
            or ""
        ).strip()
        !=
        "restaurante"
    ):

        return (
            None,
            JsonResponse(
                {
                    "ok": False,
                    "error":
                        "El bot no corresponde "
                        "a una solución Restaurante.",
                    "codigo":
                        "BOT_NO_RESTAURANTE",
                },
                status=409,
            ),
        )

    return (
        bot,
        None,
    )


def _restaurante_api_dinero(
    valor,
    *,
    etiqueta,
):

    from decimal import (
        Decimal,
    )

    from core.services.pedidos import (
        validar_importe_cobrable_restaurante,
    )

    exacto = (
        validar_importe_cobrable_restaurante(
            valor,
            etiqueta=etiqueta,
        )
    )

    # La validación anterior garantiza que
    # sólo existen ceros después de centavos.
    return format(
        exacto.quantize(
            Decimal("0.01")
        ),
        ".2f",
    )


def _restaurante_api_producto_resumen(
    producto,
):

    precio = (
        _restaurante_api_dinero(
            producto.precio,
            etiqueta=(
                "El precio base del producto "
                f"'{producto.nombre}'"
            ),
        )
    )

    grupos = getattr(
        producto,
        "restaurante_grupos_activos",
        None,
    )

    if grupos is None:

        requiere_configuracion = (
            producto
            .grupos_modificadores
            .filter(
                activo=True
            )
            .exists()
        )

    else:

        requiere_configuracion = bool(
            grupos
        )

    return {
        "id":
            producto.id,

        "sku":
            producto.sku,

        "nombre":
            producto.nombre,

        "descripcion":
            producto.descripcion,

        "precio":
            precio,

        "moneda":
            producto.catalogo.moneda,

        "stock":
            str(
                producto.stock
            ),

        "unidad":
            producto.unidad,

        "categoria": {
            "id":
                producto.categoria_id,

            "nombre":
                (
                    producto.categoria.nombre
                    if producto.categoria_id
                    else ""
                ),
        },

        "imagen_principal_url":
            _producto_media_url(
                producto.imagen_principal
            ),

        "requiere_configuracion":
            requiere_configuracion,
    }


def restaurante_categorias(
    request,
):
    """
    Categorías dinámicas del menú del restaurante.
    """

    from django.db.models import (
        Exists,
        OuterRef,
    )

    from core.models import (
        CategoriaProducto,
    )

    from core.services.catalogo import (
        productos_vendibles,
    )

    if request.method != "GET":

        return JsonResponse(
            {
                "ok": False,
                "error":
                    "Método no permitido.",
            },
            status=405,
        )

    auth_error = (
        _restaurante_api_auth_error(
            request
        )
    )

    if auth_error is not None:

        return auth_error

    bot, bot_error = (
        _restaurante_api_resolver_bot(
            request.GET.get(
                "bot_id",
                "",
            )
        )
    )

    if bot_error is not None:

        return bot_error

    # TNL-CATALOGO-REGLAS-V1
    # Sólo categorías con al menos un producto vendible.
    categorias = list(
        CategoriaProducto.objects
        .filter(
            catalogo__empresa_id=
                bot.empresa_id,

            catalogo__plantilla_id=
                bot.plantilla_id,

            catalogo__activo=True,
            activa=True,
        )
        .filter(
            Exists(
                productos_vendibles(
                    empresa_id=bot.empresa_id,
                    plantilla_id=bot.plantilla_id,
                    restaurante=True,
                ).filter(
                    categoria_id=OuterRef("pk"),
                )
            )
        )
        .order_by(
            "orden",
            "nombre",
            "id",
        )
    )

    items = [
        {
            "id":
                categoria.id,

            "nombre":
                categoria.nombre,

            "descripcion":
                categoria.descripcion,

            "orden":
                categoria.orden,
        }
        for categoria
        in categorias
    ]

    return JsonResponse(
        {
            "ok": True,

            "bot_id":
                bot.id,

            "empresa":
                bot.empresa.nombre,

            "cantidad":
                len(items),

            "categorias":
                items,

            # Arrays simples útiles para List/Choices
            # de Typebot.
            "categoria_ids": [
                item["id"]
                for item in items
            ],

            "categoria_nombres": [
                item["nombre"]
                for item in items
            ],

            # TNL-CATEGORY-IA-SENTINEL-V1
            # Arrays técnicos exclusivos para la UI
            # dinámica de Typebot. El contrato público
            # anterior permanece intacto.
            "categoria_ids_ui": [
                *[
                    item["id"]
                    for item in items
                ],
                "__TNL_IA__",
            ],

            "categoria_nombres_ui": [
                *[
                    item["nombre"]
                    for item in items
                ],
                "🤖 Asistente IA",
            ],
        },
        json_dumps_params={
            "ensure_ascii": False,
        },
    )


def restaurante_productos(
    request,
):
    """
    Lista productos disponibles de una categoría.
    """

    from django.core.exceptions import (
        ValidationError,
    )

    from django.db.models import (
        Prefetch,
    )

    from core.models import (
        CategoriaProducto,
        GrupoModificadorProducto,
        Producto,
    )

    from core.services.catalogo import (
        productos_vendibles,
    )

    if request.method != "GET":

        return JsonResponse(
            {
                "ok": False,
                "error":
                    "Método no permitido.",
            },
            status=405,
        )

    auth_error = (
        _restaurante_api_auth_error(
            request
        )
    )

    if auth_error is not None:

        return auth_error

    bot, bot_error = (
        _restaurante_api_resolver_bot(
            request.GET.get(
                "bot_id",
                "",
            )
        )
    )

    if bot_error is not None:

        return bot_error

    categoria_texto = str(
        request.GET.get(
            "categoria_id",
            "",
        )
        or ""
    ).strip()

    try:

        categoria_id = int(
            categoria_texto
        )

    except (
        TypeError,
        ValueError,
    ):

        return JsonResponse(
            {
                "ok": False,
                "error":
                    "categoria_id no es válido.",
            },
            status=400,
        )

    categoria = (
        CategoriaProducto.objects
        .select_related(
            "catalogo",
        )
        .filter(
            id=categoria_id,
            activa=True,

            catalogo__activo=True,

            catalogo__empresa_id=
                bot.empresa_id,

            catalogo__plantilla_id=
                bot.plantilla_id,
        )
        .first()
    )

    if categoria is None:

        return JsonResponse(
            {
                "ok": False,
                "error":
                    "Categoría no encontrada "
                    "para este bot.",
            },
            status=404,
        )

    grupos_qs = (
        GrupoModificadorProducto.objects
        .filter(
            activo=True,
        )
        .only(
            "id",
            "producto_id",
        )
        .order_by(
            "orden",
            "id",
        )
    )

    # TNL-CATALOGO-REGLAS-V1
    productos = list(
        productos_vendibles(
            empresa_id=bot.empresa_id,
            plantilla_id=bot.plantilla_id,
            restaurante=True,
            queryset=(
                Producto.objects
                .select_related(
                    "catalogo",
                    "categoria",
                )
                .prefetch_related(
                    Prefetch(
                        "grupos_modificadores",
                        queryset=grupos_qs,
                        to_attr=
                            "restaurante_grupos_activos",
                    )
                )
            ),
        )
        .filter(
            categoria_id=
                categoria.id,
        )
        .order_by(
            "nombre",
            "id",
        )
    )

    try:

        items = [
            _restaurante_api_producto_resumen(
                producto
            )
            for producto
            in productos
        ]

    except ValidationError as exc:

        mensajes = (
            getattr(
                exc,
                "messages",
                None,
            )
            or
            [
                str(exc)
            ]
        )

        return JsonResponse(
            {
                "ok": False,
                "error":
                    mensajes[0],

                "codigo":
                    "PRECIO_RESTAURANTE_INVALIDO",
            },
            status=409,
        )

    return JsonResponse(
        {
            "ok": True,

            "bot_id":
                bot.id,

            "empresa":
                bot.empresa.nombre,

            "categoria": {
                "id":
                    categoria.id,

                "nombre":
                    categoria.nombre,
            },

            "cantidad":
                len(items),

            "productos":
                items,

            "producto_ids": [
                item["id"]
                for item in items
            ],

            "producto_nombres": [
                item["nombre"]
                for item in items
            ],

            "producto_precios": [
                item["precio"]
                for item in items
            ],

            "imagenes_principales": [
                item[
                    "imagen_principal_url"
                ]
                for item in items
            ],
        },
        json_dumps_params={
            "ensure_ascii": False,
        },
    )


def restaurante_producto_detalle(
    request,
):
    """
    Producto + imagen + galería + configurador.
    """

    from django.core.exceptions import (
        ValidationError,
    )

    from django.db.models import (
        Prefetch,
    )

    from core.models import (
        GrupoModificadorProducto,
        OpcionModificadorProducto,
        Producto,
    )

    from core.services.catalogo import (
        productos_vendibles,
    )

    if request.method != "GET":

        return JsonResponse(
            {
                "ok": False,
                "error":
                    "Método no permitido.",
            },
            status=405,
        )

    auth_error = (
        _restaurante_api_auth_error(
            request
        )
    )

    if auth_error is not None:

        return auth_error

    bot, bot_error = (
        _restaurante_api_resolver_bot(
            request.GET.get(
                "bot_id",
                "",
            )
        )
    )

    if bot_error is not None:

        return bot_error

    producto_texto = str(
        request.GET.get(
            "producto_id",
            "",
        )
        or ""
    ).strip()

    try:

        producto_id = int(
            producto_texto
        )

    except (
        TypeError,
        ValueError,
    ):

        return JsonResponse(
            {
                "ok": False,
                "error":
                    "producto_id no es válido.",
            },
            status=400,
        )

    opciones_qs = (
        OpcionModificadorProducto.objects
        .filter(
            activa=True,
        )
        .order_by(
            "orden",
            "id",
        )
    )

    grupos_qs = (
        GrupoModificadorProducto.objects
        .filter(
            activo=True,
        )
        .prefetch_related(
            Prefetch(
                "opciones",
                queryset=
                    opciones_qs,

                to_attr=
                    "restaurante_opciones_activas",
            )
        )
        .order_by(
            "orden",
            "id",
        )
    )

    # TNL-CATALOGO-REGLAS-V1
    producto = (
        productos_vendibles(
            empresa_id=bot.empresa_id,
            plantilla_id=bot.plantilla_id,
            restaurante=True,
            queryset=(
                Producto.objects
                .select_related(
                    "catalogo",
                    "categoria",
                )
                .prefetch_related(
                    "galeria",

                    Prefetch(
                        "grupos_modificadores",
                        queryset=
                            grupos_qs,

                        to_attr=
                            "restaurante_grupos_activos",
                    ),
                )
            ),
        )
        .filter(
            id=producto_id,
        )
        .first()
    )

    if producto is None:

        return JsonResponse(
            {
                "ok": False,
                "error":
                    "Producto no encontrado "
                    "para este bot.",
            },
            status=404,
        )

    try:

        item = (
            _restaurante_api_producto_resumen(
                producto
            )
        )

        grupos = []

        for grupo in (
            producto
            .restaurante_grupos_activos
        ):

            opciones = []

            for opcion in (
                grupo
                .restaurante_opciones_activas
            ):

                opciones.append(
                    {
                        "id":
                            opcion.id,

                        "nombre":
                            opcion.nombre,

                        "precio_adicional":
                            (
                                _restaurante_api_dinero(
                                    opcion
                                    .precio_adicional,

                                    etiqueta=(
                                        "El precio adicional "
                                        f"de '{opcion.nombre}'"
                                    ),
                                )
                            ),

                        "orden":
                            opcion.orden,
                    }
                )

            grupos.append(
                {
                    "id":
                        grupo.id,

                    "nombre":
                        grupo.nombre,

                    "tipo":
                        grupo.tipo,

                    "obligatorio":
                        grupo.obligatorio,

                    "minimo":
                        grupo.minimo,

                    "maximo":
                        grupo.maximo,

                    "orden":
                        grupo.orden,

                    "opciones":
                        opciones,

                    "opcion_ids": [
                        opcion["id"]
                        for opcion
                        in opciones
                    ],

                    "opcion_nombres": [
                        opcion["nombre"]
                        for opcion
                        in opciones
                    ],
                }
            )

    except ValidationError as exc:

        mensajes = (
            getattr(
                exc,
                "messages",
                None,
            )
            or
            [
                str(exc)
            ]
        )

        return JsonResponse(
            {
                "ok": False,

                "error":
                    mensajes[0],

                "codigo":
                    "PRECIO_RESTAURANTE_INVALIDO",
            },
            status=409,
        )

    item[
        "galeria_urls"
    ] = (
        _producto_galeria_urls(
            producto
        )
    )

    item[
        "grupos"
    ] = grupos

    item[
        "requiere_configuracion"
    ] = bool(
        grupos
    )

    return JsonResponse(
        {
            "ok": True,

            "bot_id":
                bot.id,

            "empresa":
                bot.empresa.nombre,

            "producto":
                item,

            # Alias directos para simplificar
            # variables del futuro Typebot.
            "producto_id":
                producto.id,

            "nombre":
                producto.nombre,

            "precio":
                item["precio"],

            "imagen_principal_url":
                item[
                    "imagen_principal_url"
                ],

            "galeria_urls":
                item["galeria_urls"],

            "requiere_configuracion":
                item[
                    "requiere_configuracion"
                ],

            "grupos":
                grupos,
        },
        json_dumps_params={
            "ensure_ascii": False,
        },
    )




# =============================================================================
# TNL-RESTAURANTE-TYPEBOT-CONFIGURADOR-R5-V1
# =============================================================================

def restaurante_configurador_intencion(
    request,
):
    """
    TNL-MODIFICADOR-TEXTO-V1

    Interpreta la respuesta ESCRITA del paso "¿Otro extra?":
    seguir agregando o continuar con el pedido.

    Sólo normaliza texto: no toca catálogo, precios ni pedido.
    Lo que no se reconoce se devuelve como desconocido para que
    el flujo vuelva a preguntar sin recurrir a la IA.
    """

    from core.services.seleccion_modificadores import (
        interpretar_respuesta_otro_extra,
    )

    if request.method != "GET":

        return JsonResponse(
            {
                "ok": False,
                "error":
                    "Método no permitido.",
            },
            status=405,
        )

    auth_error = (
        _restaurante_api_auth_error(
            request
        )
    )

    if auth_error is not None:
        return auth_error

    bot, bot_error = (
        _restaurante_api_resolver_bot(
            request.GET.get(
                "bot_id",
                "",
            )
        )
    )

    if bot_error is not None:
        return bot_error

    resultado = (
        interpretar_respuesta_otro_extra(
            request.GET.get(
                "texto",
                "",
            )
        )
    )

    return JsonResponse(
        {
            "ok": True,

            "intencion":
                resultado["intencion"],

            "mensaje":
                resultado["mensaje"],
        },
        json_dumps_params={
            "ensure_ascii": False,
        },
    )


def restaurante_producto_configurador_resolver(
    request,
):
    """
    TNL-MODIFICADOR-TEXTO-V1

    Traduce la respuesta ESCRITA del cliente ("1", "BBQ",
    "1 y 9") a IDs reales del grupo que el configurador está
    mostrando ahora mismo.

    Reutiliza restaurante_producto_configurador() para no
    duplicar auth, aislamiento por bot, catálogo ni reglas de
    disponibilidad: aquí sólo se resuelve el texto.

    Nunca acepta precios del cliente ni opciones de otro
    grupo; si el texto es inválido o ambiguo, devuelve
    resuelto=false con un mensaje corto.
    """

    import json
    import re

    from core.services.seleccion_modificadores import (
        resolver_texto_opciones,
    )

    if request.method != "GET":

        return JsonResponse(
            {
                "ok": False,
                "error":
                    "Método no permitido.",
            },
            status=405,
        )

    configurador_response = (
        restaurante_producto_configurador(
            request
        )
    )

    if (
        configurador_response.status_code
        != 200
    ):
        return configurador_response

    try:

        grupo = json.loads(
            configurador_response.content.decode(
                "utf-8"
            )
        )

    except (
        ValueError,
        UnicodeDecodeError,
    ):

        return JsonResponse(
            {
                "ok": False,
                "error":
                    "Respuesta interna de "
                    "configurador inválida.",
            },
            status=500,
        )

    seleccionadas_crudo = str(
        request.GET.get(
            "seleccionadas",
            "",
        )
        or ""
    )

    seleccionadas = [
        parte.strip()
        for parte
        in re.split(
            r"[,;\s]+",
            seleccionadas_crudo.replace(
                "[",
                " ",
            ).replace(
                "]",
                " ",
            ).replace(
                '"',
                " ",
            ).replace(
                "'",
                " ",
            ),
        )
        if parte.strip().isdigit()
    ]

    if grupo.get("terminado"):

        return JsonResponse(
            {
                "ok": True,
                "resuelto": False,
                "opcion_ids": [],
                "opcion_ids_acumuladas":
                    seleccionadas,
                "mensaje":
                    "Este paso ya no espera opciones.",
                "motivo":
                    "terminado",
            },
            json_dumps_params={
                "ensure_ascii": False,
            },
        )

    resultado = resolver_texto_opciones(
        texto=request.GET.get(
            "texto",
            "",
        ),

        opcion_ids=grupo.get(
            "opcion_ids"
        ),

        opcion_nombres=grupo.get(
            "opcion_nombres"
        ),

        opcion_etiquetas=grupo.get(
            "opcion_etiquetas"
        ),

        maximo=grupo.get(
            "grupo_maximo",
            0,
        ),

        seleccionadas=seleccionadas,
    )

    return JsonResponse(
        {
            "ok": True,

            "resuelto":
                "true"
                if resultado["resuelto"]
                else "false",

            "grupo_id":
                grupo.get("grupo_id"),

            "grupo_nombre":
                grupo.get("grupo_nombre"),

            "grupo_maximo":
                grupo.get("grupo_maximo"),

            "opcion_ids":
                resultado["opcion_ids"],

            "opcion_ids_acumuladas":
                resultado["acumuladas"],

            "mensaje":
                resultado["mensaje"],

            "motivo":
                resultado["motivo"],
        },
        json_dumps_params={
            "ensure_ascii": False,
        },
    )


def restaurante_producto_configurador(
    request,
):
    """
    Adapter de SOLO LECTURA para Typebot.

    Convierte el contrato anidado de
    restaurante_producto_detalle() en un grupo
    de modificadores plano por grupo_indice.

    Seguridad:
    - reutiliza exactamente autenticación y tenant scope
      de restaurante_producto_detalle();
    - nunca acepta empresa_id;
    - no crea ni modifica Pedido;
    - no modifica Producto;
    - no calcula precios autoritativos;
    - sólo transforma una respuesta ya certificada.
    """

    import json
    from decimal import (
        Decimal,
        InvalidOperation,
    )

    if request.method != "GET":

        return JsonResponse(
            {
                "ok": False,
                "error":
                    "Método no permitido.",
            },
            status=405,
        )

    raw_indice = str(
        request.GET.get(
            "grupo_indice",
            "0",
        )
        or "0"
    ).strip()

    try:
        grupo_indice = int(
            raw_indice
        )
    except (
        TypeError,
        ValueError,
    ):

        return JsonResponse(
            {
                "ok": False,
                "error":
                    "grupo_indice no es válido.",
            },
            status=400,
        )

    if grupo_indice < 0:

        return JsonResponse(
            {
                "ok": False,
                "error":
                    "grupo_indice no es válido.",
            },
            status=400,
        )

    # Reusar el endpoint certificado evita duplicar:
    # - Bearer auth;
    # - resolución Bot;
    # - aislamiento tenant;
    # - catálogo;
    # - disponibilidad;
    # - contrato monetario.
    detalle_response = (
        restaurante_producto_detalle(
            request
        )
    )

    if (
        detalle_response.status_code
        != 200
    ):
        return detalle_response

    try:

        detalle = json.loads(
            detalle_response
            .content
            .decode("utf-8")
        )

    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        AttributeError,
    ):

        return JsonResponse(
            {
                "ok": False,
                "error":
                    (
                        "No fue posible interpretar "
                        "el configurador del producto."
                    ),
            },
            status=500,
        )

    if not isinstance(
        detalle,
        dict,
    ):

        return JsonResponse(
            {
                "ok": False,
                "error":
                    (
                        "Respuesta interna de "
                        "configurador inválida."
                    ),
            },
            status=500,
        )

    grupos = detalle.get(
        "grupos"
    )

    if not isinstance(
        grupos,
        list,
    ):
        grupos = []

    grupos_validos = [
        grupo
        for grupo in grupos
        if isinstance(
            grupo,
            dict,
        )
    ]

    grupos_cantidad = len(
        grupos_validos
    )

    producto_id = detalle.get(
        "producto_id"
    )

    producto_nombre = detalle.get(
        "nombre"
    )

    requiere_configuracion = bool(
        detalle.get(
            "requiere_configuracion"
        )
    )

    # Si ya recorrimos todos los grupos, Typebot puede
    # abandonar el loop y continuar con cantidad.
    if (
        grupos_cantidad == 0
        or
        grupo_indice >= grupos_cantidad
    ):

        return JsonResponse(
            {
                "ok": True,

                "producto_id":
                    producto_id,

                "producto_nombre":
                    producto_nombre,

                "requiere_configuracion":
                    requiere_configuracion,

                "grupos_cantidad":
                    grupos_cantidad,

                "grupo_indice":
                    grupo_indice,

                "terminado":
                    True,

                "grupos_restantes":
                    0,

                "grupo_id":
                    None,

                "grupo_nombre":
                    "",

                "grupo_tipo":
                    "",

                "grupo_obligatorio":
                    False,

                "grupo_minimo":
                    0,

                "grupo_maximo":
                    0,

                "opciones_cantidad":
                    0,

                "opcion_ids":
                    [],

                "opcion_nombres":
                    [],

                "opcion_precios":
                    [],

                "opcion_etiquetas":
                    [],

                "siguiente_indice":
                    grupo_indice,
            },
            json_dumps_params={
                "ensure_ascii": False,
            },
        )

    grupo = grupos_validos[
        grupo_indice
    ]

    opciones = grupo.get(
        "opciones"
    )

    if not isinstance(
        opciones,
        list,
    ):
        opciones = []

    opciones_validas = [
        opcion
        for opcion in opciones
        if isinstance(
            opcion,
            dict,
        )
    ]

    opcion_ids = []
    opcion_nombres = []
    opcion_precios = []
    opcion_etiquetas = []

    for ordinal, opcion in enumerate(
        opciones_validas,
        start=1,
    ):

        opcion_id = opcion.get(
            "id"
        )

        nombre = str(
            opcion.get(
                "nombre"
            )
            or ""
        ).strip()

        precio_raw = str(
            opcion.get(
                "precio_adicional"
            )
            or "0"
        ).strip()

        try:

            precio = Decimal(
                precio_raw
            )

        except (
            InvalidOperation,
            ValueError,
            TypeError,
        ):

            precio = Decimal(
                "0"
            )

        precio_normalizado = (
            f"{precio:.2f}"
        )

        etiqueta = (
            f"{ordinal}. {nombre}"
        )

        if precio > 0:

            etiqueta += (
                f" (+{precio_normalizado})"
            )

        elif precio < 0:

            etiqueta += (
                f" ({precio_normalizado})"
            )

        opcion_ids.append(
            opcion_id
        )

        opcion_nombres.append(
            nombre
        )

        opcion_precios.append(
            precio_normalizado
        )

        # El ordinal garantiza etiqueta única incluso
        # si existen dos opciones con el mismo nombre.
        opcion_etiquetas.append(
            etiqueta
        )

    siguiente_indice = (
        grupo_indice + 1
    )

    grupos_restantes = max(
        0,
        grupos_cantidad
        -
        siguiente_indice,
    )

    return JsonResponse(
        {
            "ok": True,

            "producto_id":
                producto_id,

            "producto_nombre":
                producto_nombre,

            "requiere_configuracion":
                requiere_configuracion,

            "grupos_cantidad":
                grupos_cantidad,

            "grupo_indice":
                grupo_indice,

            "terminado":
                False,

            "grupos_restantes":
                grupos_restantes,

            "grupo_id":
                grupo.get("id"),

            "grupo_nombre":
                str(
                    grupo.get(
                        "nombre"
                    )
                    or ""
                ),

            "grupo_tipo":
                str(
                    grupo.get(
                        "tipo"
                    )
                    or ""
                ),

            "grupo_obligatorio":
                bool(
                    grupo.get(
                        "obligatorio"
                    )
                ),

            "grupo_minimo":
                int(
                    grupo.get(
                        "minimo"
                    )
                    or 0
                ),

            "grupo_maximo":
                int(
                    grupo.get(
                        "maximo"
                    )
                    or 0
                ),

            "opciones_cantidad":
                len(
                    opciones_validas
                ),

            "opcion_ids":
                opcion_ids,

            "opcion_nombres":
                opcion_nombres,

            "opcion_precios":
                opcion_precios,

            "opcion_etiquetas":
                opcion_etiquetas,

            "siguiente_indice":
                siguiente_indice,
        },
        json_dumps_params={
            "ensure_ascii": False,
        },
    )


# =============================================================================
# TNL-RESTAURANTE-API-PEDIDO-V1
#
# Contrato HTTP Restaurante.
#
# views_api:
# - autentica;
# - resuelve Bot / Empresa / Plantilla;
# - valida estructura;
# - serializa.
#
# services/pedidos.py:
# - crea pedido;
# - agrega línea;
# - calcula importes;
# - configura logística;
# - confirma e inventaría.
#
# Esta sección NO escribe subtotal / descuento / total / importe directamente.
# =============================================================================


def _restaurante_api_body_dict(
    request,
):

    import json

    try:

        if (
            request.content_type
            ==
            "application/json"
        ):

            datos = json.loads(
                request.body.decode(
                    "utf-8"
                )
            )

        else:

            datos = (
                request.POST.dict()
            )

    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
    ):

        return (
            None,
            JsonResponse(
                {
                    "ok": False,
                    "error":
                        "El cuerpo JSON "
                        "no es válido.",
                },
                status=400,
            ),
        )

    if not isinstance(
        datos,
        dict,
    ):

        return (
            None,
            JsonResponse(
                {
                    "ok": False,
                    "error":
                        "El cuerpo debe ser "
                        "un objeto JSON.",
                },
                status=400,
            ),
        )

    return (
        datos,
        None,
    )


def _restaurante_api_validar_token(
    carrito_token,
):

    token = str(
        carrito_token
        or ""
    ).strip()

    if (
        not token
        or
        len(token) > 64
    ):

        return (
            None,
            JsonResponse(
                {
                    "ok": False,
                    "error":
                        "carrito_token "
                        "no es válido.",
                },
                status=400,
            ),
        )

    return (
        token,
        None,
    )


def _restaurante_api_resolver_pedido(
    *,
    bot,
    carrito_token,
    solo_carrito=False,
):

    from core.models import (
        Pedido,
    )

    token, token_error = (
        _restaurante_api_validar_token(
            carrito_token
        )
    )

    if token_error is not None:

        return (
            None,
            token_error,
        )

    # ================================================================
    # TNL-RESTAURANTE-BOT-SCOPE-V1
    #
    # Formato exacto:
    #     r:<bot_id>:<uuid_hex_32>
    #
    # Esto permite acreditar el Bot incluso cuando Pedido.canal=NULL.
    # No se acepta un token Restaurante antiguo/no-scoped.
    # ================================================================

    partes_token = token.split(
        ":"
    )

    token_bot_valido = (
        len(partes_token) == 3
        and
        partes_token[0] == "r"
        and
        partes_token[1] == str(bot.id)
        and
        len(partes_token[2]) == 32
        and
        all(
            caracter
            in
            "0123456789abcdefABCDEF"
            for caracter
            in partes_token[2]
        )
    )

    if not token_bot_valido:

        # No revelamos si el token pertenece
        # a otro Bot de la misma Empresa.
        return (
            None,
            JsonResponse(
                {
                    "ok": False,
                    "error":
                        "Pedido no encontrado.",
                },
                status=404,
            ),
        )

    pedidos = list(
        Pedido.objects
        .select_related(
            "canal",
            "canal__bot",
        )
        .filter(
            empresa_id=
                bot.empresa_id,

            identificador_externo=
                (
                    "typebot:"
                    +
                    token
                ),
        )
        .order_by(
            "id"
        )[:2]
    )

    if not pedidos:

        return (
            None,
            JsonResponse(
                {
                    "ok": False,
                    "error":
                        "Pedido no encontrado.",
                },
                status=404,
            ),
        )

    if len(pedidos) != 1:

        return (
            None,
            JsonResponse(
                {
                    "ok": False,
                    "error":
                        "El identificador del "
                        "carrito es ambiguo.",
                    "codigo":
                        "CARRITO_TOKEN_AMBIGUO",
                },
                status=409,
            ),
        )

    pedido = pedidos[0]

    # Si el pedido quedó asociado físicamente
    # a un canal, ese canal debe pertenecer al
    # mismo Bot que invoca esta API.
    if (
        pedido.canal_id
        and
        pedido.canal.bot_id
        !=
        bot.id
    ):

        return (
            None,
            JsonResponse(
                {
                    "ok": False,
                    "error":
                        "Pedido no encontrado.",
                },
                status=404,
            ),
        )

    if (
        solo_carrito
        and
        pedido.estado != "carrito"
    ):

        return (
            None,
            JsonResponse(
                {
                    "ok": False,

                    "error":
                        "El pedido ya no está "
                        "disponible como carrito.",

                    "pedido_numero":
                        pedido.numero,

                    "estado":
                        pedido.estado,
                },
                status=409,
            ),
        )

    return (
        pedido,
        None,
    )


def _restaurante_api_serializar_pedido(
    pedido,
    *,
    carrito_token,
):

    pedido.refresh_from_db()

    detalles = list(
        pedido.detalles
        .select_related(
            "producto",
        )
        .order_by(
            "id"
        )
    )

    lineas = []

    for detalle in detalles:

        precio_base = None

        if (
            detalle.precio_base
            is not None
        ):

            precio_base = (
                _restaurante_api_dinero(
                    detalle.precio_base,
                    etiqueta=
                        "El precio base de la línea",
                )
            )

        lineas.append(
            {
                "detalle_id":
                    detalle.id,

                "producto_id":
                    detalle.producto_id,

                "sku":
                    detalle.sku,

                "nombre":
                    detalle.nombre_producto,

                "cantidad":
                    str(
                        detalle.cantidad
                    ),

                "precio_base":
                    precio_base,

                "precio_modificadores":
                    _restaurante_api_dinero(
                        detalle
                        .precio_modificadores,

                        etiqueta=(
                            "Los modificadores "
                            "de la línea"
                        ),
                    ),

                "precio_extras":
                    _restaurante_api_dinero(
                        detalle.precio_extras,

                        etiqueta=(
                            "Los extras "
                            "de la línea"
                        ),
                    ),

                "precio_unitario":
                    _restaurante_api_dinero(
                        detalle.precio_unitario,

                        etiqueta=(
                            "El precio unitario "
                            "de la línea"
                        ),
                    ),

                "descuento":
                    _restaurante_api_dinero(
                        detalle.descuento,

                        etiqueta=(
                            "El descuento "
                            "de la línea"
                        ),
                    ),

                "importe":
                    _restaurante_api_dinero(
                        detalle.importe,

                        etiqueta=(
                            "El importe "
                            "de la línea"
                        ),
                    ),

                "modificadores":
                    detalle
                    .modificadores_snapshot,

                "extras":
                    detalle
                    .extras_snapshot,
            }
        )

    return {
        "carrito_token":
            carrito_token,

        "pedido_id":
            pedido.id,

        "pedido_numero":
            pedido.numero,

        "estado":
            pedido.estado,

        "tipo_orden":
            pedido.tipo_orden,

        "cliente_nombre":
            pedido.cliente_nombre,

        "cliente_telefono":
            pedido.cliente_telefono,

        "cliente_email":
            pedido.cliente_email,

        "direccion_entrega":
            pedido.direccion_entrega,

        "notas":
            pedido.notas,

        "tiempo_estimado_minutos":
            pedido.tiempo_estimado_minutos,

        "moneda":
            pedido.moneda,

        "subtotal_productos":
            _restaurante_api_dinero(
                pedido.subtotal_productos,
                etiqueta=
                    "El subtotal de productos",
            ),

        "subtotal_modificadores":
            _restaurante_api_dinero(
                pedido
                .subtotal_modificadores,

                etiqueta=(
                    "El subtotal "
                    "de modificadores"
                ),
            ),

        "subtotal_extras":
            _restaurante_api_dinero(
                pedido.subtotal_extras,
                etiqueta=
                    "El subtotal de extras",
            ),

        "subtotal":
            _restaurante_api_dinero(
                pedido.subtotal,
                etiqueta=
                    "El subtotal del pedido",
            ),

        "costo_envio":
            _restaurante_api_dinero(
                pedido.costo_envio,
                etiqueta=
                    "El costo de envío",
            ),

        "descuento":
            _restaurante_api_dinero(
                pedido.descuento,
                etiqueta=
                    "El descuento del pedido",
            ),

        "total":
            _restaurante_api_dinero(
                pedido.total,
                etiqueta=
                    "El total del pedido",
            ),

        "cantidad_lineas":
            len(
                lineas
            ),

        "lineas":
            lineas,
    }


# ============================================================
# TNL-RESTAURANTE-CROSSSELL-RUNTIME-V1
# ============================================================

def _restaurante_api_cross_sell_payload(
    *,
    bot,
    pedido,
    producto_origen,
    suprimir=False,
):
    """
    Resuelve una recomendación de venta cruzada
    después de agregar un producto al carrito.

    Es exclusivamente de lectura.
    Producto.precio sigue siendo la fuente
    autoritativa del precio mostrado.
    """

    from core.models import (
        ReglaVentaCruzadaIA,
    )


    vacio = {
        "cross_sell_disponible": False,
        "cross_sell_regla_id": None,
        "cross_sell_producto_id": None,
        "cross_sell_producto_nombre": "",
        "cross_sell_precio": "",
        "cross_sell_precio_texto": "",
        "cross_sell_moneda": pedido.moneda,
        "cross_sell_mensaje": "",
    }


    # TNL-RESTAURANTE-CROSSSELL-SUPPRESS-V1
    #
    # Una aceptación de venta cruzada utiliza el
    # mismo endpoint de agregado, pero no debe
    # iniciar otra promoción inmediatamente.
    if suprimir:
        return vacio


    filtros = {
        "empresa_id":
            bot.empresa_id,

        "producto_origen_id":
            producto_origen.id,

        "activa":
            True,

        "producto_recomendado__activo":
            True,

        "producto_recomendado__catalogo__activo":
            True,

        "producto_recomendado__catalogo__empresa_id":
            bot.empresa_id,

        "producto_recomendado__catalogo__plantilla_id":
            bot.plantilla_id,
    }


    from core.services.catalogo import (
        productos_vendibles,
    )

    # TNL-RESTAURANTE-DISPONIBILIDAD-V1
    # Sólo se sugiere lo que el menú vendería (Disponible /
    # Agotado); el stock numérico ya no cuenta.
    reglas = (
        ReglaVentaCruzadaIA.objects
        .filter(
            **filtros
        )
        .filter(
            producto_recomendado__in=(
                productos_vendibles(
                    empresa_id=bot.empresa_id,
                    plantilla_id=bot.plantilla_id,
                    restaurante=True,
                ).values("id")
            ),
        )
        .select_related(
            "producto_recomendado",
            "producto_recomendado__catalogo",
            "producto_recomendado__categoria",
            "producto_recomendado__categoria__catalogo",
        )
        .order_by(
            "prioridad",
            "id",
        )
    )


    for regla in reglas:

        recomendado = (
            regla.producto_recomendado
        )


        if (
            recomendado.id
            ==
            producto_origen.id
        ):
            continue


        categoria = (
            recomendado.categoria
        )


        if categoria is None:
            continue


        if not categoria.activa:
            continue


        if (
            categoria.catalogo_id
            !=
            recomendado.catalogo_id
        ):
            continue


        if (
            recomendado.catalogo.empresa_id
            !=
            bot.empresa_id
        ):
            continue


        if (
            recomendado.catalogo.plantilla_id
            !=
            bot.plantilla_id
        ):
            continue


        if (
            recomendado.catalogo.moneda
            !=
            pedido.moneda
        ):
            continue


        if (
            pedido.detalles
            .filter(
                producto_id=
                    recomendado.id
            )
            .exists()
        ):
            continue


        precio = (
            _restaurante_api_dinero(
                recomendado.precio,
                etiqueta=(
                    "El precio del producto "
                    "recomendado "
                    f"'{recomendado.nombre}'"
                ),
            )
        )


        precio_texto = (
            f"${precio} "
            f"{pedido.moneda}"
        )


        plantilla = str(
            regla.texto_promocional
            or ""
        ).strip()


        usa_precio = (
            "{{precio_recomendado}}"
            in
            plantilla
        )


        if plantilla:

            mensaje = (
                plantilla
                .replace(
                    "{{producto_origen}}",
                    producto_origen.nombre,
                )
                .replace(
                    "{{producto_recomendado}}",
                    recomendado.nombre,
                )
                .replace(
                    "{{precio_recomendado}}",
                    precio_texto,
                )
            )


            if not usa_precio:

                mensaje = (
                    mensaje.rstrip()
                    +
                    "\nPrecio actual: "
                    +
                    precio_texto
                    +
                    "."
                )

        else:

            mensaje = (
                f"Ya agregaste "
                f"{producto_origen.nombre}. "
                f"¿Deseas agregar también "
                f"{recomendado.nombre} "
                f"por {precio_texto}?"
            )


        return {
            "cross_sell_disponible":
                True,

            "cross_sell_regla_id":
                regla.id,

            "cross_sell_producto_id":
                recomendado.id,

            "cross_sell_producto_nombre":
                recomendado.nombre,

            "cross_sell_precio":
                precio,

            "cross_sell_precio_texto":
                precio_texto,

            "cross_sell_moneda":
                pedido.moneda,

            "cross_sell_mensaje":
                mensaje,
        }


    return vacio



@csrf_exempt
def restaurante_pedido_producto_agregar(
    request,
):

    from uuid import uuid4

    from django.core.exceptions import (
        ValidationError,
    )

    from django.db import (
        transaction,
    )

    from core.models import (
        Pedido,
        Producto,
    )

    from core.services.catalogo import (
        productos_vendibles,
    )

    from core.services.pedidos import (
        agregar_producto_configurado_a_pedido,
        crear_pedido,
    )

    if request.method != "POST":

        return JsonResponse(
            {
                "ok": False,
                "error":
                    "Método no permitido.",
            },
            status=405,
        )

    auth_error = (
        _restaurante_api_auth_error(
            request
        )
    )

    if auth_error is not None:

        return auth_error

    datos, body_error = (
        _restaurante_api_body_dict(
            request
        )
    )

    if body_error is not None:

        return body_error

    bot, bot_error = (
        _restaurante_api_resolver_bot(
            datos.get(
                "bot_id",
                "",
            )
        )
    )

    if bot_error is not None:

        return bot_error

    producto_texto = str(
        datos.get(
            "producto_id",
            "",
        )
        or ""
    ).strip()

    cantidad = datos.get(
        "cantidad",
        "",
    )

    opciones = datos.get(
        "opcion_ids",
        [],
    )

    carrito_token = str(
        datos.get(
            "carrito_token",
            "",
        )
        or ""
    ).strip()


    suprimir_cross_sell_valor = (
        datos.get(
            "suprimir_cross_sell",
            False,
        )
    )


    if isinstance(
        suprimir_cross_sell_valor,
        bool,
    ):

        suprimir_cross_sell = (
            suprimir_cross_sell_valor
        )

    else:

        suprimir_normalizado = str(
            suprimir_cross_sell_valor
            or ""
        ).strip().lower()


        if suprimir_normalizado in (
            "",
            "0",
            "false",
            "no",
        ):

            suprimir_cross_sell = False

        elif suprimir_normalizado in (
            "1",
            "true",
            "yes",
            "si",
            "sí",
        ):

            suprimir_cross_sell = True

        else:

            return JsonResponse(
                {
                    "ok": False,
                    "error": (
                        "suprimir_cross_sell "
                        "no es válido."
                    ),
                },
                status=400,
            )


    try:

        producto_id = int(
            producto_texto
        )

    except (
        TypeError,
        ValueError,
    ):

        return JsonResponse(
            {
                "ok": False,
                "error":
                    "producto_id no es válido.",
            },
            status=400,
        )

    if (
        cantidad is None
        or
        str(cantidad).strip() == ""
    ):

        return JsonResponse(
            {
                "ok": False,
                "error":
                    "cantidad es obligatoria.",
            },
            status=400,
        )

    if not isinstance(
        opciones,
        list,
    ):

        return JsonResponse(
            {
                "ok": False,
                "error":
                    "opcion_ids debe ser "
                    "una lista.",
            },
            status=400,
        )

    try:

        with transaction.atomic():

            # TNL-CATALOGO-REGLAS-V1
            # La regla compartida ya exige que la categoría
            # pertenezca al catálogo del producto.
            producto = (
                productos_vendibles(
                    empresa_id=bot.empresa_id,
                    plantilla_id=bot.plantilla_id,
                    restaurante=True,
                    queryset=(
                        Producto.objects
                        .select_for_update()
                        .select_related(
                            "catalogo",
                            "categoria",
                            "categoria__catalogo",
                        )
                    ),
                )
                .filter(
                    id=producto_id,
                )
                .first()
            )

            if producto is None:

                return JsonResponse(
                    {
                        "ok": False,
                        "error":
                            "Producto no encontrado "
                            "para este bot.",
                    },
                    status=404,
                )

            carrito_creado = False

            if carrito_token:

                pedido, pedido_error = (
                    _restaurante_api_resolver_pedido(
                        bot=bot,
                        carrito_token=
                            carrito_token,
                        solo_carrito=True,
                    )
                )

                if pedido_error is not None:
                    return pedido_error

                if (
                    pedido.moneda
                    !=
                    producto.catalogo.moneda
                ):

                    return JsonResponse(
                        {
                            "ok": False,
                            "error":
                                "El producto utiliza "
                                "una moneda diferente.",
                        },
                        status=409,
                    )

            else:

                # El token no se obtiene del cliente.
                # Generamos uno nuevo y evitamos incluso
                # la colisión teórica en la misma empresa.
                carrito_token = ""

                for _ in range(5):

                    # TNL-RESTAURANTE-BOT-SCOPE-V1
                    #
                    # El token conserva entropía UUID,
                    # pero además acredita explícitamente
                    # el Bot que creó el carrito.
                    candidato = (
                        "r:"
                        +
                        str(bot.id)
                        +
                        ":"
                        +
                        uuid4().hex
                    )

                    existe = (
                        Pedido.objects
                        .filter(
                            empresa_id=
                                bot.empresa_id,

                            identificador_externo=
                                (
                                    "typebot:"
                                    +
                                    candidato
                                ),
                        )
                        .exists()
                    )

                    if not existe:

                        carrito_token = (
                            candidato
                        )
                        break

                if not carrito_token:

                    raise ValidationError(
                        (
                            "No fue posible generar "
                            "un identificador de carrito."
                        )
                    )

                canal = (
                    _resolver_canal_whatsapp_pedido_typebot(
                        bot
                    )
                )

                pedido = crear_pedido(
                    empresa_id=
                        bot.empresa_id,

                    moneda=
                        producto.catalogo.moneda,

                    canal_id=(
                        canal.id
                        if canal
                        else None
                    ),

                    identificador_externo=
                        (
                            "typebot:"
                            +
                            carrito_token
                        ),
                )

                carrito_creado = True

            detalle = (
                agregar_producto_configurado_a_pedido(
                    pedido_id=
                        pedido.id,

                    producto_id=
                        producto.id,

                    cantidad=
                        cantidad,

                    seleccion_opciones=
                        opciones,

                    # Typebot no controla descuentos.
                    descuento="0.0000",
                )
            )

            detalle_id = detalle.id

            cross_sell_payload = (
                _restaurante_api_cross_sell_payload(
                    bot=bot,
                    pedido=pedido,
                    producto_origen=
                        producto,

                    suprimir=
                        suprimir_cross_sell,
                )
            )

            payload = (
                _restaurante_api_serializar_pedido(
                    pedido,
                    carrito_token=
                        carrito_token,
                )
            )

    except ValidationError as exc:

        mensajes = (
            getattr(
                exc,
                "messages",
                None,
            )
            or
            [
                str(exc)
            ]
        )

        return JsonResponse(
            {
                "ok": False,
                "error":
                    mensajes[0],
                "errores":
                    mensajes,
            },
            status=409,
        )

    return JsonResponse(
        {
            "ok": True,
            "carrito_creado":
                carrito_creado,
            "detalle_id":
                detalle_id,
            **payload,
            **cross_sell_payload,
            "mensaje":
                "Producto agregado "
                "al pedido.",
        },
        json_dumps_params={
            "ensure_ascii": False,
        },
    )


@csrf_exempt
def restaurante_pedido_datos(
    request,
):

    from django.core.exceptions import (
        ValidationError,
    )

    from django.core.validators import (
        validate_email,
    )

    from core.services.pedidos import (
        actualizar_datos_pedido,
    )

    if request.method != "POST":

        return JsonResponse(
            {
                "ok": False,
                "error":
                    "Método no permitido.",
            },
            status=405,
        )

    auth_error = (
        _restaurante_api_auth_error(
            request
        )
    )

    if auth_error is not None:
        return auth_error

    datos, body_error = (
        _restaurante_api_body_dict(
            request
        )
    )

    if body_error is not None:
        return body_error

    bot, bot_error = (
        _restaurante_api_resolver_bot(
            datos.get(
                "bot_id",
                "",
            )
        )
    )

    if bot_error is not None:
        return bot_error

    pedido, pedido_error = (
        _restaurante_api_resolver_pedido(
            bot=bot,
            carrito_token=
                datos.get(
                    "carrito_token",
                    "",
                ),
            solo_carrito=True,
        )
    )

    if pedido_error is not None:
        return pedido_error

    if not pedido.detalles.exists():

        return JsonResponse(
            {
                "ok": False,
                "error":
                    "El carrito está vacío.",
            },
            status=400,
        )

    cliente_nombre = str(
        datos.get(
            "cliente_nombre",
            "",
        )
        or ""
    ).strip()

    cliente_telefono = str(
        datos.get(
            "cliente_telefono",
            "",
        )
        or ""
    ).strip()

    if (
        not cliente_nombre
        or
        not cliente_telefono
    ):

        return JsonResponse(
            {
                "ok": False,
                "error":
                    "Nombre y teléfono "
                    "son obligatorios.",
            },
            status=400,
        )

    if len(cliente_nombre) > 200:

        return JsonResponse(
            {
                "ok": False,
                "error":
                    "El nombre es demasiado largo.",
            },
            status=400,
        )

    if len(cliente_telefono) > 50:

        return JsonResponse(
            {
                "ok": False,
                "error":
                    "El teléfono es demasiado largo.",
            },
            status=400,
        )

    if "cliente_email" in datos:

        cliente_email = str(
            datos.get(
                "cliente_email",
                "",
            )
            or ""
        ).strip()

    else:

        cliente_email = (
            pedido.cliente_email
        )

    if (
        cliente_email.casefold()
        in {
            "omitir",
            "ninguno",
            "ninguna",
            "no",
        }
    ):

        cliente_email = ""

    if cliente_email:

        try:
            validate_email(
                cliente_email
            )

        except ValidationError:

            return JsonResponse(
                {
                    "ok": False,
                    "error":
                        "El correo electrónico "
                        "no es válido.",
                },
                status=400,
            )

    if "notas" in datos:

        notas = str(
            datos.get(
                "notas",
                "",
            )
            or ""
        ).strip()

    else:

        notas = pedido.notas

    if (
        notas.casefold()
        in {
            "ninguno",
            "ninguna",
            "no",
        }
    ):

        notas = ""

    try:

        pedido = actualizar_datos_pedido(
            pedido_id=
                pedido.id,

            # Preservar asociación de canal.
            canal_id=
                pedido.canal_id,

            cliente_nombre=
                cliente_nombre,

            cliente_telefono=
                cliente_telefono,

            cliente_email=
                cliente_email,

            # Dirección pertenece exclusivamente
            # al endpoint logística.
            direccion_entrega=
                pedido.direccion_entrega,

            notas=
                notas,

            # Preservar token Typebot.
            identificador_externo=
                pedido.identificador_externo,
        )

    except ValidationError as exc:

        mensajes = (
            getattr(
                exc,
                "messages",
                None,
            )
            or
            [
                str(exc)
            ]
        )

        return JsonResponse(
            {
                "ok": False,
                "error":
                    mensajes[0],
                "errores":
                    mensajes,
            },
            status=409,
        )

    token = (
        pedido
        .identificador_externo
        .removeprefix(
            "typebot:"
        )
    )

    payload = (
        _restaurante_api_serializar_pedido(
            pedido,
            carrito_token=token,
        )
    )

    return JsonResponse(
        {
            "ok": True,
            "datos_guardados": True,
            **payload,
            "mensaje":
                "Datos del pedido "
                "guardados correctamente.",
        },
        json_dumps_params={
            "ensure_ascii": False,
        },
    )


@csrf_exempt
def restaurante_pedido_logistica(
    request,
):

    from django.core.exceptions import (
        ValidationError,
    )

    from core.services.pedidos import (
        configurar_logistica_pedido,
    )

    if request.method != "POST":

        return JsonResponse(
            {
                "ok": False,
                "error":
                    "Método no permitido.",
            },
            status=405,
        )

    auth_error = (
        _restaurante_api_auth_error(
            request
        )
    )

    if auth_error is not None:
        return auth_error

    datos, body_error = (
        _restaurante_api_body_dict(
            request
        )
    )

    if body_error is not None:
        return body_error

    bot, bot_error = (
        _restaurante_api_resolver_bot(
            datos.get(
                "bot_id",
                "",
            )
        )
    )

    if bot_error is not None:
        return bot_error

    carrito_token = str(
        datos.get(
            "carrito_token",
            "",
        )
        or ""
    ).strip()

    pedido, pedido_error = (
        _restaurante_api_resolver_pedido(
            bot=bot,
            carrito_token=
                carrito_token,
            solo_carrito=True,
        )
    )

    if pedido_error is not None:
        return pedido_error

    tipo_orden = str(
        datos.get(
            "tipo_orden",
            "",
        )
        or ""
    ).strip()

    direccion = str(
        datos.get(
            "direccion_entrega",
            "",
        )
        or ""
    ).strip()

    try:

        pedido = (
            configurar_logistica_pedido(
                pedido_id=
                    pedido.id,

                tipo_orden=
                    tipo_orden,

                direccion_entrega=
                    direccion,
            )
        )

    except ValidationError as exc:

        mensajes = (
            getattr(
                exc,
                "messages",
                None,
            )
            or
            [
                str(exc)
            ]
        )

        return JsonResponse(
            {
                "ok": False,
                "error":
                    mensajes[0],
                "errores":
                    mensajes,
            },
            status=409,
        )

    payload = (
        _restaurante_api_serializar_pedido(
            pedido,
            carrito_token=
                carrito_token,
        )
    )

    return JsonResponse(
        {
            "ok": True,
            "logistica_guardada": True,
            **payload,
            "mensaje":
                "Logística del pedido "
                "guardada correctamente.",
        },
        json_dumps_params={
            "ensure_ascii": False,
        },
    )


# TNL-RESTAURANTE-RESUMEN-TEXTO-V1
def _restaurante_api_construir_resumen_texto(
    payload,
):
    """
    Construye únicamente la representación humana
    del resumen de restaurante.

    NO recalcula precios, descuentos ni totales.
    Todos los importes provienen del payload ya
    serializado y validado por Django.

    Los modificadores y extras de cada línea se muestran
    desde el snapshot guardado (TNL-LINEAS-PEDIDO-V1).
    """

    from core.services.lineas_pedido import (
        describir_linea,
        texto_lineas,
    )

    def texto_una_linea(valor):

        return " ".join(
            str(
                valor
                if valor is not None
                else ""
            ).split()
        )

    numero_pedido = (
        texto_una_linea(
            payload.get(
                "pedido_numero"
            )
        )
        or
        "-"
    )

    moneda = (
        texto_una_linea(
            payload.get(
                "moneda"
            )
        )
        or
        "MXN"
    )

    tipo_orden = (
        texto_una_linea(
            payload.get(
                "tipo_orden"
            )
        )
    )

    tipo_orden_texto = {
        "comedor":
            "Comedor",

        "para_llevar":
            "Para llevar",

        "domicilio":
            "Domicilio",

    }.get(
        tipo_orden,
        tipo_orden or "-",
    )

    lineas = (
        payload.get(
            "lineas"
        )
        or
        []
    )

    resumen = [
        f"🧾 Pedido {numero_pedido}",
        "",
    ]

    descripciones = [
        describir_linea(
            nombre=(
                linea.get("nombre")
                or
                f"Producto {indice}"
            ),
            cantidad=linea.get("cantidad"),
            importe=(
                linea.get("importe")
                or
                "0.00"
            ),
            modificadores=linea.get(
                "modificadores"
            ),
            extras=linea.get(
                "extras"
            ),
        )
        for indice, linea in enumerate(
            lineas,
            start=1,
        )
        if isinstance(
            linea,
            dict,
        )
    ]

    if descripciones:

        resumen.append(
            texto_lineas(
                descripciones
            )
        )

    else:

        resumen.append(
            "Sin productos."
        )

    resumen.extend(
        [
            "",
            (
                "Tipo: "
                f"{tipo_orden_texto}"
            ),
            (
                "Productos: $"
                f"{payload.get('subtotal_productos', '0.00')}"
            ),
            (
                "Modificadores: $"
                f"{payload.get('subtotal_modificadores', '0.00')}"
            ),
            (
                "Extras: $"
                f"{payload.get('subtotal_extras', '0.00')}"
            ),
            (
                "Envío: $"
                f"{payload.get('costo_envio', '0.00')}"
            ),
            (
                "Descuento: $"
                f"{payload.get('descuento', '0.00')}"
            ),
            (
                "TOTAL: $"
                f"{payload.get('total', '0.00')} "
                f"{moneda}"
            ),
        ]
    )

    return "\n".join(
        resumen
    )


def restaurante_pedido_resumen(
    request,
):

    from django.core.exceptions import (
        ValidationError,
    )

    if request.method != "GET":

        return JsonResponse(
            {
                "ok": False,
                "error":
                    "Método no permitido.",
            },
            status=405,
        )

    auth_error = (
        _restaurante_api_auth_error(
            request
        )
    )

    if auth_error is not None:
        return auth_error

    bot, bot_error = (
        _restaurante_api_resolver_bot(
            request.GET.get(
                "bot_id",
                "",
            )
        )
    )

    if bot_error is not None:
        return bot_error

    carrito_token = str(
        request.GET.get(
            "carrito_token",
            "",
        )
        or ""
    ).strip()

    pedido, pedido_error = (
        _restaurante_api_resolver_pedido(
            bot=bot,
            carrito_token=
                carrito_token,
            solo_carrito=False,
        )
    )

    if pedido_error is not None:
        return pedido_error

    try:

        payload = (
            _restaurante_api_serializar_pedido(
                pedido,
                carrito_token=
                    carrito_token,
            )
        )

        payload["resumen_texto"] = (
            _restaurante_api_construir_resumen_texto(
                payload
            )
        )

    except ValidationError as exc:

        mensajes = (
            getattr(
                exc,
                "messages",
                None,
            )
            or
            [
                str(exc)
            ]
        )

        return JsonResponse(
            {
                "ok": False,
                "error":
                    mensajes[0],
            },
            status=409,
        )

    return JsonResponse(
        {
            "ok": True,
            **payload,
        },
        json_dumps_params={
            "ensure_ascii": False,
        },
    )


def _restaurante_pedido_confirmar(
    request,
):

    from django.core.exceptions import (
        ValidationError,
    )

    from core.services.pedidos import (
        confirmar_pedido,
    )

    if request.method != "POST":

        return JsonResponse(
            {
                "ok": False,
                "error":
                    "Método no permitido.",
            },
            status=405,
        )

    auth_error = (
        _restaurante_api_auth_error(
            request
        )
    )

    if auth_error is not None:
        return auth_error

    datos, body_error = (
        _restaurante_api_body_dict(
            request
        )
    )

    if body_error is not None:
        return body_error

    bot, bot_error = (
        _restaurante_api_resolver_bot(
            datos.get(
                "bot_id",
                "",
            )
        )
    )

    if bot_error is not None:
        return bot_error

    carrito_token = str(
        datos.get(
            "carrito_token",
            "",
        )
        or ""
    ).strip()

    pedido, pedido_error = (
        _restaurante_api_resolver_pedido(
            bot=bot,
            carrito_token=
                carrito_token,
            solo_carrito=True,
        )
    )

    if pedido_error is not None:
        return pedido_error

    if not pedido.detalles.exists():

        return JsonResponse(
            {
                "ok": False,
                "error":
                    "El carrito está vacío.",
            },
            status=400,
        )

    if not (
        pedido.cliente_nombre.strip()
        and
        pedido.cliente_telefono.strip()
    ):

        return JsonResponse(
            {
                "ok": False,
                "error":
                    "Faltan nombre o teléfono "
                    "del cliente.",
            },
            status=400,
        )

    if pedido.tipo_orden not in {
        "comedor",
        "para_llevar",
        "domicilio",
    }:

        return JsonResponse(
            {
                "ok": False,
                "error":
                    "Falta configurar el "
                    "tipo de orden.",
            },
            status=400,
        )

    if (
        pedido.tipo_orden
        ==
        "domicilio"
        and
        not pedido
        .direccion_entrega
        .strip()
    ):

        return JsonResponse(
            {
                "ok": False,
                "error":
                    "La dirección de entrega "
                    "es obligatoria para domicilio.",
            },
            status=400,
        )

    from core.services.pedidos import (
        CODIGO_PEDIDO_REQUIERE_REVISION,
        texto_aviso_ajuste_precios,
    )

    try:

        # TNL-RESTAURANTE-CONFIRMACION-CATALOGO-V1
        # Revisa el catálogo vigente del bot: precios del
        # servidor y disponibilidad actual.
        pedido = confirmar_pedido(
            pedido_id=
                pedido.id,
            revalidar_catalogo_plantilla_id=
                bot.plantilla_id,
        )

    except ValidationError as exc:

        mensajes = (
            getattr(
                exc,
                "messages",
                None,
            )
            or
            [
                str(exc)
            ]
        )

        requiere_revision = (
            getattr(exc, "code", None)
            == CODIGO_PEDIDO_REQUIERE_REVISION
        )

        return JsonResponse(
            {
                "ok": False,
                "error":
                    mensajes[0],
                "errores":
                    mensajes,
                "mensaje":
                    mensajes[0],
                "codigo": (
                    "PEDIDO_REQUIERE_REVISION"
                    if requiere_revision
                    else "PEDIDO_NO_CONFIRMADO"
                ),
                "pedido_numero":
                    pedido.numero,
            },
            status=409,
            json_dumps_params={
                "ensure_ascii": False,
            },
        )

    payload = (
        _restaurante_api_serializar_pedido(
            pedido,
            carrito_token=
                carrito_token,
        )
    )

    ajustes = getattr(pedido, "ajustes_precio", [])

    aviso_precios = texto_aviso_ajuste_precios(
        ajustes,
        total=pedido.total,
        moneda=pedido.moneda,
    )

    mensaje = (
        f"Pedido {pedido.numero} "
        "confirmado correctamente."
    )

    # Typebot muestra "mensaje" antes de elegir el pago.
    if aviso_precios:
        mensaje = f"{mensaje} {aviso_precios}"

    return JsonResponse(
        {
            "ok": True,
            "pedido_confirmado": True,
            **payload,
            "confirmado_en": (
                pedido
                .confirmado_en
                .isoformat()
                if pedido.confirmado_en
                else None
            ),
            "precios_actualizados":
                bool(ajustes),
            "aviso_precios":
                aviso_precios,
            "ajustes_precio": [
                {
                    "producto": ajuste["producto"],
                    "cantidad": f"{ajuste['cantidad']:.2f}",
                    "precio_anterior": f"{ajuste['antes']:.2f}",
                    "precio_actual": f"{ajuste['despues']:.2f}",
                }
                for ajuste in ajustes
            ],
            "mensaje":
                mensaje,
        },
        json_dumps_params={
            "ensure_ascii": False,
        },
    )


@csrf_exempt
def restaurante_pedido_confirmar(
    request,
):
    """
    TNL-RESTAURANTE-CONFIRMACION-CATALOGO-V1

    Typebot muestra data.mensaje cuando no se pudo confirmar: toda
    respuesta de error lleva "mensaje" para no dejar a la vista el
    de un intento anterior.
    """

    import json

    response = _restaurante_pedido_confirmar(request)

    if (
        response.status_code < 400
        or not response.get("Content-Type", "").startswith("application/json")
    ):
        return response

    try:
        data = json.loads(response.content)
    except ValueError:
        return response

    if not isinstance(data, dict) or data.get("mensaje"):
        return response

    data["mensaje"] = (
        data.get("error")
        or "No pudimos confirmar el pedido."
    )

    return JsonResponse(
        data,
        status=response.status_code,
        json_dumps_params={
            "ensure_ascii": False,
        },
    )


# =============================================================================
# TNL-RESTAURANTE-API-CIERRE-V1
#
# Cancelación:
#   valida scope Restaurante y delega al flujo legacy certificado.
#
# Checkout:
#   valida scope Restaurante y delega íntegramente al Checkout Pro existente.
#
# Consulta:
#   número + teléfono + Empresa + Bot-scoped identificador.
#
# No duplica matemática ni integración Mercado Pago.
# =============================================================================


@csrf_exempt
def restaurante_pedido_cancelar(
    request,
):

    if request.method != "POST":

        return JsonResponse(
            {
                "ok": False,
                "error":
                    "Método no permitido.",
            },
            status=405,
        )

    auth_error = (
        _restaurante_api_auth_error(
            request
        )
    )

    if auth_error is not None:
        return auth_error

    datos, body_error = (
        _restaurante_api_body_dict(
            request
        )
    )

    if body_error is not None:
        return body_error

    bot, bot_error = (
        _restaurante_api_resolver_bot(
            datos.get(
                "bot_id",
                "",
            )
        )
    )

    if bot_error is not None:
        return bot_error

    _, pedido_error = (
        _restaurante_api_resolver_pedido(
            bot=bot,
            carrito_token=
                datos.get(
                    "carrito_token",
                    "",
                ),
            solo_carrito=False,
        )
    )

    if pedido_error is not None:
        return pedido_error

    # TNL-CANCELACION-CLIENTE-V1
    # El alcance del Bot ya se validó arriba; la regla de
    # cancelación vive en cancelar_pedido_cliente.
    return carrito_cancelar(
        request
    )



# =============================================================================
# TNL-RESTAURANTE-PAGO-DIRECTO-P2-V1
#
# Pago directo con el negocio:
# - únicamente CHANGO / Empresa 7 en primera fase;
# - Pedido ya debe estar confirmado;
# - Pago = negocio / pendiente;
# - monto siempre se toma de Pedido;
# - idempotente bajo lock del Pedido;
# - incompatible con MP creado/pendiente/aprobado.
# =============================================================================

@csrf_exempt
def restaurante_pedido_pago_directo(
    request,
):

    from decimal import Decimal

    from django.db import transaction

    from core.models import (
        Pago,
        Pedido,
    )

    if request.method != "POST":

        return JsonResponse(
            {
                "ok": False,
                "error": "Método no permitido.",
            },
            status=405,
        )

    auth_error = (
        _restaurante_api_auth_error(
            request
        )
    )

    if auth_error is not None:
        return auth_error

    datos, body_error = (
        _restaurante_api_body_dict(
            request
        )
    )

    if body_error is not None:
        return body_error

    bot, bot_error = (
        _restaurante_api_resolver_bot(
            datos.get(
                "bot_id",
                "",
            )
        )
    )

    if bot_error is not None:
        return bot_error

    plantilla_tipo = str(
        getattr(
            getattr(
                bot,
                "plantilla",
                None,
            ),
            "tipo",
            "",
        )
        or ""
    ).strip()

    if plantilla_tipo != "restaurante":

        return JsonResponse(
            {
                "ok": False,
                "error":
                    (
                        "El pago directo sólo está "
                        "habilitado para plantillas "
                        "de tipo restaurante."
                    ),
            },
            status=403,
        )

    carrito_token = str(
        datos.get(
            "carrito_token",
            "",
        )
        or ""
    ).strip()

    pedido, pedido_error = (
        _restaurante_api_resolver_pedido(
            bot=bot,
            carrito_token=
                carrito_token,
            solo_carrito=False,
        )
    )

    if pedido_error is not None:
        return pedido_error

    with transaction.atomic():

        pedido_locked = (
            Pedido.objects
            .select_for_update(
                of=("self",)
            )
            .get(
                pk=pedido.pk,
                empresa_id=
                    bot.empresa_id,
            )
        )

        # -------------------------------------------------------------
        # IDEMPOTENCIA PAGO DIRECTO
        # -------------------------------------------------------------

        existente = (
            Pago.objects
            .filter(
                pedido=
                    pedido_locked,

                proveedor=
                    Pago.Proveedor
                    .NEGOCIO,
            )
            .order_by(
                "-id"
            )
            .first()
        )

        if existente is not None:

            if existente.estado in {
                Pago.Estado.PENDIENTE,
                Pago.Estado.APROBADO,
            }:

                return JsonResponse(
                    {
                        "ok": True,

                        "pago_directo_registrado":
                            True,

                        "reutilizado":
                            True,

                        "pedido_id":
                            pedido_locked.id,

                        "pedido_numero":
                            pedido_locked.numero,

                        "pago_id":
                            existente.id,

                        "estado_pago":
                            existente.estado,

                        "metodo_pago":
                            "efectivo_contra_entrega",

                        "monto":
                            str(
                                existente.monto
                            ),

                        "moneda":
                            existente.moneda,

                        "mensaje":
                            (
                                "El pago directo "
                                "ya estaba registrado."
                            ),
                    },
                    json_dumps_params={
                        "ensure_ascii": False,
                    },
                )

            return JsonResponse(
                {
                    "ok": False,
                    "error":
                        (
                            "Este pedido ya tiene "
                            "un registro previo "
                            "de pago directo."
                        ),
                },
                status=409,
            )

        # -------------------------------------------------------------
        # EXCLUSIÓN MUTUA CON MERCADO PAGO
        # -------------------------------------------------------------

        pago_mp_conflictivo = (
            Pago.objects
            .filter(
                pedido=
                    pedido_locked,

                proveedor=
                    Pago.Proveedor
                    .MERCADOPAGO,

                estado__in=[
                    Pago.Estado.CREADO,
                    Pago.Estado.PENDIENTE,
                    Pago.Estado.APROBADO,
                ],
            )
            .exists()
        )

        if pago_mp_conflictivo:

            return JsonResponse(
                {
                    "ok": False,
                    "error":
                        (
                            "Este pedido ya tiene "
                            "un proceso de Mercado Pago "
                            "activo o aprobado."
                        ),
                    "codigo":
                        "PAGO_MP_EXISTENTE",
                },
                status=409,
            )

        if (
            pedido_locked.estado
            !=
            "confirmado"
        ):

            return JsonResponse(
                {
                    "ok": False,
                    "error":
                        (
                            "Sólo un pedido confirmado "
                            "puede registrarse para "
                            "pago en efectivo "
                            "o contra entrega."
                        ),
                    "codigo":
                        "PEDIDO_NO_CONFIRMADO",

                    "pedido_numero":
                        pedido_locked.numero,

                    "estado":
                        pedido_locked.estado,
                },
                status=409,
            )

        total_real = Decimal(
            pedido_locked.total
        )

        total_2 = total_real.quantize(
            Decimal("0.01")
        )

        if total_real <= 0:

            return JsonResponse(
                {
                    "ok": False,
                    "error":
                        (
                            "El total del pedido "
                            "debe ser mayor que cero."
                        ),
                },
                status=409,
            )

        if total_real != total_2:

            return JsonResponse(
                {
                    "ok": False,
                    "error":
                        (
                            "El total del pedido "
                            "tiene una precisión "
                            "monetaria no compatible."
                        ),
                },
                status=409,
            )

        pago = Pago.objects.create(
            pedido=
                pedido_locked,

            proveedor=
                Pago.Proveedor
                .NEGOCIO,

            estado=
                Pago.Estado
                .PENDIENTE,

            monto=
                total_2,

            moneda=
                str(
                    pedido_locked.moneda
                ).upper(),
        )

        return JsonResponse(
            {
                "ok": True,

                "pago_directo_registrado":
                    True,

                "reutilizado":
                    False,

                "pedido_id":
                    pedido_locked.id,

                "pedido_numero":
                    pedido_locked.numero,

                "pago_id":
                    pago.id,

                "estado_pago":
                    pago.estado,

                "metodo_pago":
                    "efectivo_contra_entrega",

                "monto":
                    str(
                        pago.monto
                    ),

                "moneda":
                    pago.moneda,

                "mensaje":
                    (
                        "Pedido registrado para "
                        "pago en efectivo "
                        "o contra entrega."
                    ),
            },
            json_dumps_params={
                "ensure_ascii": False,
            },
        )


@csrf_exempt
def restaurante_pedido_mercadopago_checkout(
    request,
):

    if request.method != "POST":

        return JsonResponse(
            {
                "ok": False,
                "error":
                    "Método no permitido.",
            },
            status=405,
        )

    auth_error = (
        _restaurante_api_auth_error(
            request
        )
    )

    if auth_error is not None:
        return auth_error

    datos, body_error = (
        _restaurante_api_body_dict(
            request
        )
    )

    if body_error is not None:
        return body_error

    bot, bot_error = (
        _restaurante_api_resolver_bot(
            datos.get(
                "bot_id",
                "",
            )
        )
    )

    if bot_error is not None:
        return bot_error

    _, pedido_error = (
        _restaurante_api_resolver_pedido(
            bot=bot,
            carrito_token=
                datos.get(
                    "carrito_token",
                    "",
                ),
            solo_carrito=False,
        )
    )

    if pedido_error is not None:
        return pedido_error

    # La integración, idempotencia, precisión,
    # refresh token, Pago y fallback permanecen
    # en el Checkout existente.
    return carrito_mercadopago_checkout(
        request
    )


def restaurante_pedido_consultar(
    request,
):

    from core.services.lineas_pedido import (
        describir_detalle,
        texto_lineas,
    )

    if request.method != "GET":

        return JsonResponse(
            {
                "ok": False,
                "error":
                    "Método no permitido.",
            },
            status=405,
        )

    auth_error = (
        _restaurante_api_auth_error(
            request
        )
    )

    if auth_error is not None:
        return auth_error

    bot, bot_error = (
        _restaurante_api_resolver_bot(
            request.GET.get(
                "bot_id",
                "",
            )
        )
    )

    if bot_error is not None:
        return bot_error

    numero = str(
        request.GET.get(
            "numero",
            "",
        )
        or ""
    ).strip().upper()

    telefono = "".join(
        caracter
        for caracter
        in str(
            request.GET.get(
                "telefono",
                "",
            )
            or ""
        )
        if caracter.isdigit()
    )

    if (
        not numero
        or
        not telefono
    ):

        return JsonResponse(
            {
                "ok": False,
                "encontrado": False,
                "error":
                    "numero y telefono "
                    "son obligatorios.",
            },
            status=400,
        )

    from core.models import (
        Pedido,
    )

    pedido = (
        Pedido.objects
        .prefetch_related(
            "detalles"
        )
        .filter(
            empresa_id=
                bot.empresa_id,

            numero__iexact=
                numero,

            identificador_externo__startswith=
                (
                    "typebot:r:"
                    +
                    str(bot.id)
                    +
                    ":"
                ),
        )
        .first()
    )

    telefono_guardado = ""

    if pedido is not None:

        telefono_guardado = "".join(
            caracter
            for caracter
            in str(
                pedido.cliente_telefono
                or ""
            )
            if caracter.isdigit()
        )

    # Igual que el tracking histórico:
    # no distinguimos pedido inexistente
    # de teléfono incorrecto.
    if (
        pedido is None
        or
        not compare_digest(
            telefono,
            telefono_guardado,
        )
    ):

        return JsonResponse(
            {
                "ok": True,
                "encontrado": False,
                "cantidad_productos": 0,
                "mensaje":
                    "No encontramos un pedido "
                    "con esos datos.",
            },
            json_dumps_params={
                "ensure_ascii": False,
            },
        )

    detalles = list(
        pedido.detalles.all()
    )

    # Mismos snapshots que el resumen del cliente
    # (TNL-LINEAS-PEDIDO-V1): aqui no se recalcula nada.
    descripciones = [
        describir_detalle(
            detalle
        )
        for detalle
        in detalles
    ]

    lineas = [
        {
            "sku":
                detalle.sku,

            "nombre":
                detalle.nombre_producto,

            "cantidad":
                str(
                    detalle.cantidad
                ),

            "precio_unitario":
                str(
                    detalle.precio_unitario
                ),

            "importe":
                str(
                    detalle.importe
                ),

            "modificadores":
                detalle
                .modificadores_snapshot,

            "extras":
                detalle
                .extras_snapshot,

            "opciones":
                descripcion["grupos"],
        }
        for detalle, descripcion
        in zip(
            detalles,
            descripciones,
        )
    ]

    productos_resumen = texto_lineas(
        descripciones,
        numerar=False,
        con_importe=False,
    )

    return JsonResponse(
        {
            "ok": True,
            "encontrado": True,

            "pedido_numero":
                pedido.numero,

            "estado":
                pedido.estado,

            "tipo_orden":
                pedido.tipo_orden,

            "cliente_nombre":
                pedido.cliente_nombre,

            "moneda":
                pedido.moneda,

            "total":
                str(
                    pedido.total
                ),

            "tiempo_estimado_minutos":
                pedido
                .tiempo_estimado_minutos,

            "cantidad_productos":
                len(
                    lineas
                ),

            "lineas":
                lineas,

            "productos_resumen":
                productos_resumen,

            "mensaje":
                (
                    f"Pedido {pedido.numero}: "
                    f"{pedido.estado}."
                ),
        },
        json_dumps_params={
            "ensure_ascii": False,
        },
    )

