from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        (
            "core",
            "0015_google_calendar_base",
        ),
    ]

    operations = [

        migrations.CreateModel(
            name="ConfiguracionAgenda",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "duracion_predeterminada_minutos",
                    models.PositiveSmallIntegerField(
                        default=30,
                    ),
                ),
                (
                    "intervalo_slots_minutos",
                    models.PositiveSmallIntegerField(
                        default=30,
                    ),
                ),
                (
                    "anticipacion_minima_minutos",
                    models.PositiveIntegerField(
                        default=0,
                    ),
                ),
                (
                    "creado_en",
                    models.DateTimeField(
                        auto_now_add=True,
                    ),
                ),
                (
                    "actualizado_en",
                    models.DateTimeField(
                        auto_now=True,
                    ),
                ),
                (
                    "empresa",
                    models.OneToOneField(
                        on_delete=
                            django.db.models.deletion.CASCADE,
                        related_name=
                            "configuracion_agenda",
                        to="core.empresa",
                    ),
                ),
            ],
            options={
                "verbose_name":
                    "Configuración de agenda",
                "verbose_name_plural":
                    "Configuraciones de agenda",
            },
        ),

        migrations.CreateModel(
            name="HorarioAtencion",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "dia_semana",
                    models.PositiveSmallIntegerField(
                        choices=[
                            (0, "Lunes"),
                            (1, "Martes"),
                            (2, "Miércoles"),
                            (3, "Jueves"),
                            (4, "Viernes"),
                            (5, "Sábado"),
                            (6, "Domingo"),
                        ],
                    ),
                ),
                (
                    "hora_inicio",
                    models.TimeField(),
                ),
                (
                    "hora_fin",
                    models.TimeField(),
                ),
                (
                    "activo",
                    models.BooleanField(
                        default=True,
                    ),
                ),
                (
                    "creado_en",
                    models.DateTimeField(
                        auto_now_add=True,
                    ),
                ),
                (
                    "actualizado_en",
                    models.DateTimeField(
                        auto_now=True,
                    ),
                ),
                (
                    "empresa",
                    models.ForeignKey(
                        on_delete=
                            django.db.models.deletion.CASCADE,
                        related_name=
                            "horarios_atencion",
                        to="core.empresa",
                    ),
                ),
            ],
            options={
                "verbose_name":
                    "Horario de atención",
                "verbose_name_plural":
                    "Horarios de atención",
                "ordering": (
                    "empresa_id",
                    "dia_semana",
                    "hora_inicio",
                ),
            },
        ),

        migrations.AddConstraint(
            model_name="horarioatencion",
            constraint=
                models.UniqueConstraint(
                    fields=(
                        "empresa",
                        "dia_semana",
                        "hora_inicio",
                        "hora_fin",
                    ),
                    name=
                        "tnl_agenda_horario_unico",
                ),
        ),
    ]
