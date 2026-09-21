"""
TNL-CLIENT-LIFECYCLE-COMMAND-V1
"""

from django.core.management.base import (
    BaseCommand,
    CommandError,
)

from core.services.client_lifecycle import (
    reconciliar_todas_empresas,
)


class Command(BaseCommand):

    help = (
        "Reconcilia licencias, sesiones "
        "y pausa/reactiva Typebot por empresa."
    )


    def add_arguments(
        self,
        parser,
    ):

        parser.add_argument(
            "--dry-run",
            action="store_true",
            help=(
                "Calcula estado sin escribir "
                "en BD ni Evolution."
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

        result = (
            reconciliar_todas_empresas(
                dry_run=dry_run
            )
        )

        self.stdout.write(
            (
                "companies="
                f"{result['companies']} "
                "operational="
                f"{result['operational']} "
                "suspended="
                f"{result['suspended']} "
                "external_errors="
                f"{result['external_errors']} "
                "dry_run="
                f"{int(dry_run)}"
            )
        )

        if (
            result[
                "external_errors"
            ]
            and
            not dry_run
        ):

            raise CommandError(
                "La reconciliación terminó "
                "con errores externos."
            )
