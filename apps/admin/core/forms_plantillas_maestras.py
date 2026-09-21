from django import forms

from .models import (
    PlantillaMaestra,
    PlantillaVariableMaestra,
)


class PlantillaMaestraForm(forms.ModelForm):

    class Meta:
        model = PlantillaMaestra

        fields = [
            "nombre",
            "slug",
            "tipo",
            "version",
            "descripcion",
            "configuracion",
            "estado",
            "activa",
        ]

        widgets = {
            "nombre": forms.TextInput(
                attrs={
                    "class": "pm-input",
                    "placeholder": "Ej. Restaurante Base",
                }
            ),
            "slug": forms.TextInput(
                attrs={
                    "class": "pm-input",
                    "placeholder": "restaurante-base",
                }
            ),
            "tipo": forms.Select(
                attrs={"class": "pm-input"}
            ),
            "version": forms.NumberInput(
                attrs={
                    "class": "pm-input",
                    "min": "1",
                }
            ),
            "descripcion": forms.Textarea(
                attrs={
                    "class": "pm-input",
                    "rows": 4,
                }
            ),
            "configuracion": forms.Textarea(
                attrs={
                    "class": "pm-input pm-code",
                    "rows": 10,
                    "spellcheck": "false",
                }
            ),
            "estado": forms.Select(
                attrs={"class": "pm-input"}
            ),
            "activa": forms.CheckboxInput(
                attrs={"class": "pm-check"}
            ),
        }


class PlantillaVariableMaestraForm(forms.ModelForm):

    class Meta:
        model = PlantillaVariableMaestra

        fields = [
            "clave",
            "nombre",
            "tipo_dato",
            "valor_default",
            "requerida",
            "descripcion",
            "orden",
            "activa",
        ]

        widgets = {
            "clave": forms.TextInput(
                attrs={"class": "pm-input"}
            ),
            "nombre": forms.TextInput(
                attrs={"class": "pm-input"}
            ),
            "tipo_dato": forms.Select(
                attrs={"class": "pm-input"}
            ),
            "valor_default": forms.Textarea(
                attrs={
                    "class": "pm-input",
                    "rows": 3,
                }
            ),
            "requerida": forms.CheckboxInput(
                attrs={"class": "pm-check"}
            ),
            "descripcion": forms.Textarea(
                attrs={
                    "class": "pm-input",
                    "rows": 3,
                }
            ),
            "orden": forms.NumberInput(
                attrs={
                    "class": "pm-input",
                    "min": "0",
                }
            ),
            "activa": forms.CheckboxInput(
                attrs={"class": "pm-check"}
            ),
        }
