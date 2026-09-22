from django.contrib.auth import views as auth_views
from django.urls import path

from . import views
from . import views_api


app_name = "core"


urlpatterns = [

    # TNL-GOOGLE-BRAND-PUBLIC-URLS-V1

    path(
        "inicio/",
        views.inicio_publico,
        name="inicio_publico",
    ),

    path(
        "privacidad/",
        views.privacidad_publica,
        name="privacidad_publica",
    ),


    # TNL-TERMINOS-PUBLICOS-URL-V1
    # Página pública informativa. No registra aceptación.
    path(
        "terminos/",
        views.terminos_publicos,
        name="terminos_publicos",
    ),

    path("api/typebot/productos/buscar/", views_api.producto_buscar, name="api_producto_buscar"),
    path("api/typebot/productos/validar/", views_api.producto_validar, name="api_producto_validar"),
    path("api/typebot/pedidos/productos/agregar/", views_api.carrito_producto_agregar, name="api_typebot_carrito_producto_agregar"),
    path("api/typebot/pedidos/datos/guardar/", views_api.carrito_datos_guardar, name="api_typebot_carrito_datos_guardar"),
    path("api/typebot/pedidos/confirmar/", views_api.carrito_confirmar, name="api_typebot_carrito_confirmar"),
    path("api/typebot/pedidos/cancelar/", views_api.carrito_cancelar, name="api_typebot_carrito_cancelar"),
    path("api/typebot/pedidos/consultar/", views_api.pedido_consultar, name="api_typebot_pedido_consultar"),

    path(
        "",
        # TNL-URL-ROLE-GUARDS-V1
        views._nl_dashboard_required(
            views.dashboard
        ),
        name="dashboard",
    ),

    # CLIENTE-PORTAL-URL-V1
    path(
        "mi-negocio/",
        views.cliente_panel,
        name="cliente_panel",
    ),

    # TNL-CLIENTE-PROMOCIONES-IA-URL-V1
    path(
        "mi-negocio/promociones-ia/",
        views.cliente_promociones_ia,
        name="cliente_promociones_ia",
    ),

    # TNL-CLIENTE-TERMINOS-URL-V1
    path(
        "mi-negocio/terminos/estado/",
        views.cliente_terminos_estado,
        name="cliente_terminos_estado",
    ),

    path(
        "mi-negocio/terminos/aceptar/",
        views.cliente_terminos_aceptar,
        name="cliente_terminos_aceptar",
    ),

    # TNL-CLIENTE-GOOGLE-CALENDAR-URL-V1
    path(
        "mi-negocio/google-calendar/conectar/",
        views.cliente_google_calendar_conectar,
        name="cliente_google_calendar_conectar",
    ),


    # TNL-CLIENTE-AGENDA-URL-V1
    path(
        "mi-negocio/agenda/",
        views.cliente_agenda_configurar,
        name="cliente_agenda_configurar",
    ),

    # TNL-MERCADOPAGO-CLIENTE-OAUTH-URL-V1
    path(
        "mi-negocio/mercado-pago/conectar/",
        views.cliente_mercadopago_conectar,
        name="cliente_mercadopago_conectar",
    ),

    # Debe coincidir EXACTAMENTE con Mercado Pago Developers.
    path(
        "mercado-pago/oauth/callback/",
        views.mercadopago_oauth_callback,
        name="mercadopago_oauth_callback",
    ),

    # CLIENTE-WHATSAPP-SELF-SERVICE-URL-V2
    path(
        (
            "mi-negocio/whatsapp/"
            "<int:canal_id>/estado/"
        ),
        views.cliente_whatsapp_estado,
        name="cliente_whatsapp_estado",
    ),

    path(
        (
            "mi-negocio/whatsapp/"
            "<int:canal_id>/qr/"
        ),
        views.cliente_whatsapp_qr,
        name="cliente_whatsapp_qr",
    ),

    path(
        "login/",
        views.NegocioListoLoginView.as_view(
            template_name="core/login.html",
            redirect_authenticated_user=True,
        ),
        name="login",
    ),

    path(
        "logout/",
        auth_views.LogoutView.as_view(),
        name="logout",
    ),

    path(
        "empresas/",
        views._nl_admin_required(views.empresa_lista),
        name="empresa_lista",
    ),

    path(
        "empresas/nueva/",
        views._nl_admin_required(views.empresa_crear),
        name="empresa_crear",
    ),

    path(
        "empresas/<int:pk>/editar/",
        views._nl_admin_required(views.empresa_editar),
        name="empresa_editar",
    ),


    # TNL-AGENDA-EMPRESA-URL-V1
    path(
        "empresas/<int:pk>/agenda/",
        views._nl_admin_required(
            views.empresa_agenda_configurar
        ),
        name="empresa_agenda_configurar",
    ),

    path(
        "usuarios/",
        views._nl_admin_required(views.usuario_lista),
        name="usuario_lista",
    ),

    path(
        "usuarios/nuevo/",
        views._nl_admin_required(views.usuario_crear),
        name="usuario_crear",
    ),

    path(
        "usuarios/<int:pk>/editar/",
        views._nl_admin_required(views.usuario_editar),
        name="usuario_editar",
    ),


    path(
        "licencias/",
        views._nl_admin_required(views.licencia_lista),
        name="licencia_lista",
    ),

    path(
        "licencias/nueva/",
        views._nl_admin_required(views.licencia_crear),
        name="licencia_crear",
    ),

    path(
        "licencias/<int:pk>/editar/",
        views._nl_admin_required(views.licencia_editar),
        name="licencia_editar",
    ),


    path(
        "bots/",
        views._nl_admin_required(views.bot_lista),
        name="bot_lista",
    ),

    path(
        "bots/nuevo/",
        views._nl_admin_required(views.bot_crear),
        name="bot_crear",
    ),

    path(
        "bots/<int:pk>/editar/",
        views._nl_admin_required(views.bot_editar),
        name="bot_editar",
    ),


    path(
        "canales/",
        views._nl_admin_required(views.canal_lista),
        name="canal_lista",
    ),

    path(
        "canales/nuevo/",
        views._nl_admin_required(views.canal_crear),
        name="canal_crear",
    ),

    path(
        "canales/<int:pk>/editar/",
        views._nl_admin_required(views.canal_editar),
        name="canal_editar",
    ),


    path(
        "plantillas/",
        views._nl_admin_required(views.plantilla_lista),
        name="plantilla_lista",
    ),

    path(
        "plantillas/nueva/",
        views._nl_admin_required(views.plantilla_crear),
        name="plantilla_crear",
    ),

    path(
        "plantillas/<int:pk>/editar/",
        views._nl_admin_required(views.plantilla_editar),
        name="plantilla_editar",
    ),


    path(
        "variables/",
        views._nl_admin_required(views.variable_lista),
        name="variable_lista",
    ),

    path(
        "variables/nueva/",
        views._nl_admin_required(views.variable_crear),
        name="variable_crear",
    ),

    path(
        "variables/<int:pk>/editar/",
        views._nl_admin_required(views.variable_editar),
        name="variable_editar",
    ),


    path(
        "catalogos/",
        views._nl_admin_required(views.catalogo_lista),
        name="catalogo_lista",
    ),

    path(
        "catalogos/nuevo/",
        views._nl_admin_required(views.catalogo_crear),
        name="catalogo_crear",
    ),

    path(
        "catalogos/<int:pk>/editar/",
        views._nl_admin_required(views.catalogo_editar),
        name="catalogo_editar",
    ),


    path(
        "productos/",
        views._nl_admin_required(views.producto_lista),
        name="producto_lista",
    ),

    path(
        "productos/nuevo/",
        views._nl_admin_required(views.producto_crear),
        name="producto_crear",
    ),

    # TNL-PRODUCT-IMPORT-XLSX-V1
    path(
        "productos/importar/",
        views._nl_admin_required(views.producto_importar),
        name="producto_importar",
    ),

    path(
        "productos/importar/plantilla/",
        views._nl_admin_required(views.producto_importar_plantilla),
        name="producto_importar_plantilla",
    ),

    path(
        "productos/<int:pk>/editar/",
        views._nl_admin_required(views.producto_editar),
        name="producto_editar",
    ),

    # TNL-PRODUCT-IMAGE-DELETE-URL-V1
    path(
        "productos/imagenes/<int:imagen_id>/eliminar/",
        views._nl_admin_required(views.producto_imagen_eliminar),
        name="producto_imagen_eliminar",
    ),

    # TNL-MODIFICADORES-PANEL-V1
    path(
        "productos/<int:producto_id>/modificadores/",
        views._nl_admin_required(views.producto_modificadores),
        name="producto_modificadores",
    ),

    path(
        "productos/<int:producto_id>/modificadores/nuevo/",
        views._nl_admin_required(
            views.producto_modificador_grupo_crear
        ),
        name="producto_modificador_grupo_crear",
    ),

    path(
        (
            "productos/<int:producto_id>/"
            "modificadores/<int:grupo_id>/editar/"
        ),
        views._nl_admin_required(
            views.producto_modificador_grupo_editar
        ),
        name="producto_modificador_grupo_editar",
    ),

    path(
        (
            "productos/<int:producto_id>/"
            "modificadores/<int:grupo_id>/estado/"
        ),
        views._nl_admin_required(
            views.producto_modificador_grupo_estado
        ),
        name="producto_modificador_grupo_estado",
    ),

    path(
        (
            "productos/<int:producto_id>/"
            "modificadores/<int:grupo_id>/opciones/nueva/"
        ),
        views._nl_admin_required(
            views.producto_modificador_opcion_crear
        ),
        name="producto_modificador_opcion_crear",
    ),

    path(
        (
            "productos/<int:producto_id>/"
            "modificadores/<int:grupo_id>/"
            "opciones/<int:opcion_id>/editar/"
        ),
        views._nl_admin_required(
            views.producto_modificador_opcion_editar
        ),
        name="producto_modificador_opcion_editar",
    ),

    path(
        (
            "productos/<int:producto_id>/"
            "modificadores/<int:grupo_id>/"
            "opciones/<int:opcion_id>/estado/"
        ),
        views._nl_admin_required(
            views.producto_modificador_opcion_estado
        ),
        name="producto_modificador_opcion_estado",
    ),


    # TNL-IA-TYPEBOT-URL-V1
    path(
        "api/typebot/ia/responder/",
        views_api.typebot_ia_responder,
        name="api_typebot_ia_responder",
    ),
]


# ============================================================
# PEDIDOS
# ============================================================

urlpatterns += [

    path(
        "pedidos/",
        views._nl_pedido_required(views.pedido_lista),
        name="pedido_lista",
    ),

    path(
        "pedidos/nuevo/",
        views._nl_admin_required(views.pedido_crear),
        name="pedido_crear",
    ),

    path(
        "pedidos/<int:pk>/",
        views._nl_pedido_required(views.pedido_detalle),
        name="pedido_detalle",
    ),

    path(
        "pedidos/<int:pk>/editar/",
        views._nl_admin_required(views.pedido_editar),
        name="pedido_editar",
    ),

    path(
        "pedidos/<int:pk>/productos/agregar/",
        views._nl_admin_required(views.pedido_producto_agregar),
        name="pedido_producto_agregar",
    ),

    path(
        "pedidos/detalles/<int:detalle_id>/editar/",
        views._nl_admin_required(views.pedido_producto_editar),
        name="pedido_producto_editar",
    ),

    path(
        "pedidos/detalles/<int:detalle_id>/eliminar/",
        views._nl_admin_required(views.pedido_producto_eliminar),
        name="pedido_producto_eliminar",
    ),

    path(
        "pedidos/<int:pk>/confirmar/",
        views._nl_admin_required(views.pedido_confirmar),
        name="pedido_confirmar",
    ),
]


# ============================================================
# PEDIDOS
# ============================================================

urlpatterns += [

    path(
        "pedidos/",
        views._nl_pedido_required(views.pedido_lista),
        name="pedido_lista",
    ),

    path(
        "pedidos/nuevo/",
        views._nl_admin_required(views.pedido_crear),
        name="pedido_crear",
    ),

    path(
        "pedidos/<int:pk>/",
        views._nl_pedido_required(views.pedido_detalle),
        name="pedido_detalle",
    ),

    path(
        "pedidos/<int:pk>/editar/",
        views._nl_admin_required(views.pedido_editar),
        name="pedido_editar",
    ),

    path(
        "pedidos/<int:pk>/productos/agregar/",
        views._nl_admin_required(views.pedido_producto_agregar),
        name="pedido_producto_agregar",
    ),

    path(
        "pedidos/detalles/<int:detalle_id>/editar/",
        views._nl_admin_required(views.pedido_producto_editar),
        name="pedido_producto_editar",
    ),

    path(
        "pedidos/detalles/<int:detalle_id>/eliminar/",
        views._nl_admin_required(views.pedido_producto_eliminar),
        name="pedido_producto_eliminar",
    ),

    path(
        "pedidos/<int:pk>/confirmar/",
        views._nl_admin_required(views.pedido_confirmar),
        name="pedido_confirmar",
    ),
]


# ============================================================
# CONTROLADOR DE CLIENTES V1
# ============================================================

urlpatterns += [
    path(
        "empresas/<int:pk>/",
        views._nl_admin_required(views.empresa_detalle),
        name="empresa_detalle",
    ),
]


# ============================================================
# CONTROLADOR DE CLIENTES - APROVISIONAMIENTO V1
# ============================================================

urlpatterns += [
    path(
        "empresas/<int:pk>/aprovisionar/",
        views._nl_admin_required(views.empresa_aprovisionar),
        name="empresa_aprovisionar",
    ),
]


# ============================================================
# BIBLIOTECA DE PLANTILLAS MAESTRAS V1
# ============================================================

from . import views_plantillas_maestras as views_pm

urlpatterns += [

    path(
        "plantillas-maestras/",
        views._nl_admin_required(views_pm.plantilla_maestra_lista),
        name="plantilla_maestra_lista",
    ),

    path(
        "plantillas-maestras/nueva/",
        views._nl_admin_required(views_pm.plantilla_maestra_crear),
        name="plantilla_maestra_crear",
    ),

    path(
        "plantillas-maestras/<int:pk>/",
        views._nl_admin_required(views_pm.plantilla_maestra_detalle),
        name="plantilla_maestra_detalle",
    ),

    path(
        "plantillas-maestras/<int:pk>/editar/",
        views._nl_admin_required(views_pm.plantilla_maestra_editar),
        name="plantilla_maestra_editar",
    ),

    path(
        "plantillas-maestras/<int:pk>/publicar/",
        views._nl_admin_required(views_pm.plantilla_maestra_publicar),
        name="plantilla_maestra_publicar",
    ),

    path(
        "plantillas-maestras/<int:pk>/retirar/",
        views._nl_admin_required(views_pm.plantilla_maestra_retirar),
        name="plantilla_maestra_retirar",
    ),

    path(
        "plantillas-maestras/<int:pk>/nueva-version/",
        views._nl_admin_required(views_pm.plantilla_maestra_nueva_version),
        name="plantilla_maestra_nueva_version",
    ),

    path(
        "plantillas-maestras/<int:plantilla_pk>/variables/nueva/",
        views._nl_admin_required(views_pm.plantilla_variable_maestra_crear),
        name="plantilla_variable_maestra_crear",
    ),

    path(
        "variables-maestras/<int:pk>/editar/",
        views._nl_admin_required(views_pm.plantilla_variable_maestra_editar),
        name="plantilla_variable_maestra_editar",
    ),

    path(
        "variables-maestras/<int:pk>/eliminar/",
        views._nl_admin_required(views_pm.plantilla_variable_maestra_eliminar),
        name="plantilla_variable_maestra_eliminar",
    ),
]


# ============================================================
# CLIENTE-LICENCIA-INTEGRADA-URL-V1
# ============================================================

urlpatterns += [
    path(
        "empresas/<int:pk>/licencias/nueva/",
        views._nl_admin_required(views.empresa_licencia_crear),
        name="empresa_licencia_crear",
    ),
]


# ============================================================
# NEGOCIOLISTO-WHATSAPP-URL-V1
# ============================================================

urlpatterns += [

    path(
        (
            "empresas/<int:pk>/"
            "canales/<int:canal_id>/"
            "whatsapp/conectar/"
        ),
        views._nl_admin_required(views.empresa_whatsapp_conectar),
        name="empresa_whatsapp_conectar",
    ),

    path(
        (
            "empresas/<int:pk>/"
            "canales/<int:canal_id>/"
            "whatsapp/estado/"
        ),
        views._nl_admin_required(views.empresa_whatsapp_estado),
        name="empresa_whatsapp_estado",
    ),

    path(
        (
            "empresas/<int:pk>/"
            "canales/<int:canal_id>/"
            "whatsapp/activar/"
        ),
        views._nl_admin_required(views.empresa_whatsapp_activar),
        name="empresa_whatsapp_activar",
    ),

    # TNL-WHATSAPP-MANUAL-RECONNECT-V1
    path(
        (
            "empresas/<int:pk>/"
            "canales/<int:canal_id>/"
            "whatsapp/reconectar/"
        ),
        views._nl_admin_required(views.empresa_whatsapp_reconectar),
        name="empresa_whatsapp_reconectar",
    ),

]


# ============================================================================
# TNL-MERCADOPAGO-CONFIG-URL-V1
# Exclusivo Administración.
# ============================================================================

urlpatterns += [

    path(
        (
            "empresas/<int:pk>/"
            "pagos/mercado-pago/"
        ),
        views._nl_admin_required(
            views.empresa_mercadopago_configurar
        ),
        name=
            "empresa_mercadopago_configurar",
    ),

]




# =============================================================================
# TNL-IA-ACTIVAR-BOLSA-URL-V1
# Exclusivo Administración.
# =============================================================================

urlpatterns += [

    path(
        (
            "empresas/<int:pk>/"
            "ia/bolsas/activar/"
        ),
        views._nl_admin_required(
            views.empresa_ia_activar_bolsa
        ),
        name=
            "empresa_ia_activar_bolsa",
    ),

    # TNL-IA-BOLSA-EDITAR-URL-V1
    path(
        (
            "empresas/<int:pk>/"
            "ia/bolsas/actualizar/"
        ),
        views._nl_admin_required(
            views.empresa_ia_actualizar_bolsa
        ),
        name=
            "empresa_ia_actualizar_bolsa",
    ),

]


# =============================================================================
# TNL-GOOGLE-CALENDAR-OAUTH-URL-V1
# =============================================================================

urlpatterns += [

    path(
        (
            "empresas/<int:pk>/"
            "google-calendar/conectar/"
        ),
        views._nl_admin_required(
            views.empresa_google_calendar_conectar
        ),
        name=
            "empresa_google_calendar_conectar",
    ),

    # Debe coincidir EXACTAMENTE con Google Cloud.
    # Intencionalmente no lleva "/" final.
    path(
        "google-calendar/oauth/callback",
        views.google_calendar_oauth_callback,
        name=
            "google_calendar_oauth_callback",
    ),

]


# =============================================================================
# TNL-TYPEBOT-CITAS-URL-V1
# =============================================================================

urlpatterns += [

    # TNL-TYPEBOT-CITAS-ESTADO-URL-V1
    path(
        "api/typebot/citas/estado/",
        views_api.cita_estado,
        name="api_typebot_cita_estado",
    ),

    path(
        "api/typebot/citas/disponibilidad/",
        views_api.cita_disponibilidad,
        name=
            "api_typebot_cita_disponibilidad",
    ),

    path(
        "api/typebot/citas/crear/",
        views_api.cita_crear,
        name=
            "api_typebot_cita_crear",
    ),

    path(
        "api/typebot/citas/consultar/",
        views_api.cita_consultar,
        name=
            "api_typebot_cita_consultar",
    ),

    path(
        "api/typebot/citas/cancelar/",
        views_api.cita_cancelar,
        name=
            "api_typebot_cita_cancelar",
    ),

]


# =============================================================================
# TNL-MERCADOPAGO-WEBHOOK-URL-V1
# Endpoint público firmado. No requiere sesión Django.
# =============================================================================

urlpatterns += [

    path(
        "mercado-pago/webhook/",
        views_api.mercadopago_webhook,
        name="mercadopago_webhook",
    ),

]


# =============================================================================
# TNL-MERCADOPAGO-TYPEBOT-CHECKOUT-URL-V1
# =============================================================================

urlpatterns += [

    path(
        (
            "api/typebot/pedidos/"
            "mercado-pago/checkout/"
        ),
        views_api.carrito_mercadopago_checkout,
        name=
            "api_typebot_mercadopago_checkout",
    ),

]



# =============================================================================
# TNL-CITA-MERCADOPAGO-CHECKOUT-URL-V1
# =============================================================================

urlpatterns += [

    path(
        (
            "api/typebot/citas/"
            "mercado-pago/checkout/"
        ),
        views_api.cita_mercadopago_checkout,
        name=
            "api_typebot_cita_mercadopago_checkout",
    ),

]


# =============================================================================
# TNL-TYPEBOT-CITAS-SLOTS-URL-V1
# =============================================================================

urlpatterns += [

    path(
        "api/typebot/citas/horarios-disponibles/",
        views_api.cita_horarios_disponibles,
        name=
            "api_typebot_cita_horarios_disponibles",
    ),

]



# =============================================================================
# TNL-CLIENT-LIFECYCLE-URL-V1
# =============================================================================

urlpatterns += [

    path(
        (
            "empresas/<int:pk>/"
            "desactivar/"
        ),
        views._nl_admin_required(
            views.empresa_desactivar_cliente
        ),
        name=
            "empresa_desactivar_cliente",
    ),

    path(
        (
            "empresas/<int:pk>/"
            "reactivar/"
        ),
        views._nl_admin_required(
            views.empresa_reactivar_cliente
        ),
        name=
            "empresa_reactivar_cliente",
    ),

]



# =============================================================================
# TNL-CLIENT-CONNECTION-RESET-URL-V1
# =============================================================================

urlpatterns += [

    path(
        (
            "empresas/<int:pk>/"
            "conexiones/restablecer/"
        ),
        views._nl_admin_required(
            views.empresa_restablecer_conexiones
        ),
        name=
            "empresa_restablecer_conexiones",
    ),

]



# =============================================================================
# TNL-CLIENT-DELETION-URL-V1
# =============================================================================

urlpatterns += [

    path(
        (
            "empresas/<int:pk>/"
            "eliminar-definitivamente/"
        ),
        views._nl_admin_required(
            views.empresa_eliminar_definitivamente
        ),
        name=
            "empresa_eliminar_definitivamente",
    ),

]


# ============================================================
# TNL-PEDIDO-STATUS-RAPIDO-V1
# ============================================================

urlpatterns += [

    path(
        (
            "pedidos/<int:pk>/"
            "estado/<str:nuevo_estado>/"
        ),
        views._nl_pedido_required(
            views.pedido_estado_rapido
        ),
        name=
            "pedido_estado_rapido",
    ),



    path(
        (
            "pedidos/<int:pk>/"
            "pago/marcar-pagado/"
        ),
        views._nl_pedido_required(
            views.pedido_pago_marcar_pagado
        ),
        name=
            "pedido_pago_marcar_pagado",
    ),

]


# =============================================================================
# TNL-CLIENTE-PEDIDOS-PORTAL-V2
# =============================================================================

urlpatterns += [

    path(
        "mi-negocio/pedidos/",
        views._nl_pedido_required(
            views.pedido_lista
        ),
        name=
            "cliente_pedido_lista",
    ),

    path(
        "mi-negocio/pedidos/<int:pk>/",
        views._nl_pedido_required(
            views.pedido_detalle
        ),
        name=
            "cliente_pedido_detalle",
    ),

    path(
        (
            "mi-negocio/pedidos/<int:pk>/"
            "estado/<str:nuevo_estado>/"
        ),
        views._nl_pedido_required(
            views.pedido_estado_rapido
        ),
        name=
            "cliente_pedido_estado_rapido",
    ),



    path(
        (
            "mi-negocio/pedidos/<int:pk>/"
            "pago/marcar-pagado/"
        ),
        views._nl_pedido_required(
            views.pedido_pago_marcar_pagado
        ),
        name=
            "cliente_pedido_pago_marcar_pagado",
    ),

]


# =============================================================================
# TNL-RESTAURANTE-API-MENU-URLS-V1
# =============================================================================

urlpatterns += [

    path(
        "api/typebot/restaurante/categorias/",
        views_api.restaurante_categorias,
        name=
            "api_typebot_restaurante_categorias",
    ),

    path(
        "api/typebot/restaurante/productos/",
        views_api.restaurante_productos,
        name=
            "api_typebot_restaurante_productos",
    ),

    path(
        "api/typebot/restaurante/producto/",
        views_api.restaurante_producto_detalle,
        name=
            "api_typebot_restaurante_producto_detalle",
    ),
]


# =============================================================================
# TNL-RESTAURANTE-TYPEBOT-CONFIGURADOR-R5-V1
# =============================================================================

urlpatterns += [

    path(
        (
            "api/typebot/restaurante/"
            "producto/configurador/"
        ),
        views_api
        .restaurante_producto_configurador,
        name=(
            "api_typebot_restaurante_"
            "producto_configurador"
        ),
    ),

]


# =============================================================================
# TNL-RESTAURANTE-API-PEDIDO-URLS-V1
# =============================================================================

urlpatterns += [

    path(
        (
            "api/typebot/restaurante/"
            "pedido/producto/agregar/"
        ),
        views_api
        .restaurante_pedido_producto_agregar,
        name=(
            "api_typebot_restaurante_"
            "pedido_producto_agregar"
        ),
    ),

    path(
        (
            "api/typebot/restaurante/"
            "pedido/datos/"
        ),
        views_api
        .restaurante_pedido_datos,
        name=(
            "api_typebot_restaurante_"
            "pedido_datos"
        ),
    ),

    path(
        (
            "api/typebot/restaurante/"
            "pedido/logistica/"
        ),
        views_api
        .restaurante_pedido_logistica,
        name=(
            "api_typebot_restaurante_"
            "pedido_logistica"
        ),
    ),

    path(
        (
            "api/typebot/restaurante/"
            "pedido/resumen/"
        ),
        views_api
        .restaurante_pedido_resumen,
        name=(
            "api_typebot_restaurante_"
            "pedido_resumen"
        ),
    ),

    path(
        (
            "api/typebot/restaurante/"
            "pedido/confirmar/"
        ),
        views_api
        .restaurante_pedido_confirmar,
        name=(
            "api_typebot_restaurante_"
            "pedido_confirmar"
        ),
    ),
]


# =============================================================================
# TNL-RESTAURANTE-API-CIERRE-URLS-V1
# =============================================================================

urlpatterns += [

    path(
        (
            "api/typebot/restaurante/"
            "pedido/cancelar/"
        ),
        views_api
        .restaurante_pedido_cancelar,
        name=(
            "api_typebot_restaurante_"
            "pedido_cancelar"
        ),
    ),

    path(
        (
            "api/typebot/restaurante/"
            "pedido/consultar/"
        ),
        views_api
        .restaurante_pedido_consultar,
        name=(
            "api_typebot_restaurante_"
            "pedido_consultar"
        ),
    ),

    path(
        (
            "api/typebot/restaurante/"
            "pedido/pago-directo/"
        ),
        views_api
        .restaurante_pedido_pago_directo,
        name=(
            "api_typebot_restaurante_"
            "pedido_pago_directo"
        ),
    ),

    path(
        (
            "api/typebot/restaurante/"
            "pedido/mercado-pago/checkout/"
        ),
        views_api
        .restaurante_pedido_mercadopago_checkout,
        name=(
            "api_typebot_restaurante_"
            "pedido_mercadopago_checkout"
        ),
    ),
]



# ============================================================
# TNL-COCINA-TABLERO-V1
# ============================================================

urlpatterns += [

    path(
        "cocina/",
        views._nl_pedido_required(
            views.cocina_tablero
        ),
        name=
            "cocina_tablero",
    ),

    path(
        "mi-negocio/cocina/",
        views._nl_pedido_required(
            views.cocina_tablero
        ),
        name=
            "cliente_cocina_tablero",
    ),

]
