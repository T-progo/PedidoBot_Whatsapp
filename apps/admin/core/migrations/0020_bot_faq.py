from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        (
            "core",
            "0019_tipos_estetica_administrativa",
        ),
    ]

    operations = [
        migrations.AddField(
            model_name="bot",
            name="faq",
            field=models.TextField(
                blank=True,
                default="",
                help_text=(
                    "Información real del negocio que la IA puede utilizar "
                    "para responder preguntas frecuentes. "
                    "No incluyas contraseñas, tokens ni credenciales."
                ),
                max_length=20000,
                verbose_name=(
                    "Preguntas frecuentes / "
                    "Base de conocimiento"
                ),
            ),
        ),
    ]
