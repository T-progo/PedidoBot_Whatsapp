from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Max
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)
from django.views.decorators.http import require_POST

from .forms_plantillas_maestras import (
    PlantillaMaestraForm,
    PlantillaVariableMaestraForm,
)
from .models import (
    InstalacionPlantilla,
    PlantillaMaestra,
    PlantillaVariableMaestra,
)


@login_required
def plantilla_maestra_lista(request):

    plantillas = list(
        PlantillaMaestra.objects
        .all()
        .order_by(
            "tipo",
            "nombre",
            "-version",
        )
    )

    for plantilla in plantillas:

        plantilla.variables_total = (
            PlantillaVariableMaestra.objects
            .filter(
                plantilla_maestra=plantilla
            )
            .count()
        )

        plantilla.instalaciones_total = (
            InstalacionPlantilla.objects
            .filter(
                plantilla_maestra=plantilla
            )
            .count()
        )

    return render(
        request,
        "core/plantilla_maestra_lista.html",
        {
            "plantillas": plantillas,
        },
    )


@login_required
def plantilla_maestra_detalle(request, pk):

    plantilla = get_object_or_404(
        PlantillaMaestra,
        pk=pk,
    )

    variables = (
        PlantillaVariableMaestra.objects
        .filter(
            plantilla_maestra=plantilla
        )
        .order_by(
            "orden",
            "id",
        )
    )

    instalaciones = (
        InstalacionPlantilla.objects
        .filter(
            plantilla_maestra=plantilla
        )
        .select_related(
            "empresa",
            "licencia",
            "plantilla",
        )
        .order_by(
            "-id"
        )
    )

    return render(
        request,
        "core/plantilla_maestra_detalle.html",
        {
            "plantilla": plantilla,
            "variables": variables,
            "instalaciones": instalaciones,
        },
    )


@login_required
@transaction.atomic
def plantilla_maestra_crear(request):

    if request.method == "POST":

        form = PlantillaMaestraForm(
            request.POST
        )

        if form.is_valid():

            plantilla = form.save()

            messages.success(
                request,
                (
                    f"Plantilla maestra "
                    f"{plantilla.nombre} v"
                    f"{plantilla.version} creada."
                ),
            )

            return redirect(
                "core:plantilla_maestra_detalle",
                pk=plantilla.pk,
            )

    else:

        form = PlantillaMaestraForm(
            initial={
                "version": 1,
                "estado": "borrador",
                "activa": True,
                "configuracion": {
                    "moneda": "MXN",
                    "crear_bot": True,
                    "crear_catalogo": True,
                },
            }
        )

    return render(
        request,
        "core/plantilla_maestra_form.html",
        {
            "form": form,
            "titulo": "Nueva plantilla maestra",
            "modo": "crear",
        },
    )


@login_required
@transaction.atomic
def plantilla_maestra_editar(request, pk):

    plantilla = get_object_or_404(
        PlantillaMaestra,
        pk=pk,
    )

    if request.method == "POST":

        form = PlantillaMaestraForm(
            request.POST,
            instance=plantilla,
        )

        if form.is_valid():

            plantilla = form.save()

            messages.success(
                request,
                "Plantilla maestra actualizada correctamente.",
            )

            return redirect(
                "core:plantilla_maestra_detalle",
                pk=plantilla.pk,
            )

    else:

        form = PlantillaMaestraForm(
            instance=plantilla
        )

    return render(
        request,
        "core/plantilla_maestra_form.html",
        {
            "form": form,
            "plantilla": plantilla,
            "titulo": (
                f"Editar {plantilla.nombre} "
                f"v{plantilla.version}"
            ),
            "modo": "editar",
        },
    )


@login_required
@transaction.atomic
def plantilla_variable_maestra_crear(
    request,
    plantilla_pk,
):

    plantilla = get_object_or_404(
        PlantillaMaestra,
        pk=plantilla_pk,
    )

    if request.method == "POST":

        form = PlantillaVariableMaestraForm(
            request.POST
        )

        if form.is_valid():

            variable = form.save(
                commit=False
            )

            variable.plantilla_maestra = (
                plantilla
            )

            variable.save()

            messages.success(
                request,
                (
                    f"Variable "
                    f"{variable.clave} agregada."
                ),
            )

            return redirect(
                "core:plantilla_maestra_detalle",
                pk=plantilla.pk,
            )

    else:

        siguiente = (
            PlantillaVariableMaestra.objects
            .filter(
                plantilla_maestra=plantilla
            )
            .aggregate(
                mayor=Max("orden")
            )["mayor"]
            or 0
        ) + 10

        form = PlantillaVariableMaestraForm(
            initial={
                "orden": siguiente,
                "activa": True,
            }
        )

    return render(
        request,
        "core/plantilla_variable_maestra_form.html",
        {
            "form": form,
            "plantilla": plantilla,
            "titulo": "Nueva variable maestra",
        },
    )


@login_required
@transaction.atomic
def plantilla_variable_maestra_editar(
    request,
    pk,
):

    variable = get_object_or_404(
        PlantillaVariableMaestra,
        pk=pk,
    )

    plantilla = variable.plantilla_maestra

    if request.method == "POST":

        form = PlantillaVariableMaestraForm(
            request.POST,
            instance=variable,
        )

        if form.is_valid():

            form.save()

            messages.success(
                request,
                "Variable maestra actualizada.",
            )

            return redirect(
                "core:plantilla_maestra_detalle",
                pk=plantilla.pk,
            )

    else:

        form = PlantillaVariableMaestraForm(
            instance=variable
        )

    return render(
        request,
        "core/plantilla_variable_maestra_form.html",
        {
            "form": form,
            "plantilla": plantilla,
            "variable": variable,
            "titulo": "Editar variable maestra",
        },
    )


@login_required
@require_POST
@transaction.atomic
def plantilla_variable_maestra_eliminar(
    request,
    pk,
):

    variable = get_object_or_404(
        PlantillaVariableMaestra,
        pk=pk,
    )

    plantilla_pk = (
        variable.plantilla_maestra_id
    )

    clave = variable.clave

    variable.delete()

    messages.success(
        request,
        f"Variable {clave} eliminada.",
    )

    return redirect(
        "core:plantilla_maestra_detalle",
        pk=plantilla_pk,
    )


@login_required
@require_POST
@transaction.atomic
def plantilla_maestra_publicar(
    request,
    pk,
):

    plantilla = get_object_or_404(
        PlantillaMaestra,
        pk=pk,
    )

    plantilla.estado = "publicada"
    plantilla.activa = True

    plantilla.save(
        update_fields=[
            "estado",
            "activa",
            "actualizado_en",
        ]
    )

    messages.success(
        request,
        (
            f"{plantilla.nombre} "
            f"v{plantilla.version} publicada."
        ),
    )

    return redirect(
        "core:plantilla_maestra_detalle",
        pk=plantilla.pk,
    )


@login_required
@require_POST
@transaction.atomic
def plantilla_maestra_retirar(
    request,
    pk,
):

    plantilla = get_object_or_404(
        PlantillaMaestra,
        pk=pk,
    )

    plantilla.estado = "retirada"
    plantilla.activa = False

    plantilla.save(
        update_fields=[
            "estado",
            "activa",
            "actualizado_en",
        ]
    )

    messages.success(
        request,
        (
            f"{plantilla.nombre} "
            f"v{plantilla.version} retirada."
        ),
    )

    return redirect(
        "core:plantilla_maestra_detalle",
        pk=plantilla.pk,
    )


@login_required
@require_POST
@transaction.atomic
def plantilla_maestra_nueva_version(
    request,
    pk,
):

    origen = get_object_or_404(
        PlantillaMaestra,
        pk=pk,
    )

    ultima_version = (
        PlantillaMaestra.objects
        .filter(
            slug=origen.slug
        )
        .aggregate(
            version=Max("version")
        )["version"]
        or 0
    )

    nueva_version = (
        ultima_version + 1
    )

    nueva = PlantillaMaestra.objects.create(
        nombre=origen.nombre,
        slug=origen.slug,
        tipo=origen.tipo,
        version=nueva_version,
        descripcion=origen.descripcion,
        configuracion=origen.configuracion,
        estado="borrador",
        activa=False,
    )

    variables = (
        PlantillaVariableMaestra.objects
        .filter(
            plantilla_maestra=origen
        )
        .order_by(
            "orden",
            "id",
        )
    )

    nuevas_variables = []

    for variable in variables:

        nuevas_variables.append(
            PlantillaVariableMaestra(
                plantilla_maestra=nueva,
                clave=variable.clave,
                nombre=variable.nombre,
                tipo_dato=variable.tipo_dato,
                valor_default=(
                    variable.valor_default
                ),
                requerida=variable.requerida,
                descripcion=variable.descripcion,
                orden=variable.orden,
                activa=variable.activa,
            )
        )

    PlantillaVariableMaestra.objects.bulk_create(
        nuevas_variables
    )

    messages.success(
        request,
        (
            f"Creada {nueva.nombre} "
            f"v{nueva.version} como borrador."
        ),
    )

    return redirect(
        "core:plantilla_maestra_detalle",
        pk=nueva.pk,
    )
