from django import forms


class DataAttributeSelect(forms.Select):
    """
    Select whose <option> elements carry extra ``data-*`` attributes taken from
    the model instance, so page scripts can read prices or rates without an
    extra request. Example: ``DataAttributeSelect(data_attrs={"price": "price"})``
    renders ``<option data-price="560.00">``.
    """

    def __init__(self, attrs=None, choices=(), data_attrs=None):
        super().__init__(attrs, choices)
        self.data_attrs = data_attrs or {}

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)
        instance = getattr(value, "instance", None)
        if instance is not None:
            for attr_name, model_attr in self.data_attrs.items():
                option["attrs"][f"data-{attr_name}"] = str(getattr(instance, model_attr))
        return option


class DataAttributeSelectMultiple(DataAttributeSelect, forms.SelectMultiple):
    """Multi-select variant, e.g. taxes with ``data-rate``."""

    allow_multiple_selected = True
