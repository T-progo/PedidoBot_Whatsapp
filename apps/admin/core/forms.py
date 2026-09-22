from django import forms
from django.contrib.auth import get_user_model

from .models import Empresa, PerfilUsuario


User = get_user_model()


class EmpresaForm(forms.ModelForm):

    class Meta:
        model = Empresa

        fields = [
            "nombre",
            "razon_social",
            "rfc",
            "email",
            "telefono",
            "giro_negocio",
            "domicilio_calle",
            "domicilio_numero_exterior",
            "domicilio_numero_interior",
            "domicilio_colonia",
            "domicilio_codigo_postal",
            "domicilio_municipio",
            "domicilio_ciudad",
            "domicilio_estado",
            "domicilio_pais",
            "estado",
        ]

        widgets = {
            "nombre": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Nombre comercial",
                }
            ),

            "razon_social": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Razón social",
                }
            ),

            "rfc": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "RFC",
                }
            ),

            "email": forms.EmailInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "correo@empresa.com",
                }
            ),

            "telefono": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Teléfono",
                }
            ),

            # TNL-EMPRESA-SEGMENTACION-FORM-V1
            "giro_negocio": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": (
                        "Ej. Ferretería, Restaurante, "
                        "Farmacia, Servicios profesionales"
                    ),
                }
            ),

            "domicilio_calle": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Calle",
                }
            ),

            "domicilio_numero_exterior": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": (
                        "Número exterior o S/N"
                    ),
                }
            ),

            "domicilio_numero_interior": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": (
                        "Número interior (opcional)"
                    ),
                }
            ),

            "domicilio_colonia": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Colonia",
                }
            ),

            "domicilio_codigo_postal": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Código postal",
                    "inputmode": "numeric",
                }
            ),

            "domicilio_municipio": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": (
                        "Municipio o alcaldía"
                    ),
                }
            ),

            "domicilio_ciudad": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Ciudad",
                }
            ),

            "domicilio_estado": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": (
                        "Estado o entidad federativa"
                    ),
                }
            ),

            "domicilio_pais": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "País",
                }
            ),

            "estado": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),
        }

        labels = {
            "nombre": "Nombre comercial",
            "razon_social": "Razón social",
            "rfc": "RFC",
            "email": "Correo electrónico",
            "telefono": "Teléfono",
            "giro_negocio": "Giro del negocio",
            "domicilio_calle": "Calle",
            "domicilio_numero_exterior":
                "Número exterior",
            "domicilio_numero_interior":
                "Número interior",
            "domicilio_colonia": "Colonia",
            "domicilio_codigo_postal":
                "Código postal",
            "domicilio_municipio":
                "Municipio / Alcaldía",
            "domicilio_ciudad": "Ciudad",
            "domicilio_estado":
                "Estado / Entidad federativa",
            "domicilio_pais": "País",
            "estado": "Estado operativo",
        }


class UsuarioCrearForm(forms.Form):

    username = forms.CharField(
        label="Usuario",
        max_length=150,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Nombre de usuario",
                "autocomplete": "off",
            }
        ),
    )

    first_name = forms.CharField(
        label="Nombre",
        max_length=150,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Nombre",
            }
        ),
    )

    last_name = forms.CharField(
        label="Apellidos",
        max_length=150,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Apellidos",
            }
        ),
    )

    email = forms.EmailField(
        label="Correo electrónico",
        widget=forms.EmailInput(
            attrs={
                "class": "form-control",
                "placeholder": "correo@empresa.com",
            }
        ),
    )

    empresa = forms.ModelChoiceField(
        label="Empresa",
        queryset=Empresa.objects.none(),
        required=False,
        empty_label="Sin empresa (solo Administrador)",
        widget=forms.Select(
            attrs={
                "class": "form-control",
            }
        ),
    )

    # TNL-USER-ROLE-CONTRACT-V1
    rol = forms.ChoiceField(
        label="Tipo de usuario",
        choices=(
            (
                PerfilUsuario.Rol.ADMINISTRADOR,
                "Administrador",
            ),
            (
                PerfilUsuario.Rol.CLIENTE,
                "Cliente principal (dueño)",
            ),
            (
                PerfilUsuario.Rol.OPERADOR,
                "Operador",
            ),
        ),
        help_text=(
            "Cliente principal: dueño o responsable "
            "con acceso a su portal y vinculación de "
            "WhatsApp. Operador: usuario operativo "
            "de la empresa."
        ),
        widget=forms.Select(
            attrs={
                "class": "form-control",
            }
        ),
    )

    activo = forms.BooleanField(
        label="Usuario activo",
        required=False,
        initial=True,
    )

    password1 = forms.CharField(
        label="Contraseña",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "Contraseña",
                "autocomplete": "new-password",
            }
        ),
    )

    password2 = forms.CharField(
        label="Confirmar contraseña",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "Repite la contraseña",
                "autocomplete": "new-password",
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["empresa"].queryset = Empresa.objects.order_by(
            "nombre"
        )

    def clean_username(self):
        username = self.cleaned_data["username"].strip()

        if User.objects.filter(
            username__iexact=username
        ).exists():
            raise forms.ValidationError(
                "Ya existe un usuario con este nombre."
            )

        return username

    def clean(self):
        cleaned = super().clean()

        password1 = cleaned.get("password1")
        password2 = cleaned.get("password2")

        rol = cleaned.get("rol")
        empresa = cleaned.get("empresa")

        if password1 and password2:
            if password1 != password2:
                self.add_error(
                    "password2",
                    "Las contraseñas no coinciden.",
                )

        if (
            rol
            in (
                PerfilUsuario.Rol.CLIENTE,
                PerfilUsuario.Rol.OPERADOR,
            )
            and not empresa
        ):
            self.add_error(
                "empresa",
                (
                    "Selecciona una empresa para "
                    "este tipo de usuario."
                ),
            )

        if (
            rol
            == PerfilUsuario.Rol.ADMINISTRADOR
            and empresa
        ):
            self.add_error(
                "empresa",
                (
                    "El Administrador pertenece a la "
                    "administración central y no debe "
                    "tener una empresa asignada."
                ),
            )

        if (
            rol
            == PerfilUsuario.Rol.CLIENTE
            and empresa
            and PerfilUsuario.objects.filter(
                empresa=empresa,
                rol=PerfilUsuario.Rol.CLIENTE,
            ).exists()
        ):
            self.add_error(
                "empresa",
                (
                    "Esta empresa ya tiene un Cliente "
                    "principal asignado."
                ),
            )

        return cleaned


class UsuarioEditarForm(forms.Form):

    first_name = forms.CharField(
        label="Nombre",
        max_length=150,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Nombre",
            }
        ),
    )

    last_name = forms.CharField(
        label="Apellidos",
        max_length=150,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Apellidos",
            }
        ),
    )

    email = forms.EmailField(
        label="Correo electrónico",
        widget=forms.EmailInput(
            attrs={
                "class": "form-control",
                "placeholder": "correo@empresa.com",
            }
        ),
    )

    empresa = forms.ModelChoiceField(
        label="Empresa",
        queryset=Empresa.objects.none(),
        required=False,
        empty_label="Sin empresa (solo Administrador)",
        widget=forms.Select(
            attrs={
                "class": "form-control",
            }
        ),
    )

    # TNL-USER-ROLE-CONTRACT-V1
    rol = forms.ChoiceField(
        label="Tipo de usuario",
        choices=(
            (
                PerfilUsuario.Rol.ADMINISTRADOR,
                "Administrador",
            ),
            (
                PerfilUsuario.Rol.CLIENTE,
                "Cliente principal (dueño)",
            ),
            (
                PerfilUsuario.Rol.OPERADOR,
                "Operador",
            ),
        ),
        help_text=(
            "Cliente principal: dueño o responsable "
            "con acceso a su portal y vinculación de "
            "WhatsApp. Operador: usuario operativo "
            "de la empresa."
        ),
        widget=forms.Select(
            attrs={
                "class": "form-control",
            }
        ),
    )

    activo = forms.BooleanField(
        label="Usuario activo",
        required=False,
    )

    password1 = forms.CharField(
        label="Nueva contraseña",
        required=False,
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "Dejar vacío para conservarla",
                "autocomplete": "new-password",
            }
        ),
    )

    password2 = forms.CharField(
        label="Confirmar nueva contraseña",
        required=False,
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "Repite la nueva contraseña",
                "autocomplete": "new-password",
            }
        ),
    )

    def __init__(
        self,
        *args,
        perfil=None,
        **kwargs,
    ):
        super().__init__(
            *args,
            **kwargs,
        )

        self.perfil = perfil

        self.fields["empresa"].queryset = Empresa.objects.order_by(
            "nombre"
        )

    def clean(self):
        cleaned = super().clean()

        password1 = cleaned.get("password1")
        password2 = cleaned.get("password2")

        rol = cleaned.get("rol")
        empresa = cleaned.get("empresa")

        if password1 or password2:
            if password1 != password2:
                self.add_error(
                    "password2",
                    "Las contraseñas no coinciden.",
                )

        if (
            rol
            in (
                PerfilUsuario.Rol.CLIENTE,
                PerfilUsuario.Rol.OPERADOR,
            )
            and not empresa
        ):
            self.add_error(
                "empresa",
                (
                    "Selecciona una empresa para "
                    "este tipo de usuario."
                ),
            )

        if (
            rol
            == PerfilUsuario.Rol.ADMINISTRADOR
            and empresa
        ):
            self.add_error(
                "empresa",
                (
                    "El Administrador pertenece a la "
                    "administración central y no debe "
                    "tener una empresa asignada."
                ),
            )

        if (
            rol
            == PerfilUsuario.Rol.CLIENTE
            and empresa
        ):

            existing = (
                PerfilUsuario.objects
                .filter(
                    empresa=empresa,
                    rol=PerfilUsuario.Rol.CLIENTE,
                )
            )

            if self.perfil is not None:

                existing = (
                    existing.exclude(
                        pk=self.perfil.pk
                    )
                )

            if existing.exists():

                self.add_error(
                    "empresa",
                    (
                        "Esta empresa ya tiene un Cliente "
                        "principal asignado."
                    ),
                )

        return cleaned


# ============================================================
# LICENCIAS
# ============================================================

from .models import Licencia


class LicenciaForm(forms.ModelForm):

    class Meta:
        model = Licencia

        fields = [
            "empresa",
            "nombre",
            "estado",
            "fecha_inicio",
            "fecha_fin",
        ]

        widgets = {
            "empresa": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),

            "nombre": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Nombre de la licencia",
                }
            ),

            "estado": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),

            "fecha_inicio": forms.DateInput(
                attrs={
                    "class": "form-control",
                    "type": "date",
                }
            ),

            "fecha_fin": forms.DateInput(
                attrs={
                    "class": "form-control",
                    "type": "date",
                }
            ),
        }

        labels = {
            "empresa": "Empresa",
            "nombre": "Nombre",
            "estado": "Estado",
            "fecha_inicio": "Fecha de inicio",
            "fecha_fin": "Fecha de vencimiento",
        }


    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)

        self.fields["empresa"].queryset = (
            self.fields["empresa"]
            .queryset
            .order_by("nombre")
        )


    def clean(self):

        cleaned = super().clean()

        fecha_inicio = cleaned.get("fecha_inicio")
        fecha_fin = cleaned.get("fecha_fin")

        if (
            fecha_inicio
            and fecha_fin
            and fecha_fin < fecha_inicio
        ):
            self.add_error(
                "fecha_fin",
                "La fecha de vencimiento no puede ser anterior a la fecha de inicio.",
            )

        return cleaned


# ============================================================
# BOTS
# ============================================================

from .models import Bot


class BotForm(forms.ModelForm):

    class Meta:
        model = Bot

        # TNL-BOT-SYSTEM-PROMPT-FORM-V1
        fields = [
            "empresa",
            "nombre",
            "identificador_externo",
            "system_prompt",
            "faq",
            "activo",
        ]

        labels = {
            "empresa": "Empresa",
            "nombre": "Nombre",
            "identificador_externo": "Identificador externo",
            "system_prompt":
                "System Prompt / Instrucciones personalizadas",

            # TNL-BOT-FAQ-FORM-V1
            "faq":
                "Preguntas frecuentes / Base de conocimiento",

            "activo": "Bot activo",
        }

        widgets = {
            "empresa": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),

            "nombre": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Nombre del bot",
                }
            ),

            "identificador_externo": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Identificador externo",
                }
            ),

            "system_prompt": forms.Textarea(
                attrs={
                    "class":
                        "form-control system-prompt-textarea",

                    "rows":
                        14,

                    "maxlength":
                        12000,

                    "placeholder":
                        (
                            "Ejemplo: Eres el asistente comercial "
                            "de este negocio. Prioriza respuestas "
                            "breves, solicita los datos necesarios "
                            "y sigue las reglas específicas del cliente. "
                            "Déjalo vacío para utilizar el prompt base."
                        ),
                }
            ),

            "faq": forms.Textarea(
                attrs={
                    "class":
                        "form-control faq-textarea",

                    "rows":
                        18,

                    "maxlength":
                        20000,

                    "placeholder":
                        (
                            "Ejemplo:\n"
                            "Pregunta: ¿Cuál es el horario?\n"
                            "Respuesta: Atendemos de lunes a viernes "
                            "de 9:00 a 18:00.\n\n"
                            "Pregunta: ¿Dónde están ubicados?\n"
                            "Respuesta: ..."
                        ),
                }
            ),

            "activo": forms.CheckboxInput(),
        }


    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)

        self.fields["empresa"].queryset = (
            self.fields["empresa"]
            .queryset
            .order_by("nombre")
        )


# ============================================================
# CANALES
# ============================================================

from .models import Canal


class CanalForm(forms.ModelForm):

    class Meta:
        model = Canal

        fields = [
            "bot",
            "tipo",
            "nombre",
            "identificador",
            "activo",
        ]

        labels = {
            "bot": "Bot",
            "tipo": "Tipo de canal",
            "nombre": "Nombre",
            "identificador": "Identificador",
            "activo": "Canal activo",
        }

        widgets = {
            "bot": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),

            "tipo": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),

            "nombre": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Nombre del canal",
                }
            ),

            "identificador": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Identificador del canal",
                }
            ),

            "activo": forms.CheckboxInput(),
        }


    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)

        self.fields["bot"].queryset = (
            self.fields["bot"]
            .queryset
            .select_related("empresa")
            .order_by("empresa__nombre", "nombre")
        )


# ============================================================
# PLANTILLAS
# ============================================================

from .models import Plantilla


class PlantillaForm(forms.ModelForm):

    class Meta:
        model = Plantilla

        fields = [
            "empresa",
            "nombre",
            "tipo",
            "descripcion",
            "identificador_externo",
            "activa",
        ]

        labels = {
            "empresa": "Empresa",
            "nombre": "Nombre de la plantilla",
            "tipo": "Tipo de plantilla",
            "descripcion": "Descripción",
            "identificador_externo": "Identificador externo",
            "activa": "Plantilla activa",
        }

        widgets = {
            "empresa": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),

            "nombre": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Nombre de la plantilla",
                }
            ),

            "tipo": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),

            "descripcion": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "placeholder": "Describe el propósito de esta plantilla",
                    "rows": 4,
                }
            ),

            "identificador_externo": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "ID externo / Typebot ID",
                }
            ),

            "activa": forms.CheckboxInput(),
        }


    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)

        self.fields["empresa"].queryset = (
            Empresa.objects
            .order_by("nombre")
        )


# ============================================================
# VARIABLES
# ============================================================

from .models import Variable


class VariableForm(forms.ModelForm):

    class Meta:
        model = Variable

        fields = [
            "plantilla",
            "clave",
            "valor",
            "descripcion",
            "activa",
        ]

        labels = {
            "plantilla": "Plantilla",
            "clave": "Clave",
            "valor": "Valor",
            "descripcion": "Descripción",
            "activa": "Variable activa",
        }

        widgets = {
            "plantilla": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),

            "clave": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Ej. telefono, horario, direccion",
                }
            ),

            "valor": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "placeholder": "Valor de la variable",
                    "rows": 3,
                }
            ),

            "descripcion": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "placeholder": "Descripción o uso de esta variable",
                    "rows": 3,
                }
            ),

            "activa": forms.CheckboxInput(),
        }


    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)

        self.fields["plantilla"].queryset = (
            Plantilla.objects
            .select_related("empresa")
            .order_by(
                "empresa__nombre",
                "nombre",
            )
        )


    def clean(self):

        cleaned = super().clean()

        plantilla = cleaned.get("plantilla")
        clave = cleaned.get("clave")

        if plantilla and clave:

            existe = Variable.objects.filter(
                plantilla=plantilla,
                clave=clave,
            )

            if self.instance and self.instance.pk:
                existe = existe.exclude(
                    pk=self.instance.pk
                )

            if existe.exists():

                self.add_error(
                    "clave",
                    "Ya existe una variable con esta clave para la plantilla seleccionada.",
                )

        return cleaned


# ============================================================
# CATALOGOS
# ============================================================

from .models import Catalogo


class CatalogoForm(forms.ModelForm):

    class Meta:
        model = Catalogo

        fields = [
            "empresa",
            "nombre",
            "descripcion",
            "moneda",
            "identificador_externo",
            "activo",
        ]

        labels = {
            "empresa": "Empresa",
            "nombre": "Nombre del catálogo",
            "descripcion": "Descripción",
            "moneda": "Moneda",
            "identificador_externo": "Identificador externo",
            "activo": "Catálogo activo",
        }

        widgets = {
            "empresa": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),

            "nombre": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Nombre del catálogo",
                }
            ),

            "descripcion": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "placeholder": "Describe el propósito de este catálogo",
                    "rows": 3,
                }
            ),

            "moneda": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),

            "identificador_externo": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "ID externo / sistema origen",
                }
            ),

            "activo": forms.CheckboxInput(),
        }


    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)

        self.fields["empresa"].queryset = (
            self.fields["empresa"]
            .queryset
            .order_by("nombre")
        )


    def clean(self):

        cleaned = super().clean()

        empresa = cleaned.get("empresa")
        nombre = cleaned.get("nombre")

        if empresa and nombre:

            existe = Catalogo.objects.filter(
                empresa=empresa,
                nombre=nombre,
            )

            if self.instance and self.instance.pk:
                existe = existe.exclude(
                    pk=self.instance.pk
                )

            if existe.exists():

                self.add_error(
                    "nombre",
                    "Ya existe un catálogo con este nombre para la empresa seleccionada.",
                )

        return cleaned


# ============================================================
# PRODUCTOS
# ============================================================

from decimal import Decimal

from .models import Producto


# TNL-PRODUCT-FORM-IMAGES-V1
from django.core.validators import FileExtensionValidator
from core.models import validar_tamano_imagen_producto


class MultipleImageInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleImageField(forms.ImageField):

    def __init__(self, *args, **kwargs):

        kwargs.setdefault(
            "required",
            False,
        )

        kwargs.setdefault(
            "widget",
            MultipleImageInput(
                attrs={
                    "class": "form-control",
                    "accept": (
                        "image/jpeg,"
                        "image/png,"
                        "image/webp"
                    ),
                }
            ),
        )

        kwargs.setdefault(
            "validators",
            [
                FileExtensionValidator(
                    allowed_extensions=[
                        "jpg",
                        "jpeg",
                        "png",
                        "webp",
                    ]
                ),
                validar_tamano_imagen_producto,
            ],
        )

        super().__init__(
            *args,
            **kwargs
        )

    def clean(
        self,
        data,
        initial=None,
    ):

        if not data:
            return []

        files = (
            data
            if isinstance(
                data,
                (list, tuple),
            )
            else [data]
        )

        cleaned = []

        for uploaded in files:

            image = super().clean(
                uploaded,
                initial,
            )

            cleaned.append(
                image
            )

        return cleaned


class ProductoForm(forms.ModelForm):

    imagen_principal = forms.ImageField(
        required=False,
        label="Imagen principal",
        help_text=(
            "JPG, JPEG, PNG o WebP. "
            "Máximo 4 MB."
        ),
        validators=[
            FileExtensionValidator(
                allowed_extensions=[
                    "jpg",
                    "jpeg",
                    "png",
                    "webp",
                ]
            ),
            validar_tamano_imagen_producto,
        ],
        widget=forms.ClearableFileInput(
            attrs={
                "class": "form-control",
                "accept": (
                    "image/jpeg,"
                    "image/png,"
                    "image/webp"
                ),
            }
        ),
    )

    galeria_imagenes = MultipleImageField(
        label="Galería del producto",
        help_text=(
            "Selecciona varias imágenes. "
            "Máximo 10 imágenes en total "
            "por producto. "
            "Máximo 4 MB por imagen."
        ),
    )

    class Meta:
        model = Producto

        fields = [
            "catalogo",
            "sku",
            "nombre",
            "descripcion",
            "precio",
            "stock",
            "unidad",
            "imagen_principal",
            "identificador_externo",
            "activo",
        ]

        labels = {
            "catalogo": "Catálogo",
            "sku": "SKU",
            "nombre": "Nombre del producto",
            "descripcion": "Descripción",
            "precio": "Precio",
            "stock": "Existencia / Stock",
            "unidad": "Unidad",
            "identificador_externo": "Identificador externo",
            "activo": "Producto activo",
        }

        widgets = {
            "catalogo": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),

            "sku": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Opcional. Ej. SERVICIO o PROD-001",
                }
            ),

            "nombre": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Nombre del producto",
                }
            ),

            "descripcion": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "placeholder": "Descripción del producto",
                    "rows": 3,
                }
            ),

            "precio": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "step": "0.0001",
                    "min": "0",
                    "placeholder": "0.0000",
                }
            ),

            "stock": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "step": "0.0001",
                    "min": "0",
                    "placeholder": "0.0000",
                }
            ),

            "unidad": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Ej. pieza, kg, litro, metro",
                }
            ),

            "identificador_externo": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "ID externo / sistema origen",
                }
            ),

            "activo": forms.CheckboxInput(),
        }


    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)

        # TNL-PRODUCTO-DECIMAL-UI-V1
        # La BD conserva 4 decimales; la captura y
        # presentación del formulario usa 2.
        from decimal import Decimal, ROUND_HALF_UP

        class _DecimalDosInput(forms.NumberInput):
            def format_value(self, value):
                if value in (None, ""):
                    return ""

                try:
                    exacto = Decimal(str(value))
                    number = exacto.quantize(
                        Decimal("0.01"),
                        rounding=ROUND_HALF_UP,
                    )
                except Exception:
                    return super().format_value(value)

                # TNL-CATALOGO-REGLAS-V1
                # Un valor con más de 2 decimales se muestra
                # completo: redondearlo aquí lo cambiaría en
                # silencio al guardar.
                if number != exacto:
                    return format(exacto.normalize(), "f")

                return f"{number:.2f}"

        for field_name in ("precio", "stock"):
            field = self.fields.get(field_name)

            if field is None:
                raise RuntimeError(
                    f"ProductoForm no contiene {field_name}."
                )

            attrs = dict(field.widget.attrs)
            attrs.update(
                {
                    "step": "0.01",
                    "inputmode": "decimal",
                    "placeholder": "0.00",
                }
            )

            field.widget = _DecimalDosInput(
                attrs=attrs
            )

            field.decimal_places = 2


        self.fields["catalogo"].queryset = (
            self.fields["catalogo"]
            .queryset
            .select_related("empresa")
            .order_by(
                "empresa__nombre",
                "nombre",
            )
        )



    # TNL-RESTAURANTE-PRODUCTO-CATEGORIA-V1
    def clean(self):

        cleaned = super().clean()

        catalogo = cleaned.get(
            "catalogo"
        )

        if catalogo is None:
            return cleaned

        plantilla = getattr(
            catalogo,
            "plantilla",
            None,
        )

        tipo = str(
            getattr(
                plantilla,
                "tipo",
                "",
            )
            or ""
        )

        categoria_actual = getattr(
            self.instance,
            "categoria",
            None,
        )

        if tipo != "restaurante":

            if (
                categoria_actual is not None
                and
                categoria_actual.catalogo_id
                != catalogo.id
            ):
                self.instance.categoria = None

            return cleaned

        if (
            categoria_actual is not None
            and
            categoria_actual.catalogo_id
            == catalogo.id
        ):
            return cleaned

        from core.models import CategoriaProducto

        categoria = (
            CategoriaProducto.objects
            .filter(
                catalogo=catalogo,
                nombre="Menú general",
                activa=True,
            )
            .first()
        )

        if categoria is None:

            self.add_error(
                "catalogo",
                (
                    "El menú Restaurante no tiene "
                    "una categoría general activa."
                ),
            )

            return cleaned

        self.instance.categoria = categoria

        return cleaned


    def clean_galeria_imagenes(self):

        imagenes = (
            self.cleaned_data.get(
                "galeria_imagenes"
            )
            or []
        )

        # TNL-PRODUCT-GALLERY-MAX-4MB-V1
        # Validación explícita por cada archivo.
        # Esto protege también el flujo de galería
        # antes de crear ProductoImagen.
        for imagen in imagenes:
            validar_tamano_imagen_producto(
                imagen
            )

        existentes = 0

        if (
            self.instance
            and self.instance.pk
        ):
            existentes = (
                self.instance
                .galeria
                .count()
            )

        total = (
            existentes
            + len(imagenes)
        )

        if total > 10:
            raise forms.ValidationError(
                "La galería admite un máximo "
                "de 10 imágenes. Actualmente "
                f"hay {existentes} y estás "
                f"intentando agregar "
                f"{len(imagenes)}."
            )

        return imagenes


    def clean_precio(self):

        precio = self.cleaned_data.get("precio")

        if precio is not None and precio < Decimal("0"):
            raise forms.ValidationError(
                "El precio no puede ser negativo."
            )

        return precio


    def clean_stock(self):

        stock = self.cleaned_data.get("stock")

        if stock is not None and stock < Decimal("0"):
            raise forms.ValidationError(
                "La existencia no puede ser negativa."
            )

        return stock


# ============================================================
# FORMULARIOS PEDIDOS
# ============================================================

from decimal import Decimal

from django import forms

from core.models import (
    Empresa,
    Canal,
    Catalogo,
    Producto,
    Pedido,
)


MONEDAS_PEDIDO = (
    ("MXN", "Peso mexicano (MXN)"),
    ("USD", "Dólar estadounidense (USD)"),
)


class PedidoCrearForm(forms.Form):

    empresa = forms.ModelChoiceField(
        label="Empresa",
        queryset=Empresa.objects.none(),
        empty_label="---------",
    )

    canal = forms.ModelChoiceField(
        label="Canal",
        queryset=Canal.objects.none(),
        required=False,
        empty_label="Sin canal",
        error_messages={
            "invalid_choice":
                "El canal seleccionado no es válido.",
        },
    )

    moneda = forms.ChoiceField(
        label="Moneda",
        choices=MONEDAS_PEDIDO,
        initial="MXN",
    )

    cliente_nombre = forms.CharField(
        label="Nombre del cliente",
        max_length=200,
    )

    cliente_telefono = forms.CharField(
        label="Teléfono",
        max_length=50,
        required=False,
    )

    cliente_email = forms.EmailField(
        label="Correo electrónico",
        required=False,
    )

    direccion_entrega = forms.CharField(
        label="Dirección de entrega",
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder":
                    "Dirección donde se entregará el pedido",
            }
        ),
    )

    notas = forms.CharField(
        label="Notas",
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder":
                    "Notas u observaciones del pedido",
            }
        ),
    )

    identificador_externo = forms.CharField(
        label="Identificador externo",
        max_length=255,
        required=False,
        widget=forms.TextInput(
            attrs={
                "placeholder":
                    "ID externo / sistema origen",
            }
        ),
    )

    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)

        self.fields[
            "empresa"
        ].queryset = (
            Empresa.objects
            .all()
            .order_by("nombre")
        )

        self.fields[
            "canal"
        ].queryset = (
            Canal.objects
            .filter(activo=True)
            .select_related(
                "bot",
                "bot__empresa",
            )
            .order_by(
                "bot__empresa__nombre",
                "tipo",
                "nombre",
            )
        )

    def clean(self):

        cleaned = super().clean()

        empresa = cleaned.get("empresa")
        canal = cleaned.get("canal")

        if (
            empresa is not None
            and canal is not None
            and canal.bot.empresa_id != empresa.id
        ):

            self.add_error(
                "canal",
                "El canal seleccionado no pertenece "
                "a la empresa seleccionada.",
            )

        return cleaned


class PedidoEditarForm(forms.ModelForm):

    canal = forms.ModelChoiceField(
        label="Canal",
        queryset=Canal.objects.none(),
        required=False,
        empty_label="Sin canal",
        error_messages={
            "invalid_choice":
                "El canal seleccionado no es válido.",
        },
    )

    class Meta:

        model = Pedido

        fields = [
            "canal",
            "cliente_nombre",
            "cliente_telefono",
            "cliente_email",
            "direccion_entrega",
            "notas",
            "identificador_externo",
        ]

        labels = {
            "canal": "Canal",
            "cliente_nombre": "Nombre del cliente",
            "cliente_telefono": "Teléfono",
            "cliente_email": "Correo electrónico",
            "direccion_entrega": "Dirección de entrega",
            "notas": "Notas",
            "identificador_externo":
                "Identificador externo",
        }

        widgets = {
            "direccion_entrega":
                forms.Textarea(
                    attrs={"rows": 3}
                ),
            "notas":
                forms.Textarea(
                    attrs={"rows": 3}
                ),
        }

    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)

        empresa_id = getattr(
            self.instance,
            "empresa_id",
            None,
        )

        if empresa_id:

            self.fields[
                "canal"
            ].queryset = (
                Canal.objects
                .filter(
                    bot__empresa_id=empresa_id,
                    activo=True,
                )
                .select_related(
                    "bot",
                    "bot__empresa",
                )
                .order_by(
                    "tipo",
                    "nombre",
                )
            )

        else:

            self.fields[
                "canal"
            ].queryset = (
                Canal.objects.none()
            )


class PedidoDetalleAgregarForm(forms.Form):

    producto = forms.ModelChoiceField(
        label="Producto",
        queryset=Producto.objects.none(),
        empty_label="---------",
        error_messages={
            "invalid_choice":
                "El producto seleccionado no está disponible "
                "para este pedido.",
        },
    )

    cantidad = forms.DecimalField(
        label="Cantidad",
        max_digits=14,
        decimal_places=4,
        min_value=Decimal("0.0001"),
        initial=Decimal("1.0000"),
        error_messages={
            "min_value":
                "La cantidad debe ser mayor que cero.",
            "invalid":
                "Ingresa una cantidad válida.",
        },
    )

    descuento = forms.DecimalField(
        label="Descuento",
        max_digits=14,
        decimal_places=4,
        min_value=Decimal("0.0000"),
        initial=Decimal("0.0000"),
        error_messages={
            "min_value":
                "El descuento no puede ser negativo.",
            "invalid":
                "Ingresa un descuento válido.",
        },
    )

    def __init__(
        self,
        *args,
        pedido=None,
        **kwargs,
    ):

        super().__init__(*args, **kwargs)

        self.pedido = pedido

        if pedido is None:
            return

        self.fields[
            "producto"
        ].queryset = (
            Producto.objects
            .filter(
                catalogo__empresa_id=
                    pedido.empresa_id,
                catalogo__moneda=
                    pedido.moneda,
                catalogo__activo=True,
                activo=True,
            )
            .select_related(
                "catalogo",
                "catalogo__empresa",
            )
            .order_by(
                "catalogo__nombre",
                "nombre",
            )
        )


class PedidoDetalleEditarForm(forms.Form):

    cantidad = forms.DecimalField(
        label="Cantidad",
        max_digits=14,
        decimal_places=4,
        min_value=Decimal("0.0001"),
        error_messages={
            "min_value":
                "La cantidad debe ser mayor que cero.",
            "invalid":
                "Ingresa una cantidad válida.",
        },
    )

    descuento = forms.DecimalField(
        label="Descuento",
        max_digits=14,
        decimal_places=4,
        min_value=Decimal("0.0000"),
        error_messages={
            "min_value":
                "El descuento no puede ser negativo.",
            "invalid":
                "Ingresa un descuento válido.",
        },
    )


# ============================================================================
# TNL-MERCADOPAGO-CONFIG-FORM-V1
# Configuración administrativa NO sensible.
# ============================================================================

from .models import (
    ConfiguracionMercadoPago as
    _TnlConfiguracionMercadoPago,
)


class ConfiguracionMercadoPagoForm(
    forms.Form
):

    modo = forms.ChoiceField(
        label="Ambiente",
        choices=(
            _TnlConfiguracionMercadoPago
            .Modo
            .choices
        ),
        help_text=(
            "Usa Pruebas durante la integración. "
            "Producción se utilizará para cobros reales."
        ),
        widget=forms.Select(
            attrs={
                "class":
                    "form-control",
            }
        ),
    )


    def __init__(
        self,
        *args,
        configuracion=None,
        **kwargs,
    ):

        self.configuracion = (
            configuracion
        )

        super().__init__(
            *args,
            **kwargs,
        )


        if (
            configuracion is not None
            and
            not self.is_bound
        ):

            self.initial[
                "modo"
            ] = configuracion.modo


    def clean_modo(self):

        modo = (
            self.cleaned_data[
                "modo"
            ]
        )

        configuracion = (
            self.configuracion
        )


        if (
            configuracion is not None
            and
            configuracion.estado_conexion
            ==
            _TnlConfiguracionMercadoPago
            .EstadoConexion
            .CONECTADA
            and
            configuracion.modo
            != modo
        ):

            raise forms.ValidationError(
                (
                    "Desconecta primero la cuenta "
                    "de Mercado Pago antes de "
                    "cambiar el ambiente."
                )
            )


        return modo

# ============================================================
# TNL-CANAL-WHATSAPP-TECHNICAL-LOCK-V1
#
# Un Canal WhatsApp aprovisionado pertenece al contrato
# técnico de NegocioListo:
#
#     tnl-e{empresa_id}-i{instalacion_id}
#
# Al editar un canal existente se permite modificar únicamente
# datos operativos. Bot, tipo e identificador quedan bloqueados
# también del lado servidor mediante Field.disabled.
# ============================================================

_TNL_CANALFORM_ORIGINAL_INIT = (
    CanalForm.__init__
)


def _tnl_canalform_init_protegido(
    self,
    *args,
    **kwargs,
):

    _TNL_CANALFORM_ORIGINAL_INIT(
        self,
        *args,
        **kwargs,
    )

    instance = getattr(
        self,
        "instance",
        None,
    )

    if (
        instance is None
        or
        not getattr(
            instance,
            "pk",
            None,
        )
        or
        str(
            getattr(
                instance,
                "tipo",
                "",
            )
            or ""
        ).strip().casefold()
        != "whatsapp"
    ):
        return


    technical_fields = (
        "bot",
        "tipo",
        "identificador",
    )


    for field_name in technical_fields:

        field = self.fields.get(
            field_name
        )

        if field is None:
            continue

        # Django ignora cualquier valor POST manipulado
        # para un Field.disabled y conserva el inicial.
        field.disabled = True

        field.widget.attrs[
            "aria-disabled"
        ] = "true"


    identificador = self.fields.get(
        "identificador"
    )

    if identificador is not None:

        identificador.help_text = (
            "Identificador técnico administrado "
            "automáticamente por NegocioListo."
        )


CanalForm.__init__ = (
    _tnl_canalform_init_protegido
)


