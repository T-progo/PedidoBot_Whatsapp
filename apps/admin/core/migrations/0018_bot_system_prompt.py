from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        (
            "core",
            "0017_aceptacion_terminos",
        ),
    ]

    operations = [
        migrations.AddField(
            model_name="bot",
            name="system_prompt",
            field=models.TextField(
                blank=True,
                default="",
                help_text=(
                    "Instrucciones específicas para la IA de este bot. "
                    "Déjalo en blanco para utilizar las instrucciones "
                    "base definidas por NegocioListo o por su plantilla."
                ),
                max_length=12000,
                verbose_name=(
                    "System Prompt / "
                    "Instrucciones personalizadas"
                ),
            ),
        ),
    ]
