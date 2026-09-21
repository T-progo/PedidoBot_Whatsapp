from django.db import (
    migrations,
    models,
)

import django.db.models.deletion


class Migration(
    migrations.Migration
):

    dependencies = [
        (
            "core",
            "0016_agenda_horarios",
        ),
    ]


    operations = [

        migrations.CreateModel(
            name=
                "AceptacionTerminos",

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
                    "version",
                    models.CharField(
                        max_length=40,
                    ),
                ),

                (
                    "documento_sha256",
                    models.CharField(
                        max_length=64,
                    ),
                ),

                (
                    "contenido_snapshot",
                    models.TextField(),
                ),

                (
                    "origen_vinculacion",
                    models.CharField(
                        choices=[
                            (
                                "whatsapp",
                                "WhatsApp",
                            ),
                            (
                                "google_calendar",
                                "Google Calendar",
                            ),
                            (
                                "mercadopago",
                                "Mercado Pago",
                            ),
                        ],
                        max_length=30,
                    ),
                ),

                (
                    "usuario_username_snapshot",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=150,
                    ),
                ),

                (
                    "usuario_email_snapshot",
                    models.EmailField(
                        blank=True,
                        default="",
                        max_length=254,
                    ),
                ),

                (
                    "ip_aceptacion",
                    models.GenericIPAddressField(
                        blank=True,
                        null=True,
                    ),
                ),

                (
                    "user_agent",
                    models.TextField(
                        blank=True,
                        default="",
                    ),
                ),

                (
                    "aceptado_en",
                    models.DateTimeField(
                        auto_now_add=True,
                        db_index=True,
                    ),
                ),

                (
                    "empresa",
                    models.ForeignKey(
                        on_delete=
                            django.db.models.deletion.CASCADE,

                        related_name=
                            "aceptaciones_terminos",

                        to="core.empresa",
                    ),
                ),

                (
                    "perfil_usuario",
                    models.ForeignKey(
                        blank=True,
                        null=True,

                        on_delete=
                            django.db.models.deletion.SET_NULL,

                        related_name=
                            "aceptaciones_terminos",

                        to="core.perfilusuario",
                    ),
                ),

            ],

            options={
                "verbose_name":
                    "Aceptación de términos",

                "verbose_name_plural":
                    "Aceptaciones de términos",

                "ordering": (
                    "-aceptado_en",
                    "-id",
                ),
            },
        ),


        migrations.AddConstraint(
            model_name=
                "aceptacionterminos",

            constraint=
                models.UniqueConstraint(
                    fields=(
                        "empresa",
                        "version",
                    ),
                    name=
                        "tnl_terms_empresa_version_unique",
                ),
        ),


        migrations.AddIndex(
            model_name=
                "aceptacionterminos",

            index=
                models.Index(
                    fields=[
                        "empresa",
                        "version",
                    ],
                    name=
                        "tnl_terms_emp_ver_idx",
                ),
        ),

    ]
