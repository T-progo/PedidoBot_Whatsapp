from django.urls import reverse
from django.http import JsonResponse
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.db import transaction

from .forms import EmpresaForm, UsuarioCrearForm, UsuarioEditarForm, LicenciaForm, BotForm, CanalForm, PlantillaForm
from .models import (
    Bot,
    Canal,
    Empresa,
    Licencia,
    PerfilUsuario,
    Plantilla,
)


@login_required
def dashboard(request):

    # CLIENTE-DASHBOARD-REDIRECT-V1
    perfil = getattr(
        request.user,
        "perfil_negociolisto",
        None,
    )

    if (
        perfil
        and perfil.activo
        and perfil.rol
            == PerfilUsuario.Rol.CLIENTE
    ):
        return redirect(
            "core:cliente_panel"
        )

    context = {
        "total_empresas": Empresa.objects.count(),
        "total_usuarios": PerfilUsuario.objects.count(),
        "total_licencias": Licencia.objects.count(),
        "total_bots": Bot.objects.count(),
        "total_canales": Canal.objects.count(),
    }

    return render(
        request,
        "core/dashboard.html",
        context,
    )


@login_required
def empresa_lista(request):

    empresas = Empresa.objects.all()

    context = {
        "empresas": empresas,
    }

    return render(
        request,
        "core/empresa_lista.html",
        context,
    )


@login_required
def empresa_crear(request):

    if request.method == "POST":
        form = EmpresaForm(request.POST)

        if form.is_valid():
            form.save()

            return redirect(
                "core:empresa_lista"
            )

    else:
        form = EmpresaForm()

    context = {
        "form": form,
        "titulo": "Nueva empresa",
        "boton": "Guardar empresa",
    }

    return render(
        request,
        "core/empresa_form.html",
        context,
    )


@login_required
def empresa_editar(request, pk):

    empresa = get_object_or_404(
        Empresa,
        pk=pk,
    )

    if request.method == "POST":

        form = EmpresaForm(
            request.POST,
            instance=empresa,
        )

        if form.is_valid():
            form.save()

            return redirect(
                "core:empresa_lista"
            )

    else:

        form = EmpresaForm(
            instance=empresa,
        )

    context = {
        "form": form,
        "empresa": empresa,
        "titulo": "Editar empresa",
        "boton": "Guardar cambios",
    }

    return render(
        request,
        "core/empresa_form.html",
        context,
    )



# =========================================================
# USUARIOS
# =========================================================

@login_required
def usuario_lista(request):

    perfiles = (
        PerfilUsuario.objects
        .select_related("usuario", "empresa")
        .order_by("usuario__username")
    )

    return render(
        request,
        "core/usuario_lista.html",
        {
            "perfiles": perfiles,
        },
    )


@login_required
@transaction.atomic
def usuario_crear(request):

    if request.method == "POST":

        form = UsuarioCrearForm(request.POST)

        if form.is_valid():

            activo = form.cleaned_data["activo"]

            usuario = get_user_model().objects.create_user(
                username=form.cleaned_data["username"],
                email=form.cleaned_data["email"],
                password=form.cleaned_data["password1"],
                first_name=form.cleaned_data["first_name"],
                last_name=form.cleaned_data["last_name"],
                is_active=activo,
            )

            PerfilUsuario.objects.create(
                usuario=usuario,
                empresa=form.cleaned_data["empresa"],
                rol=form.cleaned_data["rol"],
                activo=activo,
            )

            return redirect("core:usuario_lista")

    else:

        form = UsuarioCrearForm()

    return render(
        request,
        "core/usuario_form.html",
        {
            "form": form,
            "titulo": "Nuevo usuario",
            "boton": "Guardar usuario",
            "modo": "crear",
        },
    )


@login_required
@transaction.atomic
def usuario_editar(request, pk):

    perfil = get_object_or_404(
        PerfilUsuario.objects.select_related(
            "usuario",
            "empresa",
        ),
        pk=pk,
    )

    usuario = perfil.usuario

    if request.method == "POST":

        # TNL-USER-EDIT-PROFILE-V1
        form = UsuarioEditarForm(
            request.POST,
            perfil=perfil,
        )

        if form.is_valid():

            usuario.first_name = form.cleaned_data["first_name"]
            usuario.last_name = form.cleaned_data["last_name"]
            usuario.email = form.cleaned_data["email"]
            usuario.is_active = form.cleaned_data["activo"]

            nueva_password = form.cleaned_data.get("password1")

            if nueva_password:
                usuario.set_password(nueva_password)

            usuario.save()

            perfil.empresa = form.cleaned_data["empresa"]
            perfil.rol = form.cleaned_data["rol"]
            perfil.activo = form.cleaned_data["activo"]
            perfil.save()

            return redirect("core:usuario_lista")

    else:

        form = UsuarioEditarForm(
            perfil=perfil,
            initial={
                "first_name": usuario.first_name,
                "last_name": usuario.last_name,
                "email": usuario.email,
                "empresa": perfil.empresa,
                "rol": perfil.rol,
                "activo": perfil.activo,
            }
        )

    return render(
        request,
        "core/usuario_form.html",
        {
            "form": form,
            "perfil": perfil,
            "usuario_obj": usuario,
            "titulo": "Editar usuario",
            "boton": "Guardar cambios",
            "modo": "editar",
        },
    )


# ============================================================
# LICENCIAS
# ============================================================

@login_required
def licencia_lista(request):

    licencias = (
        Licencia.objects
        .select_related("empresa")
        .all()
        .order_by("empresa__nombre", "nombre")
    )

    return render(
        request,
        "core/licencia_lista.html",
        {
            "licencias": licencias,
        },
    )


@login_required
def licencia_crear(request):

    if request.method == "POST":
        form = LicenciaForm(request.POST)

        if form.is_valid():
            form.save()
            return redirect("core:licencia_lista")

    else:
        form = LicenciaForm()

    return render(
        request,
        "core/licencia_form.html",
        {
            "form": form,
            "titulo": "Nueva licencia",
            "boton": "Guardar licencia",
            "modo": "crear",
        },
    )


@login_required
def licencia_editar(request, pk):

    licencia = get_object_or_404(
        Licencia.objects.select_related("empresa"),
        pk=pk,
    )

    if request.method == "POST":

        form = LicenciaForm(
            request.POST,
            instance=licencia,
        )

        if form.is_valid():
            form.save()
            return redirect("core:licencia_lista")

    else:

        form = LicenciaForm(
            instance=licencia,
        )

    return render(
        request,
        "core/licencia_form.html",
        {
            "form": form,
            "licencia": licencia,
            "titulo": "Editar licencia",
            "boton": "Guardar cambios",
            "modo": "editar",
        },
    )


# ============================================================
# BOTS
# ============================================================

@login_required
def bot_lista(request):

    bots = (
        Bot.objects
        .select_related("empresa")
        .all()
        .order_by("empresa__nombre", "nombre")
    )

    return render(
        request,
        "core/bot_lista.html",
        {
            "bots": bots,
        },
    )


@login_required
def bot_crear(request):

    if request.method == "POST":
        form = BotForm(request.POST)

        if form.is_valid():
            form.save()
            return redirect("core:bot_lista")

    else:
        form = BotForm()

    return render(
        request,
        "core/bot_form.html",
        {
            "form": form,
            "titulo": "Nuevo bot",
            "boton": "Guardar bot",
            "modo": "crear",
        },
    )


@login_required
def bot_editar(request, pk):

    bot = get_object_or_404(
        Bot.objects.select_related("empresa"),
        pk=pk,
    )

    if request.method == "POST":

        form = BotForm(
            request.POST,
            instance=bot,
        )

        if form.is_valid():
            form.save()
            return redirect("core:bot_lista")

    else:

        form = BotForm(
            instance=bot,
        )

    return render(
        request,
        "core/bot_form.html",
        {
            "form": form,
            "bot": bot,
            "titulo": "Editar bot",
            "boton": "Guardar cambios",
            "modo": "editar",
        },
    )


# ============================================================
# CANALES
# ============================================================

@login_required
def canal_lista(request):

    canales = (
        Canal.objects
        .select_related("bot", "bot__empresa")
        .all()
        .order_by(
            "bot__empresa__nombre",
            "bot__nombre",
            "tipo",
            "nombre",
        )
    )

    return render(
        request,
        "core/canal_lista.html",
        {
            "canales": canales,
        },
    )


@login_required
def canal_crear(request):

    if request.method == "POST":
        form = CanalForm(request.POST)

        if form.is_valid():
            form.save()
            return redirect("core:canal_lista")

    else:
        form = CanalForm()

    return render(
        request,
        "core/canal_form.html",
        {
            "form": form,
            "titulo": "Nuevo canal",
            "boton": "Guardar canal",
            "modo": "crear",
        },
    )


@login_required
def canal_editar(request, pk):

    canal = get_object_or_404(
        Canal.objects.select_related(
            "bot",
            "bot__empresa",
        ),
        pk=pk,
    )

    if request.method == "POST":

        form = CanalForm(
            request.POST,
            instance=canal,
        )

        if form.is_valid():
            form.save()
            return redirect("core:canal_lista")

    else:

        form = CanalForm(
            instance=canal,
        )

    return render(
        request,
        "core/canal_form.html",
        {
            "form": form,
            "canal": canal,
            "titulo": "Editar canal",
            "boton": "Guardar cambios",
            "modo": "editar",
        },
    )


# ============================================================
# PLANTILLAS
# ============================================================

@login_required
def plantilla_lista(request):

    plantillas = (
        Plantilla.objects
        .select_related("empresa")
        .all()
        .order_by(
            "empresa__nombre",
            "nombre",
        )
    )

    return render(
        request,
        "core/plantilla_lista.html",
        {
            "plantillas": plantillas,
        },
    )


@login_required
def plantilla_crear(request):

    if request.method == "POST":

        form = PlantillaForm(request.POST)

        if form.is_valid():
            form.save()

            return redirect(
                "core:plantilla_lista"
            )

    else:

        form = PlantillaForm()

    return render(
        request,
        "core/plantilla_form.html",
        {
            "form": form,
            "titulo": "Nueva plantilla",
            "boton": "Guardar plantilla",
            "modo": "crear",
        },
    )


@login_required
def plantilla_editar(request, pk):

    plantilla = get_object_or_404(
        Plantilla.objects.select_related(
            "empresa",
        ),
        pk=pk,
    )

    if request.method == "POST":

        form = PlantillaForm(
            request.POST,
            instance=plantilla,
        )

        if form.is_valid():
            form.save()

            return redirect(
                "core:plantilla_lista"
            )

    else:

        form = PlantillaForm(
            instance=plantilla,
        )

    return render(
        request,
        "core/plantilla_form.html",
        {
            "form": form,
            "plantilla": plantilla,
            "titulo": "Editar plantilla",
            "boton": "Guardar cambios",
            "modo": "editar",
        },
    )


# ============================================================
# VARIABLES
# ============================================================

from .forms import VariableForm
from .models import Variable


@login_required
def variable_lista(request):

    variables = (
        Variable.objects
        .select_related(
            "plantilla",
            "plantilla__empresa",
        )
        .all()
        .order_by(
            "plantilla__empresa__nombre",
            "plantilla__nombre",
            "clave",
        )
    )

    return render(
        request,
        "core/variable_lista.html",
        {
            "variables": variables,
        },
    )


@login_required
def variable_crear(request):

    if request.method == "POST":

        form = VariableForm(request.POST)

        if form.is_valid():

            form.save()

            return redirect(
                "core:variable_lista"
            )

    else:

        form = VariableForm()

    return render(
        request,
        "core/variable_form.html",
        {
            "form": form,
            "titulo": "Nueva variable",
            "boton": "Guardar variable",
            "modo": "crear",
        },
    )


@login_required
def variable_editar(request, pk):

    variable = get_object_or_404(
        Variable.objects.select_related(
            "plantilla",
            "plantilla__empresa",
        ),
        pk=pk,
    )

    if request.method == "POST":

        form = VariableForm(
            request.POST,
            instance=variable,
        )

        if form.is_valid():

            form.save()

            return redirect(
                "core:variable_lista"
            )

    else:

        form = VariableForm(
            instance=variable,
        )

    return render(
        request,
        "core/variable_form.html",
        {
            "form": form,
            "variable": variable,
            "titulo": "Editar variable",
            "boton": "Guardar cambios",
            "modo": "editar",
        },
    )


# ============================================================
# CATALOGOS
# ============================================================

from .forms import CatalogoForm
from .models import Catalogo


@login_required
def catalogo_lista(request):

    catalogos = (
        Catalogo.objects
        .select_related("empresa")
        .all()
        .order_by(
            "empresa__nombre",
            "nombre",
        )
    )

    return render(
        request,
        "core/catalogo_lista.html",
        {
            "catalogos": catalogos,
        },
    )


@login_required
def catalogo_crear(request):

    if request.method == "POST":

        form = CatalogoForm(
            request.POST
        )

        if form.is_valid():

            form.save()

            return redirect(
                "core:catalogo_lista"
            )

    else:

        form = CatalogoForm()

    return render(
        request,
        "core/catalogo_form.html",
        {
            "form": form,
            "titulo": "Nuevo catálogo",
            "boton": "Guardar catálogo",
            "modo": "crear",
        },
    )


@login_required
def catalogo_editar(request, pk):

    catalogo = get_object_or_404(
        Catalogo.objects.select_related(
            "empresa"
        ),
        pk=pk,
    )

    if request.method == "POST":

        form = CatalogoForm(
            request.POST,
            instance=catalogo,
        )

        if form.is_valid():

            form.save()

            return redirect(
                "core:catalogo_lista"
            )

    else:

        form = CatalogoForm(
            instance=catalogo
        )

    return render(
        request,
        "core/catalogo_form.html",
        {
            "form": form,
            "catalogo": catalogo,
            "titulo": "Editar catálogo",
            "boton": "Guardar cambios",
            "modo": "editar",
        },
    )


# ============================================================
# PRODUCTOS
# ============================================================

from .forms import ProductoForm

# TNL-PRODUCT-IMAGES-VIEWS-V1
from django.contrib import messages
from django.core.files.storage import default_storage
from django.db.models import Max
from django.views.decorators.http import require_POST
from .models import ProductoImagen
from .models import Producto

# TNL-PRODUCT-IMPORT-XLSX-V1
from django.http import HttpResponse
from django.core import signing

from .product_import import (
    ProductoImportError,
    ProductoImportarExcelForm,
    catalogos_autorizados_producto,
    eliminar_importacion_temporal,
    firmar_importacion,
    generar_plantilla_productos_xlsx,
    guardar_importacion_temporal,
    importar_productos_validados,
    leer_importacion_firmada,
    resolver_importacion_temporal,
    validar_archivo_productos,
)


@login_required
def producto_lista(request):

    # ============================================================
    # TNL-PRODUCTOS-ADMIN-FILTRO-CLIENTE-V1
    #
    # Sólo afecta el listado administrativo.
    #
    # Producto -> Catalogo -> Empresa
    # ============================================================

    empresa_param = str(
        request.GET.get(
            "empresa"
        )
        or ""
    ).strip()

    empresa_seleccionada = None

    if empresa_param:

        try:
            empresa_id = int(
                empresa_param
            )

        except (
            TypeError,
            ValueError,
        ):
            empresa_id = 0

        if empresa_id > 0:
            empresa_seleccionada = (
                empresa_id
            )

    clientes = (
        Producto.objects
        .values(
            "catalogo__empresa_id",
            "catalogo__empresa__nombre",
        )
        .distinct()
        .order_by(
            "catalogo__empresa__nombre",
            "catalogo__empresa_id",
        )
    )

    productos = (
        Producto.objects
        .select_related(
            "catalogo",
            "catalogo__empresa",
        )
        .all()
    )

    if empresa_seleccionada is not None:

        productos = (
            productos.filter(
                catalogo__empresa_id=
                    empresa_seleccionada
            )
        )

    productos = (
        productos.order_by(
            "catalogo__empresa__nombre",
            "catalogo__nombre",
            "nombre",
        )
    )

    return render(
        request,
        "core/producto_lista.html",
        {
            "productos":
                productos,

            "clientes":
                clientes,

            "empresa_seleccionada":
                empresa_seleccionada,
        },
    )


# ============================================================
# TNL-PRODUCT-IMPORT-XLSX-V1
# ============================================================

@login_required
def producto_importar(request):

    catalogos = (
        catalogos_autorizados_producto(
            request.user
        )
    )

    form = ProductoImportarExcelForm(
        catalogos=catalogos
    )

    context = {
        "form": form,
        "importacion_lista": False,
        "errores_globales": [],
        "errores_filas": [],
    }

    if request.method != "POST":

        return render(
            request,
            "core/producto_importar.html",
            context,
        )

    accion = request.POST.get(
        "accion",
        "",
    )

    if accion == "validar":

        form = ProductoImportarExcelForm(
            request.POST,
            request.FILES,
            catalogos=catalogos,
        )

        context["form"] = form

        if not form.is_valid():

            return render(
                request,
                "core/producto_importar.html",
                context,
            )

        catalogo = (
            form.cleaned_data["catalogo"]
        )

        archivo = (
            form.cleaned_data["archivo"]
        )

        resultado = (
            validar_archivo_productos(
                archivo,
                catalogo=catalogo,
            )
        )

        context[
            "errores_globales"
        ] = resultado[
            "errores_globales"
        ]

        context[
            "errores_filas"
        ] = resultado[
            "errores_filas"
        ]

        if not resultado["ok"]:

            return render(
                request,
                "core/producto_importar.html",
                context,
            )

        temporal = (
            guardar_importacion_temporal(
                archivo
            )
        )

        filas = resultado["filas"]

        token = firmar_importacion(
            catalogo_id=catalogo.pk,
            import_id=temporal["import_id"],
            file_hash=temporal["sha256"],
            row_count=len(filas),
        )

        context.update(
            {
                "importacion_lista": True,
                "catalogo": catalogo,
                "token": token,
                "total_productos": len(filas),
                "preview_filas": filas[:100],
                "preview_restantes": max(
                    len(filas) - 100,
                    0,
                ),
            }
        )

        return render(
            request,
            "core/producto_importar.html",
            context,
        )

    if accion == "importar":

        token = request.POST.get(
            "token",
            "",
        )

        try:

            payload = (
                leer_importacion_firmada(
                    token
                )
            )

        except (
            signing.BadSignature,
            signing.SignatureExpired,
        ):

            messages.error(
                request,
                "La validación caducó "
                "o no es válida.",
            )

            return redirect(
                "core:producto_importar"
            )

        catalogo = get_object_or_404(
            catalogos,
            pk=payload.get(
                "catalogo_id"
            ),
        )

        import_id = payload.get(
            "import_id"
        )

        try:

            (
                normalized_id,
                path,
                expected_rows,
            ) = resolver_importacion_temporal(
                payload
            )

            resultado = (
                validar_archivo_productos(
                    path,
                    catalogo=catalogo,
                )
            )

            if not resultado["ok"]:

                raise ProductoImportError(
                    "El Excel ya no puede "
                    "importarse. Vuelve "
                    "a validarlo."
                )

            filas = resultado["filas"]

            if (
                len(filas)
                != expected_rows
            ):

                raise ProductoImportError(
                    "El número de filas cambió."
                )

            creados = (
                importar_productos_validados(
                    catalogo=catalogo,
                    rows=filas,
                )
            )

        except ProductoImportError as exc:

            if import_id:

                eliminar_importacion_temporal(
                    import_id
                )

            messages.error(
                request,
                str(exc),
            )

            return redirect(
                "core:producto_importar"
            )

        eliminar_importacion_temporal(
            normalized_id
        )

        messages.success(
            request,
            "Importación completada: "
            f"{creados} productos creados "
            f"en {catalogo.nombre}.",
        )

        return redirect(
            "core:producto_lista"
        )

    messages.error(
        request,
        "Acción inválida.",
    )

    return redirect(
        "core:producto_importar"
    )


@login_required
def producto_importar_plantilla(
    request
):

    catalogos = (
        catalogos_autorizados_producto(
            request.user
        )
    )

    if not catalogos.exists():

        return HttpResponse(
            "No tienes catálogos "
            "disponibles.",
            status=403,
            content_type=(
                "text/plain; charset=utf-8"
            ),
        )

    response = HttpResponse(
        generar_plantilla_productos_xlsx(),
        content_type=(
            "application/vnd.openxmlformats-"
            "officedocument.spreadsheetml.sheet"
        ),
    )

    response[
        "Content-Disposition"
    ] = (
        'attachment; filename="'
        'NegocioListo_Plantilla_Productos.xlsx"'
    )

    response[
        "Cache-Control"
    ] = "no-store"

    return response


@login_required
def producto_crear(request):

    if request.method == "POST":

        form = ProductoForm(
            request.POST,
            request.FILES,
        )

        if form.is_valid():

            principal = (
                form.cleaned_data.get(
                    "imagen_principal"
                )
            )

            producto = form.save(
                commit=False
            )

            # Para productos nuevos guardamos
            # primero el registro y después
            # la imagen principal. Así el
            # upload_to ya conoce producto.pk.
            if principal:

                producto.imagen_principal = None
                producto.save()

                producto.imagen_principal = (
                    principal
                )

                producto.save(
                    update_fields=[
                        "imagen_principal",
                        "actualizado_en",
                    ]
                )

            else:

                producto.save()

            form.save_m2m()

            imagenes = (
                form.cleaned_data.get(
                    "galeria_imagenes"
                )
                or []
            )

            for orden, imagen in enumerate(
                imagenes,
                start=1,
            ):

                ProductoImagen.objects.create(
                    producto=producto,
                    imagen=imagen,
                    texto_alternativo=(
                        producto.nombre
                    ),
                    orden=orden,
                )

            messages.success(
                request,
                "Producto guardado correctamente.",
            )

            return redirect(
                "core:producto_lista"
            )

    else:

        form = ProductoForm()

    return render(
        request,
        "core/producto_form.html",
        {
            "form": form,
            "titulo": "Nuevo producto",
            "boton": "Guardar producto",
            "modo": "crear",
        },
    )


@login_required
def producto_editar(request, pk):

    producto = get_object_or_404(
        Producto.objects.select_related(
            "catalogo",
            "catalogo__empresa",
        ),
        pk=pk,
    )

    old_main_name = (
        producto.imagen_principal.name
        if producto.imagen_principal
        else ""
    )

    if request.method == "POST":

        form = ProductoForm(
            request.POST,
            request.FILES,
            instance=producto,
        )

        if form.is_valid():

            producto = form.save()

            new_main_name = (
                producto.imagen_principal.name
                if producto.imagen_principal
                else ""
            )

            if (
                old_main_name
                and old_main_name
                    != new_main_name
                and default_storage.exists(
                    old_main_name
                )
            ):
                default_storage.delete(
                    old_main_name
                )

            imagenes = (
                form.cleaned_data.get(
                    "galeria_imagenes"
                )
                or []
            )

            ultimo_orden = (
                producto.galeria.aggregate(
                    max_orden=Max("orden")
                )["max_orden"]
                or 0
            )

            for offset, imagen in enumerate(
                imagenes,
                start=1,
            ):

                ProductoImagen.objects.create(
                    producto=producto,
                    imagen=imagen,
                    texto_alternativo=(
                        producto.nombre
                    ),
                    orden=(
                        ultimo_orden
                        + offset
                    ),
                )

            messages.success(
                request,
                "Producto actualizado "
                "correctamente.",
            )

            return redirect(
                "core:producto_lista"
            )

    else:

        form = ProductoForm(
            instance=producto
        )

    return render(
        request,
        "core/producto_form.html",
        {
            "form": form,
            "producto": producto,
            "titulo": "Editar producto",
            "boton": "Guardar cambios",
            "modo": "editar",
        },
    )




@login_required
@require_POST
def producto_imagen_eliminar(
    request,
    imagen_id,
):

    imagen = get_object_or_404(
        ProductoImagen.objects
        .select_related("producto"),
        pk=imagen_id,
    )

    producto = imagen.producto

    archivo = (
        imagen.imagen.name
        if imagen.imagen
        else ""
    )

    imagen.delete()

    if (
        archivo
        and default_storage.exists(
            archivo
        )
    ):
        default_storage.delete(
            archivo
        )

    messages.success(
        request,
        "Imagen eliminada de la galería.",
    )

    return redirect(
        "core:producto_editar",
        pk=producto.pk,
    )


# ============================================================
# TNL-MODIFICADORES-PANEL-V1
#
# Administración de grupos de modificadores y sus opciones.
# Usa los modelos y validaciones que ya existen: el menú, el
# carrito y la confirmación no cambian.
# ============================================================

def _nl_producto_administrable(request, producto_id):
    """
    Producto que este usuario puede administrar
    (Producto -> Catalogo -> Empresa). 404 si no es suyo.
    """

    from core.models import PerfilUsuario, Producto

    productos = (
        Producto.objects
        .select_related(
            "catalogo",
            "catalogo__empresa",
        )
    )

    perfil = getattr(
        request.user,
        "perfil_negociolisto",
        None,
    )

    if (
        perfil
        and perfil.activo
        and perfil.rol == PerfilUsuario.Rol.CLIENTE
    ):
        productos = (
            productos.filter(
                catalogo__empresa_id=perfil.empresa_id
            )
            if perfil.empresa_id
            else productos.none()
        )

    return get_object_or_404(
        productos,
        pk=producto_id,
    )


def _nl_grupo_modificador(producto, grupo_id):

    return get_object_or_404(
        producto.grupos_modificadores,
        pk=grupo_id,
    )


def _nl_volver_a_modificadores(producto):

    return redirect(
        "core:producto_modificadores",
        producto_id=producto.pk,
    )


@login_required
def producto_modificadores(request, producto_id):

    producto = _nl_producto_administrable(
        request,
        producto_id,
    )

    grupos = (
        producto.grupos_modificadores
        .prefetch_related("opciones")
        .order_by("orden", "id")
    )

    return render(
        request,
        "core/producto_modificadores.html",
        {
            "titulo": "Modificadores",
            "producto": producto,
            "grupos": grupos,
        },
    )


@login_required
def producto_modificador_grupo_crear(request, producto_id):

    from core.forms import GrupoModificadorForm
    from core.models import GrupoModificadorProducto

    producto = _nl_producto_administrable(
        request,
        producto_id,
    )

    grupo = GrupoModificadorProducto(
        producto=producto,
    )

    if request.method == "POST":

        form = GrupoModificadorForm(
            request.POST,
            instance=grupo,
        )

        if form.is_valid():

            form.save()

            messages.success(
                request,
                "Grupo de modificadores creado.",
            )

            return _nl_volver_a_modificadores(producto)

    else:
        form = GrupoModificadorForm(instance=grupo)

    return render(
        request,
        "core/producto_modificador_form.html",
        {
            "titulo": "Nuevo grupo de modificadores",
            "subtitulo": producto.nombre,
            "boton": "Crear grupo",
            "form": form,
            "producto": producto,
        },
    )


@login_required
def producto_modificador_grupo_editar(
    request,
    producto_id,
    grupo_id,
):

    from core.forms import GrupoModificadorForm

    producto = _nl_producto_administrable(
        request,
        producto_id,
    )

    grupo = _nl_grupo_modificador(producto, grupo_id)

    if request.method == "POST":

        form = GrupoModificadorForm(
            request.POST,
            instance=grupo,
        )

        if form.is_valid():

            form.save()

            messages.success(
                request,
                "Grupo de modificadores actualizado.",
            )

            return _nl_volver_a_modificadores(producto)

    else:
        form = GrupoModificadorForm(instance=grupo)

    return render(
        request,
        "core/producto_modificador_form.html",
        {
            "titulo": "Editar grupo de modificadores",
            "subtitulo": producto.nombre + " · " + grupo.nombre,
            "boton": "Guardar cambios",
            "form": form,
            "producto": producto,
        },
    )


@login_required
def producto_modificador_grupo_estado(
    request,
    producto_id,
    grupo_id,
):
    """Activa o desactiva el grupo completo."""

    from django.http import HttpResponseNotAllowed

    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    producto = _nl_producto_administrable(
        request,
        producto_id,
    )

    grupo = _nl_grupo_modificador(producto, grupo_id)

    grupo.activo = not grupo.activo

    grupo.save(
        update_fields=[
            "activo",
            "actualizado_en",
        ]
    )

    estado = "activo" if grupo.activo else "inactivo"

    messages.success(
        request,
        "El grupo «" + grupo.nombre + "» quedó " + estado + ".",
    )

    return _nl_volver_a_modificadores(producto)


@login_required
def producto_modificador_opcion_crear(
    request,
    producto_id,
    grupo_id,
):

    from core.forms import OpcionModificadorForm
    from core.models import OpcionModificadorProducto

    producto = _nl_producto_administrable(
        request,
        producto_id,
    )

    grupo = _nl_grupo_modificador(producto, grupo_id)

    opcion = OpcionModificadorProducto(
        grupo=grupo,
    )

    if request.method == "POST":

        form = OpcionModificadorForm(
            request.POST,
            instance=opcion,
        )

        if form.is_valid():

            form.save()

            messages.success(
                request,
                "Opción creada.",
            )

            return _nl_volver_a_modificadores(producto)

    else:
        form = OpcionModificadorForm(instance=opcion)

    return render(
        request,
        "core/producto_modificador_form.html",
        {
            "titulo": "Nueva opción",
            "subtitulo": producto.nombre + " · " + grupo.nombre,
            "boton": "Crear opción",
            "form": form,
            "producto": producto,
        },
    )


@login_required
def producto_modificador_opcion_editar(
    request,
    producto_id,
    grupo_id,
    opcion_id,
):

    from core.forms import OpcionModificadorForm

    producto = _nl_producto_administrable(
        request,
        producto_id,
    )

    grupo = _nl_grupo_modificador(producto, grupo_id)

    opcion = get_object_or_404(
        grupo.opciones,
        pk=opcion_id,
    )

    if request.method == "POST":

        form = OpcionModificadorForm(
            request.POST,
            instance=opcion,
        )

        if form.is_valid():

            form.save()

            messages.success(
                request,
                "Opción actualizada.",
            )

            return _nl_volver_a_modificadores(producto)

    else:
        form = OpcionModificadorForm(instance=opcion)

    return render(
        request,
        "core/producto_modificador_form.html",
        {
            "titulo": "Editar opción",
            "subtitulo": producto.nombre + " · " + grupo.nombre,
            "boton": "Guardar cambios",
            "form": form,
            "producto": producto,
        },
    )


@login_required
def producto_modificador_opcion_estado(
    request,
    producto_id,
    grupo_id,
    opcion_id,
):
    """Marca la opción como Disponible o Agotada."""

    from django.http import HttpResponseNotAllowed

    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    producto = _nl_producto_administrable(
        request,
        producto_id,
    )

    grupo = _nl_grupo_modificador(producto, grupo_id)

    opcion = get_object_or_404(
        grupo.opciones,
        pk=opcion_id,
    )

    opcion.activa = not opcion.activa

    opcion.save(
        update_fields=[
            "activa",
            "actualizado_en",
        ]
    )

    estado = "disponible" if opcion.activa else "agotada"

    messages.success(
        request,
        "La opción «" + opcion.nombre + "» quedó " + estado + ".",
    )

    return _nl_volver_a_modificadores(producto)


# ============================================================
# VISTAS PEDIDOS
# ============================================================

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)
from django.views.decorators.http import require_POST

from core.forms import (
    PedidoCrearForm,
    PedidoEditarForm,
    PedidoDetalleAgregarForm,
    PedidoDetalleEditarForm,
)

from core.models import (
    Pedido,
    PedidoDetalle,
)

from core.services.pedidos import (
    crear_pedido,
    actualizar_datos_pedido,
    agregar_producto_a_pedido,
    actualizar_detalle_pedido,
    eliminar_detalle_pedido,
    confirmar_pedido,
)



# =============================================================================
# TNL-PEDIDO-DUENO-V3
#
# Seguridad servidor para Pedidos.
#
# Administrador:
#   acceso global.
#
# Cliente principal / Dueño:
#   exclusivamente pedidos de PerfilUsuario.empresa_id.
#
# empresa_id nunca se acepta desde navegador para determinar pertenencia.
# =============================================================================

def _nl_pedido_scope(
    request,
):

    from django.core.exceptions import (
        PermissionDenied,
    )

    from core.models import (
        PerfilUsuario,
    )


    if getattr(
        request.user,
        "is_superuser",
        False,
    ):

        return (
            None,
            False,
        )


    perfil = (
        PerfilUsuario.objects
        .filter(
            usuario=request.user,
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
        ==
        PerfilUsuario.Rol.ADMINISTRADOR
    ):

        return (
            None,
            False,
        )


    if (
        perfil.rol
        ==
        PerfilUsuario.Rol.CLIENTE
    ):

        if perfil.empresa_id is None:

            raise PermissionDenied(
                "El cliente no tiene empresa asignada."
            )

        return (
            perfil.empresa_id,
            True,
        )


    raise PermissionDenied(
        "Acceso no autorizado."
    )



def _nl_pedido_required(
    view_func,
):

    from functools import wraps


    @wraps(
        view_func
    )
    def role_guard(
        request,
        *args,
        **kwargs,
    ):

        _nl_pedido_scope(
            request
        )

        return view_func(
            request,
            *args,
            **kwargs,
        )


    wrapped = login_required(
        role_guard
    )

    wrapped._nl_pedido_security = (
        "admin_o_cliente_empresa_propia"
    )

    return wrapped


# =============================================================================
# TNL-CLIENTE-PROMOCIONES-IA-VIEW-V1
# =============================================================================

@login_required
def cliente_promociones_ia(
    request,
):
    """
    Panel del Dueño para:
    - Productos Estrella;
    - mensajes promocionales;
    - venta cruzada.

    La empresa proviene únicamente del usuario
    autenticado mediante promociones_ia_dueno.
    """

    from django.contrib import (
        messages,
    )

    from django.core.exceptions import (
        ValidationError,
    )

    from django.shortcuts import (
        redirect,
        render,
    )

    from core.services.promociones_ia_dueno import (
        eliminar_regla_crosssell,
        guardar_promocion_producto,
        guardar_regla_crosssell,
        obtener_contexto_promociones,
        resolver_empresa_dueno,
    )


    empresa = resolver_empresa_dueno(
        request.user
    )


    if request.method == "POST":

        accion = str(
            request.POST.get(
                "accion",
                "",
            )
            or ""
        ).strip()


        try:

            if accion == "guardar_promocion":

                promocion = (
                    guardar_promocion_producto(
                        empresa=empresa,

                        producto_id=
                            request.POST.get(
                                "producto_id"
                            ),

                        es_estrella=(
                            request.POST.get(
                                "es_estrella"
                            )
                            ==
                            "1"
                        ),

                        texto_promocional=
                            request.POST.get(
                                "texto_promocional",
                                "",
                            ),
                    )
                )

                messages.success(
                    request,
                    (
                        "Configuración de "
                        f"{promocion.producto.nombre} "
                        "guardada correctamente."
                    ),
                )


            elif accion == "guardar_crosssell":

                guardar_regla_crosssell(
                    empresa=empresa,

                    regla_id=
                        request.POST.get(
                            "regla_id",
                            "",
                        ),

                    producto_origen_id=
                        request.POST.get(
                            "producto_origen_id"
                        ),

                    producto_recomendado_id=
                        request.POST.get(
                            "producto_recomendado_id"
                        ),

                    texto_promocional=
                        request.POST.get(
                            "texto_promocional",
                            "",
                        ),

                    prioridad=
                        request.POST.get(
                            "prioridad",
                            "100",
                        ),

                    activa=(
                        request.POST.get(
                            "activa"
                        )
                        ==
                        "1"
                    ),
                )

                messages.success(
                    request,
                    (
                        "Recomendación de compra "
                        "guardada correctamente."
                    ),
                )


            elif accion == "eliminar_crosssell":

                eliminar_regla_crosssell(
                    empresa=empresa,

                    regla_id=
                        request.POST.get(
                            "regla_id"
                        ),
                )

                messages.success(
                    request,
                    (
                        "Recomendación eliminada "
                        "correctamente."
                    ),
                )


            else:

                raise ValidationError(
                    "Acción no válida."
                )


        except ValidationError as exc:

            messages.error(
                request,
                " ".join(
                    exc.messages
                ),
            )


        return redirect(
            "core:cliente_promociones_ia"
        )


    contexto = (
        obtener_contexto_promociones(
            empresa
        )
    )


    return render(
        request,
        "core/cliente_promociones_ia.html",
        {
            "empresa":
                empresa,

            **contexto,
        },
    )



def _pedido_error_texto(exc):

    if isinstance(
        exc,
        ValidationError,
    ):

        return " ".join(
            exc.messages
        )

    return str(exc)


@login_required
def pedido_lista(request):

    # TNL-RESTAURANTE-LISTA-R3-B2B1-V1
    from core.services.pedidos import (
        evaluar_inicio_preparacion_pedido,
        siguiente_estado_operativo_pedido,
    )

    empresa_scope, pedido_modo_cliente = (
        _nl_pedido_scope(
            request
        )
    )

    pedidos_qs = (
        Pedido.objects
        .select_related(
            "empresa",
            "canal",
            "canal__bot",
        )
        .order_by(
            "-creado_en",
            "-id",
        )
    )

    if empresa_scope is not None:

        pedidos_qs = (
            pedidos_qs
            .filter(
                empresa_id=
                    empresa_scope
            )
        )

    pedidos = list(
        pedidos_qs
    )

    tipos_restaurante = {
        "comedor",
        "para_llevar",
        "domicilio",
    }

    labels_estado = dict(
        Pedido.ESTADOS
    )

    for pedido in pedidos:

        pedido.es_pedido_restaurante_ui = (
            pedido.tipo_orden
            in
            tipos_restaurante
        )

        siguiente = (
            siguiente_estado_operativo_pedido(
                pedido.estado,
                tipo_orden=
                    pedido.tipo_orden,
            )
        )


        if (
            siguiente
            ==
            "preparando"
        ):

            gate_preparacion = (
                evaluar_inicio_preparacion_pedido(
                    pedido
                )
            )

            if (
                gate_preparacion[
                    "aplica"
                ]
                and
                not gate_preparacion[
                    "permitido"
                ]
            ):

                siguiente = ""


        pedido.siguiente_estado_operativo_ui = (
            siguiente
        )

        pedido.siguiente_estado_label_ui = (
            labels_estado.get(
                siguiente,
                siguiente,
            )
            if siguiente
            else ""
        )

    return render(
        request,
        (
            "core/cliente_pedido_lista.html"
            if pedido_modo_cliente
            else "core/pedido_lista.html"
        ),
        {
            "pedidos":
                pedidos,

            "pedido_modo_cliente":
                pedido_modo_cliente,
        },
    )



@login_required
def pedido_crear(request):

    if request.method == "POST":

        form = PedidoCrearForm(
            request.POST
        )

        if form.is_valid():

            data = form.cleaned_data
            canal = data.get("canal")

            try:

                pedido = crear_pedido(
                    empresa_id=
                        data["empresa"].id,
                    canal_id=(
                        canal.id
                        if canal
                        else None
                    ),
                    moneda=data["moneda"],
                    cliente_nombre=
                        data["cliente_nombre"],
                    cliente_telefono=
                        data["cliente_telefono"],
                    cliente_email=
                        data["cliente_email"],
                    direccion_entrega=
                        data["direccion_entrega"],
                    notas=data["notas"],
                    identificador_externo=
                        data[
                            "identificador_externo"
                        ],
                )

            except ValidationError as exc:

                form.add_error(
                    None,
                    _pedido_error_texto(
                        exc
                    ),
                )

            else:

                messages.success(
                    request,
                    (
                        f"Pedido {pedido.numero} "
                        "creado correctamente."
                    ),
                )

                return redirect(
                    "core:pedido_detalle",
                    pk=pedido.pk,
                )

    else:

        form = PedidoCrearForm()

    return render(
        request,
        "core/pedido_form.html",
        {
            "form": form,
            "titulo": "Nuevo pedido",
            "subtitulo":
                "Registra un nuevo carrito para una empresa.",
            "boton": "Crear pedido",
            "modo": "crear",
        },
    )


@login_required
# =============================================================================
# TNL-RESTAURANTE-PANEL-R3-B2A-V1
# Contexto operativo único para panel Admin y portal Cliente.
# =============================================================================

def pedido_detalle(request, pk):

    # TNL-RESTAURANTE-DETALLE-R3-B2B2-V1

    from core.services.pedidos import (
        evaluar_inicio_preparacion_pedido,
        siguiente_estado_operativo_pedido,
    )

    empresa_scope, pedido_modo_cliente = (
        _nl_pedido_scope(
            request
        )
    )

    filtros_pedido = {
        "pk": pk,
    }

    if empresa_scope is not None:

        filtros_pedido[
            "empresa_id"
        ] = empresa_scope

    pedido = get_object_or_404(
        Pedido.objects
        .select_related(
            "empresa",
            "canal",
            "canal__bot",
        ),
        **filtros_pedido,
    )

    detalles = (
        PedidoDetalle.objects
        .filter(
            pedido_id=pedido.id
        )
        .select_related(
            "producto",
        )
        .order_by("id")
    )

    tipos_restaurante = {
        "comedor",
        "para_llevar",
        "domicilio",
    }

    es_pedido_restaurante = (
        pedido.tipo_orden
        in
        tipos_restaurante
    )

    siguiente_estado_operativo = (
        siguiente_estado_operativo_pedido(
            pedido.estado,
            tipo_orden=
                pedido.tipo_orden,
        )
    )

    labels_estado = dict(
        Pedido.ESTADOS
    )

    pedido.es_pedido_restaurante_ui = (
        es_pedido_restaurante
    )


    if (
        siguiente_estado_operativo
        ==
        "preparando"
    ):

        gate_preparacion = (
            evaluar_inicio_preparacion_pedido(
                pedido
            )
        )

        if (
            gate_preparacion[
                "aplica"
            ]
            and
            not gate_preparacion[
                "permitido"
            ]
        ):

            siguiente_estado_operativo = ""


    pedido.siguiente_estado_operativo_ui = (
        siguiente_estado_operativo
    )

    pedido.siguiente_estado_label_ui = (
        labels_estado.get(
            siguiente_estado_operativo,
            siguiente_estado_operativo,
        )
        if siguiente_estado_operativo
        else ""
    )

    # ================================================================
    # TNL-PAGO-DIRECTO-P2-V1
    # Estado financiero separado del estado operativo.
    # ================================================================

    pago_actual = (
        pedido.pagos
        .order_by(
            "-id"
        )
        .first()
    )

    if pago_actual is not None:

        if (
            pago_actual.proveedor
            ==
            "negocio"
        ):

            pago_actual.metodo_label_ui = (
                "Efectivo / contra entrega"
            )

        else:

            pago_actual.metodo_label_ui = (
                pago_actual
                .get_proveedor_display()
            )

        if (
            pago_actual.estado
            ==
            "aprobado"
        ):

            pago_actual.estado_label_ui = (
                "Pagado"
            )

        else:

            pago_actual.estado_label_ui = (
                pago_actual
                .get_estado_display()
            )


        pago_actual.puede_marcar_pagado_ui = (
            es_pedido_restaurante
            and
            pedido.empresa_id == 7
            and
            pago_actual.proveedor == "negocio"
            and
            pago_actual.estado == "pendiente"
            and
            pedido.estado
            in {
                "pendiente",
                "confirmado",
                "pagado",
                "preparando",
                "listo",
                "en_camino",
                "enviado",
                "entregado",
            }
        )


    eventos_estado = list(
        pedido.estado_eventos
        .select_related(
            "usuario",
        )
        .order_by(
            "-fecha",
            "-id",
        )[:50]
    )

    for evento in eventos_estado:

        evento.estado_anterior_label_ui = (
            labels_estado.get(
                evento.estado_anterior,
                evento.estado_anterior,
            )
            if evento.estado_anterior
            else "Inicio"
        )

        evento.estado_nuevo_label_ui = (
            labels_estado.get(
                evento.estado_nuevo,
                evento.estado_nuevo,
            )
        )

    return render(
        request,
        (
            "core/cliente_pedido_detalle.html"
            if pedido_modo_cliente
            else "core/pedido_detalle.html"
        ),
        {
            "pedido":
                pedido,

            "detalles":
                detalles,

            "editable":
                (
                    pedido.estado
                    ==
                    "carrito"
                    and
                    not pedido_modo_cliente
                ),

            "pedido_modo_cliente":
                pedido_modo_cliente,

            "es_pedido_restaurante":
                es_pedido_restaurante,

            "siguiente_estado_operativo":
                siguiente_estado_operativo,

            "eventos_estado":
                eventos_estado,


            "pago_actual":
                pago_actual,
        },
    )




@login_required
def pedido_editar(request, pk):

    pedido = get_object_or_404(
        Pedido,
        pk=pk,
    )

    if pedido.estado != "carrito":

        messages.error(
            request,
            (
                "Solo se puede editar un pedido "
                "que esté en estado Carrito."
            ),
        )

        return redirect(
            "core:pedido_detalle",
            pk=pedido.pk,
        )

    if request.method == "POST":

        form = PedidoEditarForm(
            request.POST,
            instance=pedido,
        )

        if form.is_valid():

            data = form.cleaned_data
            canal = data.get("canal")

            try:

                actualizar_datos_pedido(
                    pedido_id=pedido.id,
                    canal_id=(
                        canal.id
                        if canal
                        else None
                    ),
                    cliente_nombre=
                        data["cliente_nombre"],
                    cliente_telefono=
                        data["cliente_telefono"],
                    cliente_email=
                        data["cliente_email"],
                    direccion_entrega=
                        data["direccion_entrega"],
                    notas=data["notas"],
                    identificador_externo=
                        data[
                            "identificador_externo"
                        ],
                )

            except ValidationError as exc:

                form.add_error(
                    None,
                    _pedido_error_texto(
                        exc
                    ),
                )

            else:

                messages.success(
                    request,
                    (
                        f"Pedido {pedido.numero} "
                        "actualizado correctamente."
                    ),
                )

                return redirect(
                    "core:pedido_detalle",
                    pk=pedido.pk,
                )

    else:

        form = PedidoEditarForm(
            instance=pedido
        )

    return render(
        request,
        "core/pedido_form.html",
        {
            "form": form,
            "pedido": pedido,
            "titulo":
                f"Editar {pedido.numero}",
            "subtitulo":
                "Actualiza los datos generales del carrito.",
            "boton": "Guardar cambios",
            "modo": "editar",
        },
    )


@login_required
def pedido_producto_agregar(
    request,
    pk,
):

    pedido = get_object_or_404(
        Pedido,
        pk=pk,
    )

    if pedido.estado != "carrito":

        messages.error(
            request,
            (
                "No se pueden agregar productos "
                "a un pedido confirmado."
            ),
        )

        return redirect(
            "core:pedido_detalle",
            pk=pedido.pk,
        )

    if request.method == "POST":

        form = PedidoDetalleAgregarForm(
            request.POST,
            pedido=pedido,
        )

        if form.is_valid():

            data = form.cleaned_data

            try:

                agregar_producto_a_pedido(
                    pedido_id=pedido.id,
                    producto_id=
                        data["producto"].id,
                    cantidad=
                        data["cantidad"],
                    descuento=
                        data["descuento"],
                )

            except ValidationError as exc:

                form.add_error(
                    None,
                    _pedido_error_texto(
                        exc
                    ),
                )

            else:

                messages.success(
                    request,
                    "Producto agregado al pedido.",
                )

                return redirect(
                    "core:pedido_detalle",
                    pk=pedido.pk,
                )

    else:

        form = PedidoDetalleAgregarForm(
            pedido=pedido,
        )

    return render(
        request,
        "core/pedido_detalle_form.html",
        {
            "pedido": pedido,
            "form": form,
            "titulo": "Agregar producto",
            "subtitulo":
                f"Agrega una línea a {pedido.numero}.",
            "boton": "Agregar producto",
            "modo": "agregar",
        },
    )


@login_required
def pedido_producto_editar(
    request,
    detalle_id,
):

    detalle = get_object_or_404(
        PedidoDetalle.objects
        .select_related(
            "pedido",
        ),
        pk=detalle_id,
    )

    pedido = detalle.pedido

    if pedido.estado != "carrito":

        messages.error(
            request,
            (
                "No se pueden editar productos "
                "de un pedido confirmado."
            ),
        )

        return redirect(
            "core:pedido_detalle",
            pk=pedido.pk,
        )

    if request.method == "POST":

        form = PedidoDetalleEditarForm(
            request.POST
        )

        if form.is_valid():

            data = form.cleaned_data

            try:

                actualizar_detalle_pedido(
                    detalle_id=
                        detalle.id,
                    cantidad=
                        data["cantidad"],
                    descuento=
                        data["descuento"],
                )

            except ValidationError as exc:

                form.add_error(
                    None,
                    _pedido_error_texto(
                        exc
                    ),
                )

            else:

                messages.success(
                    request,
                    "Línea actualizada correctamente.",
                )

                return redirect(
                    "core:pedido_detalle",
                    pk=pedido.pk,
                )

    else:

        form = PedidoDetalleEditarForm(
            initial={
                "cantidad":
                    detalle.cantidad,
                "descuento":
                    detalle.descuento,
            }
        )

    return render(
        request,
        "core/pedido_detalle_form.html",
        {
            "pedido": pedido,
            "detalle": detalle,
            "form": form,
            "titulo":
                f"Editar {detalle.sku}",
            "subtitulo":
                "Modifica la cantidad o el descuento de la línea.",
            "boton": "Guardar cambios",
            "modo": "editar",
        },
    )


@login_required
@require_POST
def pedido_producto_eliminar(
    request,
    detalle_id,
):

    detalle = get_object_or_404(
        PedidoDetalle.objects
        .select_related(
            "pedido",
        ),
        pk=detalle_id,
    )

    pedido_id = detalle.pedido_id

    try:

        eliminar_detalle_pedido(
            detalle_id=detalle.id,
        )

    except ValidationError as exc:

        messages.error(
            request,
            _pedido_error_texto(
                exc
            ),
        )

    else:

        messages.success(
            request,
            "Producto eliminado del pedido.",
        )

    return redirect(
        "core:pedido_detalle",
        pk=pedido_id,
    )


@login_required
@require_POST
def pedido_confirmar(
    request,
    pk,
):
    pedido = get_object_or_404(
        Pedido,
        pk=pk,
    )

    es_ajax = (
        request.headers.get(
            "X-Requested-With"
        )
        == "XMLHttpRequest"
    )

    try:
        pedido = confirmar_pedido(
            pedido_id=pedido.id,
        )

    except ValidationError as exc:
        mensaje = _pedido_error_texto(
            exc
        )

        if es_ajax:
            return JsonResponse(
                {
                    "ok": False,
                    "tipo": "validation_error",
                    "pedido": pedido.numero,
                    "message": mensaje,
                },
                status=409,
            )

        messages.error(
            request,
            mensaje,
        )

        return redirect(
            "core:pedido_detalle",
            pk=pedido.pk,
        )

    mensaje = (
        f"Pedido {pedido.numero} "
        "confirmado correctamente."
    )

    if es_ajax:
        return JsonResponse(
            {
                "ok": True,
                "pedido": pedido.numero,
                "message": mensaje,
                "redirect_url": reverse(
                    "core:pedido_detalle",
                    kwargs={
                        "pk": pedido.pk,
                    },
                ),
            },
            status=200,
        )

    messages.success(
        request,
        mensaje,
    )

    return redirect(
        "core:pedido_detalle",
        pk=pedido.pk,
    )




# ============================================================
# CONTROLADOR DE CLIENTES V1
# ============================================================

@login_required
def empresa_detalle(request, pk):
    """
    Panel integral de una empresa/cliente.

    Esta primera versión es exclusivamente de consulta.
    No realiza aprovisionamientos ni modifica datos.
    """

    from django.shortcuts import get_object_or_404, render
    from django.utils import timezone

    from core.models import (
        Empresa,
        PerfilUsuario,
        Licencia,
        Bot,
        Canal,
        Plantilla,
        Variable,
        Catalogo,
        Producto,
        Pedido,
        InstalacionPlantilla,
        PlantillaMaestra,
    )

    empresa = get_object_or_404(
        Empresa,
        pk=pk,
    )

    hoy = timezone.localdate()

    # --------------------------------------------------------
    # LICENCIAS
    # --------------------------------------------------------

    licencias = list(
        Licencia.objects
        .filter(
            empresa=empresa
        )
        .order_by(
            "-fecha_fin",
            "-id",
        )
    )

    licencia_actual = None

    for licencia in licencias:

        if (
            licencia.estado == "activa"
            and licencia.fecha_inicio <= hoy
            and licencia.fecha_fin >= hoy
        ):
            licencia_actual = licencia
            break

    # --------------------------------------------------------
    # USUARIOS
    # --------------------------------------------------------

    usuarios = (
        PerfilUsuario.objects
        .filter(
            empresa=empresa
        )
        .select_related(
            "usuario"
        )
        .order_by(
            "usuario__username"
        )
    )

    # --------------------------------------------------------
    # INSTALACIONES
    # --------------------------------------------------------

    instalaciones_qs = (
        InstalacionPlantilla.objects
        .filter(
            empresa=empresa
        )
        .select_related(
            "licencia",
            "plantilla_maestra",
            "plantilla",
        )
        .order_by(
            "-iniciada_en",
            "-id",
        )
    )

    instalaciones = []

    for instalacion in instalaciones_qs:

        plantilla = instalacion.plantilla

        bot = None
        catalogo = None
        cantidad_variables = 0

        if plantilla is not None:

            cantidad_variables = (
                Variable.objects
                .filter(
                    plantilla=plantilla
                )
                .count()
            )

            bot = (
                Bot.objects
                .filter(
                    plantilla=plantilla
                )
                .order_by("id")
                .first()
            )

            catalogo = (
                Catalogo.objects
                .filter(
                    plantilla=plantilla
                )
                .order_by("id")
                .first()
            )

        instalaciones.append(
            {
                "instalacion": instalacion,
                "plantilla": plantilla,
                "bot": bot,
                "catalogo": catalogo,
                "variables": cantidad_variables,
            }
        )

    # --------------------------------------------------------
    # WHATSAPP
    # NEGOCIOLISTO-WHATSAPP-UI-V1
    # --------------------------------------------------------

    canales_whatsapp = []

    for item in instalaciones:

        instalacion = item[
            "instalacion"
        ]

        bot = item[
            "bot"
        ]

        if bot is None:
            continue


        canal = (
            Canal.objects
            .filter(
                bot=bot,
                tipo="whatsapp",
            )
            .order_by("id")
            .first()
        )


        if canal is None:
            continue


        canales_whatsapp.append(
            {
                "canal": canal,
                "bot": bot,
                "instalacion":
                    instalacion,

                "instance_name": (
                    f"tnl-e{empresa.id}"
                    f"-i{instalacion.id}"
                ),
            }
        )


    # --------------------------------------------------------
    # RESUMEN OPERATIVO
    # --------------------------------------------------------

    resumen = {
        "usuarios": (
            PerfilUsuario.objects
            .filter(
                empresa=empresa
            )
            .count()
        ),
        "plantillas": (
            Plantilla.objects
            .filter(
                empresa=empresa
            )
            .count()
        ),
        "instalaciones": (
            InstalacionPlantilla.objects
            .filter(
                empresa=empresa
            )
            .count()
        ),
        "bots": (
            Bot.objects
            .filter(
                empresa=empresa
            )
            .count()
        ),
        "canales": (
            Canal.objects
            .filter(
                bot__empresa=empresa
            )
            .count()
        ),
        "catalogos": (
            Catalogo.objects
            .filter(
                empresa=empresa
            )
            .count()
        ),
        "productos": (
            Producto.objects
            .filter(
                catalogo__empresa=empresa
            )
            .count()
        ),
        "pedidos": (
            Pedido.objects
            .filter(
                empresa=empresa
            )
            .count()
        ),
    }

    plantillas_maestras = (
        PlantillaMaestra.objects
        .filter(
            estado=PlantillaMaestra.Estado.PUBLICADA,
            activa=True,
        )
        .order_by(
            "tipo",
            "nombre",
            "-version",
        )
    )

    # TNL-MERCADOPAGO-EMPRESA-CONTEXT-V1
    from core.models import (
        ConfiguracionMercadoPago,
    )

    configuracion_mercadopago = (
        ConfiguracionMercadoPago.objects
        .filter(
            empresa=empresa
        )
        .first()
    )



    # TNL-IA-EMPRESA-CONTEXT-V1
    from core.services.ia_bolsa import obtener_estado_ia

    estado_ia = obtener_estado_ia(
        empresa.id
    )

    porcentaje_ia = 0.0

    if (
        estado_ia["cantidad_palabras"]
        > 0
    ):

        porcentaje_ia = round(
            (
                estado_ia[
                    "palabras_consumidas"
                ]
                * 100
            )
            /
            estado_ia[
                "cantidad_palabras"
            ],
            1,
        )


    # TNL-GOOGLE-CALENDAR-EMPRESA-CONTEXT-V1
    from core.models import (
        Cita,
        ConfiguracionGoogleCalendar,
    )

    from core.services.google_calendar_oauth import (
        oauth_configurado,
        obtener_redirect_uri,
    )


    google_calendar_config = (
        ConfiguracionGoogleCalendar.objects
        .filter(
            empresa=empresa
        )
        .first()
    )


    google_oauth_ready = oauth_configurado()


    if google_calendar_config is None:

        estado_google_calendar = {
            "configurada": False,
            "estado": "desconectada",
            "habilitada": False,
            "conectada": False,
            "cuenta_email": "",
            "calendar_id": "",
            "calendar_nombre": "",
            "zona_horaria":
                "America/Mexico_City",
            "oauth_configurado":
                google_oauth_ready,
            "redirect_uri":
                obtener_redirect_uri(),
            "citas_total":
                Cita.objects
                .filter(
                    empresa=empresa
                )
                .count(),
        }

    else:

        estado_google_calendar = {
            "configurada": True,
            "estado":
                google_calendar_config
                .estado_conexion,
            "habilitada":
                google_calendar_config
                .habilitada,
            "conectada": bool(
                google_calendar_config
                .estado_conexion
                ==
                "conectada"
                and
                google_calendar_config
                .habilitada
            ),
            "cuenta_email":
                google_calendar_config
                .cuenta_email,
            "calendar_id":
                google_calendar_config
                .calendar_id,
            "calendar_nombre":
                google_calendar_config
                .calendar_nombre,
            "zona_horaria":
                google_calendar_config
                .zona_horaria,
            "oauth_configurado":
                google_oauth_ready,
            "redirect_uri":
                obtener_redirect_uri(),
            "citas_total":
                Cita.objects
                .filter(
                    empresa=empresa
                )
                .count(),
        }

    context = {
        "empresa": empresa,
        "estado_ia": estado_ia,
        "porcentaje_ia": porcentaje_ia,
        "estado_google_calendar": estado_google_calendar,
        "hoy": hoy,
        "licencias": licencias,
        "licencia_actual": licencia_actual,
        "usuarios": usuarios,
        "instalaciones": instalaciones,
        "canales_whatsapp":
            canales_whatsapp,

        "configuracion_mercadopago":
            configuracion_mercadopago,
        "resumen": resumen,
        "plantillas_maestras": plantillas_maestras,
    }

    return render(
        request,
        "core/empresa_detalle.html",
        context,
    )


# ============================================================
# CONTROLADOR DE CLIENTES - APROVISIONAMIENTO AJAX V1
# ============================================================

@login_required
def empresa_aprovisionar(request, pk):
    """
    Aprovisiona una Plantilla Maestra para una empresa.

    La licencia se determina y valida exclusivamente
    del lado servidor.

    Devuelve JSON para la interfaz SweetAlert2.
    """

    import json

    from django.core.exceptions import ValidationError
    from django.http import JsonResponse
    from django.utils import timezone

    from core.models import (
        Empresa,
        Licencia,
        PlantillaMaestra,
    )

    from core.services.aprovisionamiento import (
        provisionar_empresa_desde_plantilla,
    )


    # --------------------------------------------------------
    # MÉTODO
    # --------------------------------------------------------

    if request.method != "POST":

        return JsonResponse(
            {
                "ok": False,
                "message": "Método no permitido.",
            },
            status=405,
        )


    # --------------------------------------------------------
    # EMPRESA
    # --------------------------------------------------------

    empresa = (
        Empresa.objects
        .filter(
            pk=pk
        )
        .first()
    )

    if empresa is None:

        return JsonResponse(
            {
                "ok": False,
                "message": "La empresa indicada no existe.",
            },
            status=404,
        )


    # --------------------------------------------------------
    # PAYLOAD
    # --------------------------------------------------------

    try:

        payload = json.loads(
            request.body.decode("utf-8")
            if request.body
            else "{}"
        )

    except (
        json.JSONDecodeError,
        UnicodeDecodeError,
    ):

        return JsonResponse(
            {
                "ok": False,
                "message": "La solicitud recibida no es válida.",
            },
            status=400,
        )


    plantilla_maestra_id = payload.get(
        "plantilla_maestra_id"
    )

    if not plantilla_maestra_id:

        return JsonResponse(
            {
                "ok": False,
                "message": (
                    "Debes seleccionar una plantilla."
                ),
            },
            status=400,
        )


    # --------------------------------------------------------
    # PLANTILLA MAESTRA
    # --------------------------------------------------------

    plantilla_maestra = (
        PlantillaMaestra.objects
        .filter(
            pk=plantilla_maestra_id,
            estado=(
                PlantillaMaestra
                .Estado
                .PUBLICADA
            ),
            activa=True,
        )
        .first()
    )

    if plantilla_maestra is None:

        return JsonResponse(
            {
                "ok": False,
                "message": (
                    "La plantilla seleccionada no existe, "
                    "no está publicada o se encuentra inactiva."
                ),
            },
            status=404,
        )


    # --------------------------------------------------------
    # LICENCIA ACTIVA Y VIGENTE
    # --------------------------------------------------------

    hoy = timezone.localdate()

    licencia = (
        Licencia.objects
        .filter(
            empresa=empresa,
            estado="activa",
            fecha_inicio__lte=hoy,
            fecha_fin__gte=hoy,
        )
        .order_by(
            "-fecha_fin",
            "-id",
        )
        .first()
    )

    if licencia is None:

        return JsonResponse(
            {
                "ok": False,
                "message": (
                    "La empresa no tiene una licencia "
                    "activa y vigente."
                ),
            },
            status=409,
        )


    # --------------------------------------------------------
    # APROVISIONAMIENTO
    # --------------------------------------------------------

    try:

        resultado = (
            provisionar_empresa_desde_plantilla(
                empresa_id=empresa.id,
                licencia_id=licencia.id,
                plantilla_maestra_id=(
                    plantilla_maestra.id
                ),
            )
        )

    except ValidationError as exc:

        mensajes = getattr(
            exc,
            "messages",
            None,
        )

        mensaje = (
            " ".join(
                str(item)
                for item in mensajes
            )
            if mensajes
            else str(exc)
        )

        return JsonResponse(
            {
                "ok": False,
                "message": mensaje,
            },
            status=409,
        )

    except Exception as exc:

        return JsonResponse(
            {
                "ok": False,
                "message": (
                    "No se pudo completar el "
                    "aprovisionamiento."
                ),
                "detail": str(exc),
            },
            status=500,
        )


    instalacion = resultado[
        "instalacion"
    ]

    plantilla = resultado[
        "plantilla"
    ]

    bot = resultado[
        "bot"
    ]

    catalogo = resultado[
        "catalogo"
    ]

    idempotente = bool(
        resultado.get(
            "idempotente",
            False,
        )
    )


    # --------------------------------------------------------
    # RESPUESTA
    # --------------------------------------------------------

    if idempotente:

        mensaje = (
            f"{plantilla_maestra.nombre} "
            f"v{plantilla_maestra.version} "
            "ya estaba instalada para esta empresa."
        )

    else:

        mensaje = (
            f"{plantilla_maestra.nombre} "
            f"v{plantilla_maestra.version} "
            "fue aprovisionada correctamente."
        )


    return JsonResponse(
        {
            "ok": True,
            "idempotente": idempotente,
            "message": mensaje,

            "empresa": {
                "id": empresa.id,
                "nombre": empresa.nombre,
            },

            "licencia": {
                "id": licencia.id,
                "nombre": licencia.nombre,
                "fecha_fin": (
                    licencia.fecha_fin.isoformat()
                ),
            },

            "instalacion": {
                "id": instalacion.id,
                "estado": instalacion.estado,
            },

            "plantilla": {
                "id": (
                    plantilla.id
                    if plantilla
                    else None
                ),
                "nombre": (
                    plantilla.nombre
                    if plantilla
                    else None
                ),
            },

            "bot": {
                "id": (
                    bot.id
                    if bot
                    else None
                ),
                "nombre": (
                    bot.nombre
                    if bot
                    else None
                ),
            },

            "catalogo": {
                "id": (
                    catalogo.id
                    if catalogo
                    else None
                ),
                "nombre": (
                    catalogo.nombre
                    if catalogo
                    else None
                ),
            },
        },
        status=200,
    )


# ============================================================
# CLIENTE-LICENCIA-INTEGRADA-V1
# ============================================================

@login_required
def empresa_licencia_crear(request, pk):
    """
    Crea una licencia dentro del contexto de un cliente.

    La Empresa se fija exclusivamente del lado servidor.
    El usuario no puede cambiar la empresa mediante POST.
    """

    from django.shortcuts import (
        get_object_or_404,
        redirect,
        render,
    )

    from core.forms import LicenciaForm
    from core.models import Empresa


    empresa = get_object_or_404(
        Empresa,
        pk=pk,
    )


    if request.method == "POST":

        payload = request.POST.copy()

        # Seguridad:
        # ignoramos cualquier empresa recibida del navegador
        # y forzamos la empresa de la URL.
        payload["empresa"] = str(
            empresa.pk
        )

        form = LicenciaForm(
            payload
        )


        if form.is_valid():

            licencia = form.save(
                commit=False
            )

            licencia.empresa = empresa

            licencia.save()

            # TNL-CLIENT-LIFECYCLE-LICENSE-RECONCILE-V1
            from core.services.client_lifecycle import (
                reconciliar_empresa,
            )

            reconciliar_empresa(
                empresa
            )

            return redirect(
                "core:empresa_detalle",
                pk=empresa.pk,
            )

    else:

        form = LicenciaForm(
            initial={
                "empresa": empresa.pk,
            }
        )


    context = {
        "empresa": empresa,
        "form": form,
    }


    return render(
        request,
        "core/empresa_licencia_form.html",
        context,
    )


# ============================================================
# NEGOCIOLISTO-WHATSAPP-UI-V1
# CONEXION WHATSAPP POR CLIENTE
# ============================================================

from django.contrib.auth.decorators import (
    login_required as
    _nl_login_required,
)


def _nl_whatsapp_json(
    payload,
    status=200,
):

    from django.http import (
        JsonResponse,
    )


    response = JsonResponse(
        payload,
        status=status,
    )

    response[
        "Cache-Control"
    ] = (
        "no-store, no-cache, "
        "must-revalidate, private"
    )

    response[
        "Pragma"
    ] = "no-cache"


    return response


def _nl_whatsapp_contexto(
    empresa,
    canal,
):

    from django.core.exceptions import (
        ValidationError,
    )

    from core.models import (
        InstalacionPlantilla,
    )


    bot = canal.bot


    if bot.empresa_id != empresa.id:

        raise ValidationError(
            "El canal no pertenece "
            "al cliente indicado."
        )


    if canal.tipo != "whatsapp":

        raise ValidationError(
            "El canal indicado "
            "no es WhatsApp."
        )


    if bot.plantilla_id is None:

        raise ValidationError(
            "El Bot no está vinculado "
            "a una plantilla."
        )


    instalacion = (
        InstalacionPlantilla.objects
        .filter(
            empresa=empresa,
            plantilla_id=
                bot.plantilla_id,
            estado="lista",
        )
        .order_by(
            "-id"
        )
        .first()
    )


    if instalacion is None:

        raise ValidationError(
            "No existe una instalación "
            "lista para este canal."
        )


    instance_name = (
        f"tnl-e{empresa.id}"
        f"-i{instalacion.id}"
    )


    current_identifier = (
        canal.identificador
        or ""
    ).strip()


    if (
        current_identifier
        and
        current_identifier
        != instance_name
    ):

        raise ValidationError(
            "El canal ya está vinculado "
            "a otra instancia."
        )


    return (
        instalacion,
        instance_name,
    )


@_nl_login_required
def empresa_whatsapp_conectar(
    request,
    pk,
    canal_id,
):

    from django.core.exceptions import (
        ValidationError,
    )

    from django.shortcuts import (
        get_object_or_404,
    )

    from core.integrations.evolution_client import (
        EvolutionClient,
        EvolutionClientError,
    )

    from core.models import (
        Canal,
        Empresa,
    )


    if request.method != "POST":

        return _nl_whatsapp_json(
            {
                "ok": False,
                "message":
                    "Método no permitido.",
            },
            status=405,
        )


    empresa = get_object_or_404(
        Empresa,
        pk=pk,
    )


    canal = get_object_or_404(
        Canal.objects.select_related(
            "bot",
            "bot__empresa",
        ),
        pk=canal_id,
        bot__empresa=empresa,
    )


    try:

        (
            instalacion,
            instance_name,
        ) = _nl_whatsapp_contexto(
            empresa,
            canal,
        )


        client = EvolutionClient()


        summary = (
            client.find_instance(
                instance_name
            )
        )


        if summary is None:

            client.create_instance(
                instance_name
            )

            summary = (
                client.find_instance(
                    instance_name
                )
            )


        if (
            summary
            and
            summary.get(
                "integration"
            )
            and
            summary.get(
                "integration"
            )
            != "WHATSAPP-BAILEYS"
        ):

            raise ValidationError(
                "La instancia existente "
                "usa una integración "
                "inesperada."
            )


        # --------------------------------------------------------
        # NEGOCIOLISTO-WHATSAPP-TYPEBOT-AUTO-V1
        # --------------------------------------------------------
        #
        # El identificador_externo del Bot sigue siendo
        # el ID editable/interno de Typebot.
        #
        # Evolution utiliza el publicId determinista:
        # tnl-e{empresa}-i{instalacion}.
        #
        # Si la solución no utiliza Typebot,
        # no se crea ninguna integración.
        #

        typebot_internal_id = str(
            canal.bot.identificador_externo
            or ""
        ).strip()

        if typebot_internal_id:

            client.ensure_typebot_integration(
                instance_name
            )


        connected = bool(
            summary
            and
            summary.get("state")
            == "open"
            and
            summary.get(
                "owner_present"
            )
        )


        if connected:

            # TNL-WHATSAPP-CONNECT-AUTO-REBIND-V1
            with transaction.atomic():

                locked = (
                    Canal.objects
                    .select_for_update()
                    .get(
                        pk=canal.pk
                    )
                )


                current_identifier = (
                    locked.identificador
                    or ""
                ).strip()


                if (
                    current_identifier
                    and
                    current_identifier
                    != instance_name
                ):

                    raise ValidationError(
                        "El canal cambió de "
                        "identificador durante "
                        "la vinculación."
                    )


                changed = False


                if (
                    locked.identificador
                    != instance_name
                ):

                    locked.identificador = (
                        instance_name
                    )

                    changed = True


                if not locked.activo:

                    locked.activo = True

                    changed = True


                if changed:

                    locked.save(
                        update_fields=[
                            "identificador",
                            "activo",
                            "actualizado_en",
                        ]
                    )

            return _nl_whatsapp_json(
                {
                    "ok": True,
                    "connected": True,
                    "state": "open",
                    "qr": None,
                }
            )


        connect_data = (
            client.connect_instance(
                instance_name
            )
        )


        qr = (
            client.extract_qr(
                connect_data
            )
        )


        summary = (
            client.find_instance(
                instance_name
            )
        )


        connected = bool(
            summary
            and
            summary.get("state")
            == "open"
            and
            summary.get(
                "owner_present"
            )
        )


        if (
            not connected
            and
            not qr
        ):

            return _nl_whatsapp_json(
                {
                    "ok": False,
                    "message": (
                        "Evolution todavía "
                        "no entregó un QR "
                        "disponible."
                    ),
                    "state": (
                        summary.get(
                            "state"
                        )
                        if summary
                        else "desconocido"
                    ),
                },
                status=409,
            )


        if connected:

            # TNL-WHATSAPP-CONNECT-AUTO-REBIND-V1
            with transaction.atomic():

                locked = (
                    Canal.objects
                    .select_for_update()
                    .get(
                        pk=canal.pk
                    )
                )


                current_identifier = (
                    locked.identificador
                    or ""
                ).strip()


                if (
                    current_identifier
                    and
                    current_identifier
                    != instance_name
                ):

                    raise ValidationError(
                        "El canal cambió de "
                        "identificador durante "
                        "la vinculación."
                    )


                changed = False


                if (
                    locked.identificador
                    != instance_name
                ):

                    locked.identificador = (
                        instance_name
                    )

                    changed = True


                if not locked.activo:

                    locked.activo = True

                    changed = True


                if changed:

                    locked.save(
                        update_fields=[
                            "identificador",
                            "activo",
                            "actualizado_en",
                        ]
                    )

        return _nl_whatsapp_json(
            {
                "ok": True,
                "connected":
                    connected,

                "state": (
                    summary.get(
                        "state"
                    )
                    if summary
                    else "connecting"
                ),

                "qr": (
                    None
                    if connected
                    else qr
                ),
            }
        )


    except ValidationError as exc:

        return _nl_whatsapp_json(
            {
                "ok": False,
                "message":
                    str(exc),
            },
            status=409,
        )


    except EvolutionClientError as exc:

        return _nl_whatsapp_json(
            {
                "ok": False,
                "message":
                    str(exc),
            },
            status=502,
        )


@_nl_login_required
def empresa_whatsapp_estado(
    request,
    pk,
    canal_id,
):

    from django.core.exceptions import (
        ValidationError,
    )

    from django.shortcuts import (
        get_object_or_404,
    )

    from core.integrations.evolution_client import (
        EvolutionClient,
        EvolutionClientError,
    )

    from core.models import (
        Canal,
        Empresa,
    )


    if request.method != "GET":

        return _nl_whatsapp_json(
            {
                "ok": False,
                "message":
                    "Método no permitido.",
            },
            status=405,
        )


    empresa = get_object_or_404(
        Empresa,
        pk=pk,
    )


    canal = get_object_or_404(
        Canal.objects.select_related(
            "bot",
            "bot__empresa",
        ),
        pk=canal_id,
        bot__empresa=empresa,
    )


    try:

        (
            instalacion,
            instance_name,
        ) = _nl_whatsapp_contexto(
            empresa,
            canal,
        )


        client = EvolutionClient()


        summary = (
            client.find_instance(
                instance_name
            )
        )


        if summary is None:

            return _nl_whatsapp_json(
                {
                    "ok": True,
                    "exists": False,
                    "connected": False,
                    "state": "not_created",
                    "channel_active":
                        canal.activo,
                }
            )


        connected = bool(
            summary.get(
                "state"
            )
            == "open"
            and
            summary.get(
                "owner_present"
            )
        )


        payload = {
            "ok": True,
            "exists": True,
            "connected":
                connected,

            "state":
                summary.get(
                    "state"
                ),

            "channel_active":
                canal.activo,
        }


        # TNL-WHATSAPP-MANUAL-RECONNECT-V1
        # La tarjeta del panel pide ?vivo=1: estado VIVO en palabras
        # simples. El flujo del QR no lo pide y queda igual.
        if request.GET.get("vivo") == "1":

            from core.services.whatsapp_watchdog import (
                estado_panel,
            )

            payload["estado_panel"] = estado_panel(
                cliente=client,
                nombre=instance_name,
                metadatos=summary,
            )


        return _nl_whatsapp_json(
            payload
        )


    except ValidationError as exc:

        return _nl_whatsapp_json(
            {
                "ok": False,
                "message":
                    str(exc),
            },
            status=409,
        )


    except EvolutionClientError as exc:

        return _nl_whatsapp_json(
            {
                "ok": False,
                "message":
                    str(exc),
            },
            status=502,
        )


@_nl_login_required
def empresa_whatsapp_activar(
    request,
    pk,
    canal_id,
):

    from django.core.exceptions import (
        ValidationError,
    )

    from django.db import (
        transaction,
    )

    from django.shortcuts import (
        get_object_or_404,
    )

    from core.integrations.evolution_client import (
        EvolutionClient,
        EvolutionClientError,
    )

    from core.models import (
        Canal,
        Empresa,
    )


    if request.method != "POST":

        return _nl_whatsapp_json(
            {
                "ok": False,
                "message":
                    "Método no permitido.",
            },
            status=405,
        )


    empresa = get_object_or_404(
        Empresa,
        pk=pk,
    )


    canal = get_object_or_404(
        Canal.objects.select_related(
            "bot",
            "bot__empresa",
        ),
        pk=canal_id,
        bot__empresa=empresa,
    )


    try:

        (
            instalacion,
            instance_name,
        ) = _nl_whatsapp_contexto(
            empresa,
            canal,
        )


        client = EvolutionClient()


        summary = (
            client.find_instance(
                instance_name
            )
        )


        connected = bool(
            summary
            and
            summary.get(
                "state"
            )
            == "open"
            and
            summary.get(
                "owner_present"
            )
        )


        if not connected:

            return _nl_whatsapp_json(
                {
                    "ok": False,
                    "message": (
                        "WhatsApp todavía "
                        "no está vinculado."
                    ),
                    "state": (
                        summary.get(
                            "state"
                        )
                        if summary
                        else "not_created"
                    ),
                },
                status=409,
            )


        # TNL-WHATSAPP-POLICY-SYNC-ADMIN-V1
        client.sync_negociolisto_typebot_policies(
            debounce_time=3,
            skip_if_owner_fingerprint_seen=False,
        )

        with transaction.atomic():

            locked = (
                Canal.objects
                .select_for_update()
                .get(
                    pk=canal.pk
                )
            )


            current_identifier = (
                locked.identificador
                or ""
            ).strip()


            if (
                current_identifier
                and
                current_identifier
                != instance_name
            ):

                raise ValidationError(
                    "El canal cambió de "
                    "identificador durante "
                    "la vinculación."
                )


            changed = False


            if (
                locked.identificador
                != instance_name
            ):

                locked.identificador = (
                    instance_name
                )

                changed = True


            if not locked.activo:

                locked.activo = True

                changed = True


            if changed:

                locked.save(
                    update_fields=[
                        "identificador",
                        "activo",
                        "actualizado_en",
                    ]
                )


        return _nl_whatsapp_json(
            {
                "ok": True,
                "connected": True,
                "channel_active": True,
                "state": "open",
            }
        )


    except ValidationError as exc:

        return _nl_whatsapp_json(
            {
                "ok": False,
                "message":
                    str(exc),
            },
            status=409,
        )


    except EvolutionClientError as exc:

        return _nl_whatsapp_json(
            {
                "ok": False,
                "message":
                    str(exc),
            },
            status=502,
        )


# ============================================================
# TNL-WHATSAPP-MANUAL-RECONNECT-V1
# ============================================================

_NL_WHATSAPP_RECONECTAR_MENSAJES = {
    "conectado": (
        messages.INFO,
        "WhatsApp ya está conectado.",
    ),
    "reinicio_solicitado": (
        messages.SUCCESS,
        "Se solicitó la reconexión de WhatsApp.",
    ),
    "reconexion_solicitada": (
        messages.SUCCESS,
        "Se solicitó la reconexión de WhatsApp.",
    ),
    "requiere_vinculacion": (
        messages.WARNING,
        "La sesión necesita volver a vincularse mediante QR.",
    ),
    "enfriamiento": (
        messages.WARNING,
        "Ya se solicitó una reconexión recientemente. "
        "Espera unos segundos e intenta nuevamente.",
    ),
    "en_curso": (
        messages.WARNING,
        "Hay una revisión de WhatsApp en curso. "
        "Espera unos segundos e intenta nuevamente.",
    ),
    "canal_inactivo": (
        messages.ERROR,
        "El canal o el cliente no están activos; "
        "WhatsApp no se reconectó.",
    ),
    "canal_no_configurado": (
        messages.ERROR,
        "Este canal de WhatsApp no tiene una instancia configurada.",
    ),
    "error_evolution": (
        messages.ERROR,
        "No fue posible solicitar la reconexión de WhatsApp "
        "en este momento.",
    ),
}

_NL_WHATSAPP_RECONECTAR_NO_DISPONIBLE = (
    messages.ERROR,
    "No fue posible consultar WhatsApp en este momento.",
)


@_nl_login_required
def empresa_whatsapp_reconectar(
    request,
    pk,
    canal_id,
):
    """
    Reconexión manual segura desde el panel (POST).

    La instancia sale del Canal validado (empresa + tipo WhatsApp),
    nunca del navegador. La decisión y el enfriamiento son los del
    watchdog: nunca hace logout, delete ni recrea la instancia.
    """

    from django.http import (
        HttpResponseNotAllowed,
    )

    from core.models import (
        Canal,
        Empresa,
    )

    from core.services.whatsapp_watchdog import (
        reconectar_instancia_manual,
    )


    if request.method != "POST":

        return HttpResponseNotAllowed(
            [
                "POST",
            ]
        )


    empresa = get_object_or_404(
        Empresa,
        pk=pk,
    )


    canal = get_object_or_404(
        Canal.objects.select_related(
            "bot",
            "bot__empresa",
        ),
        pk=canal_id,
        bot__empresa=empresa,
        tipo="whatsapp",
    )


    resultado = reconectar_instancia_manual(
        canal=canal,
    )["resultado"]


    nivel, texto = _NL_WHATSAPP_RECONECTAR_MENSAJES.get(
        resultado,
        _NL_WHATSAPP_RECONECTAR_NO_DISPONIBLE,
    )

    messages.add_message(
        request,
        nivel,
        texto,
    )


    return redirect(
        reverse(
            "core:empresa_detalle",
            args=[
                empresa.pk,
            ],
        )
        +
        "#whatsapp"
    )




# ============================================================
# CLIENTE-PORTAL-V1
# ============================================================

@login_required
def cliente_panel(request):
    """
    Portal principal del cliente.

    La empresa se obtiene EXCLUSIVAMENTE del perfil
    autenticado. No acepta empresa_id desde URL.
    """

    from django.core.exceptions import PermissionDenied
    from django.utils import timezone

    from core.models import (
        Catalogo,
        InstalacionPlantilla,
        Pedido,
        Producto,
    )

    perfil = getattr(
        request.user,
        "perfil_negociolisto",
        None,
    )

    if perfil is None:
        raise PermissionDenied(
            "El usuario no tiene perfil NegocioListo."
        )

    if not perfil.activo:
        raise PermissionDenied(
            "El perfil se encuentra inactivo."
        )

    if (
        perfil.rol
        != PerfilUsuario.Rol.CLIENTE
    ):
        return redirect(
            "core:dashboard"
        )

    if perfil.empresa_id is None:
        raise PermissionDenied(
            "El perfil cliente no tiene empresa asignada."
        )

    empresa = get_object_or_404(
        Empresa,
        pk=perfil.empresa_id,
    )

    hoy = timezone.localdate()

    # --------------------------------------------------------
    # LICENCIAS
    # --------------------------------------------------------

    licencias = list(
        Licencia.objects
        .filter(
            empresa=empresa
        )
        .order_by(
            "-fecha_fin",
            "-id",
        )
    )

    licencia_actual = None

    for licencia in licencias:

        if (
            licencia.estado == "activa"
            and licencia.fecha_inicio <= hoy
            and licencia.fecha_fin >= hoy
        ):
            licencia_actual = licencia
            break

    # --------------------------------------------------------
    # RECURSOS EXCLUSIVOS DE LA EMPRESA
    # --------------------------------------------------------

    instalaciones = list(
        InstalacionPlantilla.objects
        .filter(
            empresa=empresa
        )
        .select_related(
            "plantilla_maestra",
            "plantilla",
        )
        .order_by(
            "-id"
        )
    )

    bots = list(
        Bot.objects
        .filter(
            empresa=empresa
        )
        .select_related(
            "plantilla"
        )
        .order_by(
            "-id"
        )
    )

    canales = list(
        Canal.objects
        .filter(
            bot__empresa=empresa
        )
        .select_related(
            "bot"
        )
        .order_by(
            "-id"
        )
    )

    # TNL-CLIENTE-WHATSAPP-CONTEXT-V1
    canales_whatsapp = [
        canal
        for canal in canales
        if canal.tipo == "whatsapp"
    ]

    catalogos = list(
        Catalogo.objects
        .filter(
            empresa=empresa
        )
        .order_by(
            "-id"
        )
    )

    productos_total = (
        Producto.objects
        .filter(
            catalogo__empresa=empresa
        )
        .count()
    )

    pedidos_qs = (
        Pedido.objects
        .filter(
            empresa=empresa
        )
        .order_by(
            "-id"
        )
    )

    pedidos_total = (
        pedidos_qs.count()
    )

    pedidos_recientes = list(
        pedidos_qs[:5]
    )

    resumen = {
        "instalaciones":
            len(instalaciones),

        "bots":
            len(bots),

        "canales":
            len(canales),

        "canales_activos":
            sum(
                1
                for canal in canales
                if canal.activo
            ),

        "catalogos":
            len(catalogos),

        "productos":
            productos_total,

        "pedidos":
            pedidos_total,
    }

    # --------------------------------------------------------
    # TNL-CLIENTE-MERCADOPAGO-CONTEXT-V1
    # --------------------------------------------------------

    from core.models import (
        ConfiguracionMercadoPago,
    )

    from core.services.mercadopago import (
        oauth_configurado as
        _tnl_mp_oauth_configurado,
    )

    configuracion_mp = (
        ConfiguracionMercadoPago.objects
        .filter(
            empresa=empresa
        )
        .first()
    )

    mp_conectada = bool(
        configuracion_mp
        and
        configuracion_mp.habilitada
        and
        configuracion_mp.estado_conexion
        ==
        ConfiguracionMercadoPago
        .EstadoConexion
        .CONECTADA
    )

    estado_mercadopago = {
        "configurada":
            configuracion_mp is not None,

        "conectada":
            mp_conectada,

        "estado":
            (
                configuracion_mp
                .get_estado_conexion_display()
                if configuracion_mp
                else
                "No conectado"
            ),

        "conectado_en":
            (
                configuracion_mp.conectado_en
                if configuracion_mp
                else
                None
            ),

        "oauth_configurado":
            _tnl_mp_oauth_configurado(),
    }


    # --------------------------------------------------------
    # TNL-CLIENTE-GOOGLE-CALENDAR-CONTEXT-V1
    # --------------------------------------------------------

    from core.models import (
        ConfiguracionGoogleCalendar,
    )

    from core.services.google_calendar_oauth import (
        oauth_configurado as
        _tnl_gc_oauth_configurado,
    )


    configuracion_gc = (
        ConfiguracionGoogleCalendar.objects
        .filter(
            empresa=empresa
        )
        .first()
    )


    gc_conectada = bool(
        configuracion_gc
        and
        configuracion_gc.habilitada
        and
        configuracion_gc.estado_conexion
        ==
        ConfiguracionGoogleCalendar
        .ESTADO_CONECTADA
    )


    estado_google_calendar = {

        "configurada":
            configuracion_gc
            is not None,

        "conectada":
            gc_conectada,

        "estado":
            (
                configuracion_gc
                .get_estado_conexion_display()
                if configuracion_gc
                else
                "No conectado"
            ),

        "cuenta_email":
            (
                configuracion_gc.cuenta_email
                if configuracion_gc
                else
                ""
            ),

        "calendar_nombre":
            (
                configuracion_gc.calendar_nombre
                if configuracion_gc
                else
                ""
            ),

        "zona_horaria":
            (
                configuracion_gc.zona_horaria
                if configuracion_gc
                else
                ""
            ),

        "conectado_en":
            (
                configuracion_gc.conectado_en
                if configuracion_gc
                else
                None
            ),

        "oauth_configurado":
            _tnl_gc_oauth_configurado(),
    }


    context = {
        "perfil_cliente": perfil,
        "empresa": empresa,

        "estado_google_calendar":
            estado_google_calendar,

        "estado_mercadopago":
            estado_mercadopago,
        "hoy": hoy,

        "licencias": licencias,
        "licencia_actual":
            licencia_actual,

        "instalaciones":
            instalaciones,

        "bots": bots,
        "canales": canales,
        "canales_whatsapp":
            canales_whatsapp,
        "catalogos": catalogos,

        "pedidos_recientes":
            pedidos_recientes,

        "resumen": resumen,
    }

    return render(
        request,
        "core/cliente_panel.html",
        context,
    )




# =============================================================================
# TNL-CLIENTE-TERMINOS-VIEWS-V1
# Términos obligatorios antes de la primera vinculación del dueño.
# =============================================================================


def _nl_cliente_perfil_empresa_seguro(
    request,
):

    from django.core.exceptions import (
        PermissionDenied,
    )

    perfil = getattr(
        request.user,
        "perfil_negociolisto",
        None,
    )


    if perfil is None:
        raise PermissionDenied(
            "El usuario no tiene perfil NegocioListo."
        )


    if not perfil.activo:
        raise PermissionDenied(
            "El perfil se encuentra inactivo."
        )


    if (
        perfil.rol
        != PerfilUsuario.Rol.CLIENTE
    ):
        raise PermissionDenied(
            "Esta acción corresponde al cliente principal."
        )


    if perfil.empresa_id is None:
        raise PermissionDenied(
            "El perfil cliente no tiene empresa asignada."
        )


    return (
        perfil,
        perfil.empresa,
    )


@login_required
def cliente_terminos_estado(
    request,
):

    from django.http import (
        JsonResponse,
    )

    from core.services.terminos import (
        TERMINOS_CONTENIDO,
        TERMINOS_SHA256,
        TERMINOS_TITULO,
        TERMINOS_VERSION,
        obtener_aceptacion_empresa,
    )


    if request.method != "GET":

        return JsonResponse(
            {
                "ok": False,
                "codigo":
                    "METODO_NO_PERMITIDO",
                "message":
                    "Método no permitido.",
            },
            status=405,
            json_dumps_params={
                "ensure_ascii": False,
            },
        )


    perfil, empresa = (
        _nl_cliente_perfil_empresa_seguro(
            request
        )
    )


    aceptacion = (
        obtener_aceptacion_empresa(
            empresa
        )
    )


    return JsonResponse(
        {
            "ok": True,

            "aceptados":
                aceptacion is not None,

            "version":
                TERMINOS_VERSION,

            "sha256":
                TERMINOS_SHA256,

            "titulo":
                TERMINOS_TITULO,

            "contenido":
                (
                    ""
                    if aceptacion
                    else TERMINOS_CONTENIDO
                ),

            "empresa_id":
                empresa.pk,

            "aceptado_en":
                (
                    aceptacion
                    .aceptado_en
                    .isoformat()
                    if aceptacion
                    else None
                ),

            "version_aceptada":
                (
                    aceptacion.version
                    if aceptacion
                    else ""
                ),
        },
        json_dumps_params={
            "ensure_ascii": False,
        },
    )


@login_required
def cliente_terminos_aceptar(
    request,
):

    import json

    from django.http import (
        JsonResponse,
    )

    from core.services.terminos import (
        TERMINOS_VERSION,
        TerminosConfiguracionError,
        registrar_aceptacion,
    )


    if request.method != "POST":

        return JsonResponse(
            {
                "ok": False,
                "codigo":
                    "METODO_NO_PERMITIDO",
                "message":
                    "Método no permitido.",
            },
            status=405,
            json_dumps_params={
                "ensure_ascii": False,
            },
        )


    perfil, empresa = (
        _nl_cliente_perfil_empresa_seguro(
            request
        )
    )


    if (
        request.content_type
        and
        "application/json"
        in request.content_type.lower()
    ):

        try:

            datos = json.loads(
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

            return JsonResponse(
                {
                    "ok": False,
                    "codigo":
                        "JSON_INVALIDO",
                    "message":
                        "Solicitud inválida.",
                },
                status=400,
                json_dumps_params={
                    "ensure_ascii": False,
                },
            )

    else:

        datos = request.POST


    acepta_raw = datos.get(
        "acepta"
    )


    acepta = bool(
        acepta_raw is True
        or
        str(
            acepta_raw
            or
            ""
        ).strip().lower()
        in {
            "1",
            "true",
            "on",
            "si",
            "sí",
        }
    )


    if not acepta:

        return JsonResponse(
            {
                "ok": False,
                "codigo":
                    "ACEPTACION_REQUERIDA",
                "message":
                    (
                        "Debes marcar la casilla "
                        "de aceptación para continuar."
                    ),
            },
            status=400,
            json_dumps_params={
                "ensure_ascii": False,
            },
        )


    version = str(
        datos.get(
            "version"
        )
        or
        ""
    ).strip()


    if version != TERMINOS_VERSION:

        return JsonResponse(
            {
                "ok": False,
                "codigo":
                    "VERSION_TERMINOS_INVALIDA",
                "message":
                    (
                        "La versión de los términos "
                        "no es válida. Actualiza la página."
                    ),
            },
            status=409,
            json_dumps_params={
                "ensure_ascii": False,
            },
        )


    origen = str(
        datos.get(
            "origen"
        )
        or
        ""
    ).strip()


    try:

        aceptacion, creada = (
            registrar_aceptacion(
                empresa=empresa,
                perfil=perfil,
                request=request,
                origen=origen,
            )
        )


    except ValueError as exc:

        return JsonResponse(
            {
                "ok": False,
                "codigo":
                    "DATOS_ACEPTACION_INVALIDOS",
                "message":
                    str(exc),
            },
            status=400,
            json_dumps_params={
                "ensure_ascii": False,
            },
        )


    except TerminosConfiguracionError:

        return JsonResponse(
            {
                "ok": False,
                "codigo":
                    "TERMINOS_CONFIGURACION_ERROR",
                "message":
                    (
                        "No fue posible registrar "
                        "la aceptación en este momento."
                    ),
            },
            status=500,
            json_dumps_params={
                "ensure_ascii": False,
            },
        )


    return JsonResponse(
        {
            "ok": True,

            "aceptados":
                True,

            "creada":
                creada,

            "aceptacion_id":
                aceptacion.pk,

            "version":
                aceptacion.version,

            "aceptado_en":
                aceptacion
                .aceptado_en
                .isoformat(),

            "message":
                (
                    "Términos y Condiciones "
                    "aceptados correctamente."
                    if creada
                    else
                    "Los Términos y Condiciones "
                    "ya habían sido aceptados."
                ),
        },
        json_dumps_params={
            "ensure_ascii": False,
        },
    )


# =============================================================================
# TNL-MERCADOPAGO-CLIENTE-OAUTH-V1
# OAuth individual por empresa desde el portal cliente.
# =============================================================================

_TNL_MP_SESSION_STATE = (
    "tnl_mercadopago_oauth_state"
)

_TNL_MP_SESSION_EMPRESA = (
    "tnl_mercadopago_oauth_empresa_id"
)

_TNL_MP_SESSION_ISSUED = (
    "tnl_mercadopago_oauth_issued_at"
)

_TNL_MP_SESSION_CODE_VERIFIER = (
    "tnl_mercadopago_oauth_code_verifier"
)

# Mercado Pago documenta 10 minutos para el authorization code.
_TNL_MP_OAUTH_TTL_SECONDS = 600


def _tnl_mp_limpiar_sesion(
    request,
):

    for key in (
        _TNL_MP_SESSION_STATE,
        _TNL_MP_SESSION_EMPRESA,
        _TNL_MP_SESSION_ISSUED,
        _TNL_MP_SESSION_CODE_VERIFIER,
    ):

        request.session.pop(
            key,
            None,
        )


def _tnl_mp_cliente_empresa(
    request,
):

    from django.core.exceptions import (
        PermissionDenied,
    )

    perfil = getattr(
        request.user,
        "perfil_negociolisto",
        None,
    )

    if perfil is None:
        raise PermissionDenied(
            "El usuario no tiene perfil NegocioListo."
        )

    if not perfil.activo:
        raise PermissionDenied(
            "El perfil se encuentra inactivo."
        )

    if (
        perfil.rol
        !=
        PerfilUsuario.Rol.CLIENTE
    ):
        raise PermissionDenied(
            "Esta acción corresponde al portal cliente."
        )

    if perfil.empresa_id is None:
        raise PermissionDenied(
            "El perfil cliente no tiene empresa asignada."
        )

    return get_object_or_404(
        Empresa,
        pk=perfil.empresa_id,
    )


def _tnl_mp_cliente_url():

    return (
        reverse(
            "core:cliente_panel"
        )
        +
        "#mercado-pago"
    )


@login_required
def cliente_mercadopago_conectar(
    request,
):

    import logging
    import time

    from django.contrib import messages
    from django.http import HttpResponseNotAllowed

    from core.services.mercadopago import (
        construir_url_autorizacion,
        generar_estado_oauth,
        generar_pkce,
        oauth_configurado,
    )

    if request.method != "POST":

        return HttpResponseNotAllowed(
            [
                "POST"
            ]
        )

    empresa = _tnl_mp_cliente_empresa(
        request
    )

    destino = _tnl_mp_cliente_url()

    # TNL-MERCADOPAGO-CLIENTE-TERMINOS-GUARD-V1
    from core.services.terminos import (
        TerminosNoAceptadosError,
        requerir_terminos_aceptados,
    )


    try:

        requerir_terminos_aceptados(
            empresa
        )

    except TerminosNoAceptadosError:

        messages.warning(
            request,
            (
                "Debes aceptar los Términos y "
                "Condiciones antes de vincular "
                "Mercado Pago."
            ),
        )

        return redirect(
            destino
        )


    if not oauth_configurado():

        messages.error(
            request,
            (
                "Mercado Pago todavía no está "
                "disponible para conexión."
            ),
        )

        return redirect(
            destino
        )

    _tnl_mp_limpiar_sesion(
        request
    )

    try:

        state = generar_estado_oauth()

        (
            code_verifier,
            code_challenge,
        ) = generar_pkce()

        authorization_url = (
            construir_url_autorizacion(
                state=state,
                code_challenge=
                    code_challenge,
            )
        )

    except Exception as exc:

        logging.getLogger(
            "negociolisto.mercadopago"
        ).error(
            (
                "TNL_MP_OAUTH_PREP_FAIL "
                "empresa=%s exception=%s"
            ),
            empresa.pk,
            type(exc).__name__,
        )

        messages.error(
            request,
            (
                "No fue posible preparar la "
                "conexión con Mercado Pago."
            ),
        )

        return redirect(
            destino
        )

    request.session[
        _TNL_MP_SESSION_STATE
    ] = state

    request.session[
        _TNL_MP_SESSION_EMPRESA
    ] = empresa.pk

    request.session[
        _TNL_MP_SESSION_ISSUED
    ] = time.time()

    request.session[
        _TNL_MP_SESSION_CODE_VERIFIER
    ] = code_verifier

    request.session.modified = True

    return redirect(
        authorization_url
    )


@login_required
def mercadopago_oauth_callback(
    request,
):

    import logging
    import secrets
    import time

    from datetime import timedelta

    from django.contrib import messages
    from django.utils import timezone

    from core.models import (
        ConfiguracionMercadoPago,
    )

    from core.services.mercadopago import (
        MercadoPagoOAuthError,
        cifrar_secreto,
        intercambiar_codigo_oauth,
    )

    destino = _tnl_mp_cliente_url()

    empresa = _tnl_mp_cliente_empresa(
        request
    )

    from core.services.terminos import (
        TerminosNoAceptadosError,
        requerir_terminos_aceptados,
    )


    try:

        requerir_terminos_aceptados(
            empresa
        )

    except TerminosNoAceptadosError:

        _tnl_mp_limpiar_sesion(
            request
        )

        messages.warning(
            request,
            (
                "Debes aceptar los Términos "
                "y Condiciones antes de "
                "vincular Mercado Pago."
            ),
        )

        return redirect(
            destino
        )


    expected_state = (
        request.session.get(
            _TNL_MP_SESSION_STATE
        )
    )

    empresa_id = (
        request.session.get(
            _TNL_MP_SESSION_EMPRESA
        )
    )

    issued_at = (
        request.session.get(
            _TNL_MP_SESSION_ISSUED
        )
    )

    code_verifier = (
        request.session.get(
            _TNL_MP_SESSION_CODE_VERIFIER
        )
    )

    received_state = str(
        request.GET.get(
            "state",
            "",
        )
        or ""
    )

    empresa_valida = bool(
        empresa_id
        and
        str(empresa_id)
        ==
        str(empresa.pk)
    )

    state_valido = bool(
        expected_state
        and
        received_state
        and
        secrets.compare_digest(
            str(expected_state),
            received_state,
        )
    )

    tiempo_valido = False

    try:

        edad = (
            time.time()
            -
            float(issued_at)
        )

        tiempo_valido = (
            0
            <= edad
            <= _TNL_MP_OAUTH_TTL_SECONDS
        )

    except (
        TypeError,
        ValueError,
    ):

        tiempo_valido = False

    verifier_valido = bool(
        isinstance(
            code_verifier,
            str,
        )
        and
        43
        <= len(code_verifier)
        <= 128
    )

    if (
        not empresa_valida
        or
        not state_valido
        or
        not tiempo_valido
        or
        not verifier_valido
    ):

        _tnl_mp_limpiar_sesion(
            request
        )

        messages.error(
            request,
            (
                "La validación de seguridad "
                "de Mercado Pago falló o expiró. "
                "Intenta conectar nuevamente."
            ),
        )

        return redirect(
            destino
        )

    oauth_error = str(
        request.GET.get(
            "error",
            "",
        )
        or ""
    ).strip()

    if oauth_error:

        _tnl_mp_limpiar_sesion(
            request
        )

        if oauth_error == "access_denied":

            messages.warning(
                request,
                (
                    "La autorización de Mercado Pago "
                    "fue cancelada."
                ),
            )

        else:

            messages.error(
                request,
                (
                    "Mercado Pago no completó "
                    "la autorización."
                ),
            )

        return redirect(
            destino
        )

    code = str(
        request.GET.get(
            "code",
            "",
        )
        or ""
    ).strip()

    if not code:

        _tnl_mp_limpiar_sesion(
            request
        )

        messages.error(
            request,
            (
                "Mercado Pago no devolvió "
                "un código de autorización."
            ),
        )

        return redirect(
            destino
        )

    # State y PKCE pasan a ser de un solo uso.
    _tnl_mp_limpiar_sesion(
        request
    )

    oauth_etapa = "inicio"

    try:

        oauth_etapa = "intercambiar_codigo"

        token_data = (
            intercambiar_codigo_oauth(
                code=code,
                code_verifier=
                    code_verifier,
            )
        )

        oauth_etapa = "validar_respuesta"

        access_token = str(
            token_data.get(
                "access_token"
            )
            or ""
        ).strip()

        refresh_token = str(
            token_data.get(
                "refresh_token"
            )
            or ""
        ).strip()

        mp_user_id = str(
            token_data.get(
                "user_id"
            )
            or ""
        ).strip()

        expires_raw = (
            token_data.get(
                "expires_in"
            )
        )

        expires_in = int(
            expires_raw
        )

        if not access_token:
            raise MercadoPagoOAuthError(
                "Access Token ausente."
            )

        if not mp_user_id:
            raise MercadoPagoOAuthError(
                "User ID ausente."
            )

        if expires_in <= 0:
            raise MercadoPagoOAuthError(
                "Expiración inválida."
            )

        existente = (
            ConfiguracionMercadoPago.objects
            .filter(
                empresa=empresa
            )
            .first()
        )

        refresh_token_cifrado = ""

        if existente is not None:

            refresh_token_cifrado = (
                existente
                .refresh_token_cifrado
                or ""
            )

        if refresh_token:

            refresh_token_cifrado = (
                cifrar_secreto(
                    refresh_token
                )
            )

        if not refresh_token_cifrado:

            raise MercadoPagoOAuthError(
                "Refresh Token ausente."
            )

        oauth_etapa = "cifrar_tokens"

        access_token_cifrado = (
            cifrar_secreto(
                access_token
            )
        )

        token_expira_en = (
            timezone.now()
            +
            timedelta(
                seconds=expires_in
            )
        )

        oauth_etapa = "guardar_bd"

        # TNL-MERCADOPAGO-CALLBACK-TERMINOS-GUARD-V1
        requerir_terminos_aceptados(
            empresa
        )


        with transaction.atomic():

            config = (
                ConfiguracionMercadoPago.objects
                .select_for_update()
                .filter(
                    empresa=empresa
                )
                .first()
            )

            if config is None:

                config = (
                    ConfiguracionMercadoPago(
                        empresa=empresa,
                        modo=(
                            ConfiguracionMercadoPago
                            .Modo
                            .PRODUCCION
                        ),
                    )
                )

            config.modo = (
                ConfiguracionMercadoPago
                .Modo
                .PRODUCCION
            )

            config.estado_conexion = (
                ConfiguracionMercadoPago
                .EstadoConexion
                .CONECTADA
            )

            config.habilitada = True

            config.mp_user_id = (
                mp_user_id
            )

            config.access_token_cifrado = (
                access_token_cifrado
            )

            config.refresh_token_cifrado = (
                refresh_token_cifrado
            )

            config.token_expira_en = (
                token_expira_en
            )

            config.conectado_en = (
                timezone.now()
            )

            config.ultima_validacion_en = (
                timezone.now()
            )

            config.ultimo_error = ""

            config.save()

        messages.success(
            request,
            (
                "Mercado Pago se conectó "
                "correctamente a tu empresa."
            ),
        )

    except Exception as exc:

        logging.getLogger(
            "negociolisto.mercadopago"
        ).error(
            (
                "TNL_MP_OAUTH_FAIL "
                "empresa=%s etapa=%s exception=%s"
            ),
            empresa.pk,
            oauth_etapa,
            type(exc).__name__,
        )

        # Importante:
        # una reconexión fallida NO borra los
        # tokens válidos existentes.
        messages.error(
            request,
            (
                "No fue posible completar "
                "la conexión con Mercado Pago. "
                "Puedes intentarlo nuevamente."
            ),
        )

    return redirect(
        destino
    )


# ============================================================================
# TNL-ROLE-SECURITY-V2
#
# Seguridad de acceso:
# - Administrador: back-office.
# - Cliente: portal propio.
# - Operador: cerrado temporalmente hasta aislamiento empresarial.
#
# Los guards se aplican desde core/urls.py.
# ============================================================================

from functools import wraps as _nl_role_wraps

from django.contrib.auth.decorators import (
    login_required as _nl_role_login_required,
)

from django.http import (
    HttpResponseForbidden as
    _nl_HttpResponseForbidden,
)


def _nl_perfil_request(
    request,
):
    """
    Devuelve únicamente perfiles NegocioListo activos.
    """

    from core.models import (
        PerfilUsuario,
    )

    try:

        perfil = (
            request.user
            .perfil_negociolisto
        )

    except (
        PerfilUsuario.DoesNotExist,
        AttributeError,
    ):

        return None


    if not perfil.activo:
        return None


    return perfil


def _nl_admin_required(
    view_func,
):
    """
    Back-office exclusivo de Administrador.

    Superuser se conserva como acceso de emergencia
    administrativo.
    """

    @_nl_role_wraps(
        view_func
    )
    def role_guard(
        request,
        *args,
        **kwargs,
    ):

        from core.models import (
            PerfilUsuario,
        )


        if getattr(
            request.user,
            "is_superuser",
            False,
        ):

            return view_func(
                request,
                *args,
                **kwargs,
            )


        perfil = (
            _nl_perfil_request(
                request
            )
        )


        if (
            perfil is None
            or
            perfil.rol
            != PerfilUsuario.Rol.ADMINISTRADOR
        ):

            return _nl_HttpResponseForbidden(
                "Acceso no autorizado."
            )


        return view_func(
            request,
            *args,
            **kwargs,
        )


    wrapped = (
        _nl_role_login_required(
            role_guard
        )
    )

    wrapped._nl_role_security = (
        "administrador"
    )

    return wrapped


def _nl_dashboard_required(
    view_func,
):
    """
    Entrada principal:

    Administrador -> dashboard.
    Cliente       -> Mi Negocio.
    Operador      -> cerrado temporalmente.
    """

    @_nl_role_wraps(
        view_func
    )
    def role_guard(
        request,
        *args,
        **kwargs,
    ):

        from django.shortcuts import (
            redirect,
        )

        from core.models import (
            PerfilUsuario,
        )


        if getattr(
            request.user,
            "is_superuser",
            False,
        ):

            return view_func(
                request,
                *args,
                **kwargs,
            )


        perfil = (
            _nl_perfil_request(
                request
            )
        )


        if perfil is None:

            return _nl_HttpResponseForbidden(
                "Acceso no autorizado."
            )


        if (
            perfil.rol
            == PerfilUsuario.Rol.CLIENTE
        ):

            return redirect(
                "core:cliente_panel"
            )


        if (
            perfil.rol
            != PerfilUsuario.Rol.ADMINISTRADOR
        ):

            return _nl_HttpResponseForbidden(
                "Acceso no autorizado."
            )


        return view_func(
            request,
            *args,
            **kwargs,
        )


    wrapped = (
        _nl_role_login_required(
            role_guard
        )
    )

    wrapped._nl_role_security = (
        "dashboard"
    )

    return wrapped


def _nl_cliente_whatsapp_canal(
    request,
    canal_id,
):
    """
    Resuelve un canal WhatsApp únicamente de la
    empresa asociada al Cliente autenticado.

    No consulta Evolution.
    No escribe en BD.
    """

    from django.core.exceptions import (
        PermissionDenied,
        ValidationError,
    )

    from django.shortcuts import (
        get_object_or_404,
    )

    from core.models import (
        Canal,
        PerfilUsuario,
    )


    perfil = (
        _nl_perfil_request(
            request
        )
    )


    if (
        perfil is None
        or
        perfil.rol
        != PerfilUsuario.Rol.CLIENTE
    ):

        raise PermissionDenied(
            "Acceso exclusivo del Cliente."
        )


    if perfil.empresa_id is None:

        raise PermissionDenied(
            "El Cliente no tiene empresa asignada."
        )


    canal = get_object_or_404(
        Canal.objects
        .select_related(
            "bot",
            "bot__empresa",
        ),
        pk=canal_id,
        tipo="whatsapp",
        bot__empresa_id=
            perfil.empresa_id,
    )


    # --------------------------------------------------------
    # La instancia debe proceder del contrato NegocioListo.
    #
    # Para canales nuevos todavía sin identificador,
    # _nl_whatsapp_contexto puede derivar:
    #
    # tnl-e{empresa}-i{instalacion}
    #
    # Si existe un identificador antiguo incompatible,
    # se falla cerrado y NO se utiliza para self-service.
    # --------------------------------------------------------

    instance_name = ""

    try:

        (
            _instalacion,
            expected_instance,
        ) = _nl_whatsapp_contexto(
            perfil.empresa,
            canal,
        )

        instance_name = (
            expected_instance
            or ""
        ).strip()

    except ValidationError:

        instance_name = ""


    return (
        perfil,
        canal,
        instance_name,
    )


@_nl_role_login_required
def cliente_whatsapp_estado(
    request,
    canal_id,
):
    """
    Consulta únicamente el estado de una instancia
    previamente preparada por Administración.

    CERO escrituras.
    """

    from core.integrations.evolution_client import (
        EvolutionClient,
        EvolutionClientError,
    )


    if request.method != "GET":

        return _nl_whatsapp_json(
            {
                "ok": False,
                "message":
                    "Método no permitido.",
            },
            status=405,
        )


    (
        _perfil,
        canal,
        instance_name,
    ) = _nl_cliente_whatsapp_canal(
        request,
        canal_id,
    )


    if not instance_name:

        return _nl_whatsapp_json(
            {
                "ok": True,
                "prepared": False,
                "connected": False,
                "state": "not_prepared",
                "channel_active":
                    canal.activo,
            }
        )


    try:

        client = EvolutionClient()

        summary = (
            client.find_instance(
                instance_name
            )
        )


        if summary is None:

            return _nl_whatsapp_json(
                {
                    "ok": True,
                    "prepared": False,
                    "connected": False,
                    "state":
                        "instance_missing",
                    "channel_active":
                        canal.activo,
                }
            )


        connected = bool(
            summary.get("state")
            == "open"
            and
            summary.get(
                "owner_present"
            )
        )

        if connected:
            # TNL-WHATSAPP-POLICY-SYNC-CLIENT-STATUS-V1
            client.sync_negociolisto_typebot_policies(
                debounce_time=3,
                skip_if_owner_fingerprint_seen=True,
            )


        return _nl_whatsapp_json(
            {
                "ok": True,
                "prepared": True,
                "connected":
                    connected,
                "state":
                    summary.get(
                        "state"
                    ),
                "channel_active":
                    canal.activo,
            }
        )


    except EvolutionClientError:

        return _nl_whatsapp_json(
            {
                "ok": False,
                "message": (
                    "No fue posible consultar "
                    "el estado de WhatsApp."
                ),
            },
            status=502,
        )


@_nl_role_login_required
def cliente_whatsapp_qr(
    request,
    canal_id,
):
    """
    Obtiene únicamente el QR de una instancia
    YA PREPARADA.

    Esta vista NO puede:
    - crear instancia;
    - configurar Typebot;
    - activar Canal;
    - modificar Empresa;
    - modificar Bot.
    """

    from core.integrations.evolution_client import (
        EvolutionClient,
        EvolutionClientError,
    )


    if request.method != "POST":

        return _nl_whatsapp_json(
            {
                "ok": False,
                "message":
                    "Método no permitido.",
            },
            status=405,
        )


    # TNL-CLIENTE-INTEGRACIONES-TERMINOS-GUARD-V1
    from core.services.terminos import (
        TerminosNoAceptadosError,
        requerir_terminos_aceptados,
    )


    (
        _perfil_seguro,
        empresa_segura,
    ) = (
        _nl_cliente_perfil_empresa_seguro(
            request
        )
    )


    try:

        requerir_terminos_aceptados(
            empresa_segura
        )

    except TerminosNoAceptadosError:

        return _nl_whatsapp_json(
            {
                "ok": False,
                "codigo":
                    "TERMINOS_REQUERIDOS",
                "terminos_requeridos":
                    True,
                "message": (
                    "Debes aceptar los Términos "
                    "y Condiciones antes de "
                    "vincular WhatsApp."
                ),
            },
            status=428,
        )


    (
        _perfil,
        _canal,
        instance_name,
    ) = _nl_cliente_whatsapp_canal(
        request,
        canal_id,
    )


    if not instance_name:

        return _nl_whatsapp_json(
            {
                "ok": False,
                "prepared": False,
                "message": (
                    "WhatsApp todavía no ha "
                    "sido preparado por el "
                    "administrador."
                ),
            },
            status=409,
        )


    try:

        client = EvolutionClient()


        summary = (
            client.find_instance(
                instance_name
            )
        )


        if summary is None:

            return _nl_whatsapp_json(
                {
                    "ok": False,
                    "prepared": False,
                    "message": (
                        "WhatsApp todavía no ha "
                        "sido preparado por el "
                        "administrador."
                    ),
                },
                status=409,
            )


        connected = bool(
            summary.get("state")
            == "open"
            and
            summary.get(
                "owner_present"
            )
        )

        if connected:
            # TNL-WHATSAPP-POLICY-SYNC-CLIENT-QR-V1-1
            client.sync_negociolisto_typebot_policies(
                debounce_time=3,
                skip_if_owner_fingerprint_seen=True,
            )


        if connected:

            return _nl_whatsapp_json(
                {
                    "ok": True,
                    "prepared": True,
                    "connected": True,
                    "state": "open",
                    "qr": None,
                }
            )


        connect_data = (
            client.connect_instance(
                instance_name
            )
        )


        qr = (
            client.extract_qr(
                connect_data
            )
        )


        summary = (
            client.find_instance(
                instance_name
            )
        )


        connected = bool(
            summary
            and
            summary.get("state")
            == "open"
            and
            summary.get(
                "owner_present"
            )
        )

        if connected:
            # TNL-WHATSAPP-POLICY-SYNC-CLIENT-QR-V1-2
            client.sync_negociolisto_typebot_policies(
                debounce_time=3,
                skip_if_owner_fingerprint_seen=True,
            )


        if (
            not connected
            and
            not qr
        ):

            return _nl_whatsapp_json(
                {
                    "ok": False,
                    "prepared": True,
                    "connected": False,
                    "message": (
                        "WhatsApp no entregó "
                        "un QR disponible."
                    ),
                },
                status=409,
            )


        return _nl_whatsapp_json(
            {
                "ok": True,
                "prepared": True,
                "connected":
                    connected,
                "state": (
                    summary.get(
                        "state"
                    )
                    if summary
                    else "connecting"
                ),
                "qr": (
                    None
                    if connected
                    else qr
                ),
            }
        )


    except EvolutionClientError:

        return _nl_whatsapp_json(
            {
                "ok": False,
                "message": (
                    "No fue posible obtener "
                    "el código QR de WhatsApp."
                ),
            },
            status=502,
        )


# ============================================================================
# TNL-MERCADOPAGO-CONFIG-VIEW-V1
# Configuración administrativa NO sensible.
# ============================================================================

@login_required
def empresa_mercadopago_configurar(
    request,
    pk,
):

    from django.contrib import (
        messages as
        _tnl_mp_messages,
    )

    from django.db import (
        transaction as
        _tnl_mp_transaction,
    )

    from django.shortcuts import (
        get_object_or_404 as
        _tnl_mp_get_object_or_404,

        redirect as
        _tnl_mp_redirect,

        render as
        _tnl_mp_render,
    )

    from django.urls import (
        reverse as
        _tnl_mp_reverse,
    )

    from core.forms import (
        ConfiguracionMercadoPagoForm,
    )

    from core.models import (
        ConfiguracionMercadoPago,
        Empresa,
    )


    empresa = (
        _tnl_mp_get_object_or_404(
            Empresa,
            pk=pk,
        )
    )


    configuracion = (
        ConfiguracionMercadoPago.objects
        .filter(
            empresa=empresa
        )
        .first()
    )


    if request.method == "POST":

        form = (
            ConfiguracionMercadoPagoForm(
                request.POST,
                configuracion=
                    configuracion,
            )
        )


        if form.is_valid():

            modo = (
                form.cleaned_data[
                    "modo"
                ]
            )


            with (
                _tnl_mp_transaction.atomic()
            ):

                actual = (
                    ConfiguracionMercadoPago
                    .objects
                    .select_for_update()
                    .filter(
                        empresa=empresa
                    )
                    .first()
                )


                if actual is None:

                    actual = (
                        ConfiguracionMercadoPago
                        .objects
                        .create(
                            empresa=empresa,
                            modo=modo,
                            habilitada=False,
                            estado_conexion=(
                                ConfiguracionMercadoPago
                                .EstadoConexion
                                .DESCONECTADA
                            ),
                        )
                    )


                elif (
                    actual.estado_conexion
                    ==
                    ConfiguracionMercadoPago
                    .EstadoConexion
                    .CONECTADA
                    and
                    actual.modo
                    != modo
                ):

                    form.add_error(
                        "modo",
                        (
                            "La cuenta está conectada. "
                            "Desconéctala antes de "
                            "cambiar el ambiente."
                        ),
                    )


                elif actual.modo != modo:

                    actual.modo = modo

                    actual.save(
                        update_fields=[
                            "modo",
                            "actualizado_en",
                        ]
                    )


            if not form.errors:

                _tnl_mp_messages.success(
                    request,
                    (
                        "Configuración de Mercado Pago "
                        "guardada correctamente."
                    ),
                )


                return _tnl_mp_redirect(
                    (
                        _tnl_mp_reverse(
                            "core:empresa_detalle",
                            kwargs={
                                "pk":
                                    empresa.pk,
                            },
                        )
                        + "#pasarela-pagos"
                    )
                )


            configuracion = (
                ConfiguracionMercadoPago.objects
                .filter(
                    empresa=empresa
                )
                .first()
            )


    else:

        form = (
            ConfiguracionMercadoPagoForm(
                configuracion=
                    configuracion,
            )
        )


    return _tnl_mp_render(
        request,
        "core/mercadopago_config_form.html",
        {
            "empresa":
                empresa,

            "configuracion":
                configuracion,

            "form":
                form,
        },
    )




# =============================================================================
# TNL-IA-ACTIVAR-BOLSA-VIEW-V1
# Sólo Administración.
# =============================================================================


def empresa_ia_activar_bolsa(
    request,
    pk,
):

    from django.contrib import messages as django_messages
    from django.http import HttpResponseNotAllowed
    from django.shortcuts import (
        get_object_or_404,
        redirect,
    )
    from django.urls import reverse

    from core.models import Empresa

    from core.services.ia_bolsa import (
        BolsaIAActivaError,
        BolsaIACantidadInvalidaError,
        TAMANO_BOLSA_BASE,
        activar_nueva_bolsa,
    )


    if request.method != "POST":

        return HttpResponseNotAllowed(
            [
                "POST",
            ]
        )


    empresa = get_object_or_404(
        Empresa,
        pk=pk,
    )


    cantidad = request.POST.get(
        "cantidad_palabras",
        TAMANO_BOLSA_BASE,
    )


    try:

        bolsa = activar_nueva_bolsa(
            empresa_id=empresa.id,
            cantidad_palabras=cantidad,
            notas=(
                "Bolsa activada manualmente "
                "desde Administración."
            ),
        )


    except BolsaIACantidadInvalidaError as exc:

        django_messages.error(
            request,
            str(exc),
        )


    except BolsaIAActivaError:

        django_messages.warning(
            request,
            (
                "La empresa ya cuenta "
                "con una bolsa de IA activa."
            ),
        )


    else:

        django_messages.success(
            request,
            (
                "Nueva bolsa de "
                f"{bolsa.cantidad_palabras:,} "
                "palabras activada correctamente."
            ),
        )


    return redirect(
        reverse(
            "core:empresa_detalle",
            args=[
                empresa.id,
            ],
        )
        +
        "#inteligencia-artificial"
    )


# =============================================================================
# TNL-IA-BOLSA-EDITAR-ADMIN-V1
# Sólo Administración.
# =============================================================================

def empresa_ia_actualizar_bolsa(
    request,
    pk,
):

    from django.contrib import messages as django_messages
    from django.http import HttpResponseNotAllowed
    from django.shortcuts import (
        get_object_or_404,
        redirect,
    )
    from django.urls import reverse

    from core.models import Empresa

    from core.services.ia_bolsa import (
        BolsaIACantidadInvalidaError,
        BolsaIASinActivaError,
        actualizar_bolsa_activa,
    )


    if request.method != "POST":

        return HttpResponseNotAllowed(
            [
                "POST",
            ]
        )


    empresa = get_object_or_404(
        Empresa,
        pk=pk,
    )


    try:

        bolsa = actualizar_bolsa_activa(
            empresa_id=empresa.id,
            cantidad_palabras=
                request.POST.get(
                    "cantidad_palabras",
                    "",
                ),
        )


    except BolsaIACantidadInvalidaError as exc:

        django_messages.error(
            request,
            str(exc),
        )


    except BolsaIASinActivaError:

        django_messages.warning(
            request,
            (
                "La empresa no cuenta "
                "con una bolsa activa editable."
            ),
        )


    else:

        django_messages.success(
            request,
            (
                "Bolsa actualizada: "
                f"{bolsa.cantidad_palabras:,} "
                "palabras asignadas, "
                f"{bolsa.palabras_consumidas:,} "
                "consumidas y "
                f"{bolsa.palabras_disponibles:,} "
                "disponibles."
            ),
        )


    return redirect(
        reverse(
            "core:empresa_detalle",
            args=[
                empresa.id,
            ],
        )
        +
        "#inteligencia-artificial"
    )



# =============================================================================
# TNL-GOOGLE-CALENDAR-OAUTH-V1
# Conexión OAuth individual por empresa.
# =============================================================================

_TNL_GC_SESSION_STATE = (
    "tnl_google_calendar_oauth_state"
)

_TNL_GC_SESSION_EMPRESA = (
    "tnl_google_calendar_oauth_empresa_id"
)

_TNL_GC_SESSION_ISSUED = (
    "tnl_google_calendar_oauth_issued_at"
)

# TNL-GOOGLE-CALENDAR-PKCE-SESSION-V1
_TNL_GC_SESSION_CODE_VERIFIER = (
    "tnl_google_calendar_oauth_code_verifier"
)

_TNL_GC_OAUTH_TTL_SECONDS = 900


# TNL-GOOGLE-CALENDAR-OAUTH-ACTOR-SESSION-V1
_TNL_GC_SESSION_USER = (
    "tnl_google_calendar_oauth_user_id"
)

_TNL_GC_SESSION_ORIGEN = (
    "tnl_google_calendar_oauth_origen"
)


def _tnl_google_calendar_limpiar_sesion(
    request,
):

    for key in (
        _TNL_GC_SESSION_STATE,
        _TNL_GC_SESSION_EMPRESA,
        _TNL_GC_SESSION_ISSUED,
        _TNL_GC_SESSION_CODE_VERIFIER,
        _TNL_GC_SESSION_USER,
        _TNL_GC_SESSION_ORIGEN,
    ):

        request.session.pop(
            key,
            None,
        )


def _tnl_google_calendar_empresa_url(
    empresa,
):

    return (
        reverse(
            "core:empresa_detalle",
            args=[
                empresa.pk
            ],
        )
        +
        "#google-calendar"
    )


def empresa_google_calendar_conectar(
    request,
    pk,
):

    import time

    from django.contrib import messages

    from core.services.google_calendar_oauth import (
        GoogleCalendarConfiguracionError,
        generar_url_autorizacion,
        oauth_configurado,
    )


    empresa = get_object_or_404(
        Empresa,
        pk=pk,
    )


    destino = (
        _tnl_google_calendar_empresa_url(
            empresa
        )
    )


    if not oauth_configurado():

        messages.error(
            request,
            (
                "Las credenciales OAuth de "
                "Google Calendar no están "
                "configuradas."
            ),
        )

        return redirect(
            destino
        )


    _tnl_google_calendar_limpiar_sesion(
        request
    )


    try:

        (
            authorization_url,
            state,
            code_verifier,
        ) = generar_url_autorizacion()

    except GoogleCalendarConfiguracionError:

        messages.error(
            request,
            (
                "No fue posible preparar "
                "Google Calendar. Revisa la "
                "configuración OAuth."
            ),
        )

        return redirect(
            destino
        )


    if not state:

        messages.error(
            request,
            (
                "Google OAuth no generó un "
                "estado de seguridad válido."
            ),
        )

        return redirect(
            destino
        )


    if not code_verifier:

        messages.error(
            request,
            (
                "Google OAuth no generó la "
                "verificación PKCE necesaria."
            ),
        )

        return redirect(
            destino
        )


    request.session[
        _TNL_GC_SESSION_STATE
    ] = state

    request.session[
        _TNL_GC_SESSION_EMPRESA
    ] = empresa.pk

    request.session[
        _TNL_GC_SESSION_ISSUED
    ] = time.time()

    request.session[
        _TNL_GC_SESSION_CODE_VERIFIER
    ] = code_verifier

    request.session[
        _TNL_GC_SESSION_USER
    ] = request.user.pk

    request.session[
        _TNL_GC_SESSION_ORIGEN
    ] = "admin"

    request.session.modified = True


    return redirect(
        authorization_url
    )



# =============================================================================
# TNL-CLIENTE-GOOGLE-CALENDAR-OAUTH-V1
# El dueño sólo puede vincular Google Calendar de SU empresa.
# =============================================================================


def _tnl_google_calendar_cliente_url():

    from django.urls import reverse

    return (
        reverse(
            "core:cliente_panel"
        )
        +
        "#google-calendar"
    )


@login_required
def cliente_google_calendar_conectar(
    request,
):

    import time

    from django.contrib import messages
    from django.http import HttpResponseNotAllowed

    from core.services.google_calendar_oauth import (
        GoogleCalendarConfiguracionError,
        generar_url_autorizacion,
        oauth_configurado,
    )

    from core.services.terminos import (
        TerminosNoAceptadosError,
        requerir_terminos_aceptados,
    )


    if request.method != "POST":

        return HttpResponseNotAllowed(
            [
                "POST"
            ]
        )


    (
        _perfil,
        empresa,
    ) = (
        _nl_cliente_perfil_empresa_seguro(
            request
        )
    )


    destino = (
        _tnl_google_calendar_cliente_url()
    )


    try:

        requerir_terminos_aceptados(
            empresa
        )

    except TerminosNoAceptadosError:

        messages.warning(
            request,
            (
                "Debes aceptar los Términos y "
                "Condiciones antes de vincular "
                "Google Calendar."
            ),
        )

        return redirect(
            destino
        )


    if not oauth_configurado():

        messages.error(
            request,
            (
                "Google Calendar todavía no "
                "está disponible para conexión."
            ),
        )

        return redirect(
            destino
        )


    _tnl_google_calendar_limpiar_sesion(
        request
    )


    try:

        (
            authorization_url,
            state,
            code_verifier,
        ) = generar_url_autorizacion()

    except GoogleCalendarConfiguracionError:

        messages.error(
            request,
            (
                "No fue posible preparar "
                "Google Calendar."
            ),
        )

        return redirect(
            destino
        )


    if (
        not state
        or
        not code_verifier
    ):

        messages.error(
            request,
            (
                "No fue posible generar una "
                "sesión OAuth segura."
            ),
        )

        return redirect(
            destino
        )


    request.session[
        _TNL_GC_SESSION_STATE
    ] = state

    request.session[
        _TNL_GC_SESSION_EMPRESA
    ] = empresa.pk

    request.session[
        _TNL_GC_SESSION_ISSUED
    ] = time.time()

    request.session[
        _TNL_GC_SESSION_CODE_VERIFIER
    ] = code_verifier

    request.session[
        _TNL_GC_SESSION_USER
    ] = request.user.pk

    request.session[
        _TNL_GC_SESSION_ORIGEN
    ] = "cliente"

    request.session.modified = True


    return redirect(
        authorization_url
    )


@login_required
def google_calendar_oauth_callback(
    request,
):

    import secrets
    import time

    from datetime import timezone as dt_timezone

    from django.contrib import messages
    from django.utils import timezone

    from googleapiclient.discovery import build

    from core.models import (
        ConfiguracionGoogleCalendar,
    )

    from core.services.google_calendar_oauth import (
        GOOGLE_CALENDAR_SCOPES,
        cifrar_token,
        crear_flujo_oauth,
    )


    expected_state = (
        request.session.get(
            _TNL_GC_SESSION_STATE
        )
    )

    empresa_id = (
        request.session.get(
            _TNL_GC_SESSION_EMPRESA
        )
    )

    issued_at = (
        request.session.get(
            _TNL_GC_SESSION_ISSUED
        )
    )

    code_verifier = (
        request.session.get(
            _TNL_GC_SESSION_CODE_VERIFIER
        )
    )

    session_user_id = (
        request.session.get(
            _TNL_GC_SESSION_USER
        )
    )

    session_origen = str(
        request.session.get(
            _TNL_GC_SESSION_ORIGEN,
            "",
        )
        or
        ""
    ).strip()


    if not empresa_id:

        _tnl_google_calendar_limpiar_sesion(
            request
        )

        messages.error(
            request,
            (
                "La sesión de autorización de "
                "Google Calendar no existe o "
                "ya expiró."
            ),
        )

        return redirect(
            "core:empresa_lista"
        )


    empresa = get_object_or_404(
        Empresa,
        pk=empresa_id,
    )


    usuario_valido = bool(
        session_user_id
        and
        str(session_user_id)
        ==
        str(request.user.pk)
    )

    origen_valido = (
        session_origen
        in {
            "admin",
            "cliente",
        }
    )


    if (
        not usuario_valido
        or
        not origen_valido
    ):

        _tnl_google_calendar_limpiar_sesion(
            request
        )

        messages.error(
            request,
            (
                "La sesión OAuth de Google "
                "Calendar no corresponde al "
                "usuario actual."
            ),
        )

        return redirect(
            "core:dashboard"
        )


    if session_origen == "cliente":

        (
            _perfil_cliente,
            empresa_cliente,
        ) = (
            _nl_cliente_perfil_empresa_seguro(
                request
            )
        )


        if (
            empresa_cliente.pk
            !=
            empresa.pk
        ):

            _tnl_google_calendar_limpiar_sesion(
                request
            )

            messages.error(
                request,
                (
                    "La autorización de Google "
                    "Calendar no corresponde a "
                    "tu empresa."
                ),
            )

            return redirect(
                "core:cliente_panel"
            )


        destino = (
            _tnl_google_calendar_cliente_url()
        )


        from core.services.terminos import (
            TerminosNoAceptadosError,
            requerir_terminos_aceptados,
        )


        try:

            requerir_terminos_aceptados(
                empresa
            )

        except TerminosNoAceptadosError:

            _tnl_google_calendar_limpiar_sesion(
                request
            )

            messages.warning(
                request,
                (
                    "Debes aceptar los Términos "
                    "y Condiciones antes de "
                    "vincular Google Calendar."
                ),
            )

            return redirect(
                destino
            )


    else:

        destino = (
            _tnl_google_calendar_empresa_url(
                empresa
            )
        )


    received_state = (
        request.GET.get(
            "state",
            "",
        )
    )


    state_valido = bool(
        expected_state
        and
        received_state
        and
        secrets.compare_digest(
            str(expected_state),
            str(received_state),
        )
    )


    tiempo_valido = False

    try:

        edad = (
            time.time()
            -
            float(issued_at)
        )

        tiempo_valido = (
            0
            <= edad
            <= _TNL_GC_OAUTH_TTL_SECONDS
        )

    except (
        TypeError,
        ValueError,
    ):

        tiempo_valido = False


    verifier_valido = bool(
        isinstance(
            code_verifier,
            str,
        )
        and
        43
        <=
        len(code_verifier)
        <=
        128
    )


    if (
        not state_valido
        or
        not tiempo_valido
        or
        not verifier_valido
    ):

        _tnl_google_calendar_limpiar_sesion(
            request
        )

        messages.error(
            request,
            (
                "La validación de seguridad "
                "OAuth falló o expiró. "
                "Intenta conectar nuevamente."
            ),
        )

        return redirect(
            destino
        )


    # A partir de aquí el state es de un solo uso.
    _tnl_google_calendar_limpiar_sesion(
        request
    )


    oauth_error = (
        request.GET.get(
            "error",
            "",
        )
        .strip()
    )


    if oauth_error:

        if oauth_error == "access_denied":

            messages.warning(
                request,
                (
                    "La autorización de Google "
                    "Calendar fue cancelada."
                ),
            )

        else:

            messages.error(
                request,
                (
                    "Google no completó la "
                    "autorización de Calendar."
                ),
            )

        return redirect(
            destino
        )


    code = (
        request.GET.get(
            "code",
            "",
        )
        .strip()
    )


    if not code:

        messages.error(
            request,
            (
                "Google no devolvió el código "
                "de autorización."
            ),
        )

        return redirect(
            destino
        )


    # TNL-GOOGLE-CALENDAR-OAUTH-DIAG-V1
    oauth_etapa = "inicio"

    try:

        # ----------------------------------------------------
        # Intercambio code -> credenciales.
        # ----------------------------------------------------

        oauth_etapa = "crear_flujo"

        flow = crear_flujo_oauth(
            state=expected_state,
            code_verifier=code_verifier,
            autogenerate_code_verifier=False,
        )

        oauth_etapa = "fetch_token"

        flow.fetch_token(
            code=code
        )

        oauth_etapa = "token_recibido"

        credentials = (
            flow.credentials
        )


        if not credentials.token:

            raise RuntimeError(
                "ACCESS_TOKEN_AUSENTE"
            )


        # ----------------------------------------------------
        # Consultar calendario principal.
        # No se utiliza userinfo.email.
        # ----------------------------------------------------

        oauth_etapa = "crear_calendar_service"

        calendar_service = build(
            "calendar",
            "v3",
            credentials=credentials,
            cache_discovery=False,
        )


        oauth_etapa = "listar_calendarios"

        calendar_list = (
            calendar_service
            .calendarList()
            .list(
                showHidden=True
            )
            .execute()
        )


        primary = None

        for item in (
            calendar_list.get(
                "items",
                []
            )
            or []
        ):

            if item.get(
                "primary"
            ):

                primary = item
                break


        if primary is None:

            raise RuntimeError(
                "CALENDARIO_PRINCIPAL_NO_ENCONTRADO"
            )


        calendar_id = str(
            primary.get(
                "id"
            )
            or ""
        ).strip()


        if not calendar_id:

            raise RuntimeError(
                "CALENDAR_ID_VACIO"
            )


        calendar_nombre = str(
            primary.get(
                "summaryOverride"
            )
            or
            primary.get(
                "summary"
            )
            or
            "Calendario principal"
        ).strip()


        zona_horaria = str(
            primary.get(
                "timeZone"
            )
            or
            "America/Mexico_City"
        ).strip()


        # El ID del calendario principal de una
        # cuenta Google normalmente corresponde
        # al correo. No pedimos scope userinfo.email.
        cuenta_email = ""

        if "@" in calendar_id:

            cuenta_email = (
                calendar_id
            )


        # ----------------------------------------------------
        # Expiración del access token.
        # ----------------------------------------------------

        token_expira_en = (
            credentials.expiry
        )


        if (
            token_expira_en is not None
            and
            timezone.is_naive(
                token_expira_en
            )
        ):

            token_expira_en = (
                timezone.make_aware(
                    token_expira_en,
                    dt_timezone.utc,
                )
            )


        # ----------------------------------------------------
        # Scopes realmente concedidos.
        # ----------------------------------------------------

        scopes = (
            credentials.scopes
            or
            GOOGLE_CALENDAR_SCOPES
        )


        scopes_concedidos = (
            "\n".join(
                sorted(
                    {
                        str(x).strip()
                        for x in scopes
                        if str(x).strip()
                    }
                )
            )
        )


        # ----------------------------------------------------
        # Preservar refresh token previo si Google,
        # durante una reconexión, no devuelve uno nuevo.
        # ----------------------------------------------------

        existente = (
            ConfiguracionGoogleCalendar.objects
            .filter(
                empresa=empresa
            )
            .first()
        )


        refresh_token_cifrado = ""

        if (
            existente is not None
        ):

            refresh_token_cifrado = (
                existente
                .refresh_token_cifrado
                or
                ""
            )


        if credentials.refresh_token:

            refresh_token_cifrado = (
                cifrar_token(
                    credentials.refresh_token
                )
            )


        if not refresh_token_cifrado:

            raise RuntimeError(
                "REFRESH_TOKEN_AUSENTE"
            )


        oauth_etapa = "cifrar_tokens"

        access_token_cifrado = (
            cifrar_token(
                credentials.token
            )
        )


        # ----------------------------------------------------
        # Guardado atómico por empresa.
        # ----------------------------------------------------

        oauth_etapa = "guardar_bd"

        # TNL-GOOGLE-CALENDAR-CALLBACK-TERMINOS-GUARD-V1
        if session_origen == "cliente":

            from core.services.terminos import (
                requerir_terminos_aceptados,
            )

            requerir_terminos_aceptados(
                empresa
            )


        with transaction.atomic():

            config = (
                ConfiguracionGoogleCalendar.objects
                .select_for_update()
                .filter(
                    empresa=empresa
                )
                .first()
            )


            if config is None:

                config = (
                    ConfiguracionGoogleCalendar(
                        empresa=empresa
                    )
                )


            config.estado_conexion = (
                ConfiguracionGoogleCalendar
                .ESTADO_CONECTADA
            )

            config.habilitada = True

            config.cuenta_email = (
                cuenta_email
            )

            config.calendar_id = (
                calendar_id
            )

            config.calendar_nombre = (
                calendar_nombre
            )

            config.zona_horaria = (
                zona_horaria
            )

            config.access_token_cifrado = (
                access_token_cifrado
            )

            config.refresh_token_cifrado = (
                refresh_token_cifrado
            )

            config.token_expira_en = (
                token_expira_en
            )

            config.scopes_concedidos = (
                scopes_concedidos
            )

            config.ultimo_error = ""

            config.conectado_en = (
                timezone.now()
            )

            config.save()


        messages.success(
            request,
            (
                "Google Calendar se conectó "
                "correctamente a esta empresa."
            ),
        )


    except Exception as exc:

        # Diagnóstico seguro:
        # sólo etapa + clase de excepción.
        # NO se registra str(exc), tokens, code ni secretos.
        import logging

        logging.getLogger(
            "negociolisto.google_calendar"
        ).error(
            "TNL_GC_OAUTH_FAIL empresa=%s etapa=%s exception=%s",
            empresa.pk,
            oauth_etapa,
            type(exc).__name__,
        )

        # No mostramos ni almacenamos tokens,
        # respuestas OAuth ni secretos.
        messages.error(
            request,
            (
                "No fue posible completar la "
                "conexión con Google Calendar. "
                "Puedes intentarlo nuevamente."
            ),
        )


    return redirect(
        destino
    )

# ============================================================
# TNL-TERMINOS-PUBLICOS-V1
#
# Página pública informativa para:
# - Google OAuth / Google Cloud;
# - visitantes;
# - consulta del documento vigente.
#
# IMPORTANTE:
# - NO requiere autenticación.
# - NO registra aceptación.
# - NO consulta datos de empresas.
# - NO modifica AceptacionTerminos.
# - Reutiliza la autoridad canónica de core.services.terminos.
# ============================================================

def terminos_publicos(
    request,
):
    from django.shortcuts import render

    from core.services.terminos import (
        TERMINOS_CONTENIDO,
        TERMINOS_SHA256,
        TERMINOS_TITULO,
        TERMINOS_VERSION,
    )

    return render(
        request,
        "core/terminos_publicos.html",
        {
            "terminos_titulo":
                TERMINOS_TITULO,

            "terminos_version":
                TERMINOS_VERSION,

            "terminos_contenido":
                TERMINOS_CONTENIDO,

            "terminos_sha256":
                TERMINOS_SHA256,
        },
    )

# ============================================================
# TNL-GOOGLE-BRAND-PUBLIC-PAGES-V1
#
# Páginas públicas requeridas para identidad de marca:
#
# /inicio/
# /privacidad/
#
# No requieren autenticación.
# No consultan datos de clientes.
# No registran consentimiento.
# ============================================================

def inicio_publico(
    request,
):

    from django.shortcuts import render

    return render(
        request,
        "core/inicio_publico.html",
    )


def privacidad_publica(
    request,
):

    from django.shortcuts import render

    return render(
        request,
        "core/privacidad_publica.html",
    )




# =============================================================================
# TNL-AGENDA-EMPRESA-ADMIN-V1
# Administración de reglas comerciales y horarios de atención por empresa.
#
# Google Calendar conserva exclusivamente la autoridad de ocupación.
# Esta vista administra:
#   - duración de cita;
#   - intervalo de slots;
#   - anticipación mínima;
#   - bloques de atención;
#   - zona horaria del Calendar ya vinculado.
# =============================================================================

@login_required
def empresa_agenda_configurar(
    request,
    pk,
):
    from datetime import datetime
    from zoneinfo import (
        ZoneInfo,
        ZoneInfoNotFoundError,
    )

    from django.contrib import messages
    from django.db import transaction
    from django.shortcuts import (
        get_object_or_404,
        redirect,
        render,
    )

    from core.models import (
        Empresa,
        ConfiguracionAgenda,
        HorarioAtencion,
        ConfiguracionGoogleCalendar,
    )


    empresa = get_object_or_404(
        Empresa,
        pk=pk,
    )


    dias_semana = (
        (0, "Lunes"),
        (1, "Martes"),
        (2, "Miércoles"),
        (3, "Jueves"),
        (4, "Viernes"),
        (5, "Sábado"),
        (6, "Domingo"),
    )


    # Hasta tres bloques permite:
    #
    # 08:00 - 14:00
    # 15:00 - 18:00
    # y un tercer bloque si la operación lo requiere.
    max_bloques = 3


    zonas_base = [
        (
            "America/Mexico_City",
            "Centro de México — America/Mexico_City",
        ),
        (
            "America/Monterrey",
            "Monterrey — America/Monterrey",
        ),
        (
            "America/Cancun",
            "Cancún / Quintana Roo — America/Cancun",
        ),
        (
            "America/Chihuahua",
            "Chihuahua — America/Chihuahua",
        ),
        (
            "America/Hermosillo",
            "Sonora — America/Hermosillo",
        ),
        (
            "America/Mazatlan",
            "Mazatlán / Sinaloa — America/Mazatlan",
        ),
        (
            "America/Tijuana",
            "Tijuana / Baja California — America/Tijuana",
        ),
        (
            "UTC",
            "UTC",
        ),
    ]


    agenda = (
        ConfiguracionAgenda.objects
        .filter(
            empresa=empresa
        )
        .first()
    )


    google = (
        ConfiguracionGoogleCalendar.objects
        .filter(
            empresa=empresa
        )
        .first()
    )


    zona_actual = (
        str(
            google.zona_horaria
            or ""
        ).strip()
        if google
        else ""
    )

    if not zona_actual:
        zona_actual = (
            "America/Mexico_City"
        )


    if zona_actual not in {
        item[0]
        for item in zonas_base
    }:
        zonas_base.append(
            (
                zona_actual,
                zona_actual,
            )
        )


    def _dias_desde_bd():

        por_dia = {
            dia: []
            for dia, _nombre
            in dias_semana
        }

        horarios = (
            HorarioAtencion.objects
            .filter(
                empresa=empresa,
                activo=True,
            )
            .order_by(
                "dia_semana",
                "hora_inicio",
                "id",
            )
        )

        for horario in horarios:

            por_dia.setdefault(
                horario.dia_semana,
                [],
            ).append(
                {
                    "inicio":
                        horario
                        .hora_inicio
                        .strftime("%H:%M"),

                    "fin":
                        horario
                        .hora_fin
                        .strftime("%H:%M"),
                }
            )


        resultado = []

        for dia, nombre in dias_semana:

            existentes = (
                por_dia.get(
                    dia,
                    [],
                )
            )

            bloques = []

            for numero in range(
                1,
                max_bloques + 1,
            ):

                item = (
                    existentes[
                        numero - 1
                    ]
                    if
                    numero <= len(
                        existentes
                    )
                    else
                    {
                        "inicio": "",
                        "fin": "",
                    }
                )

                bloques.append(
                    {
                        "numero":
                            numero,

                        "inicio":
                            item[
                                "inicio"
                            ],

                        "fin":
                            item[
                                "fin"
                            ],
                    }
                )

            resultado.append(
                {
                    "dia":
                        dia,

                    "nombre":
                        nombre,

                    "bloques":
                        bloques,
                }
            )

        return resultado


    def _dias_desde_post():

        resultado = []

        for dia, nombre in dias_semana:

            bloques = []

            for numero in range(
                1,
                max_bloques + 1,
            ):

                prefix = (
                    f"dia_{dia}_"
                    f"bloque_{numero}"
                )

                bloques.append(
                    {
                        "numero":
                            numero,

                        "inicio":
                            str(
                                request.POST.get(
                                    prefix
                                    + "_inicio",
                                    "",
                                )
                                or ""
                            ).strip(),

                        "fin":
                            str(
                                request.POST.get(
                                    prefix
                                    + "_fin",
                                    "",
                                )
                                or ""
                            ).strip(),
                    }
                )

            resultado.append(
                {
                    "dia":
                        dia,

                    "nombre":
                        nombre,

                    "bloques":
                        bloques,
                }
            )

        return resultado


    if request.method == "POST":

        errores = []

        def _entero(
            nombre,
            etiqueta,
            minimo,
            maximo=None,
        ):

            raw = str(
                request.POST.get(
                    nombre,
                    "",
                )
                or ""
            ).strip()

            try:
                value = int(raw)

            except (
                TypeError,
                ValueError,
            ):

                errores.append(
                    f"{etiqueta}: "
                    "captura un número válido."
                )

                return None


            if value < minimo:

                errores.append(
                    f"{etiqueta}: "
                    f"el mínimo es {minimo}."
                )

                return None


            if (
                maximo is not None
                and
                value > maximo
            ):

                errores.append(
                    f"{etiqueta}: "
                    f"el máximo es {maximo}."
                )

                return None


            return value


        duracion = _entero(
            "duracion_predeterminada_minutos",
            "Duración",
            1,
            1440,
        )

        intervalo = _entero(
            "intervalo_slots_minutos",
            "Intervalo",
            1,
            1440,
        )

        anticipacion = _entero(
            "anticipacion_minima_minutos",
            "Anticipación mínima",
            0,
        )



        # TNL-AGENDA-PAYMENT-UI-V1
        from decimal import Decimal, InvalidOperation

        politica_pago_cita = str(
            request.POST.get(
                "politica_pago_cita",
                ConfiguracionAgenda.POLITICA_SIN_PAGO,
            )
            or ConfiguracionAgenda.POLITICA_SIN_PAGO
        ).strip()

        politicas_pago_validas = {
            ConfiguracionAgenda.POLITICA_SIN_PAGO,
            ConfiguracionAgenda.POLITICA_ANTICIPO,
            ConfiguracionAgenda.POLITICA_PAGO_COMPLETO,
        }

        if politica_pago_cita not in politicas_pago_validas:
            errores.append(
                "La política de pago de citas no es válida."
            )
            politica_pago_cita = (
                ConfiguracionAgenda.POLITICA_SIN_PAGO
            )

        raw_porcentaje_anticipo = str(
            request.POST.get(
                "porcentaje_anticipo",
                "0",
            )
            or "0"
        ).strip().replace(",", ".")

        porcentaje_valido = True

        try:
            porcentaje_anticipo = Decimal(
                raw_porcentaje_anticipo
            )

            if not porcentaje_anticipo.is_finite():
                raise InvalidOperation

            porcentaje_anticipo = (
                porcentaje_anticipo.quantize(
                    Decimal("0.01")
                )
            )

        except (
            InvalidOperation,
            ValueError,
        ):
            porcentaje_valido = False
            porcentaje_anticipo = Decimal("0.00")

            errores.append(
                "El porcentaje de anticipo no es válido."
            )

        raw_retencion_pago = str(
            request.POST.get(
                "retencion_pago_minutos",
                "15",
            )
            or "15"
        ).strip()

        try:
            retencion_pago_minutos = int(
                raw_retencion_pago
            )

            if not (
                5
                <= retencion_pago_minutos
                <= 60
            ):
                raise ValueError

        except (
            TypeError,
            ValueError,
        ):
            retencion_pago_minutos = 15

            errores.append(
                "El tiempo para completar el pago "
                "debe estar entre 5 y 60 minutos."
            )

        if (
            politica_pago_cita
            ==
            ConfiguracionAgenda.POLITICA_SIN_PAGO
        ):
            porcentaje_anticipo = Decimal("0.00")

        elif (
            politica_pago_cita
            ==
            ConfiguracionAgenda.POLITICA_ANTICIPO
        ):
            if (
                porcentaje_valido
                and not (
                    Decimal("0.00")
                    < porcentaje_anticipo
                    < Decimal("100.00")
                )
            ):
                errores.append(
                    "El anticipo debe ser mayor a 0 % "
                    "y menor a 100 %."
                )

        elif (
            politica_pago_cita
            ==
            ConfiguracionAgenda.POLITICA_PAGO_COMPLETO
        ):
            porcentaje_anticipo = Decimal("100.00")


        zona = str(
            request.POST.get(
                "zona_horaria",
                "",
            )
            or ""
        ).strip()


        try:

            ZoneInfo(
                zona
            )

        except (
            ZoneInfoNotFoundError,
            ValueError,
        ):

            errores.append(
                "La zona horaria "
                "seleccionada no es válida."
            )


        bloques_nuevos = []


        for dia, nombre in dias_semana:

            intervalos_dia = []

            for numero in range(
                1,
                max_bloques + 1,
            ):

                prefix = (
                    f"dia_{dia}_"
                    f"bloque_{numero}"
                )

                inicio_raw = str(
                    request.POST.get(
                        prefix + "_inicio",
                        "",
                    )
                    or ""
                ).strip()

                fin_raw = str(
                    request.POST.get(
                        prefix + "_fin",
                        "",
                    )
                    or ""
                ).strip()


                if (
                    not inicio_raw
                    and
                    not fin_raw
                ):
                    continue


                if (
                    not inicio_raw
                    or
                    not fin_raw
                ):

                    errores.append(
                        f"{nombre}, bloque "
                        f"{numero}: captura "
                        "hora inicial y final."
                    )

                    continue


                try:

                    hora_inicio = (
                        datetime.strptime(
                            inicio_raw,
                            "%H:%M",
                        )
                        .time()
                    )

                    hora_fin = (
                        datetime.strptime(
                            fin_raw,
                            "%H:%M",
                        )
                        .time()
                    )

                except ValueError:

                    errores.append(
                        f"{nombre}, bloque "
                        f"{numero}: horario "
                        "inválido."
                    )

                    continue


                if (
                    hora_fin
                    <=
                    hora_inicio
                ):

                    errores.append(
                        f"{nombre}, bloque "
                        f"{numero}: la hora "
                        "final debe ser "
                        "posterior a la inicial."
                    )

                    continue


                intervalos_dia.append(
                    (
                        hora_inicio,
                        hora_fin,
                        numero,
                    )
                )


            intervalos_dia.sort(
                key=lambda item:
                    item[0]
            )


            anterior_fin = None

            for (
                hora_inicio,
                hora_fin,
                numero,
            ) in intervalos_dia:

                if (
                    anterior_fin
                    is not None
                    and
                    hora_inicio
                    <
                    anterior_fin
                ):

                    errores.append(
                        f"{nombre}: existen "
                        "bloques de horario "
                        "empalmados."
                    )

                    break

                anterior_fin = (
                    hora_fin
                )


            for (
                hora_inicio,
                hora_fin,
                _numero,
            ) in intervalos_dia:

                bloques_nuevos.append(
                    (
                        dia,
                        hora_inicio,
                        hora_fin,
                    )
                )


        if not bloques_nuevos:

            errores.append(
                "Debes configurar al menos "
                "un bloque de atención."
            )


        if errores:

            for error in errores:

                messages.error(
                    request,
                    error,
                )

            dias_ui = (
                _dias_desde_post()
            )

            agenda_valores = {
                "duracion":
                    request.POST.get(
                        "duracion_predeterminada_minutos",
                        "30",
                    ),

                "intervalo":
                    request.POST.get(
                        "intervalo_slots_minutos",
                        "30",
                    ),

                "anticipacion":
                    request.POST.get(
                        "anticipacion_minima_minutos",
                        "0",
                    ),
                "politica_pago": request.POST.get("politica_pago_cita", "sin_pago"),
                "porcentaje_anticipo": request.POST.get("porcentaje_anticipo", "0"),
                "retencion_pago": request.POST.get("retencion_pago_minutos", "15"),
            }

            zona_actual = (
                zona
                or
                zona_actual
            )


            return render(
                request,
                "core/empresa_agenda_configurar.html",
                {
                    "empresa":
                        empresa,

                    "agenda":
                        agenda,

                    "google_config":
                        google,

                    "agenda_valores":
                        agenda_valores,

                    "dias_ui":
                        dias_ui,

                    "zonas_horarias":
                        zonas_base,

                    "zona_actual":
                        zona_actual,
                },
            )


        with transaction.atomic():

            agenda_obj, _created = (
                ConfiguracionAgenda.objects
                .get_or_create(
                    empresa=empresa
                )
            )

            agenda_obj.duracion_predeterminada_minutos = (
                duracion
            )

            agenda_obj.intervalo_slots_minutos = (
                intervalo
            )

            agenda_obj.anticipacion_minima_minutos = (
                anticipacion
            )


            agenda_obj.politica_pago_cita = (
                politica_pago_cita
            )

            agenda_obj.porcentaje_anticipo = (
                porcentaje_anticipo
            )

            agenda_obj.retencion_pago_minutos = (
                retencion_pago_minutos
            )

            agenda_obj.save(
                update_fields=[
                    "duracion_predeterminada_minutos",
                    "intervalo_slots_minutos",
                    "anticipacion_minima_minutos",
                    "actualizado_en",
                    "politica_pago_cita",
                    "porcentaje_anticipo",
                    "retencion_pago_minutos",
                ]
            )


            # Los horarios pertenecen exclusivamente
            # a esta empresa.
            HorarioAtencion.objects.filter(
                empresa=empresa
            ).delete()


            HorarioAtencion.objects.bulk_create(
                [
                    HorarioAtencion(
                        empresa=empresa,
                        dia_semana=dia,
                        hora_inicio=inicio,
                        hora_fin=fin,
                        activo=True,
                    )
                    for (
                        dia,
                        inicio,
                        fin,
                    )
                    in bloques_nuevos
                ]
            )


            if google is not None:

                google_locked = (
                    ConfiguracionGoogleCalendar
                    .objects
                    .select_for_update()
                    .get(
                        pk=google.pk
                    )
                )

                if (
                    google_locked
                    .zona_horaria
                    !=
                    zona
                ):

                    google_locked.zona_horaria = (
                        zona
                    )

                    google_locked.save(
                        update_fields=[
                            "zona_horaria",
                            "actualizado_en",
                        ]
                    )


        if google is None:

            messages.warning(
                request,
                (
                    "Agenda y horarios guardados. "
                    "Google Calendar todavía no "
                    "está configurado; conéctalo "
                    "antes de operar citas."
                ),
            )

        else:

            messages.success(
                request,
                (
                    "Agenda y horarios de atención "
                    "guardados correctamente."
                ),
            )


        return redirect(
            "core:empresa_agenda_configurar",
            pk=empresa.pk,
        )


    # -------------------------------------------------------------
    # GET
    # -------------------------------------------------------------

    agenda_valores = {
        "duracion":
            (
                agenda
                .duracion_predeterminada_minutos
                if agenda
                else 30
            ),

        "intervalo":
            (
                agenda
                .intervalo_slots_minutos
                if agenda
                else 30
            ),

        "anticipacion":
            (
                agenda
                .anticipacion_minima_minutos
                if agenda
                else 0
            ),
        "politica_pago": (agenda.politica_pago_cita if agenda else "sin_pago"),
        "porcentaje_anticipo": (agenda.porcentaje_anticipo if agenda else 0),
        "retencion_pago": (agenda.retencion_pago_minutos if agenda else 15),
    }


    return render(
        request,
        "core/empresa_agenda_configurar.html",
        {
            "empresa":
                empresa,

            "agenda":
                agenda,

            "google_config":
                google,

            "agenda_valores":
                agenda_valores,

            "dias_ui":
                _dias_desde_bd(),

            "zonas_horarias":
                zonas_base,

            "zona_actual":
                zona_actual,
        },
    )


# =============================================================================
# TNL-CLIENTE-AGENDA-ADMIN-V1
#
# Self-service de agenda para el Dueño.
#
# SEGURIDAD:
# - NO recibe empresa_id;
# - NO recibe pk de Empresa;
# - NO confía en POST para determinar tenant;
# - resuelve PerfilUsuario -> Empresa en servidor;
# - únicamente modifica ConfiguracionAgenda /
#   HorarioAtencion de la empresa autenticada.
# =============================================================================

@_nl_role_login_required
def cliente_agenda_configurar(
    request,
):
    from datetime import datetime

    from zoneinfo import (
        ZoneInfo,
        ZoneInfoNotFoundError,
    )

    from django.contrib import messages

    from django.db import transaction

    from django.http import (
        HttpResponseNotAllowed,
    )

    from django.shortcuts import (
        redirect,
        render,
    )

    from core.models import (
        ConfiguracionAgenda,
        HorarioAtencion,
        ConfiguracionGoogleCalendar,
    )


    if request.method not in {
        "GET",
        "POST",
    }:

        return HttpResponseNotAllowed(
            [
                "GET",
                "POST",
            ]
        )


    # ---------------------------------------------------------
    # AUTORIDAD DEL TENANT.
    #
    # El navegador NO puede escoger Empresa.
    # ---------------------------------------------------------

    (
        _perfil,
        empresa,
    ) = (
        _nl_cliente_perfil_empresa_seguro(
            request
        )
    )


    dias_semana = (
        (0, "Lunes"),
        (1, "Martes"),
        (2, "Miércoles"),
        (3, "Jueves"),
        (4, "Viernes"),
        (5, "Sábado"),
        (6, "Domingo"),
    )


    max_bloques = 3


    zonas_base = [
        (
            "America/Mexico_City",
            (
                "Centro de México — "
                "America/Mexico_City"
            ),
        ),
        (
            "America/Monterrey",
            (
                "Monterrey — "
                "America/Monterrey"
            ),
        ),
        (
            "America/Cancun",
            (
                "Cancún / Quintana Roo — "
                "America/Cancun"
            ),
        ),
        (
            "America/Chihuahua",
            (
                "Chihuahua — "
                "America/Chihuahua"
            ),
        ),
        (
            "America/Hermosillo",
            (
                "Sonora — "
                "America/Hermosillo"
            ),
        ),
        (
            "America/Mazatlan",
            (
                "Mazatlán / Sinaloa — "
                "America/Mazatlan"
            ),
        ),
        (
            "America/Tijuana",
            (
                "Tijuana / Baja California — "
                "America/Tijuana"
            ),
        ),
        (
            "UTC",
            "UTC",
        ),
    ]


    agenda = (
        ConfiguracionAgenda.objects
        .filter(
            empresa=empresa
        )
        .first()
    )


    google = (
        ConfiguracionGoogleCalendar.objects
        .filter(
            empresa=empresa
        )
        .first()
    )


    zona_actual = (
        str(
            google.zona_horaria
            or ""
        ).strip()
        if google
        else ""
    )


    if not zona_actual:

        zona_actual = (
            "America/Mexico_City"
        )


    zonas_existentes = {
        value
        for (
            value,
            _label,
        )
        in zonas_base
    }


    if (
        zona_actual
        not in zonas_existentes
    ):

        zonas_base.append(
            (
                zona_actual,
                zona_actual,
            )
        )


    def _dias_desde_bd():

        por_dia = {
            dia: []
            for (
                dia,
                _nombre,
            )
            in dias_semana
        }


        horarios = (
            HorarioAtencion.objects
            .filter(
                empresa=empresa,
                activo=True,
            )
            .order_by(
                "dia_semana",
                "hora_inicio",
                "id",
            )
        )


        for horario in horarios:

            por_dia.setdefault(
                horario.dia_semana,
                [],
            ).append(
                {
                    "inicio":
                        horario
                        .hora_inicio
                        .strftime(
                            "%H:%M"
                        ),

                    "fin":
                        horario
                        .hora_fin
                        .strftime(
                            "%H:%M"
                        ),
                }
            )


        resultado = []


        for (
            dia,
            nombre,
        ) in dias_semana:

            existentes = (
                por_dia.get(
                    dia,
                    [],
                )
            )


            bloques = []


            for numero in range(
                1,
                max_bloques + 1,
            ):

                item = (
                    existentes[
                        numero - 1
                    ]
                    if
                    numero
                    <=
                    len(existentes)
                    else
                    {
                        "inicio": "",
                        "fin": "",
                    }
                )


                bloques.append(
                    {
                        "numero":
                            numero,

                        "inicio":
                            item[
                                "inicio"
                            ],

                        "fin":
                            item[
                                "fin"
                            ],
                    }
                )


            resultado.append(
                {
                    "dia":
                        dia,

                    "nombre":
                        nombre,

                    "bloques":
                        bloques,
                }
            )


        return resultado


    def _dias_desde_post():

        resultado = []


        for (
            dia,
            nombre,
        ) in dias_semana:

            bloques = []


            for numero in range(
                1,
                max_bloques + 1,
            ):

                prefix = (
                    f"dia_{dia}_"
                    f"bloque_{numero}"
                )


                bloques.append(
                    {
                        "numero":
                            numero,

                        "inicio":
                            str(
                                request.POST.get(
                                    (
                                        prefix
                                        +
                                        "_inicio"
                                    ),
                                    "",
                                )
                                or ""
                            ).strip(),

                        "fin":
                            str(
                                request.POST.get(
                                    (
                                        prefix
                                        +
                                        "_fin"
                                    ),
                                    "",
                                )
                                or ""
                            ).strip(),
                    }
                )


            resultado.append(
                {
                    "dia":
                        dia,

                    "nombre":
                        nombre,

                    "bloques":
                        bloques,
                }
            )


        return resultado


    def _contexto(
        *,
        dias_ui,
        valores,
        zona,
    ):

        return {
            "empresa":
                empresa,

            "agenda":
                agenda,

            "google_config":
                google,

            "agenda_valores":
                valores,

            "dias_ui":
                dias_ui,

            "zonas_horarias":
                zonas_base,

            "zona_actual":
                zona,
        }


    # ---------------------------------------------------------
    # POST
    # ---------------------------------------------------------

    if request.method == "POST":

        errores = []


        def _entero(
            nombre,
            etiqueta,
            minimo,
            maximo=None,
        ):

            raw = str(
                request.POST.get(
                    nombre,
                    "",
                )
                or ""
            ).strip()


            try:

                value = int(
                    raw
                )

            except (
                TypeError,
                ValueError,
            ):

                errores.append(
                    (
                        f"{etiqueta}: "
                        "captura un número válido."
                    )
                )

                return None


            if value < minimo:

                errores.append(
                    (
                        f"{etiqueta}: "
                        f"el mínimo es {minimo}."
                    )
                )

                return None


            if (
                maximo is not None
                and
                value > maximo
            ):

                errores.append(
                    (
                        f"{etiqueta}: "
                        f"el máximo es {maximo}."
                    )
                )

                return None


            return value


        duracion = _entero(
            (
                "duracion_"
                "predeterminada_minutos"
            ),
            "Duración",
            1,
            1440,
        )


        intervalo = _entero(
            "intervalo_slots_minutos",
            "Intervalo",
            1,
            1440,
        )


        anticipacion = _entero(
            (
                "anticipacion_"
                "minima_minutos"
            ),
            "Anticipación mínima",
            0,
        )



        # TNL-AGENDA-PAYMENT-UI-V1
        from decimal import Decimal, InvalidOperation

        politica_pago_cita = str(
            request.POST.get(
                "politica_pago_cita",
                ConfiguracionAgenda.POLITICA_SIN_PAGO,
            )
            or ConfiguracionAgenda.POLITICA_SIN_PAGO
        ).strip()

        politicas_pago_validas = {
            ConfiguracionAgenda.POLITICA_SIN_PAGO,
            ConfiguracionAgenda.POLITICA_ANTICIPO,
            ConfiguracionAgenda.POLITICA_PAGO_COMPLETO,
        }

        if politica_pago_cita not in politicas_pago_validas:
            errores.append(
                "La política de pago de citas no es válida."
            )
            politica_pago_cita = (
                ConfiguracionAgenda.POLITICA_SIN_PAGO
            )

        raw_porcentaje_anticipo = str(
            request.POST.get(
                "porcentaje_anticipo",
                "0",
            )
            or "0"
        ).strip().replace(",", ".")

        porcentaje_valido = True

        try:
            porcentaje_anticipo = Decimal(
                raw_porcentaje_anticipo
            )

            if not porcentaje_anticipo.is_finite():
                raise InvalidOperation

            porcentaje_anticipo = (
                porcentaje_anticipo.quantize(
                    Decimal("0.01")
                )
            )

        except (
            InvalidOperation,
            ValueError,
        ):
            porcentaje_valido = False
            porcentaje_anticipo = Decimal("0.00")

            errores.append(
                "El porcentaje de anticipo no es válido."
            )

        raw_retencion_pago = str(
            request.POST.get(
                "retencion_pago_minutos",
                "15",
            )
            or "15"
        ).strip()

        try:
            retencion_pago_minutos = int(
                raw_retencion_pago
            )

            if not (
                5
                <= retencion_pago_minutos
                <= 60
            ):
                raise ValueError

        except (
            TypeError,
            ValueError,
        ):
            retencion_pago_minutos = 15

            errores.append(
                "El tiempo para completar el pago "
                "debe estar entre 5 y 60 minutos."
            )

        if (
            politica_pago_cita
            ==
            ConfiguracionAgenda.POLITICA_SIN_PAGO
        ):
            porcentaje_anticipo = Decimal("0.00")

        elif (
            politica_pago_cita
            ==
            ConfiguracionAgenda.POLITICA_ANTICIPO
        ):
            if (
                porcentaje_valido
                and not (
                    Decimal("0.00")
                    < porcentaje_anticipo
                    < Decimal("100.00")
                )
            ):
                errores.append(
                    "El anticipo debe ser mayor a 0 % "
                    "y menor a 100 %."
                )

        elif (
            politica_pago_cita
            ==
            ConfiguracionAgenda.POLITICA_PAGO_COMPLETO
        ):
            porcentaje_anticipo = Decimal("100.00")


        zona = str(
            request.POST.get(
                "zona_horaria",
                "",
            )
            or ""
        ).strip()


        try:

            ZoneInfo(
                zona
            )

        except (
            ZoneInfoNotFoundError,
            ValueError,
        ):

            errores.append(
                (
                    "La zona horaria "
                    "seleccionada no es válida."
                )
            )


        bloques_nuevos = []


        for (
            dia,
            nombre,
        ) in dias_semana:

            intervalos_dia = []


            for numero in range(
                1,
                max_bloques + 1,
            ):

                prefix = (
                    f"dia_{dia}_"
                    f"bloque_{numero}"
                )


                inicio_raw = str(
                    request.POST.get(
                        (
                            prefix
                            +
                            "_inicio"
                        ),
                        "",
                    )
                    or ""
                ).strip()


                fin_raw = str(
                    request.POST.get(
                        (
                            prefix
                            +
                            "_fin"
                        ),
                        "",
                    )
                    or ""
                ).strip()


                if (
                    not inicio_raw
                    and
                    not fin_raw
                ):

                    continue


                if (
                    not inicio_raw
                    or
                    not fin_raw
                ):

                    errores.append(
                        (
                            f"{nombre}, "
                            f"bloque {numero}: "
                            "captura hora inicial "
                            "y final."
                        )
                    )

                    continue


                try:

                    hora_inicio = (
                        datetime.strptime(
                            inicio_raw,
                            "%H:%M",
                        )
                        .time()
                    )


                    hora_fin = (
                        datetime.strptime(
                            fin_raw,
                            "%H:%M",
                        )
                        .time()
                    )


                except ValueError:

                    errores.append(
                        (
                            f"{nombre}, "
                            f"bloque {numero}: "
                            "horario inválido."
                        )
                    )

                    continue


                if (
                    hora_fin
                    <=
                    hora_inicio
                ):

                    errores.append(
                        (
                            f"{nombre}, "
                            f"bloque {numero}: "
                            "la hora final debe "
                            "ser posterior a "
                            "la inicial."
                        )
                    )

                    continue


                intervalos_dia.append(
                    (
                        hora_inicio,
                        hora_fin,
                        numero,
                    )
                )


            intervalos_dia.sort(
                key=lambda item:
                    item[0]
            )


            anterior_fin = None


            for (
                hora_inicio,
                hora_fin,
                _numero,
            ) in intervalos_dia:

                if (
                    anterior_fin
                    is not None
                    and
                    hora_inicio
                    <
                    anterior_fin
                ):

                    errores.append(
                        (
                            f"{nombre}: "
                            "existen bloques de "
                            "horario empalmados."
                        )
                    )

                    break


                anterior_fin = (
                    hora_fin
                )


            for (
                hora_inicio,
                hora_fin,
                _numero,
            ) in intervalos_dia:

                bloques_nuevos.append(
                    (
                        dia,
                        hora_inicio,
                        hora_fin,
                    )
                )


        if not bloques_nuevos:

            errores.append(
                (
                    "Debes configurar al menos "
                    "un bloque de atención."
                )
            )


        if errores:

            for error in errores:

                messages.error(
                    request,
                    error,
                )


            valores = {
                "duracion":
                    request.POST.get(
                        (
                            "duracion_"
                            "predeterminada_minutos"
                        ),
                        "30",
                    ),

                "intervalo":
                    request.POST.get(
                        (
                            "intervalo_"
                            "slots_minutos"
                        ),
                        "30",
                    ),

                "anticipacion":
                    request.POST.get(
                        (
                            "anticipacion_"
                            "minima_minutos"
                        ),
                        "0",
                    ),
                "politica_pago": request.POST.get("politica_pago_cita", "sin_pago"),
                "porcentaje_anticipo": request.POST.get("porcentaje_anticipo", "0"),
                "retencion_pago": request.POST.get("retencion_pago_minutos", "15"),
            }


            return render(
                request,
                (
                    "core/"
                    "cliente_agenda_configurar.html"
                ),
                _contexto(
                    dias_ui=
                        _dias_desde_post(),

                    valores=
                        valores,

                    zona=
                        (
                            zona
                            or
                            zona_actual
                        ),
                ),
            )


        # -----------------------------------------------------
        # Escritura atómica exclusivamente del tenant.
        # -----------------------------------------------------

        with transaction.atomic():

            agenda_obj, _created = (
                ConfiguracionAgenda.objects
                .get_or_create(
                    empresa=empresa
                )
            )


            agenda_obj.duracion_predeterminada_minutos = (
                duracion
            )

            agenda_obj.intervalo_slots_minutos = (
                intervalo
            )

            agenda_obj.anticipacion_minima_minutos = (
                anticipacion
            )



            agenda_obj.politica_pago_cita = (
                politica_pago_cita
            )

            agenda_obj.porcentaje_anticipo = (
                porcentaje_anticipo
            )

            agenda_obj.retencion_pago_minutos = (
                retencion_pago_minutos
            )

            agenda_obj.save(
                update_fields=[
                    (
                        "duracion_"
                        "predeterminada_minutos"
                    ),
                    (
                        "intervalo_"
                        "slots_minutos"
                    ),
                    (
                        "anticipacion_"
                        "minima_minutos"
                    ),
                    "actualizado_en",
                    "politica_pago_cita",
                    "porcentaje_anticipo",
                    "retencion_pago_minutos",
                ]
            )


            # El reemplazo se limita con empresa=empresa.
            HorarioAtencion.objects.filter(
                empresa=empresa
            ).delete()


            HorarioAtencion.objects.bulk_create(
                [
                    HorarioAtencion(
                        empresa=empresa,
                        dia_semana=dia,
                        hora_inicio=inicio,
                        hora_fin=fin,
                        activo=True,
                    )
                    for (
                        dia,
                        inicio,
                        fin,
                    )
                    in bloques_nuevos
                ]
            )


            # La zona pertenece a la configuración
            # Calendar de ESA misma empresa.
            if google is not None:

                google_locked = (
                    ConfiguracionGoogleCalendar
                    .objects
                    .select_for_update()
                    .get(
                        pk=google.pk,
                        empresa=empresa,
                    )
                )


                if (
                    google_locked
                    .zona_horaria
                    != zona
                ):

                    google_locked.zona_horaria = (
                        zona
                    )


                    google_locked.save(
                        update_fields=[
                            "zona_horaria",
                            "actualizado_en",
                        ]
                    )


        if google is None:

            messages.warning(
                request,
                (
                    "Tus horarios fueron "
                    "guardados. Conecta Google "
                    "Calendar antes de operar "
                    "las citas."
                ),
            )

        else:

            messages.success(
                request,
                (
                    "Agenda y horarios "
                    "guardados correctamente."
                ),
            )


        return redirect(
            "core:cliente_agenda_configurar"
        )


    # ---------------------------------------------------------
    # GET
    # ---------------------------------------------------------

    valores = {
        "duracion":
            (
                agenda
                .duracion_predeterminada_minutos
                if agenda
                else 30
            ),

        "intervalo":
            (
                agenda
                .intervalo_slots_minutos
                if agenda
                else 30
            ),

        "anticipacion":
            (
                agenda
                .anticipacion_minima_minutos
                if agenda
                else 0
            ),
        "politica_pago": (agenda.politica_pago_cita if agenda else "sin_pago"),
        "porcentaje_anticipo": (agenda.porcentaje_anticipo if agenda else 0),
        "retencion_pago": (agenda.retencion_pago_minutos if agenda else 15),
    }


    return render(
        request,
        (
            "core/"
            "cliente_agenda_configurar.html"
        ),
        _contexto(
            dias_ui=
                _dias_desde_bd(),

            valores=
                valores,

            zona=
                zona_actual,
        ),
    )


# =============================================================================
# TNL-CLIENT-LIFECYCLE-LOGIN-V1
# =============================================================================

from django.contrib.auth.views import (
    LoginView as _TNLBaseLoginView,
)


class NegocioListoLoginView(
    _TNLBaseLoginView
):

    def form_valid(
        self,
        form,
    ):

        from core.services.client_lifecycle import (
            usuario_puede_iniciar_sesion,
        )

        user = form.get_user()

        if not usuario_puede_iniciar_sesion(
            user
        ):

            form.add_error(
                None,
                (
                    "El servicio de esta empresa "
                    "se encuentra suspendido o "
                    "sin una licencia vigente. "
                    "Contacta a Administración."
                ),
            )

            return self.form_invalid(
                form
            )

        return super().form_valid(
            form
        )


# =============================================================================
# TNL-CLIENT-LIFECYCLE-ADMIN-V1
# =============================================================================

def empresa_desactivar_cliente(
    request,
    pk,
):

    from django.contrib import messages
    from django.http import (
        HttpResponseNotAllowed,
    )
    from django.shortcuts import (
        get_object_or_404,
        redirect,
    )

    from core.models import Empresa

    from core.services.client_lifecycle import (
        desactivar_empresa_admin,
    )


    if request.method != "POST":

        return HttpResponseNotAllowed(
            [
                "POST",
            ]
        )


    empresa = get_object_or_404(
        Empresa,
        pk=pk,
    )


    result = (
        desactivar_empresa_admin(
            empresa.id
        )
    )


    if result[
        "external_errors"
    ]:

        messages.warning(
            request,
            (
                "El cliente quedó suspendido "
                "en NegocioListo y sus sesiones "
                "fueron cerradas, pero una "
                "integración externa requiere "
                "reconciliación automática."
            ),
        )

    else:

        messages.success(
            request,
            (
                "Cliente desactivado. "
                "Sus datos y conexiones "
                "se conservaron."
            ),
        )


    return redirect(
        "core:empresa_detalle",
        pk=empresa.id,
    )


def empresa_reactivar_cliente(
    request,
    pk,
):

    from django.contrib import messages
    from django.http import (
        HttpResponseNotAllowed,
    )
    from django.shortcuts import (
        get_object_or_404,
        redirect,
    )

    from core.models import Empresa

    from core.services.client_lifecycle import (
        LicenciaNoVigenteError,
        LifecycleExternalError,
        reactivar_empresa_admin,
    )


    if request.method != "POST":

        return HttpResponseNotAllowed(
            [
                "POST",
            ]
        )


    empresa = get_object_or_404(
        Empresa,
        pk=pk,
    )


    try:

        reactivar_empresa_admin(
            empresa.id
        )


    except LicenciaNoVigenteError:

        messages.error(
            request,
            (
                "No se puede reactivar: "
                "primero renueva una licencia "
                "activa y vigente."
            ),
        )


    except LifecycleExternalError:

        messages.error(
            request,
            (
                "No fue posible reactivar "
                "completamente las integraciones. "
                "El cliente permanece suspendido."
            ),
        )


    else:

        messages.success(
            request,
            (
                "Cliente reactivado "
                "correctamente."
            ),
        )


    return redirect(
        "core:empresa_detalle",
        pk=empresa.id,
    )



# =============================================================================
# TNL-CLIENT-CONNECTION-RESET-VIEW-V1
# =============================================================================

def empresa_restablecer_conexiones(
    request,
    pk,
):

    from django.contrib import messages
    from django.http import (
        HttpResponseNotAllowed,
    )
    from django.shortcuts import (
        get_object_or_404,
        redirect,
    )
    from django.urls import reverse

    from core.models import Empresa

    from core.services.client_connection_reset import (
        ConnectionResetError,
        restablecer_conexiones_empresa,
    )


    if request.method != "POST":

        return HttpResponseNotAllowed(
            [
                "POST",
            ]
        )


    empresa = get_object_or_404(
        Empresa,
        pk=pk,
    )


    confirmacion = str(
        request.POST.get(
            "confirmacion",
            "",
        )
        or
        ""
    ).strip()


    if confirmacion != "RESTABLECER":

        messages.error(
            request,
            (
                "Para ejecutar esta acción "
                "escribe exactamente "
                "RESTABLECER."
            ),
        )

        return redirect(
            reverse(
                "core:empresa_detalle",
                args=[
                    empresa.id,
                ],
            )
            +
            "#restablecer-conexiones"
        )


    try:

        result = (
            restablecer_conexiones_empresa(
                empresa.id
            )
        )


        #
        # Importantísimo:
        # la request actual puede tener un
        # SessionStore ya cargado en memoria.
        #
        # Lo limpiamos también aquí para evitar
        # que Middleware vuelva a persistir un
        # state OAuth anterior.
        #
        _tnl_mp_limpiar_sesion(
            request
        )

        _tnl_google_calendar_limpiar_sesion(
            request
        )


    except ConnectionResetError:

        messages.error(
            request,
            (
                "No fue posible completar "
                "el restablecimiento. "
                "No vuelvas a vincular las "
                "cuentas hasta revisar el "
                "estado de esta empresa."
            ),
        )


    else:

        messages.success(
            request,
            (
                "Conexiones restablecidas. "
                "WhatsApp, Mercado Pago y "
                "Google Calendar quedaron "
                "preparados para una nueva "
                "vinculación. "
                "Los datos comerciales e "
                "históricos se conservaron."
            ),
        )


    return redirect(
        reverse(
            "core:empresa_detalle",
            args=[
                empresa.id,
            ],
        )
        +
        "#restablecer-conexiones"
    )



# =============================================================================
# TNL-CLIENT-DELETION-VIEW-V1
# =============================================================================

def empresa_eliminar_definitivamente(
    request,
    pk,
):

    from django.contrib import messages
    from django.http import (
        HttpResponseNotAllowed,
    )
    from django.shortcuts import (
        get_object_or_404,
        redirect,
    )

    from core.models import Empresa

    from core.services.client_deletion import (
        ClientDeletionError,
        ClientDeletionPartialError,
        ClientDeletionPreflightError,
        eliminar_cliente_definitivamente,
    )


    if request.method != "POST":

        return HttpResponseNotAllowed(
            [
                "POST",
            ]
        )


    empresa = get_object_or_404(
        Empresa,
        pk=pk,
    )


    confirmacion = str(
        request.POST.get(
            "confirmacion",
            "",
        )
        or
        ""
    ).strip()


    empresa_id_confirmacion = str(
        request.POST.get(
            "empresa_id_confirmacion",
            "",
        )
        or
        ""
    ).strip()


    if confirmacion != "ELIMINAR CLIENTE":

        messages.error(
            request,
            (
                "Para eliminar definitivamente "
                "debes escribir exactamente "
                "ELIMINAR CLIENTE."
            ),
        )

        return redirect(
            "core:empresa_detalle",
            pk=empresa.id,
        )


    if (
        empresa_id_confirmacion
        !=
        str(
            empresa.id
        )
    ):

        messages.error(
            request,
            (
                "El ID de confirmación "
                "no corresponde al cliente."
            ),
        )

        return redirect(
            "core:empresa_detalle",
            pk=empresa.id,
        )


    empresa_nombre = (
        empresa.nombre
    )


    try:

        result = (
            eliminar_cliente_definitivamente(
                empresa.id
            )
        )


    except ClientDeletionPreflightError:

        messages.error(
            request,
            (
                "La eliminación fue bloqueada "
                "por una validación de seguridad. "
                "No continúes hasta revisar "
                "esta empresa."
            ),
        )

        return redirect(
            "core:empresa_detalle",
            pk=empresa.id,
        )


    except ClientDeletionPartialError:

        messages.warning(
            request,
            (
                "El cliente fue eliminado de "
                "NegocioListo, pero quedó "
                "pendiente limpiar al menos un "
                "archivo físico del servidor."
            ),
        )

        return redirect(
            "core:empresa_lista"
        )


    except ClientDeletionError:

        if (
            Empresa.objects
            .filter(
                pk=pk
            )
            .exists()
        ):

            messages.error(
                request,
                (
                    "La eliminación no pudo "
                    "completarse. El cliente "
                    "permanece suspendido para "
                    "evitar actividad parcial."
                ),
            )

            return redirect(
                "core:empresa_detalle",
                pk=pk,
            )


        messages.warning(
            request,
            (
                "El registro principal fue "
                "eliminado, pero una verificación "
                "posterior requiere revisión."
            ),
        )

        return redirect(
            "core:empresa_lista"
        )


    else:

        messages.success(
            request,
            (
                "Cliente eliminado "
                "definitivamente: "
                f"{empresa_nombre}. "
                "Sus recursos operativos y "
                "conexiones quedaron retirados."
            ),
        )

        return redirect(
            "core:empresa_lista"
        )


# ============================================================
# TNL-PEDIDO-STATUS-RAPIDO-V1
# ============================================================


# =============================================================================
# TNL-PAGO-DIRECTO-P3-V1
# Confirmación manual de pago Efectivo / contra entrega.
# =============================================================================

def pedido_pago_marcar_pagado(
    request,
    pk,
):

    from django.core.exceptions import (
        ObjectDoesNotExist,
        ValidationError,
    )

    from django.http import (
        Http404,
        HttpResponseNotAllowed,
    )

    from core.models import (
        Pedido,
    )

    from core.services.pedidos import (
        marcar_pago_directo_pagado,
    )


    empresa_scope, pedido_modo_cliente = (
        _nl_pedido_scope(
            request
        )
    )


    if request.method != "POST":

        return HttpResponseNotAllowed(
            ["POST"]
        )


    pedido_scope_qs = (
        Pedido.objects
        .filter(
            pk=pk
        )
    )


    if empresa_scope is not None:

        pedido_scope_qs = (
            pedido_scope_qs
            .filter(
                empresa_id=
                    empresa_scope
            )
        )


    if not pedido_scope_qs.exists():

        raise Http404(
            "Pedido no encontrado."
        )


    try:

        resultado = (
            marcar_pago_directo_pagado(
                pedido_id=
                    pk,
            )
        )


    except ObjectDoesNotExist:

        messages.error(
            request,
            "El pedido no existe.",
        )


    except ValidationError as exc:

        messages.error(
            request,
            _pedido_error_texto(
                exc
            ),
        )


    else:

        pedido = resultado[
            "pedido"
        ]


        if resultado[
            "cambio_real"
        ]:

            if resultado[
                "pedido_cambio_real"
            ]:

                messages.success(
                    request,
                    (
                        f"Pedido {pedido.numero}: "
                        "pago marcado como Pagado. "
                        "El pedido quedó en estado Pagado."
                    ),
                )

            else:

                messages.success(
                    request,
                    (
                        f"Pedido {pedido.numero}: "
                        "pago marcado como Pagado. "
                        "Se conservó el estado operativo "
                        f"{pedido.get_estado_display()}."
                    ),
                )


        else:

            messages.info(
                request,
                (
                    f"Pedido {pedido.numero}: "
                    "el pago ya se encontraba "
                    "marcado como Pagado."
                ),
            )


    return redirect(
        (
            "core:cliente_pedido_detalle"
            if pedido_modo_cliente
            else "core:pedido_detalle"
        ),
        pk=pk,
    )




def pedido_estado_rapido(
    request,
    pk,
    nuevo_estado,
):
    """
    Cambio rápido de estado operativo.

    Legacy conserva la notificación histórica.
    Restaurante en R3 registra Pedido + Evento,
    pero WhatsApp Restaurante se conecta en R4.
    """

    from django.core.exceptions import (
        ObjectDoesNotExist,
        ValidationError,
    )

    from django.http import (
        HttpResponseNotAllowed,
    )

    from core.services.pedidos import (
        cambiar_estado_pedido,
        cancelar_pedido_administrativo,
    )

    from core.services.pedido_notificaciones import (
        notificar_estado_pedido_whatsapp,
        notificar_evento_pedido_whatsapp,
    )

    empresa_scope, pedido_modo_cliente = (
        _nl_pedido_scope(
            request
        )
    )

    if request.method != "POST":
        return HttpResponseNotAllowed(
            ["POST"]
        )

    from django.http import Http404
    from core.models import Pedido

    pedido_scope_qs = (
        Pedido.objects
        .filter(
            pk=pk
        )
    )

    if empresa_scope is not None:
        pedido_scope_qs = (
            pedido_scope_qs
            .filter(
                empresa_id=
                    empresa_scope
            )
        )

    if not pedido_scope_qs.exists():
        raise Http404(
            "Pedido no encontrado."
        )

    origen = str(
        request.POST.get(
            "origen"
        )
        or ""
    ).strip().lower()

    try:

        estado_solicitado = str(
            nuevo_estado
            or ""
        ).strip().lower()

        if estado_solicitado == "cancelado":

            resultado = (
                cancelar_pedido_administrativo(
                    pedido_id=
                        pk,

                    usuario_id=
                        request.user.pk,
                )
            )

        else:

            resultado = (
                cambiar_estado_pedido(
                    pedido_id=
                        pk,

                    nuevo_estado=
                        nuevo_estado,

                    usuario_id=
                        request.user.pk,
                )
            )

    except ObjectDoesNotExist:

        messages.error(
            request,
            "El pedido no existe.",
        )

        return redirect(
            (
                "core:cliente_pedido_lista"
                if pedido_modo_cliente
                else "core:pedido_lista"
            )
        )

    except ValidationError as exc:

        messages.error(
            request,
            _pedido_error_texto(
                exc
            ),
        )

    else:

        pedido = resultado[
            "pedido"
        ]

        if resultado[
            "cambio_real"
        ]:

            tipos_restaurante = {
                "comedor",
                "para_llevar",
                "domicilio",
            }

            if (
                pedido.tipo_orden
                in
                tipos_restaurante
            ):

                # ========================================================
                # TNL-PEDIDO-WHATSAPP-CONTROLADOR-R5-V1
                #
                # cambiar_estado_pedido() ya confirmó Pedido + Evento.
                #
                # Restaurante notifica:
                #   - preparando
                #   - listo
                #   - en_camino
                #   - entregado
                #
                # El servicio por evento es idempotente y está
                # desacoplado del wrapper WhatsApp legacy.
                #
                # Un fallo de WhatsApp nunca revierte Pedido.
                # ========================================================

                evento = resultado.get(
                    "evento"
                )

                estado_evento = str(
                    getattr(
                        evento,
                        "estado_nuevo",
                        "",
                    )
                    or ""
                ).strip().lower()

                if (
                    evento is not None
                    and
                    estado_evento
                    in {
                        "preparando",
                        "listo",
                        "en_camino",
                        "entregado",
                        "cancelado",
                    }
                ):

                    notificacion = (
                        notificar_evento_pedido_whatsapp(
                            evento_id=
                                evento.id
                        )
                    )

                    if notificacion[
                        "enviado"
                    ]:

                        messages.success(
                            request,
                            (
                                f"Pedido {pedido.numero}: "
                                "estado actualizado a "
                                f"{pedido.get_estado_display()} "
                                "y cliente notificado por WhatsApp."
                            ),
                        )

                    elif notificacion[
                        "aplicable"
                    ]:

                        messages.warning(
                            request,
                            (
                                f"Pedido {pedido.numero}: "
                                "estado actualizado a "
                                f"{pedido.get_estado_display()}. "
                                "No se pudo enviar WhatsApp: "
                                f"{notificacion['motivo']}"
                            ),
                        )

                    else:

                        messages.warning(
                            request,
                            (
                                f"Pedido {pedido.numero}: "
                                "estado actualizado a "
                                f"{pedido.get_estado_display()}. "
                                "No se envió WhatsApp: "
                                f"{notificacion['motivo']}"
                            ),
                        )

                else:

                    messages.success(
                        request,
                        (
                            f"Pedido {pedido.numero}: "
                            "estado actualizado a "
                            f"{pedido.get_estado_display()}."
                        ),
                    )

            else:

                # Comportamiento legacy preservado.
                notificacion = (
                    notificar_estado_pedido_whatsapp(
                        pedido=pedido
                    )
                )

                if notificacion[
                    "enviado"
                ]:

                    messages.success(
                        request,
                        (
                            f"Pedido {pedido.numero}: "
                            "estado actualizado a "
                            f"{pedido.get_estado_display()} "
                            "y cliente notificado por WhatsApp."
                        ),
                    )

                elif notificacion[
                    "aplicable"
                ]:

                    messages.warning(
                        request,
                        (
                            f"Pedido {pedido.numero}: "
                            "estado actualizado a "
                            f"{pedido.get_estado_display()}. "
                            "No se pudo enviar WhatsApp: "
                            f"{notificacion['motivo']}"
                        ),
                    )

                else:

                    messages.warning(
                        request,
                        (
                            f"Pedido {pedido.numero}: "
                            "estado actualizado a "
                            f"{pedido.get_estado_display()}. "
                            f"{notificacion['motivo']}"
                        ),
                    )

        else:

            messages.info(
                request,
                (
                    f"Pedido {pedido.numero}: "
                    "ya se encontraba en estado "
                    f"{pedido.get_estado_display()}."
                ),
            )

    if origen == "lista":

        return redirect(
            (
                "core:cliente_pedido_lista"
                if pedido_modo_cliente
                else "core:pedido_lista"
            )
        )

    return redirect(
        (
            "core:cliente_pedido_detalle"
            if pedido_modo_cliente
            else "core:pedido_detalle"
        ),
        pk=pk,
    )


