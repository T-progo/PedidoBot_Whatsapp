"""
TNL-WHATSAPP-WATCHDOG-V1

Una sola pasada del watchdog de instancias WhatsApp.
La programación cada 60 segundos la hará systemd.
"""

from django.core.management.base import (
    BaseCommand,
    CommandError,
)

from core.services.whatsapp_watchdog import (
    HEALTHY,
    EstadoWatchdogArchivo,
    ejecutar_pasada,
    ruta_estado,
)


class Command(BaseCommand):

    help = (
        "Revisa una vez las instancias WhatsApp activas "
        "y recupera sólo las conexiones seguras."
    )


    def add_arguments(
        self,
        parser,
    ):

        parser.add_argument(
            "--dry-run",
            action="store_true",
            help=(
                "Consulta y clasifica sin reiniciar, "
                "reconectar ni guardar estado."
            ),
        )

        parser.add_argument(
            "--state-file",
            default=None,
            help=(
                "Archivo de estado anti-bucle "
                "(por defecto $TNL_WHATSAPP_WATCHDOG_STATE "
                "o /var/lib/tnl-whatsapp-watchdog/estado.json)."
            ),
        )


    def handle(
        self,
        *args,
        **options,
    ):

        dry_run = bool(
            options["dry_run"]
        )

        almacen = EstadoWatchdogArchivo(
            options["state_file"]
            or
            ruta_estado()
        )

        resultado = ejecutar_pasada(
            dry_run=dry_run,
            almacen=almacen,
        )

        # Sólo instancias con algo que reportar; nada de datos
        # de clientes, números ni QR.
        for item in resultado["instancias"]:

            if (
                item["clasificacion"] == HEALTHY
                and item["accion"] == "none"
            ):
                continue

            self.stdout.write(
                (
                    f"instance={item['instancia']} "
                    f"state={item['estado']} "
                    f"class={item['clasificacion']} "
                    f"action={item['accion']} "
                    f"consecutive={item['consecutivos']}"
                )
            )

        resumen = resultado["resumen"]

        self.stdout.write(
            (
                f"checked={resumen['checked']} "
                f"healthy={resumen['healthy']} "
                f"recoverable={resumen['recoverable']} "
                f"recovered={resumen['recovered']} "
                f"human_required={resumen['human_required']} "
                f"unknown={resumen['unknown']} "
                f"errors={resumen['errors']} "
                f"dry_run={int(dry_run)} "
                f"state_corrupt={int(resumen['state_corrupt'])}"
            )
        )

        if (
            resumen["errors"]
            and
            not dry_run
        ):

            raise CommandError(
                "La revisión de instancias WhatsApp "
                "terminó con errores."
            )
