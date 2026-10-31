"""
Form helpers shared by every app.

``BootstrapFormMixin`` decorates widgets with the right Bootstrap classes so a
single ``partials/_form_fields.html`` include renders any form consistently.
"""

from django import forms


class BootstrapFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, (forms.CheckboxInput, forms.CheckboxSelectMultiple, forms.RadioSelect)):
                css = "form-check-input"
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                css = "form-select"
            else:
                css = "form-control"
            existing = widget.attrs.get("class", "")
            widget.attrs["class"] = f"{existing} {css}".strip()

            if isinstance(widget, forms.Textarea):
                widget.attrs.setdefault("rows", 3)
            elif isinstance(widget, forms.DateTimeInput):
                widget.input_type = "datetime-local"
                widget.format = "%Y-%m-%dT%H:%M"
            elif isinstance(widget, forms.DateInput):
                widget.input_type = "date"
                widget.format = "%Y-%m-%d"

            if field.required:
                widget.attrs.setdefault("required", True)


class DateInput(forms.DateInput):
    input_type = "date"

    def __init__(self, **kwargs):
        kwargs.setdefault("format", "%Y-%m-%d")
        super().__init__(**kwargs)
