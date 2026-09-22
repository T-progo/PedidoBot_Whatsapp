"""
Cliente mínimo de Evolution API para NegocioListo.

No persiste ni expone API keys, tokens, JIDs o QR.
El QR solamente se devuelve a vistas Django autenticadas.
"""

import json
import ssl

from pathlib import Path
from urllib.error import (
    HTTPError,
    URLError,
)
from urllib.parse import quote
from urllib.request import (
    Request,
    urlopen,
)


BASE_URL = (
    "https://evolution.negociolisto.com.mx"
)

SECRET_PATH = Path(
    "/opt/tunegociolisto/"
    "configs/django-secrets/"
    "evolution_api_key"
)


class EvolutionClientError(Exception):
    pass


class EvolutionClient:

    def __init__(self):

        self.base_url = (
            BASE_URL.rstrip("/")
        )

        self.api_key = (
            self._read_api_key()
        )


    def _read_api_key(self):

        try:

            value = (
                SECRET_PATH
                .read_text(
                    encoding="utf-8"
                )
                .strip()
            )

        except OSError as exc:

            raise EvolutionClientError(
                "No fue posible cargar "
                "la credencial de Evolution."
            ) from exc


        if not value:

            raise EvolutionClientError(
                "La credencial de Evolution "
                "está vacía."
            )


        return value


    def _request(
        self,
        method,
        path,
        payload=None,
        timeout=30,
    ):

        url = (
            self.base_url
            + path
        )


        body = None

        headers = {
            "apikey": self.api_key,
            "Accept": "application/json",
        }


        if payload is not None:

            body = json.dumps(
                payload
            ).encode(
                "utf-8"
            )

            headers[
                "Content-Type"
            ] = "application/json"


        request = Request(
            url=url,
            data=body,
            headers=headers,
            method=method,
        )


        try:

            with urlopen(
                request,
                timeout=timeout,
                context=ssl.create_default_context(),
            ) as response:

                raw = (
                    response
                    .read()
                    .decode(
                        "utf-8"
                    )
                )

        except HTTPError as exc:

            raise EvolutionClientError(
                f"Evolution respondió HTTP "
                f"{exc.code}."
            ) from exc

        except URLError as exc:

            raise EvolutionClientError(
                "No fue posible conectar "
                "con Evolution."
            ) from exc

        except TimeoutError as exc:

            raise EvolutionClientError(
                "Evolution agotó el tiempo "
                "de respuesta."
            ) from exc


        if not raw.strip():

            return {}


        try:

            return json.loads(
                raw
            )

        except json.JSONDecodeError as exc:

            raise EvolutionClientError(
                "Evolution devolvió una "
                "respuesta JSON inválida."
            ) from exc


    @staticmethod
    def _items(data):

        if isinstance(
            data,
            list,
        ):

            return data


        if isinstance(
            data,
            dict,
        ):

            if isinstance(
                data.get("instances"),
                list,
            ):

                return data["instances"]


            if isinstance(
                data.get("data"),
                list,
            ):

                return data["data"]


            return [data]


        return []


    @staticmethod
    def _summary(item):

        if not isinstance(
            item,
            dict,
        ):

            return None


        instance = item.get(
            "instance",
            item,
        )


        if not isinstance(
            instance,
            dict,
        ):

            instance = item


        name = (
            instance.get(
                "instanceName"
            )
            or
            instance.get(
                "name"
            )
            or
            item.get(
                "instanceName"
            )
            or
            item.get(
                "name"
            )
        )


        if not name:

            return None


        state = (
            instance.get(
                "connectionStatus"
            )
            or
            instance.get(
                "state"
            )
            or
            instance.get(
                "status"
            )
            or
            item.get(
                "connectionStatus"
            )
            or
            item.get(
                "state"
            )
            or
            item.get(
                "status"
            )
            or
            "desconocido"
        )


        owner = (
            instance.get(
                "ownerJid"
            )
            or
            item.get(
                "ownerJid"
            )
        )


        integration = (
            instance.get(
                "integration"
            )
            or
            item.get(
                "integration"
            )
            or
            ""
        )


        # TNL-WHATSAPP-WATCHDOG-V1
        # Sólo el código numérico; disconnectionObject
        # puede contener JIDs y nunca se expone.
        reason = (
            instance.get(
                "disconnectionReasonCode"
            )
            if instance.get(
                "disconnectionReasonCode"
            ) is not None
            else item.get(
                "disconnectionReasonCode"
            )
        )

        try:
            reason = (
                int(reason)
                if reason is not None
                else None
            )
        except (
            TypeError,
            ValueError,
        ):
            reason = None


        return {
            "name": str(name),
            "state": str(state),
            "owner_present": bool(
                owner
            ),
            "integration": str(
                integration
            ),
            "disconnection_reason": reason,
        }


    def fetch_instances(self):

        return self._request(
            "GET",
            "/instance/fetchInstances",
            timeout=20,
        )


    def find_instance(
        self,
        instance_name,
    ):

        data = (
            self.fetch_instances()
        )


        for item in self._items(
            data
        ):

            summary = (
                self._summary(
                    item
                )
            )


            if (
                summary
                and
                summary["name"]
                == instance_name
            ):

                return summary


        return None


    def create_instance(
        self,
        instance_name,
    ):

        payload = {
            "instanceName":
                instance_name,

            "integration":
                "WHATSAPP-BAILEYS",

            "qrcode":
                True,

            "settings": {
                "groupsIgnore":
                    True,

                "alwaysOnline":
                    False,

                "readMessages":
                    False,

                "readStatus":
                    False,

                "rejectCall":
                    False,
            },
        }


        return self._request(
            "POST",
            "/instance/create",
            payload=payload,
            timeout=30,
        )


    def connect_instance(
        self,
        instance_name,
    ):

        safe_name = quote(
            instance_name,
            safe="",
        )


        return self._request(
            "GET",
            (
                "/instance/connect/"
                + safe_name
            ),
            timeout=30,
        )


    # --------------------------------------------------------
    # TNL-WHATSAPP-WATCHDOG-V1
    #
    # Sólo lectura de estado vivo y reinicio de la conexión.
    # No hay logout ni delete aquí.
    # --------------------------------------------------------

    @staticmethod
    def _instancia_administrada(
        instance_name,
    ):

        import re

        instance_name = str(
            instance_name
            or ""
        ).strip()


        if not re.fullmatch(
            r"tnl-e[0-9]+-i[0-9]+",
            instance_name,
        ):

            raise EvolutionClientError(
                "Instancia Evolution inválida."
            )


        return instance_name


    def connection_state(
        self,
        instance_name,
    ):
        """
        Estado VIVO de la instancia (open/connecting/close).

        fetchInstances devuelve el estado guardado, que puede
        quedarse en "connecting" aunque la sesión esté cerrada.
        """

        instance_name = (
            self._instancia_administrada(
                instance_name
            )
        )

        data = self._request(
            "GET",
            (
                "/instance/connectionState/"
                + quote(
                    instance_name,
                    safe="",
                )
            ),
            timeout=15,
        )

        instance = (
            data.get("instance")
            if isinstance(data, dict)
            else None
        )

        state = (
            instance.get("state")
            if isinstance(instance, dict)
            else None
        )

        return {
            "name": instance_name,
            "state": (
                str(state).strip().lower()
                if state
                else "desconocido"
            ),
        }


    def restart_instance(
        self,
        instance_name,
    ):
        """
        Reinicia la conexión de una instancia open/connecting.

        Evolution puede responder HTTP 200 con {"error": true};
        eso se trata como fallo, igual que un HTTP de error.
        """

        instance_name = (
            self._instancia_administrada(
                instance_name
            )
        )

        data = self._request(
            "POST",
            (
                "/instance/restart/"
                + quote(
                    instance_name,
                    safe="",
                )
            ),
            timeout=30,
        )

        instance = (
            data.get("instance")
            if isinstance(data, dict)
            else None
        )

        if (
            not isinstance(data, dict)
            or data.get("error") is True
            or not isinstance(instance, dict)
        ):

            raise EvolutionClientError(
                "Evolution no confirmó el reinicio "
                "de la instancia."
            )

        state = (
            instance.get("status")
            or
            instance.get("state")
        )

        return {
            "name": instance_name,
            "state": (
                str(state).strip().lower()
                if state
                else "desconocido"
            ),
        }


    # --------------------------------------------------------
    # NEGOCIOLISTO-TYPEBOT-AUTO-V1
    # --------------------------------------------------------

    def find_typebots(
        self,
        instance_name,
    ):
        """
        Obtiene las integraciones Typebot de una
        instancia Evolution.
        """

        safe_name = quote(
            instance_name,
            safe="",
        )

        return self._request(
            "GET",
            (
                "/typebot/find/"
                + safe_name
            ),
            timeout=30,
        )


    # NEGOCIOLISTO-TYPEBOT-SESSION-POLICY-V2
    def ensure_typebot_integration(
        self,
        instance_name,
    ):
        """
        Garantiza la integración Typebot de una
        nueva instancia NegocioListo.

        Seguridad:
        - no modifica integraciones existentes;
        - si existe una configuración diferente,
          falla de forma cerrada;
        - solo crea cuando no existe ninguna.
        """

        import re

        instance_name = str(
            instance_name
            or ""
        ).strip()

        if not re.fullmatch(
            r"tnl-e[0-9]+-i[0-9]+",
            instance_name,
        ):
            raise EvolutionClientError(
                "La instancia no cumple "
                "el patrón NegocioListo."
            )


        expected = {
            "enabled": True,

            "description":
                "TNL-LIST-FALLBACK-V1",

            "url":
                "https://bot.negociolisto.com.mx",

            "typebot":
                instance_name,

            "triggerType":
                "all",

            "triggerOperator":
                "equals",

            "triggerValue":
                "hola",

            "expire":
                30,

            "keepOpen":
                False,

            "keywordFinish":
                "",

            "delayMessage":
                0,

            "unknownMessage":
                "",

            "listeningFromMe":
                False,

            "stopBotFromMe":
                False,

            # NEGOCIOLISTO-TYPEBOT-ANTI-LOOP-V1
            "debounceTime":
                3,

            "ignoreJids":
                self._nl_managed_ignore_jids(
                    exclude_instance=
                        instance_name,
                ),
        }


        current_data = (
            self.find_typebots(
                instance_name
            )
        )

        current = self._items(
            current_data
        )

        current = [
            item
            for item in current
            if isinstance(
                item,
                dict,
            )
        ]


        if len(current) > 1:
            raise EvolutionClientError(
                "La instancia tiene más de una "
                "integración Typebot."
            )


        critical_fields = (
            "enabled",
            "url",
            "typebot",
            "triggerType",
            "triggerOperator",
            "triggerValue",
            "expire",
            "keepOpen",
        )


        if len(current) == 1:

            integration = current[0]

            mismatches = [
                field
                for field in critical_fields
                if integration.get(field)
                != expected[field]
            ]

            if mismatches:
                raise EvolutionClientError(
                    "La integración Typebot "
                    "existente no coincide con "
                    "la configuración esperada: "
                    + ", ".join(
                        mismatches
                    )
                    + "."
                )

            # Muy importante:
            # una integración existente correcta
            # se conserva INTACTA.
            return {
                "created": False,
                "integration":
                    integration,
            }


        safe_name = quote(
            instance_name,
            safe="",
        )

        self._request(
            "POST",
            (
                "/typebot/create/"
                + safe_name
            ),
            payload=expected,
            timeout=30,
        )


        verify_data = (
            self.find_typebots(
                instance_name
            )
        )

        verify = [
            item
            for item in self._items(
                verify_data
            )
            if isinstance(
                item,
                dict,
            )
        ]


        if len(verify) != 1:
            raise EvolutionClientError(
                "No fue posible verificar "
                "la integración Typebot creada."
            )


        integration = verify[0]

        mismatches = [
            field
            for field in critical_fields
            if integration.get(field)
            != expected[field]
        ]

        if mismatches:
            raise EvolutionClientError(
                "La integración Typebot creada "
                "no coincide con lo esperado: "
                + ", ".join(
                    mismatches
                )
                + "."
            )


        if (
            integration.get(
                "description"
            )
            !=
            "TNL-LIST-FALLBACK-V1"
        ):
            raise EvolutionClientError(
                "Evolution no conservó la marca "
                "de compatibilidad Typebot."
            )


        return {
            "created": True,
            "integration":
                integration,
        }


    # --------------------------------------------------------
    # NEGOCIOLISTO-TYPEBOT-ANTI-LOOP-V1
    # --------------------------------------------------------
    #
    # Política global:
    # - cualquier mensaje puede iniciar;
    # - debounce 3 segundos;
    # - sesión 30 minutos;
    # - no escuchar mensajes propios;
    # - ignorar otros WhatsApps administrados
    #   por NegocioListo.
    #

    @staticmethod
    def _nl_owner_digits(
        value,
    ):
        import re

        text = str(
            value
            or ""
        ).strip()

        if not text:
            return ""

        if "@" in text:

            domain = (
                text
                .split("@", 1)[1]
                .lower()
            )

            if domain not in (
                "s.whatsapp.net",
                "c.us",
            ):
                return ""

        local = (
            text
            .split("@", 1)[0]
            .split(":", 1)[0]
        )

        return re.sub(
            r"\D",
            "",
            local,
        )


    @classmethod
    def _nl_owner_jid_variants(
        cls,
        value,
    ):
        """
        Replica las variantes relevantes
        utilizadas por Baileys/Evolution.

        México:
        52XXXXXXXXXX
        521XXXXXXXXXX

        Argentina:
        54XXXXXXXXXX
        549XXXXXXXXXX
        """

        digits = cls._nl_owner_digits(
            value
        )

        if not digits:
            return set()


        variants = {
            digits
        }


        if digits.startswith(
            "52"
        ):

            if (
                len(digits) == 13
                and
                digits[2:3] == "1"
            ):

                variants.add(
                    digits[:2]
                    +
                    digits[3:]
                )

            elif len(digits) == 12:

                variants.add(
                    digits[:2]
                    +
                    "1"
                    +
                    digits[2:]
                )


        elif digits.startswith(
            "54"
        ):

            if (
                len(digits) == 13
                and
                digits[2:3] == "9"
            ):

                variants.add(
                    digits[:2]
                    +
                    digits[3:]
                )

            elif len(digits) == 12:

                variants.add(
                    digits[:2]
                    +
                    "9"
                    +
                    digits[2:]
                )


        return {
            item
            +
            "@s.whatsapp.net"
            for item in variants
            if item
        }


    def _nl_managed_whatsapp_context(
        self,
    ):
        import re

        from core.models import Canal

        canales = (
            Canal.objects
            .filter(
                tipo="whatsapp"
            )
            .select_related(
                "bot",
                "bot__empresa",
            )
            .order_by("id")
        )


        managed = {}

        for canal in canales:

            instance = str(
                canal.identificador
                or ""
            ).strip()

            if not re.fullmatch(
                r"tnl-e[0-9]+-i[0-9]+",
                instance,
            ):
                continue

            if not str(
                canal.bot.identificador_externo
                or ""
            ).strip():
                continue

            managed[
                instance
            ] = canal


        raw_instances = (
            self.fetch_instances()
        )

        evolution_items = [
            item
            for item in self._items(
                raw_instances
            )
            if isinstance(
                item,
                dict,
            )
        ]


        by_name = {}

        for item in evolution_items:

            name = str(
                item.get("name")
                or
                item.get(
                    "instanceName"
                )
                or
                ""
            ).strip()

            if name:
                by_name[name] = item


        owners = {}
        variants = {}


        for instance in managed:

            item = by_name.get(
                instance
            )

            if not item:
                continue

            owner_raw = (
                item.get("ownerJid")
                or ""
            )

            digits = (
                self._nl_owner_digits(
                    owner_raw
                )
            )

            if not digits:
                continue

            owners[
                instance
            ] = (
                digits
                +
                "@s.whatsapp.net"
            )

            variants[
                instance
            ] = (
                self
                ._nl_owner_jid_variants(
                    owner_raw
                )
            )


        return (
            managed,
            owners,
            variants,
        )


    def _nl_managed_ignore_jids(
        self,
        *,
        exclude_instance=None,
    ):
        (
            _managed,
            _owners,
            variants,
        ) = (
            self
            ._nl_managed_whatsapp_context()
        )


        result = set()

        for (
            instance,
            values,
        ) in variants.items():

            if (
                instance
                ==
                exclude_instance
            ):
                continue

            result.update(
                values
            )


        return sorted(
            result
        )


    def update_typebot_integration(
        self,
        instance_name,
        integration_id,
        payload,
    ):
        import re

        instance_name = str(
            instance_name
            or ""
        ).strip()

        integration_id = str(
            integration_id
            or ""
        ).strip()


        if not re.fullmatch(
            r"tnl-e[0-9]+-i[0-9]+",
            instance_name,
        ):

            raise EvolutionClientError(
                "Instancia Evolution inválida."
            )


        if not integration_id:

            raise EvolutionClientError(
                "Integración Typebot sin ID."
            )


        safe_name = quote(
            instance_name,
            safe="",
        )

        safe_id = quote(
            integration_id,
            safe="",
        )


        return self._request(
            "PUT",
            (
                "/typebot/update/"
                + safe_id
                + "/"
                + safe_name
            ),
            payload=payload,
            timeout=30,
        )


    def _nl_typebot_policy_payload(
        self,
        integration,
        *,
        debounce_time,
        ignore_jids,
    ):
        allowed_fields = (
            "enabled",
            "description",
            "url",
            "typebot",
            "triggerType",
            "triggerOperator",
            "triggerValue",
            "expire",
            "keywordFinish",
            "delayMessage",
            "unknownMessage",
            "listeningFromMe",
            "stopBotFromMe",
            "keepOpen",
            "debounceTime",
            "ignoreJids",
            "splitMessages",
            "timePerChar",
        )


        payload = {}

        for field in allowed_fields:

            if field not in integration:
                continue

            value = integration.get(
                field
            )

            if value is None:
                continue

            payload[
                field
            ] = value


        for field in (
            "enabled",
            "url",
            "typebot",
            "triggerType",
        ):

            if field not in payload:

                raise EvolutionClientError(
                    "Integración Typebot "
                    "incompleta: "
                    + field
                    + "."
                )


        payload[
            "debounceTime"
        ] = int(
            debounce_time
        )

        payload[
            "ignoreJids"
        ] = sorted(
            {
                str(value)
                for value
                in (
                    ignore_jids
                    or []
                )
                if str(
                    value
                ).strip()
            }
        )


        return payload


    def sync_negociolisto_typebot_policies(
        self,
        *,
        debounce_time=3,
        dry_run=False,
        skip_if_owner_fingerprint_seen=False,
    ):
        """
        Sincroniza exclusivamente Typebots
        asociados a Canales WhatsApp
        administrados por NegocioListo.

        No conecta ni desconecta WhatsApp.
        No modifica el flujo visual Typebot.
        """

        if (
            not isinstance(
                debounce_time,
                int,
            )
            or
            debounce_time < 1
            or
            debounce_time > 30
        ):

            raise EvolutionClientError(
                "debounceTime fuera "
                "del rango permitido."
            )


        (
            managed,
            owners,
            variants,
        ) = (
            self
            ._nl_managed_whatsapp_context()
        )


        owner_fingerprint = tuple(
            sorted(
                (
                    instance,
                    owner,
                )
                for (
                    instance,
                    owner,
                ) in owners.items()
            )
        )


        cache = getattr(
            type(self),
            "_nl_policy_owner_fingerprints",
            set(),
        )


        if (
            skip_if_owner_fingerprint_seen
            and
            not dry_run
            and
            owner_fingerprint
            and
            owner_fingerprint
            in cache
        ):

            return {
                "managed_count":
                    len(managed),

                "owner_count":
                    len(
                        set(
                            owners.values()
                        )
                    ),

                "planned_changes":
                    0,

                "updated_count":
                    0,

                "cached":
                    True,

                "dry_run":
                    False,
            }


        # TNL-CLIENT-LIFECYCLE-EVOLUTION-V1
        # `enabled` pertenece ahora al ciclo de vida del tenant.
        # La política anti-loop lo preserva, no exige True.
        expected_critical = {
            "url":
                "https://bot.negociolisto.com.mx",

            "triggerType":
                "all",

            "triggerOperator":
                "equals",

            "triggerValue":
                "hola",

            "expire":
                30,

            "keepOpen":
                False,

            "listeningFromMe":
                False,

            "stopBotFromMe":
                False,
        }


        plans = []


        #
        # PRE-FLIGHT COMPLETO:
        # no PUT hasta validar todos.
        #
        for (
            instance,
            canal,
        ) in managed.items():

            rows = [
                row
                for row in self._items(
                    self.find_typebots(
                        instance
                    )
                )
                if isinstance(
                    row,
                    dict,
                )
            ]


            if len(rows) != 1:

                raise EvolutionClientError(
                    "La instancia "
                    + instance
                    + " no tiene exactamente "
                    + "una integración Typebot."
                )


            integration = rows[0]

            integration_id = (
                integration.get("id")
                or
                integration.get("_id")
            )


            if not integration_id:

                raise EvolutionClientError(
                    "Integración Typebot "
                    "sin identificador."
                )


            mismatches = []

            for (
                field,
                expected,
            ) in (
                expected_critical.items()
            ):

                if (
                    integration.get(
                        field
                    )
                    !=
                    expected
                ):

                    mismatches.append(
                        field
                    )


            if (
                integration.get(
                    "typebot"
                )
                !=
                instance
            ):

                mismatches.append(
                    "typebot"
                )


            if mismatches:

                raise EvolutionClientError(
                    "Configuración crítica "
                    "inesperada en "
                    + instance
                    + ": "
                    + ", ".join(
                        sorted(
                            set(
                                mismatches
                            )
                        )
                    )
                    + "."
                )


            desired_ignore = set()

            for (
                other_instance,
                other_variants,
            ) in variants.items():

                if (
                    other_instance
                    ==
                    instance
                ):
                    continue

                desired_ignore.update(
                    other_variants
                )


            own_variants = (
                variants.get(
                    instance,
                    set(),
                )
            )


            if (
                desired_ignore
                &
                own_variants
            ):

                raise EvolutionClientError(
                    "La política intentó "
                    "ignorar el propio JID."
                )


            current_ignore = {
                str(value)
                for value in (
                    integration.get(
                        "ignoreJids"
                    )
                    or []
                )
                if str(
                    value
                ).strip()
            }


            changed = (
                integration.get(
                    "debounceTime"
                )
                !=
                debounce_time
                or
                current_ignore
                !=
                desired_ignore
            )


            payload = (
                self
                ._nl_typebot_policy_payload(
                    integration,
                    debounce_time=
                        debounce_time,
                    ignore_jids=
                        desired_ignore,
                )
            )


            plans.append(
                {
                    "instance":
                        instance,

                    "integration_id":
                        integration_id,

                    "payload":
                        payload,

                    "desired_ignore":
                        desired_ignore,

                    "own_variants":
                        own_variants,

                    "changed":
                        changed,

                    "empresa_id":
                        canal.bot.empresa_id,
                }
            )


        result = {
            "managed_count":
                len(managed),

            "owner_count":
                len(
                    set(
                        owners.values()
                    )
                ),

            "planned_changes":
                sum(
                    1
                    for plan in plans
                    if plan[
                        "changed"
                    ]
                ),

            "updated_count":
                0,

            "cached":
                False,

            "dry_run":
                bool(
                    dry_run
                ),
        }


        if dry_run:

            return result


        #
        # APLICACIÓN.
        #
        for plan in plans:

            if not plan[
                "changed"
            ]:

                continue

            self.update_typebot_integration(
                plan[
                    "instance"
                ],
                plan[
                    "integration_id"
                ],
                plan[
                    "payload"
                ],
            )

            result[
                "updated_count"
            ] += 1


        #
        # VERIFICACIÓN POSTERIOR.
        #
        for plan in plans:

            rows = [
                row
                for row in self._items(
                    self.find_typebots(
                        plan[
                            "instance"
                        ]
                    )
                )
                if isinstance(
                    row,
                    dict,
                )
            ]


            if len(rows) != 1:

                raise EvolutionClientError(
                    "No fue posible verificar "
                    "la integración."
                )


            current = rows[0]


            if (
                current.get(
                    "triggerType"
                )
                !=
                "all"
            ):

                raise EvolutionClientError(
                    "triggerType dejó de ser all."
                )


            if (
                current.get(
                    "debounceTime"
                )
                !=
                debounce_time
            ):

                raise EvolutionClientError(
                    "debounceTime no quedó "
                    "con el valor esperado."
                )


            current_ignore = {
                str(value)
                for value
                in (
                    current.get(
                        "ignoreJids"
                    )
                    or []
                )
                if str(
                    value
                ).strip()
            }


            if (
                current_ignore
                !=
                plan[
                    "desired_ignore"
                ]
            ):

                raise EvolutionClientError(
                    "ignoreJids no quedó "
                    "sincronizado."
                )


            if (
                current_ignore
                &
                plan[
                    "own_variants"
                ]
            ):

                raise EvolutionClientError(
                    "Una instancia quedó "
                    "ignorándose a sí misma."
                )


        if owner_fingerprint:

            cache.add(
                owner_fingerprint
            )

            setattr(
                type(self),
                "_nl_policy_owner_fingerprints",
                cache,
            )


        return result



    @classmethod
    def extract_qr(cls, data):

        if isinstance(
            data,
            dict,
        ):

            base64_value = (
                data.get(
                    "base64"
                )
            )


            if (
                isinstance(
                    base64_value,
                    str,
                )
                and
                base64_value.strip()
            ):

                value = (
                    base64_value.strip()
                )


                if value.startswith(
                    "data:image/"
                ):

                    return value


                return (
                    "data:image/png;base64,"
                    + value
                )


            for value in data.values():

                result = (
                    cls.extract_qr(
                        value
                    )
                )

                if result:
                    return result


        elif isinstance(
            data,
            list,
        ):

            for value in data:

                result = (
                    cls.extract_qr(
                        value
                    )
                )

                if result:
                    return result


        return None

    # TNL-CLIENT-CONNECTION-RESET-EVOLUTION-V1
    # ========================================================
    # TNL-EVOLUTION-SEND-TEXT-V1
    # ========================================================

    def send_text(
        self,
        *,
        instance_name,
        number,
        text,
        timeout=30,
    ):
        """
        Envía texto mediante Evolution API v2.

        Endpoint:
        POST /message/sendText/{instance}

        Payload:
        {
            "number": "...",
            "text": "..."
        }
        """

        import re


        instance_name = str(
            instance_name
            or ""
        ).strip()


        if not re.fullmatch(
            r"tnl-e[1-9][0-9]*-i[1-9][0-9]*",
            instance_name,
        ):

            raise EvolutionClientError(
                "La instancia Evolution no es válida."
            )


        number = str(
            number
            or ""
        ).strip()


        if (
            not number.isdigit()
            or
            not (
                8
                <=
                len(number)
                <=
                15
            )
        ):

            raise EvolutionClientError(
                "El destinatario WhatsApp no es válido."
            )


        text = str(
            text
            or ""
        ).strip()


        if not text:

            raise EvolutionClientError(
                "El mensaje WhatsApp está vacío."
            )


        if len(text) > 4096:

            raise EvolutionClientError(
                "El mensaje WhatsApp excede el tamaño permitido."
            )


        try:

            timeout = int(
                timeout
            )

        except (
            TypeError,
            ValueError,
        ):

            timeout = 30


        timeout = max(
            1,
            min(
                timeout,
                60,
            ),
        )


        return self._request(
            "POST",
            (
                "/message/sendText/"
                +
                instance_name
            ),
            payload={
                "number":
                    number,

                "text":
                    text,
            },
            timeout=timeout,
        )


    def delete_instance(
        self,
        instance_name,
    ):
        """
        Elimina completamente una instancia
        Evolution administrada por NegocioListo.
        """

        import re

        instance_name = str(
            instance_name
            or ""
        ).strip()


        if not re.fullmatch(
            r"tnl-e[0-9]+-i[0-9]+",
            instance_name,
        ):

            raise EvolutionClientError(
                "Instancia Evolution inválida."
            )


        safe_name = quote(
            instance_name,
            safe="",
        )


        return self._request(
            "DELETE",
            (
                "/instance/delete/"
                + safe_name
            ),
            timeout=30,
        )

