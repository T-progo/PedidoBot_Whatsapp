import uuid
from django.conf import settings
from django.db import models
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator


class Empresa(models.Model):

    class Estado(models.TextChoices):
        ACTIVA = "activa", "Activa"
        INACTIVA = "inactiva", "Inactiva"
        SUSPENDIDA = "suspendida", "Suspendida"

    nombre = models.CharField(
        max_length=150
    )

    razon_social = models.CharField(
        max_length=200,
        blank=True
    )

    rfc = models.CharField(
        max_length=20,
        blank=True
    )

    email = models.EmailField(
        blank=True
    )

    telefono = models.CharField(
        max_length=30,
        blank=True
    )

    # ========================================================
    # TNL-EMPRESA-SEGMENTACION-V1
    # Datos comerciales y domicilio estructurado.
    # ========================================================

    giro_negocio = models.CharField(
        max_length=150,
        default="",
    )

    domicilio_calle = models.CharField(
        max_length=150,
        default="",
    )

    domicilio_numero_exterior = models.CharField(
        max_length=30,
        default="",
    )

    domicilio_numero_interior = models.CharField(
        max_length=30,
        blank=True,
        default="",
    )

    domicilio_colonia = models.CharField(
        max_length=150,
        default="",
    )

    domicilio_codigo_postal = models.CharField(
        max_length=12,
        default="",
    )

    domicilio_municipio = models.CharField(
        max_length=150,
        default="",
    )

    domicilio_ciudad = models.CharField(
        max_length=150,
        default="",
    )

    domicilio_estado = models.CharField(
        max_length=100,
        default="",
    )

    domicilio_pais = models.CharField(
        max_length=100,
        default="México",
    )

    estado = models.CharField(
        max_length=20,
        choices=Estado.choices,
        default=Estado.ACTIVA
    )

    creado_en = models.DateTimeField(
        auto_now_add=True
    )

    actualizado_en = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        ordering = ["nombre"]
        verbose_name = "Empresa"
        verbose_name_plural = "Empresas"

    def __str__(self):
        return self.nombre


class PerfilUsuario(models.Model):

    class Rol(models.TextChoices):
        ADMINISTRADOR = "administrador", "Administrador"
        CLIENTE = "cliente", "Cliente"
        OPERADOR = "operador", "Operador"

    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="perfil_negociolisto"
    )

    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="usuarios"
    )

    rol = models.CharField(
        max_length=20,
        choices=Rol.choices,
        default=Rol.CLIENTE
    )

    activo = models.BooleanField(
        default=True
    )

    creado_en = models.DateTimeField(
        auto_now_add=True
    )

    actualizado_en = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        verbose_name = "Perfil de usuario"
        verbose_name_plural = "Perfiles de usuario"

    def __str__(self):
        return self.usuario.get_username()


class Licencia(models.Model):

    class Estado(models.TextChoices):
        ACTIVA = "activa", "Activa"
        SUSPENDIDA = "suspendida", "Suspendida"
        VENCIDA = "vencida", "Vencida"

    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.CASCADE,
        related_name="licencias"
    )

    nombre = models.CharField(
        max_length=120
    )

    estado = models.CharField(
        max_length=20,
        choices=Estado.choices,
        default=Estado.ACTIVA
    )

    fecha_inicio = models.DateField()

    fecha_fin = models.DateField()

    creado_en = models.DateTimeField(
        auto_now_add=True
    )

    actualizado_en = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        ordering = ["-fecha_fin"]
        verbose_name = "Licencia"
        verbose_name_plural = "Licencias"

    def __str__(self):
        return f"{self.empresa} - {self.nombre}"


class Bot(models.Model):

    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.CASCADE,
        related_name="bots"
    )

    plantilla = models.ForeignKey(
        "Plantilla",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bots",
    )

    nombre = models.CharField(
        max_length=150
    )

    identificador_externo = models.CharField(
        max_length=255,
        blank=True
    )

    # TNL-BOT-SYSTEM-PROMPT-MODEL-V1
    system_prompt = models.TextField(
        max_length=12000,
        blank=True,
        default="",
        verbose_name=(
            "System Prompt / "
            "Instrucciones personalizadas"
        ),
        help_text=(
            "Instrucciones específicas para la IA de este bot. "
            "Déjalo en blanco para utilizar las instrucciones "
            "base definidas por NegocioListo o por su plantilla."
        ),
    )

    # TNL-BOT-FAQ-MODEL-V1
    faq = models.TextField(
        max_length=20000,
        blank=True,
        default="",
        verbose_name=(
            "Preguntas frecuentes / "
            "Base de conocimiento"
        ),
        help_text=(
            "Información real del negocio que la IA puede utilizar "
            "para responder preguntas frecuentes. "
            "No incluyas contraseñas, tokens ni credenciales."
        ),
    )

    activo = models.BooleanField(
        default=True
    )

    creado_en = models.DateTimeField(
        auto_now_add=True
    )

    actualizado_en = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        ordering = ["empresa", "nombre"]
        verbose_name = "Bot"
        verbose_name_plural = "Bots"

    def __str__(self):
        return f"{self.empresa} - {self.nombre}"


class Canal(models.Model):

    class Tipo(models.TextChoices):
        WHATSAPP = "whatsapp", "WhatsApp"
        MESSENGER = "messenger", "Messenger"
        TELEGRAM = "telegram", "Telegram"

    bot = models.ForeignKey(
        Bot,
        on_delete=models.CASCADE,
        related_name="canales"
    )

    tipo = models.CharField(
        max_length=20,
        choices=Tipo.choices
    )

    nombre = models.CharField(
        max_length=150,
        blank=True
    )

    identificador = models.CharField(
        max_length=255,
        blank=True
    )

    activo = models.BooleanField(
        default=True
    )

    creado_en = models.DateTimeField(
        auto_now_add=True
    )

    actualizado_en = models.DateTimeField(
        auto_now=True
    )

    class Meta:
        ordering = ["bot", "tipo"]
        verbose_name = "Canal"
        verbose_name_plural = "Canales"

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "bot",
                    "tipo",
                ],
                name="uniq_canal_bot_tipo",
            ),
        ]

    def __str__(self):
        return f"{self.bot} - {self.get_tipo_display()}"


# ============================================================
# PLANTILLAS
# ============================================================

class Plantilla(models.Model):

    TIPO_ABARROTES = "abarrotes"
    TIPO_FERRETERIA = "ferreteria"
    TIPO_FARMACIA = "farmacia"
    TIPO_RESTAURANTE = "restaurante"
    TIPO_CLINICA = "clinica"
    TIPO_ESTETICA = "estetica"
    TIPO_ADMINISTRATIVA = "administrativa"
    TIPO_NEXOS = "nexos"
    TIPO_PERSONALIZADA = "personalizada"

    # Tipo legado conservado temporalmente para instalaciones
    # existentes, como el MVP operativo de IT-MAC.
    TIPO_ABARROTES_FERRETERIA = "abarrotes_ferreteria"

    TIPOS = [
        (
            TIPO_ABARROTES,
            "Abarrotes",
        ),
        (
            TIPO_FERRETERIA,
            "Ferretería",
        ),
        (
            TIPO_FARMACIA,
            "Farmacia",
        ),
        (
            TIPO_RESTAURANTE,
            "Restaurante",
        ),
        (
            TIPO_CLINICA,
            "Clínica",
        ),
        (
            TIPO_ESTETICA,
            "Estética",
        ),
        (
            TIPO_ADMINISTRATIVA,
            "Administrativa",
        ),
        (
            TIPO_NEXOS,
            "Nexos Estratégicos",
        ),
        (
            TIPO_PERSONALIZADA,
            "Personalizada",
        ),
        (
            TIPO_ABARROTES_FERRETERIA,
            "Abarrotes / Ferretería (legado)",
        ),
    ]

    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.CASCADE,
        related_name="plantillas",
    )

    nombre = models.CharField(
        max_length=150,
    )

    tipo = models.CharField(
        max_length=50,
        choices=TIPOS,
    )

    descripcion = models.TextField(
        blank=True,
    )

    identificador_externo = models.CharField(
        max_length=255,
        blank=True,
    )

    activa = models.BooleanField(
        default=True,
    )

    creado_en = models.DateTimeField(
        auto_now_add=True,
    )

    actualizado_en = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["empresa", "nombre"]
        verbose_name = "Plantilla"
        verbose_name_plural = "Plantillas"

    def __str__(self):
        return f"{self.empresa} - {self.nombre}"


# ============================================================
# VARIABLES
# ============================================================

class Variable(models.Model):

    plantilla = models.ForeignKey(
        Plantilla,
        on_delete=models.CASCADE,
        related_name="variables",
    )

    clave = models.CharField(
        max_length=150,
    )

    valor = models.TextField(
        blank=True,
    )

    descripcion = models.TextField(
        blank=True,
    )

    activa = models.BooleanField(
        default=True,
    )

    creado_en = models.DateTimeField(
        auto_now_add=True,
    )

    actualizado_en = models.DateTimeField(
        auto_now=True,
    )

    class Meta:

        ordering = [
            "plantilla",
            "clave",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "plantilla",
                    "clave",
                ],
                name="uniq_variable_plantilla_clave",
            ),
        ]

        verbose_name = "Variable"
        verbose_name_plural = "Variables"

    def __str__(self):
        return f"{self.plantilla} - {self.clave}"


# ============================================================
# CATALOGOS
# ============================================================

class Catalogo(models.Model):

    MONEDAS = [
        ("MXN", "Peso mexicano (MXN)"),
        ("USD", "Dólar estadounidense (USD)"),
    ]

    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.CASCADE,
        related_name="catalogos",
    )

    plantilla = models.ForeignKey(
        "Plantilla",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="catalogos",
    )

    nombre = models.CharField(
        max_length=150,
    )

    descripcion = models.TextField(
        blank=True,
    )

    moneda = models.CharField(
        max_length=3,
        choices=MONEDAS,
        default="MXN",
    )

    identificador_externo = models.CharField(
        max_length=255,
        blank=True,
    )

    activo = models.BooleanField(
        default=True,
    )

    creado_en = models.DateTimeField(
        auto_now_add=True,
    )

    actualizado_en = models.DateTimeField(
        auto_now=True,
    )

    class Meta:

        ordering = [
            "empresa",
            "nombre",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "empresa",
                    "nombre",
                ],
                name="uniq_catalogo_empresa_nombre",
            ),
        ]

        verbose_name = "Catálogo"
        verbose_name_plural = "Catálogos"

    def __str__(self):
        return f"{self.empresa} - {self.nombre}"


# ============================================================
# TNL-RESTAURANTE-CATEGORIA-PRODUCTO-V1
# ============================================================

class CategoriaProducto(models.Model):

    catalogo = models.ForeignKey(
        Catalogo,
        on_delete=models.CASCADE,
        related_name="categorias",
    )

    nombre = models.CharField(max_length=150)

    descripcion = models.TextField(blank=True)

    orden = models.PositiveIntegerField(default=0)

    activa = models.BooleanField(default=True)

    creado_en = models.DateTimeField(auto_now_add=True)

    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["orden", "nombre", "id"]

        constraints = [
            models.UniqueConstraint(
                fields=["catalogo", "nombre"],
                name="uniq_categoria_catalogo_nombre",
            ),
        ]

        indexes = [
            models.Index(
                fields=["catalogo", "activa", "orden"],
                name="idx_catprod_cat_act_ord",
            ),
        ]

        verbose_name = "Categoría de producto"
        verbose_name_plural = "Categorías de producto"

    def __str__(self):
        return f"{self.catalogo} - {self.nombre}"


# ============================================================
# TNL-RESTAURANTE-CONFIGURACION-V1
# ============================================================

class ConfiguracionRestaurante(models.Model):

    empresa = models.OneToOneField(
        Empresa,
        on_delete=models.CASCADE,
        related_name="configuracion_restaurante",
    )

    costo_envio_fijo = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        default=0,
    )

    envio_gratis_desde = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        null=True,
        blank=True,
    )

    tiempo_estimado_minutos = models.PositiveIntegerField(
        default=30,
    )

    habilitada = models.BooleanField(default=True)

    creado_en = models.DateTimeField(auto_now_add=True)

    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(costo_envio_fijo__gte=0),
                name="rest_costo_envio_no_neg",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(envio_gratis_desde__isnull=True)
                    |
                    models.Q(envio_gratis_desde__gte=0)
                ),
                name="rest_envio_gratis_no_neg",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    tiempo_estimado_minutos__gt=0
                ),
                name="rest_tiempo_estimado_pos",
            ),
        ]

        verbose_name = "Configuración de restaurante"
        verbose_name_plural = "Configuraciones de restaurante"

    def __str__(self):
        return f"Restaurante - {self.empresa}"


# ============================================================
# PRODUCTOS
# ============================================================



# ============================================================
# TNL-PRODUCT-IMAGES-HELPERS-V1
# ============================================================

def validar_tamano_imagen_producto(archivo):
    # TNL-PRODUCT-IMAGE-MAX-4MB-V1
    limite = 4 * 1024 * 1024

    if archivo.size > limite:
        raise ValidationError(
            "La imagen no puede superar 4 MB."
        )



# ============================================================
# TNL-PRODUCT-IMAGE-OPTIMIZER-V1
# ============================================================

PRODUCT_IMAGE_MAX_DIMENSION = 2560
PRODUCT_IMAGE_WEBP_QUALITY = 88


def optimizar_imagen_producto(archivo):
    """
    Optimiza únicamente archivos nuevos.

    - Corrige orientación EXIF.
    - Mantiene proporción.
    - Nunca recorta ni estira.
    - Reduce imágenes gigantes a máximo 2560 px.
    - PNG/transparencia: WebP lossless.
    - Fotos: WebP calidad 88.
    - Si el resultado pesa más que el original,
      conserva el archivo original.
    """

    from io import BytesIO
    from pathlib import Path

    from django.core.files.base import ContentFile
    from PIL import Image, ImageOps

    if not archivo:
        return archivo

    try:
        archivo.seek(0)

        original_bytes = archivo.read()

        archivo.seek(0)

        imagen = Image.open(
            archivo
        )

        formato_original = (
            imagen.format
            or ""
        ).upper()

        imagen.load()

        imagen = ImageOps.exif_transpose(
            imagen
        )

    except Exception as exc:
        raise ValidationError(
            "No fue posible procesar "
            "la imagen cargada."
        ) from exc


    ancho_original, alto_original = (
        imagen.size
    )

    max_dimension = max(
        ancho_original,
        alto_original,
    )

    if (
        max_dimension
        > PRODUCT_IMAGE_MAX_DIMENSION
    ):

        imagen.thumbnail(
            (
                PRODUCT_IMAGE_MAX_DIMENSION,
                PRODUCT_IMAGE_MAX_DIMENSION,
            ),
            Image.Resampling.LANCZOS,
        )


    tiene_alpha = (
        imagen.mode in (
            "RGBA",
            "LA",
        )
        or (
            imagen.mode == "P"
            and "transparency"
            in imagen.info
        )
    )


    if tiene_alpha:

        if imagen.mode != "RGBA":
            imagen = imagen.convert(
                "RGBA"
            )

    else:

        if imagen.mode != "RGB":
            imagen = imagen.convert(
                "RGB"
            )


    # PNG y transparencias se conservan
    # sin pérdida de información visual.
    usar_lossless = (
        formato_original == "PNG"
        or tiene_alpha
    )


    salida = BytesIO()

    if usar_lossless:

        imagen.save(
            salida,
            format="WEBP",
            lossless=True,
            method=6,
        )

    else:

        imagen.save(
            salida,
            format="WEBP",
            quality=PRODUCT_IMAGE_WEBP_QUALITY,
            method=6,
        )


    webp_bytes = salida.getvalue()

    # Si por alguna razón WebP pesa más
    # que el original, no aumentamos
    # artificialmente el almacenamiento.
    if (
        len(webp_bytes)
        >= len(original_bytes)
        and max_dimension
            <= PRODUCT_IMAGE_MAX_DIMENSION
    ):

        archivo.seek(0)

        return archivo


    nombre_original = getattr(
        archivo,
        "name",
        "producto",
    )

    stem = (
        Path(nombre_original)
        .stem
    )

    contenido = ContentFile(
        webp_bytes,
        name=f"{stem}.webp",
    )

    return contenido


def ruta_imagen_principal_producto(
    instance,
    filename,
):
    import os
    import uuid

    extension = (
        os.path.splitext(filename)[1]
        .lower()
    )

    empresa_id = (
        instance.catalogo.empresa_id
        if instance.catalogo_id
        else "sin_empresa"
    )

    producto_id = (
        instance.pk
        or "nuevo"
    )

    return (
        f"productos/empresa_{empresa_id}/"
        f"producto_{producto_id}/"
        f"principal/"
        f"{uuid.uuid4().hex}{extension}"
    )


def ruta_imagen_galeria_producto(
    instance,
    filename,
):
    import os
    import uuid

    extension = (
        os.path.splitext(filename)[1]
        .lower()
    )

    empresa_id = (
        instance.producto.catalogo.empresa_id
        if instance.producto_id
        else "sin_empresa"
    )

    producto_id = (
        instance.producto_id
        or "nuevo"
    )

    return (
        f"productos/empresa_{empresa_id}/"
        f"producto_{producto_id}/"
        f"galeria/"
        f"{uuid.uuid4().hex}{extension}"
    )


class Producto(models.Model):

    catalogo = models.ForeignKey(
        Catalogo,
        on_delete=models.CASCADE,
        related_name="productos",
    )

    # TNL-RESTAURANTE-PRODUCTO-CATEGORIA-V1
    categoria = models.ForeignKey(
        "CategoriaProducto",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="productos",
    )

    # TNL-PRODUCT-SKU-OPTIONAL-REPEATABLE-V1
    sku = models.CharField(
        max_length=100,
        blank=True,
    )

    nombre = models.CharField(
        max_length=200,
    )

    descripcion = models.TextField(
        blank=True,
    )

    precio = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        default=0,
    )

    stock = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        default=0,
    )

    unidad = models.CharField(
        max_length=50,
        default="pieza",
    )

    imagen_principal = models.ImageField(
        upload_to=ruta_imagen_principal_producto,
        blank=True,
        max_length=500,
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
    )

    identificador_externo = models.CharField(
        max_length=255,
        blank=True,
    )

    activo = models.BooleanField(
        default=True,
    )

    creado_en = models.DateTimeField(
        auto_now_add=True,
    )

    actualizado_en = models.DateTimeField(
        auto_now=True,
    )

    # TNL-PRODUCT-MAIN-IMAGE-SAVE-V1
    def save(self, *args, **kwargs):

        if (
            self.imagen_principal
            and not getattr(
                self.imagen_principal,
                "_committed",
                True,
            )
        ):

            self.imagen_principal = (
                optimizar_imagen_producto(
                    self.imagen_principal.file
                )
            )

        return super().save(
            *args,
            **kwargs
        )


    class Meta:

        ordering = [
            "catalogo",
            "nombre",
        ]

        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    precio__gte=0
                ),
                name="producto_precio_no_negativo",
            ),

            models.CheckConstraint(
                condition=models.Q(
                    stock__gte=0
                ),
                name="producto_stock_no_negativo",
            ),
        ]

        verbose_name = "Producto"
        verbose_name_plural = "Productos"

    def __str__(self):
        return f"{self.sku} - {self.nombre}"


# ============================================================
# TNL-PRODUCTOS-ESTRELLA-CROSSSELL-IA-V1
# ============================================================

class ProductoPromocionIA(models.Model):
    """
    Configuración comercial que el dueño puede aplicar
    a un producto existente.

    Producto sigue siendo la fuente de verdad para:
    - nombre;
    - precio;
    - stock;
    - imagen;
    - estado.

    Este modelo sólo controla promoción por IA.
    """

    empresa = models.ForeignKey(
        "Empresa",
        on_delete=models.CASCADE,
        related_name="productos_promocion_ia",
    )

    producto = models.OneToOneField(
        Producto,
        on_delete=models.CASCADE,
        related_name="promocion_ia",
    )

    es_estrella = models.BooleanField(
        default=False,
    )

    texto_promocional = models.TextField(
        blank=True,
        default="",
    )

    activa = models.BooleanField(
        default=True,
    )

    creado_en = models.DateTimeField(
        auto_now_add=True,
    )

    actualizado_en = models.DateTimeField(
        auto_now=True,
    )

    def clean(self):
        from django.core.exceptions import (
            ValidationError,
        )

        super().clean()

        if (
            self.empresa_id
            and
            self.producto_id
        ):
            producto_empresa_id = (
                self.producto
                .catalogo
                .empresa_id
            )

            if (
                producto_empresa_id
                !=
                self.empresa_id
            ):
                raise ValidationError(
                    {
                        "producto": (
                            "El producto no pertenece "
                            "a la empresa seleccionada."
                        )
                    }
                )

    def save(
        self,
        *args,
        **kwargs,
    ):
        self.full_clean()

        return super().save(
            *args,
            **kwargs,
        )

    class Meta:
        ordering = [
            "empresa_id",
            "producto_id",
        ]

        indexes = [
            models.Index(
                fields=[
                    "empresa",
                    "activa",
                    "es_estrella",
                ],
                name=
                    "idx_promia_emp_act_est",
            ),
        ]

        verbose_name = (
            "Promoción IA de producto"
        )

        verbose_name_plural = (
            "Promociones IA de productos"
        )

    def __str__(self):
        return (
            f"{self.empresa} - "
            f"{self.producto} - "
            f"estrella={self.es_estrella}"
        )


class ReglaVentaCruzadaIA(models.Model):
    """
    Regla de cross-selling configurada por el dueño.

    Ejemplo:
        origen:
            Alitas

        recomendado:
            Hamburguesa doble

        mensaje:
            Ya adquiriste tus Alitas.
            ¿Deseas agregar una Hamburguesa
            Doble por {{precio_recomendado}}?

    El precio nunca se toma como verdad del texto.
    Siempre se resuelve desde Producto.
    """

    empresa = models.ForeignKey(
        "Empresa",
        on_delete=models.CASCADE,
        related_name=
            "reglas_venta_cruzada_ia",
    )

    producto_origen = models.ForeignKey(
        Producto,
        on_delete=models.CASCADE,
        related_name=
            "reglas_cross_sell_origen",
    )

    producto_recomendado = (
        models.ForeignKey(
            Producto,
            on_delete=models.CASCADE,
            related_name=
                "reglas_cross_sell_recomendado",
        )
    )

    texto_promocional = models.TextField(
        blank=True,
        default="",
    )

    activa = models.BooleanField(
        default=True,
    )

    prioridad = models.PositiveIntegerField(
        default=100,
    )

    creado_en = models.DateTimeField(
        auto_now_add=True,
    )

    actualizado_en = models.DateTimeField(
        auto_now=True,
    )

    def clean(self):
        from django.core.exceptions import (
            ValidationError,
        )

        super().clean()

        errors = {}

        if (
            self.producto_origen_id
            and
            self.producto_recomendado_id
            and
            self.producto_origen_id
            ==
            self.producto_recomendado_id
        ):
            errors[
                "producto_recomendado"
            ] = (
                "El producto recomendado debe "
                "ser diferente al producto origen."
            )

        if (
            self.empresa_id
            and
            self.producto_origen_id
        ):
            origen_empresa_id = (
                self.producto_origen
                .catalogo
                .empresa_id
            )

            if (
                origen_empresa_id
                !=
                self.empresa_id
            ):
                errors[
                    "producto_origen"
                ] = (
                    "El producto origen no pertenece "
                    "a la empresa seleccionada."
                )

        if (
            self.empresa_id
            and
            self.producto_recomendado_id
        ):
            recomendado_empresa_id = (
                self.producto_recomendado
                .catalogo
                .empresa_id
            )

            if (
                recomendado_empresa_id
                !=
                self.empresa_id
            ):
                errors[
                    "producto_recomendado"
                ] = (
                    "El producto recomendado no "
                    "pertenece a la empresa "
                    "seleccionada."
                )

        if errors:
            raise ValidationError(
                errors
            )

    def save(
        self,
        *args,
        **kwargs,
    ):
        self.full_clean()

        return super().save(
            *args,
            **kwargs,
        )

    class Meta:
        ordering = [
            "empresa_id",
            "prioridad",
            "id",
        ]

        indexes = [
            models.Index(
                fields=[
                    "empresa",
                    "producto_origen",
                    "activa",
                    "prioridad",
                ],
                name=
                    "idx_crossia_emp_ori_act",
            ),
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "empresa",
                    "producto_origen",
                    "producto_recomendado",
                ],
                name=
                    "uniq_crossia_emp_ori_rec",
            ),
        ]

        verbose_name = (
            "Regla de venta cruzada IA"
        )

        verbose_name_plural = (
            "Reglas de venta cruzada IA"
        )

    def __str__(self):
        return (
            f"{self.empresa}: "
            f"{self.producto_origen} -> "
            f"{self.producto_recomendado}"
        )



# ============================================================
# TNL-RESTAURANTE-MODIFICADORES-V1
# ============================================================

class GrupoModificadorProducto(models.Model):

    class Tipo(models.TextChoices):
        MODIFICADOR = "modificador", "Modificador"
        EXTRA = "extra", "Extra"

    producto = models.ForeignKey(
        Producto,
        on_delete=models.CASCADE,
        related_name="grupos_modificadores",
    )

    nombre = models.CharField(max_length=150)

    tipo = models.CharField(
        max_length=20,
        choices=Tipo.choices,
        default=Tipo.MODIFICADOR,
    )

    obligatorio = models.BooleanField(default=False)

    minimo = models.PositiveSmallIntegerField(default=0)

    maximo = models.PositiveSmallIntegerField(default=1)

    orden = models.PositiveIntegerField(default=0)

    activo = models.BooleanField(default=True)

    creado_en = models.DateTimeField(auto_now_add=True)

    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["orden", "id"]

        constraints = [
            models.UniqueConstraint(
                fields=["producto", "nombre"],
                name="uniq_grupo_mod_prod_nombre",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    maximo__gte=models.F("minimo")
                ),
                name="grupo_mod_min_le_max",
            ),
            models.CheckConstraint(
                condition=models.Q(maximo__gte=1),
                name="grupo_mod_max_pos",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(obligatorio=False)
                    |
                    models.Q(minimo__gte=1)
                ),
                name="grupo_mod_oblig_min",
            ),
        ]

        indexes = [
            models.Index(
                fields=["producto", "activo", "orden"],
                name="idx_grupomod_prod_act_ord",
            ),
        ]

        verbose_name = "Grupo modificador"
        verbose_name_plural = "Grupos modificadores"

    def __str__(self):
        return f"{self.producto} - {self.nombre}"


class OpcionModificadorProducto(models.Model):

    grupo = models.ForeignKey(
        GrupoModificadorProducto,
        on_delete=models.CASCADE,
        related_name="opciones",
    )

    nombre = models.CharField(max_length=150)

    precio_adicional = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        default=0,
    )

    orden = models.PositiveIntegerField(default=0)

    activa = models.BooleanField(default=True)

    creado_en = models.DateTimeField(auto_now_add=True)

    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["orden", "id"]

        constraints = [
            models.UniqueConstraint(
                fields=["grupo", "nombre"],
                name="uniq_opcion_grupo_nombre",
            ),
            models.CheckConstraint(
                condition=models.Q(precio_adicional__gte=0),
                name="opcion_mod_precio_no_neg",
            ),
        ]

        indexes = [
            models.Index(
                fields=["grupo", "activa", "orden"],
                name="idx_opmod_grup_act_ord",
            ),
        ]

        verbose_name = "Opción de modificador"
        verbose_name_plural = "Opciones de modificador"

    def __str__(self):
        return f"{self.grupo} - {self.nombre}"




# ============================================================
# TNL-PRODUCT-GALLERY-V1
# ============================================================

class ProductoImagen(models.Model):

    producto = models.ForeignKey(
        Producto,
        on_delete=models.CASCADE,
        related_name="galeria",
    )

    imagen = models.ImageField(
        upload_to=ruta_imagen_galeria_producto,
        max_length=500,
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
    )

    texto_alternativo = models.CharField(
        max_length=200,
        blank=True,
    )

    orden = models.PositiveIntegerField(
        default=0,
    )

    activa = models.BooleanField(
        default=True,
    )

    creado_en = models.DateTimeField(
        auto_now_add=True,
    )

    actualizado_en = models.DateTimeField(
        auto_now=True,
    )

    # TNL-PRODUCT-GALLERY-IMAGE-SAVE-V1
    def save(self, *args, **kwargs):

        if (
            self.imagen
            and not getattr(
                self.imagen,
                "_committed",
                True,
            )
        ):

            self.imagen = (
                optimizar_imagen_producto(
                    self.imagen.file
                )
            )

        return super().save(
            *args,
            **kwargs
        )


    class Meta:

        ordering = [
            "orden",
            "id",
        ]

        indexes = [
            models.Index(
                fields=[
                    "producto",
                    "orden",
                ],
                name="idx_prodimg_producto_orden",
            ),
        ]

        verbose_name = "Imagen de producto"
        verbose_name_plural = (
            "Imágenes de producto"
        )

    def __str__(self):
        return (
            f"{self.producto} "
            f"- imagen {self.id}"
        )


# ============================================================
# PEDIDOS
# ============================================================

class Pedido(models.Model):

    ESTADOS = [
        ("carrito", "Carrito"),
        ("pendiente", "Pendiente"),
        ("confirmado", "Confirmado"),
        ("pagado", "Pagado"),
        ("preparando", "Preparando"),
        ("listo", "Listo"),
        ("en_camino", "En camino"),
        ("enviado", "Enviado"),
        ("entregado", "Entregado"),
        ("cancelado", "Cancelado"),
    ]

    TIPOS_ORDEN = [
        ("comedor", "Comedor"),
        ("para_llevar", "Para llevar"),
        ("domicilio", "A domicilio"),
    ]

    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.CASCADE,
        related_name="pedidos",
    )

    canal = models.ForeignKey(
        Canal,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pedidos",
    )

    numero = models.CharField(
        max_length=50,
    )

    estado = models.CharField(
        max_length=20,
        choices=ESTADOS,
        default="carrito",
    )

    # TNL-RESTAURANTE-TIPO-ORDEN-V1
    tipo_orden = models.CharField(
        max_length=20,
        choices=TIPOS_ORDEN,
        blank=True,
        default="",
    )

    cliente_nombre = models.CharField(
        max_length=200,
        blank=True,
    )

    cliente_telefono = models.CharField(
        max_length=50,
        blank=True,
    )

    cliente_email = models.EmailField(
        blank=True,
    )

    direccion_entrega = models.TextField(
        blank=True,
    )

    tiempo_estimado_minutos = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    notas = models.TextField(
        blank=True,
    )

    moneda = models.CharField(
        max_length=3,
        default="MXN",
    )

    subtotal = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        default=0,
    )

    # TNL-RESTAURANTE-DESGLOSE-PEDIDO-V1
    subtotal_productos = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        default=0,
    )

    subtotal_modificadores = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        default=0,
    )

    subtotal_extras = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        default=0,
    )

    costo_envio = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        default=0,
    )

    descuento = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        default=0,
    )

    total = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        default=0,
    )

    identificador_externo = models.CharField(
        max_length=255,
        blank=True,
    )

    creado_en = models.DateTimeField(
        auto_now_add=True,
    )

    actualizado_en = models.DateTimeField(
        auto_now=True,
    )

    confirmado_en = models.DateTimeField(
        null=True,
        blank=True,
    )

    class Meta:

        ordering = [
            "-creado_en",
        ]

        constraints = [

            models.UniqueConstraint(
                fields=[
                    "empresa",
                    "numero",
                ],
                name="uniq_pedido_empresa_numero",
            ),

            models.CheckConstraint(
                condition=models.Q(
                    subtotal__gte=0
                ),
                name="pedido_subtotal_no_negativo",
            ),

            models.CheckConstraint(
                condition=models.Q(
                    descuento__gte=0
                ),
                name="pedido_descuento_no_negativo",
            ),

            models.CheckConstraint(
                condition=models.Q(
                    total__gte=0
                ),
                name="pedido_total_no_negativo",
            ),

            models.CheckConstraint(
                condition=models.Q(
                    subtotal_productos__gte=0
                ),
                name="pedido_subprod_no_neg",
            ),

            models.CheckConstraint(
                condition=models.Q(
                    subtotal_modificadores__gte=0
                ),
                name="pedido_submod_no_neg",
            ),

            models.CheckConstraint(
                condition=models.Q(
                    subtotal_extras__gte=0
                ),
                name="pedido_subextra_no_neg",
            ),

            models.CheckConstraint(
                condition=models.Q(
                    costo_envio__gte=0
                ),
                name="pedido_envio_no_neg",
            ),
        ]

        verbose_name = "Pedido"
        verbose_name_plural = "Pedidos"

    def __str__(self):
        return f"{self.numero} - {self.empresa}"


# ============================================================
# DETALLES DE PEDIDO
# ============================================================

class PedidoDetalle(models.Model):

    pedido = models.ForeignKey(
        Pedido,
        on_delete=models.CASCADE,
        related_name="detalles",
    )

    producto = models.ForeignKey(
        Producto,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="detalles_pedido",
    )

    sku = models.CharField(
        max_length=100,
    )

    nombre_producto = models.CharField(
        max_length=200,
    )

    cantidad = models.DecimalField(
        max_digits=14,
        decimal_places=4,
    )

    precio_unitario = models.DecimalField(
        max_digits=14,
        decimal_places=4,
    )

    # TNL-RESTAURANTE-DETALLE-SNAPSHOT-V1
    precio_base = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        null=True,
        blank=True,
    )

    precio_modificadores = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        default=0,
    )

    precio_extras = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        default=0,
    )

    modificadores_snapshot = models.JSONField(
        default=list,
        blank=True,
    )

    extras_snapshot = models.JSONField(
        default=list,
        blank=True,
    )

    descuento = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        default=0,
    )

    importe = models.DecimalField(
        max_digits=14,
        decimal_places=4,
    )

    creado_en = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:

        ordering = [
            "id",
        ]

        constraints = [

            models.CheckConstraint(
                condition=models.Q(
                    cantidad__gt=0
                ),
                name="pedido_detalle_cantidad_positiva",
            ),

            models.CheckConstraint(
                condition=models.Q(
                    precio_unitario__gte=0
                ),
                name="pedido_detalle_precio_no_negativo",
            ),

            models.CheckConstraint(
                condition=models.Q(
                    descuento__gte=0
                ),
                name="pedido_detalle_descuento_no_negativo",
            ),

            models.CheckConstraint(
                condition=models.Q(
                    importe__gte=0
                ),
                name="pedido_detalle_importe_no_negativo",
            ),

            models.CheckConstraint(
                condition=(
                    models.Q(precio_base__isnull=True)
                    |
                    models.Q(precio_base__gte=0)
                ),
                name="ped_det_precio_base_no_neg",
            ),

            models.CheckConstraint(
                condition=models.Q(
                    precio_modificadores__gte=0
                ),
                name="ped_det_mod_no_neg",
            ),

            models.CheckConstraint(
                condition=models.Q(
                    precio_extras__gte=0
                ),
                name="ped_det_extra_no_neg",
            ),
        ]

        verbose_name = "Detalle de pedido"
        verbose_name_plural = "Detalles de pedido"

    def __str__(self):
        return f"{self.pedido.numero} - {self.sku}"


# ============================================================
# TNL-RESTAURANTE-PEDIDO-ESTADO-EVENTO-V1
# ============================================================

class PedidoEstadoEvento(models.Model):

    pedido = models.ForeignKey(
        Pedido,
        on_delete=models.CASCADE,
        related_name="estado_eventos",
    )

    estado_anterior = models.CharField(
        max_length=20,
        blank=True,
        default="",
    )

    estado_nuevo = models.CharField(
        max_length=20,
        choices=Pedido.ESTADOS,
    )

    fecha = models.DateTimeField(auto_now_add=True)

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="eventos_estado_pedido",
    )

    notificacion_whatsapp_enviada = models.BooleanField(
        default=False,
    )

    notificacion_whatsapp_intentada_en = models.DateTimeField(
        null=True,
        blank=True,
    )

    message_id = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )

    notificacion_error = models.TextField(
        blank=True,
        default="",
    )

    class Meta:
        ordering = ["fecha", "id"]

        indexes = [
            models.Index(
                fields=["pedido", "fecha"],
                name="idx_pedestado_ped_fecha",
            ),
            models.Index(
                fields=["pedido", "estado_nuevo"],
                name="idx_pedestado_ped_estado",
            ),
        ]

        verbose_name = "Evento de estado de pedido"
        verbose_name_plural = "Eventos de estado de pedido"

    def __str__(self):
        return (
            f"{self.pedido.numero}: "
            f"{self.estado_anterior or '-'} "
            f"-> {self.estado_nuevo}"
        )


# ============================================================
# MOTOR DE PLANTILLAS MAESTRAS
# ============================================================


class PlantillaMaestra(models.Model):

    class Tipo(models.TextChoices):
        ABARROTES = (
            "abarrotes",
            "Abarrotes",
        )
        FERRETERIA = (
            "ferreteria",
            "Ferretería",
        )
        FARMACIA = (
            "farmacia",
            "Farmacia",
        )
        RESTAURANTE = (
            "restaurante",
            "Restaurante",
        )
        CLINICA = (
            "clinica",
            "Clínica",
        )
        ESTETICA = (
            "estetica",
            "Estética",
        )
        ADMINISTRATIVA = (
            "administrativa",
            "Administrativa",
        )
        NEXOS = (
            "nexos",
            "Nexos Estratégicos",
        )
        PERSONALIZADA = (
            "personalizada",
            "Personalizada",
        )

    class Estado(models.TextChoices):
        BORRADOR = (
            "borrador",
            "Borrador",
        )
        PUBLICADA = (
            "publicada",
            "Publicada",
        )
        RETIRADA = (
            "retirada",
            "Retirada",
        )

    nombre = models.CharField(
        max_length=150,
    )

    slug = models.SlugField(
        max_length=180,
    )

    tipo = models.CharField(
        max_length=50,
        choices=Tipo.choices,
    )

    version = models.PositiveIntegerField(
        default=1,
    )

    descripcion = models.TextField(
        blank=True,
    )

    identificador_externo = models.CharField(
        max_length=255,
        blank=True,
    )

    configuracion = models.JSONField(
        default=dict,
        blank=True,
    )

    estado = models.CharField(
        max_length=20,
        choices=Estado.choices,
        default=Estado.BORRADOR,
    )

    activa = models.BooleanField(
        default=True,
    )

    creado_en = models.DateTimeField(
        auto_now_add=True,
    )

    actualizado_en = models.DateTimeField(
        auto_now=True,
    )

    class Meta:

        ordering = [
            "tipo",
            "nombre",
            "-version",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "slug",
                    "version",
                ],
                name="uniq_plantilla_maestra_slug_version",
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "tipo",
                    "estado",
                    "activa",
                ],
                name="idx_pm_tipo_estado_activa",
            ),
        ]

        verbose_name = "Plantilla maestra"
        verbose_name_plural = "Plantillas maestras"

    def __str__(self):
        return (
            f"{self.nombre} "
            f"v{self.version}"
        )


class PlantillaVariableMaestra(models.Model):

    class TipoDato(models.TextChoices):
        TEXTO = (
            "texto",
            "Texto",
        )
        NUMERO = (
            "numero",
            "Número",
        )
        BOOLEANO = (
            "booleano",
            "Sí / No",
        )
        FECHA = (
            "fecha",
            "Fecha",
        )
        HORA = (
            "hora",
            "Hora",
        )
        JSON = (
            "json",
            "JSON",
        )

    plantilla_maestra = models.ForeignKey(
        PlantillaMaestra,
        on_delete=models.CASCADE,
        related_name="variables",
    )

    clave = models.CharField(
        max_length=120,
    )

    nombre = models.CharField(
        max_length=150,
    )

    tipo_dato = models.CharField(
        max_length=20,
        choices=TipoDato.choices,
        default=TipoDato.TEXTO,
    )

    valor_default = models.TextField(
        blank=True,
    )

    requerida = models.BooleanField(
        default=False,
    )

    descripcion = models.TextField(
        blank=True,
    )

    orden = models.PositiveIntegerField(
        default=0,
    )

    activa = models.BooleanField(
        default=True,
    )

    creado_en = models.DateTimeField(
        auto_now_add=True,
    )

    actualizado_en = models.DateTimeField(
        auto_now=True,
    )

    class Meta:

        ordering = [
            "plantilla_maestra",
            "orden",
            "clave",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "plantilla_maestra",
                    "clave",
                ],
                name="uniq_pm_variable_clave",
            ),
        ]

        verbose_name = "Variable maestra"
        verbose_name_plural = "Variables maestras"

    def __str__(self):
        return (
            f"{self.plantilla_maestra} "
            f"- {self.clave}"
        )


class InstalacionPlantilla(models.Model):

    class Estado(models.TextChoices):
        PENDIENTE = (
            "pendiente",
            "Pendiente",
        )
        APROVISIONANDO = (
            "aprovisionando",
            "Aprovisionando",
        )
        LISTA = (
            "lista",
            "Lista",
        )
        ERROR = (
            "error",
            "Error",
        )
        SUSPENDIDA = (
            "suspendida",
            "Suspendida",
        )

    empresa = models.ForeignKey(
        "Empresa",
        on_delete=models.CASCADE,
        related_name="instalaciones_plantilla",
    )

    licencia = models.ForeignKey(
        "Licencia",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="instalaciones_plantilla",
    )

    plantilla_maestra = models.ForeignKey(
        PlantillaMaestra,
        on_delete=models.PROTECT,
        related_name="instalaciones",
    )

    plantilla = models.OneToOneField(
        "Plantilla",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="instalacion_maestra",
    )

    version_instalada = models.PositiveIntegerField(
        default=1,
    )

    estado = models.CharField(
        max_length=20,
        choices=Estado.choices,
        default=Estado.PENDIENTE,
    )

    clave_idempotencia = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
    )

    ultimo_error = models.TextField(
        blank=True,
    )

    iniciada_en = models.DateTimeField(
        auto_now_add=True,
    )

    completada_en = models.DateTimeField(
        null=True,
        blank=True,
    )

    actualizado_en = models.DateTimeField(
        auto_now=True,
    )

    class Meta:

        ordering = [
            "-iniciada_en",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "empresa",
                    "plantilla_maestra",
                ],
                name="uniq_instalacion_empresa_pm",
            ),
        ]

        indexes = [
            models.Index(
                fields=[
                    "empresa",
                    "estado",
                ],
                name="idx_inst_empresa_estado",
            ),
        ]

        verbose_name = "Instalación de plantilla"
        verbose_name_plural = (
            "Instalaciones de plantillas"
        )

    def __str__(self):
        return (
            f"{self.empresa} - "
            f"{self.plantilla_maestra}"
        )


# ============================================================================
# TNL-MERCADOPAGO-MODELS-V1
#
# Base multiempresa para Mercado Pago.
#
# IMPORTANTE:
# access_token_cifrado y refresh_token_cifrado
# NUNCA deben almacenar credenciales en texto plano.
# El cifrado se implementa en la capa de integración.
# ============================================================================

import uuid as _tnl_mp_uuid


class ConfiguracionMercadoPago(
    models.Model
):

    class Modo(
        models.TextChoices
    ):
        PRUEBAS = (
            "pruebas",
            "Pruebas",
        )

        PRODUCCION = (
            "produccion",
            "Producción",
        )


    class EstadoConexion(
        models.TextChoices
    ):
        DESCONECTADA = (
            "desconectada",
            "Desconectada",
        )

        CONECTADA = (
            "conectada",
            "Conectada",
        )

        ERROR = (
            "error",
            "Error",
        )


    empresa = models.OneToOneField(
        Empresa,
        on_delete=models.CASCADE,
        related_name=
            "configuracion_mercadopago",
    )

    habilitada = models.BooleanField(
        default=False,
    )

    modo = models.CharField(
        max_length=20,
        choices=Modo.choices,
        default=Modo.PRUEBAS,
    )

    estado_conexion = models.CharField(
        max_length=20,
        choices=EstadoConexion.choices,
        default=
            EstadoConexion.DESCONECTADA,
    )

    mp_user_id = models.CharField(
        max_length=64,
        blank=True,
        default="",
    )

    access_token_cifrado = models.TextField(
        blank=True,
        default="",
    )

    refresh_token_cifrado = models.TextField(
        blank=True,
        default="",
    )

    token_expira_en = models.DateTimeField(
        null=True,
        blank=True,
    )

    conectado_en = models.DateTimeField(
        null=True,
        blank=True,
    )

    ultima_validacion_en = models.DateTimeField(
        null=True,
        blank=True,
    )

    ultimo_error = models.TextField(
        blank=True,
        default="",
    )

    creado_en = models.DateTimeField(
        auto_now_add=True,
    )

    actualizado_en = models.DateTimeField(
        auto_now=True,
    )


    class Meta:

        verbose_name = (
            "Configuración Mercado Pago"
        )

        verbose_name_plural = (
            "Configuraciones Mercado Pago"
        )


    def __str__(self):

        return (
            "Mercado Pago · "
            + self.empresa.nombre
        )


class Pago(
    models.Model
):

    class Proveedor(
        models.TextChoices
    ):
        MERCADOPAGO = (
            "mercadopago",
            "Mercado Pago",
        )


        # TNL-PAGO-DIRECTO-P2-V1
        NEGOCIO = (
            "negocio",
            "Efectivo / contra entrega",
        )


    class Estado(
        models.TextChoices
    ):
        CREADO = (
            "creado",
            "Creado",
        )

        PENDIENTE = (
            "pendiente",
            "Pendiente",
        )

        APROBADO = (
            "aprobado",
            "Aprobado",
        )

        RECHAZADO = (
            "rechazado",
            "Rechazado",
        )

        CANCELADO = (
            "cancelado",
            "Cancelado",
        )

        REEMBOLSADO = (
            "reembolsado",
            "Reembolsado",
        )

        CONTRACARGO = (
            "contracargo",
            "Contracargo",
        )

        EXPIRADO = (
            "expirado",
            "Expirado",
        )

        ERROR = (
            "error",
            "Error",
        )


    # TNL-PAGO-DESTINO-XOR-V1
    pedido = models.ForeignKey(
        Pedido,
        on_delete=models.PROTECT,
        related_name="pagos",
        null=True,
        blank=True,
    )

    cita = models.ForeignKey(
        "Cita",
        on_delete=models.PROTECT,
        related_name="pagos",
        null=True,
        blank=True,
    )

    proveedor = models.CharField(
        max_length=30,
        choices=Proveedor.choices,
        default=Proveedor.MERCADOPAGO,
    )

    estado = models.CharField(
        max_length=20,
        choices=Estado.choices,
        default=Estado.CREADO,
    )

    referencia = models.UUIDField(
        default=_tnl_mp_uuid.uuid4,
        unique=True,
        editable=False,
    )

    monto = models.DecimalField(
        max_digits=14,
        decimal_places=2,
    )

    moneda = models.CharField(
        max_length=10,
        default="MXN",
    )

    preference_id = models.CharField(
        max_length=200,
        null=True,
        blank=True,
        unique=True,
    )

    payment_id = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        unique=True,
    )

    merchant_order_id = models.CharField(
        max_length=100,
        blank=True,
        default="",
    )

    checkout_url = models.URLField(
        max_length=1200,
        blank=True,
        default="",
    )

    estado_proveedor = models.CharField(
        max_length=50,
        blank=True,
        default="",
    )

    detalle_estado_proveedor = (
        models.CharField(
            max_length=150,
            blank=True,
            default="",
        )
    )

    aprobado_en = models.DateTimeField(
        null=True,
        blank=True,
    )

    ultima_notificacion_en = (
        models.DateTimeField(
            null=True,
            blank=True,
        )
    )

    creado_en = models.DateTimeField(
        auto_now_add=True,
    )

    actualizado_en = models.DateTimeField(
        auto_now=True,
    )


    class Meta:

        ordering = (
            "-id",
        )

        indexes = [
            models.Index(
                fields=[
                    "proveedor",
                    "estado",
                ],
                name=
                    "core_pago_prov_est_idx",
            ),

            models.Index(
                fields=[
                    "pedido",
                    "estado",
                ],
                name=
                    "core_pago_ped_est_idx",
            ),

            models.Index(
                fields=[
                    "cita",
                    "estado",
                ],
                name=
                    "core_pago_cita_est_idx",
            ),
        ]

        constraints = (
            models.CheckConstraint(
                condition=(
                    (
                        models.Q(
                            pedido__isnull=False
                        )
                        &
                        models.Q(
                            cita__isnull=True
                        )
                    )
                    |
                    (
                        models.Q(
                            pedido__isnull=True
                        )
                        &
                        models.Q(
                            cita__isnull=False
                        )
                    )
                ),
                name=
                    "core_pago_destino_xor",
            ),
        )

        verbose_name = "Pago"
        verbose_name_plural = "Pagos"


    def __str__(self):

        # TNL-PAGO-DESTINO-STR-V1
        if self.pedido_id:

            # Preservar exactamente la representación
            # histórica de pagos asociados a Pedido.
            return (
                str(self.referencia)
                + " · "
                + self.pedido.numero
            )

        if self.cita_id:

            return (
                str(self.referencia)
                + " · Cita "
                + str(self.cita_id)
            )

        # Estado defensivo. La constraint
        # core_pago_destino_xor impide persistirlo.
        return str(
            self.referencia
        )




# =============================================================================
# TNL-IA-BOLSA-BASE-V1
# =============================================================================


class ConfiguracionIA(models.Model):

    PROVEEDOR_OPENAI = "openai"

    PROVEEDOR_CHOICES = [
        (
            PROVEEDOR_OPENAI,
            "OpenAI",
        ),
    ]


    ESTADO_INACTIVA = "inactiva"
    ESTADO_ACTIVA = "activa"
    ESTADO_PAUSADA_AGOTADA = "pausada_agotada"
    ESTADO_ERROR = "error"

    ESTADO_CHOICES = [
        (
            ESTADO_INACTIVA,
            "Inactiva",
        ),
        (
            ESTADO_ACTIVA,
            "Activa",
        ),
        (
            ESTADO_PAUSADA_AGOTADA,
            "Pausada por bolsa agotada",
        ),
        (
            ESTADO_ERROR,
            "Error",
        ),
    ]


    empresa = models.OneToOneField(
        Empresa,
        on_delete=models.CASCADE,
        related_name="configuracion_ia",
    )

    proveedor = models.CharField(
        max_length=30,
        choices=PROVEEDOR_CHOICES,
        default=PROVEEDOR_OPENAI,
    )

    modelo = models.CharField(
        max_length=100,
        blank=True,
        default="",
    )

    habilitada = models.BooleanField(
        default=False,
    )

    estado = models.CharField(
        max_length=30,
        choices=ESTADO_CHOICES,
        default=ESTADO_INACTIVA,
    )

    ultimo_error = models.TextField(
        blank=True,
        default="",
    )

    ultima_actividad_en = models.DateTimeField(
        null=True,
        blank=True,
    )

    creado_en = models.DateTimeField(
        auto_now_add=True,
    )

    actualizado_en = models.DateTimeField(
        auto_now=True,
    )


    class Meta:

        ordering = [
            "empresa_id",
        ]


    def __str__(self):

        return (
            f"IA {self.empresa} "
            f"({self.proveedor})"
        )



class BolsaIA(models.Model):

    ESTADO_ACTIVA = "activa"
    ESTADO_AGOTADA = "agotada"
    ESTADO_CANCELADA = "cancelada"

    ESTADO_CHOICES = [
        (
            ESTADO_ACTIVA,
            "Activa",
        ),
        (
            ESTADO_AGOTADA,
            "Agotada",
        ),
        (
            ESTADO_CANCELADA,
            "Cancelada",
        ),
    ]


    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.CASCADE,
        related_name="bolsas_ia",
    )

    cantidad_palabras = models.PositiveIntegerField(
        default=1000,
    )

    palabras_consumidas = models.PositiveIntegerField(
        default=0,
    )

    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default=ESTADO_ACTIVA,
    )

    activada_en = models.DateTimeField(
        auto_now_add=True,
    )

    agotada_en = models.DateTimeField(
        null=True,
        blank=True,
    )

    notas = models.TextField(
        blank=True,
        default="",
    )

    creado_en = models.DateTimeField(
        auto_now_add=True,
    )

    actualizado_en = models.DateTimeField(
        auto_now=True,
    )


    class Meta:

        ordering = [
            "-activada_en",
            "-id",
        ]

        constraints = [

            models.UniqueConstraint(
                fields=[
                    "empresa",
                ],
                condition=models.Q(
                    estado="activa",
                ),
                name="core_bolsaia_activa_uniq",
            ),

            models.CheckConstraint(
                condition=models.Q(
                    cantidad_palabras__gt=0,
                ),
                name="core_bolsaia_cantidad_ck",
            ),

            models.CheckConstraint(
                condition=models.Q(
                    palabras_consumidas__lte=
                        models.F(
                            "cantidad_palabras"
                        ),
                ),
                name="core_bolsaia_consumo_ck",
            ),
        ]


    @property
    def palabras_disponibles(self):

        return max(
            self.cantidad_palabras
            -
            self.palabras_consumidas,
            0,
        )


    def __str__(self):

        return (
            f"Bolsa IA {self.id} - "
            f"{self.empresa} - "
            f"{self.palabras_disponibles} disponibles"
        )



class ConsumoIA(models.Model):

    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.CASCADE,
        related_name="consumos_ia",
    )

    bolsa = models.ForeignKey(
        BolsaIA,
        on_delete=models.PROTECT,
        related_name="consumos",
    )

    proveedor = models.CharField(
        max_length=30,
        default="openai",
    )

    modelo = models.CharField(
        max_length=100,
        blank=True,
        default="",
    )

    palabras_salida = models.PositiveIntegerField()

    tokens_entrada = models.PositiveIntegerField(
        default=0,
    )

    tokens_salida = models.PositiveIntegerField(
        default=0,
    )

    referencia_conversacion = models.CharField(
        max_length=200,
        blank=True,
        default="",
        db_index=True,
    )

    origen = models.CharField(
        max_length=30,
        blank=True,
        default="",
    )

    creado_en = models.DateTimeField(
        auto_now_add=True,
    )


    class Meta:

        ordering = [
            "-creado_en",
            "-id",
        ]

        indexes = [

            models.Index(
                fields=[
                    "empresa",
                    "creado_en",
                ],
                name="core_consumoia_emp_fecha_idx",
            ),

            models.Index(
                fields=[
                    "bolsa",
                    "creado_en",
                ],
                name="core_consumoia_bol_fecha_idx",
            ),
        ]


    def __str__(self):

        return (
            f"Consumo IA {self.id} - "
            f"{self.palabras_salida} palabras"
        )


# =============================================================================
# TNL-GOOGLE-CALENDAR-MODELS-V1
# =============================================================================


class ConfiguracionGoogleCalendar(models.Model):

    ESTADO_DESCONECTADA = "desconectada"
    ESTADO_CONECTADA = "conectada"
    ESTADO_ERROR = "error"

    ESTADOS = (
        (
            ESTADO_DESCONECTADA,
            "Desconectada",
        ),
        (
            ESTADO_CONECTADA,
            "Conectada",
        ),
        (
            ESTADO_ERROR,
            "Error",
        ),
    )


    empresa = models.OneToOneField(
        "Empresa",
        on_delete=models.CASCADE,
        related_name=
            "configuracion_google_calendar",
    )


    estado_conexion = models.CharField(
        max_length=20,
        choices=ESTADOS,
        default=ESTADO_DESCONECTADA,
        db_index=True,
    )


    habilitada = models.BooleanField(
        default=False
    )


    # Cuenta Google autorizada.
    cuenta_email = models.EmailField(
        blank=True,
        default="",
    )


    # Calendario seleccionado por la empresa.
    calendar_id = models.CharField(
        max_length=512,
        blank=True,
        default="",
    )


    calendar_nombre = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )


    zona_horaria = models.CharField(
        max_length=64,
        default="America/Mexico_City",
    )


    # Los valores almacenados aquí deberán estar
    # cifrados por el servicio OAuth.
    access_token_cifrado = models.TextField(
        blank=True,
        default="",
    )


    refresh_token_cifrado = models.TextField(
        blank=True,
        default="",
    )


    token_expira_en = models.DateTimeField(
        null=True,
        blank=True,
    )


    scopes_concedidos = models.TextField(
        blank=True,
        default="",
    )


    ultimo_error = models.TextField(
        blank=True,
        default="",
    )


    conectado_en = models.DateTimeField(
        null=True,
        blank=True,
    )


    creado_en = models.DateTimeField(
        auto_now_add=True
    )


    actualizado_en = models.DateTimeField(
        auto_now=True
    )


    class Meta:

        ordering = (
            "empresa_id",
        )


    def __str__(self):

        return (
            f"Google Calendar - "
            f"{self.empresa}"
        )



class Cita(models.Model):

    ESTADO_PENDIENTE_CONFIRMACION = (
        "pendiente_confirmacion"
    )

    ESTADO_PROGRAMADA = "programada"
    ESTADO_CANCELADA = "cancelada"
    ESTADO_COMPLETADA = "completada"
    ESTADO_ERROR = "error"


    ESTADOS = (
        (
            ESTADO_PENDIENTE_CONFIRMACION,
            "Pendiente de confirmación",
        ),
        (
            ESTADO_PROGRAMADA,
            "Programada",
        ),
        (
            ESTADO_CANCELADA,
            "Cancelada",
        ),
        (
            ESTADO_COMPLETADA,
            "Completada",
        ),
        (
            ESTADO_ERROR,
            "Error",
        ),
    )


    ORIGEN_CHATBOT = "chatbot"
    ORIGEN_ADMIN = "admin"
    ORIGEN_API = "api"


    ORIGENES = (
        (
            ORIGEN_CHATBOT,
            "Chatbot",
        ),
        (
            ORIGEN_ADMIN,
            "Administración",
        ),
        (
            ORIGEN_API,
            "API",
        ),
    )


    empresa = models.ForeignKey(
        "Empresa",
        on_delete=models.CASCADE,
        related_name="citas",
    )


    bot = models.ForeignKey(
        "Bot",
        on_delete=models.SET_NULL,
        related_name="citas",
        null=True,
        blank=True,
    )


    estado = models.CharField(
        max_length=32,
        choices=ESTADOS,
        default=
            ESTADO_PENDIENTE_CONFIRMACION,
        db_index=True,
    )


    origen = models.CharField(
        max_length=20,
        choices=ORIGENES,
        default=ORIGEN_CHATBOT,
    )


    nombre_cliente = models.CharField(
        max_length=200,
        blank=True,
        default="",
    )


    telefono_cliente = models.CharField(
        max_length=50,
        blank=True,
        default="",
    )


    email_cliente = models.EmailField(
        blank=True,
        default="",
    )


    # TNL-CITA-SERVICIO-PRODUCTO-V1
    servicio_producto = models.ForeignKey(
        Producto,
        on_delete=models.SET_NULL,
        related_name="citas_servicio",
        null=True,
        blank=True,
    )

    servicio = models.CharField(
        max_length=255,
        blank=True,
        default="",
    )


    titulo = models.CharField(
        max_length=255,
    )


    descripcion = models.TextField(
        blank=True,
        default="",
    )


    inicio = models.DateTimeField()


    fin = models.DateTimeField()


    zona_horaria = models.CharField(
        max_length=64,
        default="America/Mexico_City",
    )


    # Copia del calendario utilizado para mantener
    # trazabilidad incluso si la empresa cambia
    # posteriormente su calendario principal.
    google_calendar_id = models.CharField(
        max_length=512,
        blank=True,
        default="",
    )


    google_event_id = models.CharField(
        max_length=512,
        blank=True,
        default="",
    )


    google_event_etag = models.CharField(
        max_length=512,
        blank=True,
        default="",
    )


    google_html_link = models.URLField(
        max_length=1000,
        blank=True,
        default="",
    )


    # TNL-CITA-PAYMENT-SNAPSHOT-V1
    politica_pago_aplicada = models.CharField(
        max_length=30,
        choices=(
            (
                "sin_pago",
                "No requiere pago",
            ),
            (
                "anticipo",
                "Requiere anticipo",
            ),
            (
                "pago_completo",
                "Requiere pago completo",
            ),
        ),
        default="sin_pago",
    )

    importe_total = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
    )

    # TNL-CITA-CURRENCY-SNAPSHOT-V1
    moneda = models.CharField(
        max_length=3,
        blank=True,
        default="",
    )


    porcentaje_pago_requerido = (
        models.DecimalField(
            max_digits=5,
            decimal_places=2,
            default=0,
        )
    )

    importe_pago_requerido = (
        models.DecimalField(
            max_digits=14,
            decimal_places=2,
            default=0,
        )
    )

    importe_pagado = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
    )

    retencion_pago_hasta = (
        models.DateTimeField(
            null=True,
            blank=True,
        )
    )

    pago_confirmado_en = (
        models.DateTimeField(
            null=True,
            blank=True,
        )
    )

    referencia_conversacion = models.CharField(
        max_length=255,
        blank=True,
        default="",
        db_index=True,
    )


    confirmada_en = models.DateTimeField(
        null=True,
        blank=True,
    )


    cancelada_en = models.DateTimeField(
        null=True,
        blank=True,
    )


    google_sincronizada_en = models.DateTimeField(
        null=True,
        blank=True,
    )


    ultimo_error = models.TextField(
        blank=True,
        default="",
    )


    creado_en = models.DateTimeField(
        auto_now_add=True
    )


    actualizado_en = models.DateTimeField(
        auto_now=True
    )


    class Meta:

        ordering = (
            "-inicio",
            "-id",
        )

        constraints = (

            models.CheckConstraint(
                condition=models.Q(
                    fin__gt=
                        models.F(
                            "inicio"
                        )
                ),
                name=
                    "core_cita_fin_gt_inicio",
            ),

            models.UniqueConstraint(
                fields=(
                    "empresa",
                    "google_event_id",
                ),
                condition=~models.Q(
                    google_event_id=""
                ),
                name=
                    "core_cita_google_event_uniq",
            ),

        )

        indexes = (

            models.Index(
                fields=(
                    "empresa",
                    "inicio",
                ),
                name=
                    "core_cita_emp_inicio_idx",
            ),

            models.Index(
                fields=(
                    "empresa",
                    "estado",
                    "inicio",
                ),
                name=
                    "core_cita_emp_est_ini_idx",
            ),

        )


    def __str__(self):

        return (
            f"{self.titulo} - "
            f"{self.inicio}"
        )


# =============================================================================
# TNL-AGENDA-HORARIOS-V1
# Configuración comercial de agenda por empresa.
#
# No representa ocupación de Google Calendar.
# Define CUÁNDO una empresa ofrece citas.
#
# La ocupación real continúa siendo autoridad de Google FreeBusy.
# =============================================================================


class ConfiguracionAgenda(models.Model):

    empresa = models.OneToOneField(
        Empresa,
        on_delete=models.CASCADE,
        related_name="configuracion_agenda",
    )

    # Conserva el comportamiento histórico del
    # flujo Typebot actual: 30 minutos si el
    # cliente no especifica otra duración.
    duracion_predeterminada_minutos = (
        models.PositiveSmallIntegerField(
            default=30,
        )
    )

    # Separación entre horas candidatas.
    # Ejemplo: 30 genera 09:00, 09:30, 10:00...
    intervalo_slots_minutos = (
        models.PositiveSmallIntegerField(
            default=30,
        )
    )

    # 0 preserva el comportamiento actual:
    # permite una cita inmediata si Google está libre.
    anticipacion_minima_minutos = (
        models.PositiveIntegerField(
            default=0,
        )
    )

    # TNL-AGENDA-PAYMENT-POLICY-V1
    POLITICA_SIN_PAGO = "sin_pago"
    POLITICA_ANTICIPO = "anticipo"
    POLITICA_PAGO_COMPLETO = "pago_completo"

    POLITICAS_PAGO = (
        (
            POLITICA_SIN_PAGO,
            "No requiere pago",
        ),
        (
            POLITICA_ANTICIPO,
            "Requiere anticipo",
        ),
        (
            POLITICA_PAGO_COMPLETO,
            "Requiere pago completo",
        ),
    )

    politica_pago_cita = models.CharField(
        max_length=30,
        choices=POLITICAS_PAGO,
        default=POLITICA_SIN_PAGO,
    )

    porcentaje_anticipo = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
    )

    retencion_pago_minutos = (
        models.PositiveSmallIntegerField(
            default=15,
        )
    )

    creado_en = models.DateTimeField(
        auto_now_add=True,
    )

    actualizado_en = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        verbose_name = (
            "Configuración de agenda"
        )

        verbose_name_plural = (
            "Configuraciones de agenda"
        )

    def __str__(self):
        return (
            f"Agenda - {self.empresa}"
        )


class HorarioAtencion(models.Model):

    DIA_LUNES = 0
    DIA_MARTES = 1
    DIA_MIERCOLES = 2
    DIA_JUEVES = 3
    DIA_VIERNES = 4
    DIA_SABADO = 5
    DIA_DOMINGO = 6

    DIAS_SEMANA = (
        (DIA_LUNES, "Lunes"),
        (DIA_MARTES, "Martes"),
        (DIA_MIERCOLES, "Miércoles"),
        (DIA_JUEVES, "Jueves"),
        (DIA_VIERNES, "Viernes"),
        (DIA_SABADO, "Sábado"),
        (DIA_DOMINGO, "Domingo"),
    )

    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.CASCADE,
        related_name="horarios_atencion",
    )

    dia_semana = (
        models.PositiveSmallIntegerField(
            choices=DIAS_SEMANA,
        )
    )

    hora_inicio = models.TimeField()

    hora_fin = models.TimeField()

    activo = models.BooleanField(
        default=True,
    )

    creado_en = models.DateTimeField(
        auto_now_add=True,
    )

    actualizado_en = models.DateTimeField(
        auto_now=True,
    )

    class Meta:

        verbose_name = (
            "Horario de atención"
        )

        verbose_name_plural = (
            "Horarios de atención"
        )

        ordering = (
            "empresa_id",
            "dia_semana",
            "hora_inicio",
        )

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "empresa",
                    "dia_semana",
                    "hora_inicio",
                    "hora_fin",
                ],
                name=
                    "tnl_agenda_horario_unico",
            ),
        ]

    def clean(self):

        from django.core.exceptions import (
            ValidationError,
        )

        super().clean()

        if (
            self.hora_inicio
            and
            self.hora_fin
            and
            self.hora_fin
            <=
            self.hora_inicio
        ):

            raise ValidationError(
                {
                    "hora_fin":
                        (
                            "La hora final debe ser "
                            "posterior a la hora inicial."
                        )
                }
            )

    def __str__(self):

        return (
            f"{self.empresa} - "
            f"{self.get_dia_semana_display()} "
            f"{self.hora_inicio:%H:%M}-"
            f"{self.hora_fin:%H:%M}"
        )


# =============================================================================
# TNL-TERMINOS-ACEPTACION-MODEL-V1
#
# Evidencia auditable de aceptación de Términos y Condiciones.
#
# Una aceptación corresponde a:
#
#     Empresa + versión de términos
#
# No se utiliza un simple BooleanField porque necesitamos preservar:
# - quién aceptó;
# - qué versión aceptó;
# - cuál era el contenido;
# - hash del contenido;
# - cuándo;
# - desde qué IP/navegador;
# - qué integración originó la primera aceptación.
# =============================================================================


class AceptacionTerminos(
    models.Model
):

    class OrigenVinculacion(
        models.TextChoices
    ):

        WHATSAPP = (
            "whatsapp",
            "WhatsApp",
        )

        GOOGLE_CALENDAR = (
            "google_calendar",
            "Google Calendar",
        )

        MERCADOPAGO = (
            "mercadopago",
            "Mercado Pago",
        )


    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.CASCADE,
        related_name=
            "aceptaciones_terminos",
    )


    perfil_usuario = models.ForeignKey(
        PerfilUsuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name=
            "aceptaciones_terminos",
    )


    version = models.CharField(
        max_length=40,
    )


    documento_sha256 = models.CharField(
        max_length=64,
    )


    contenido_snapshot = models.TextField()


    origen_vinculacion = models.CharField(
        max_length=30,
        choices=
            OrigenVinculacion.choices,
    )


    usuario_username_snapshot = (
        models.CharField(
            max_length=150,
            blank=True,
            default="",
        )
    )


    usuario_email_snapshot = (
        models.EmailField(
            max_length=254,
            blank=True,
            default="",
        )
    )


    ip_aceptacion = (
        models.GenericIPAddressField(
            null=True,
            blank=True,
        )
    )


    user_agent = models.TextField(
        blank=True,
        default="",
    )


    aceptado_en = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
    )


    class Meta:

        ordering = (
            "-aceptado_en",
            "-id",
        )

        verbose_name = (
            "Aceptación de términos"
        )

        verbose_name_plural = (
            "Aceptaciones de términos"
        )

        constraints = [

            models.UniqueConstraint(
                fields=(
                    "empresa",
                    "version",
                ),
                name=
                    "tnl_terms_empresa_version_unique",
            ),

        ]

        indexes = [

            models.Index(
                fields=(
                    "empresa",
                    "version",
                ),
                name=
                    "tnl_terms_emp_ver_idx",
            ),

        ]


    def __str__(
        self
    ):

        return (
            f"{self.empresa} · "
            f"Términos {self.version}"
        )
