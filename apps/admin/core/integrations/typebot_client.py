import json
from copy import deepcopy
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class TypebotError(RuntimeError):
    pass


class TypebotClient:

    BASE_URL = (
        "https://builder.negociolisto.com.mx"
    )

    TOKEN_FILE = Path(
        "/opt/tunegociolisto/"
        "infrastructure/secrets/"
        "typebot_api_token"
    )

    def __init__(
        self,
        base_url=None,
        token=None,
    ):
        self.base_url = (
            base_url or self.BASE_URL
        ).rstrip("/")

        self.token = (
            token or self._read_token()
        )

    # --------------------------------------------------------
    # SEGURIDAD
    # --------------------------------------------------------

    def _read_token(self):

        try:
            token = (
                self.TOKEN_FILE
                .read_text(
                    encoding="utf-8"
                )
                .strip()
            )

        except OSError as exc:
            raise TypebotError(
                "No fue posible leer "
                "el API Token de Typebot."
            ) from exc

        if not token:
            raise TypebotError(
                "El API Token de Typebot "
                "está vacío."
            )

        return token

    # --------------------------------------------------------
    # HTTP
    # --------------------------------------------------------

    def _request(
        self,
        method,
        path,
        *,
        params=None,
        body=None,
    ):

        url = (
            self.base_url
            + path
        )

        if params:
            url += (
                "?"
                + urlencode(params)
            )

        headers = {
            "Authorization":
                f"Bearer {self.token}",
            "Accept":
                "application/json",
        }

        data = None

        if body is not None:

            headers[
                "Content-Type"
            ] = "application/json"

            data = json.dumps(
                body
            ).encode("utf-8")

        request = Request(
            url=url,
            data=data,
            headers=headers,
            method=method,
        )

        try:

            with urlopen(
                request,
                timeout=20,
            ) as response:

                raw = response.read()

                if not raw:
                    payload = {}
                else:
                    payload = json.loads(
                        raw.decode("utf-8")
                    )

                return {
                    "ok": True,
                    "status": response.status,
                    "data": payload,
                }

        except HTTPError as exc:

            raw = exc.read()

            try:
                payload = json.loads(
                    raw.decode("utf-8")
                )
            except Exception:
                payload = {
                    "message":
                        raw.decode(
                            "utf-8",
                            errors="replace",
                        )
                }

            return {
                "ok": False,
                "status": exc.code,
                "data": payload,
            }

        except URLError as exc:

            raise TypebotError(
                f"No fue posible conectar "
                f"con Typebot: {exc.reason}"
            ) from exc

    # --------------------------------------------------------
    # WORKSPACES
    # --------------------------------------------------------

    def listar_workspaces(self):

        return self._request(
            "GET",
            "/api/v1/workspaces",
        )

    def obtener_workspace(
        self,
        workspace_id,
    ):

        return self._request(
            "GET",
            (
                "/api/v1/workspaces/"
                f"{workspace_id}"
            ),
        )

    def resolver_workspace(self):

        respuesta = (
            self.listar_workspaces()
        )

        if not respuesta["ok"]:
            raise TypebotError(
                "Typebot no permitió "
                "listar los workspaces."
            )

        workspaces = (
            respuesta["data"]
            .get(
                "workspaces",
                [],
            )
        )

        if not workspaces:
            raise TypebotError(
                "No existe ningún workspace "
                "accesible en Typebot."
            )

        # Actualmente tenemos un único workspace.
        return workspaces[0]

    # --------------------------------------------------------
    # TYPEBOTS
    # --------------------------------------------------------

    def listar_typebots(
        self,
        workspace_id=None,
    ):

        if workspace_id is None:

            workspace = (
                self.resolver_workspace()
            )

            workspace_id = (
                workspace["id"]
            )

        # Typebot 3.17.2 instalado en
        # NegocioListo requiere workspaceId.
        return self._request(
            "GET",
            "/api/v1/typebots",
            params={
                "workspaceId":
                    workspace_id,
            },
        )

    # --------------------------------------------------------
    # DIAGNOSTICO
    # --------------------------------------------------------

    def comprobar_conexion(self):

        workspace = (
            self.resolver_workspace()
        )

        bots = self.listar_typebots(
            workspace["id"]
        )

        if not bots["ok"]:
            raise TypebotError(
                "El workspace fue encontrado, "
                "pero Typebot no permitió "
                "listar los bots."
            )

        return {
            "ok": True,
            "workspace_id":
                workspace.get("id"),
            "workspace_nombre":
                workspace.get("name"),
            "typebots":
                len(
                    bots["data"].get(
                        "typebots",
                        [],
                    )
                ),
        }

    def crear_typebot(
        self,
        nombre,
        workspace_id=None,
    ):

        if workspace_id is None:
            workspace = self.resolver_workspace()
            workspace_id = workspace["id"]

        return self._request(
            "POST",
            "/api/v1/typebots",
            body={
                "workspaceId": workspace_id,
                "typebot": {
                    "name": nombre,
                },
            },
        )


    def obtener_typebot(
        self,
        typebot_id,
    ):

        return self._request(
            "GET",
            f"/api/v1/typebots/{typebot_id}",
        )


    def importar_typebot(
        self,
        typebot,
        *,
        nombre=None,
        workspace_id=None,
    ):
        """
        Importa una copia completa de un Typebot.

        Se eliminan identificadores y metadatos que no deben
        heredarse al nuevo Typebot.
        """

        if not isinstance(typebot, dict):
            raise TypebotError(
                "El Typebot a importar no tiene "
                "una estructura válida."
            )

        if workspace_id is None:
            workspace = self.resolver_workspace()
            workspace_id = workspace["id"]

        copia = deepcopy(typebot)

        # ----------------------------------------------------
        # NO HEREDAR IDENTIDAD / PUBLICACIÓN / CANALES
        # ----------------------------------------------------

        campos_no_clonables = (
            "id",
            "workspaceId",
            "publicId",
            "createdAt",
            "updatedAt",
            "customDomain",
            "isArchived",
            "isClosed",
            "riskLevel",
            "whatsAppCredentialsId",
        )

        for campo in campos_no_clonables:
            copia.pop(
                campo,
                None,
            )

        if nombre:
            copia["name"] = nombre

        return self._request(
            "POST",
            "/api/v1/typebots/import",
            body={
                "workspaceId": workspace_id,
                "typebot": copia,
            },
        )


    def duplicar_typebot(
        self,
        typebot_id,
        *,
        nombre,
        workspace_id=None,
    ):
        """
        Obtiene un Typebot existente y crea una copia
        independiente dentro del workspace.
        """

        origen = self.obtener_typebot(
            typebot_id
        )

        if not origen["ok"]:
            raise TypebotError(
                "No fue posible obtener el "
                "Typebot origen para duplicarlo."
            )

        typebot = (
            origen["data"]
            .get(
                "typebot",
                origen["data"],
            )
        )

        return self.importar_typebot(
            typebot,
            nombre=nombre,
            workspace_id=workspace_id,
        )


    def actualizar_typebot(
        self,
        typebot_id,
        *,
        typebot,
        overwrite=True,
    ):
        """
        Actualiza parcialmente un Typebot existente.

        Se utilizará para parametrizar exclusivamente
        clones privados después de crear el Bot local.
        """

        if not isinstance(typebot, dict):
            raise TypebotError(
                "La actualización Typebot requiere "
                "un objeto typebot válido."
            )

        return self._request(
            "PATCH",
            f"/api/v1/typebots/{typebot_id}",
            body={
                "typebot": typebot,
                "overwrite": bool(overwrite),
            },
        )


    def eliminar_typebot(
        self,
        typebot_id,
    ):
        """
        Elimina un Typebot.

        Typebot requiere cuerpo JSON vacío en DELETE.
        Se utilizará principalmente como rollback
        de aprovisionamientos externos incompletos.
        """

        return self._request(
            "DELETE",
            f"/api/v1/typebots/{typebot_id}",
            body={},
        )


    def publicar_typebot(
        self,
        typebot_id,
    ):

        return self._request(
            "POST",
            f"/api/v1/typebots/{typebot_id}/publish",
            body={},
        )

    def obtener_typebot_publicado(
        self,
        typebot_id,
    ):
        """
        Obtiene el snapshot PublicTypebot asociado
        al Typebot editable.

        Typebot 3.17.x responde HTTP 200 con
        publishedTypebot=None si no existe publicación.
        """

        return self._request(
            "GET",
            (
                f"/api/v1/typebots/"
                f"{typebot_id}/publishedTypebot"
            ),
        )

