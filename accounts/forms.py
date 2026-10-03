from django import forms

from .models import Application


class ApplicationForm(forms.ModelForm):
    class Meta:
        model = Application
        fields = ["name", "email", "phone", "batch"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Full name"}),
            "email": forms.EmailInput(attrs={"class": "form-control", "placeholder": "you@gmail.com"}),
            "phone": forms.TextInput(attrs={"class": "form-control", "placeholder": "01XXXXXXXXX"}),
            "batch": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, role=None, **kwargs):
        super().__init__(*args, **kwargs)
        if role == "teacher":
            # Teachers don't have a batch, so remove that field entirely
            self.fields.pop("batch")
        else:
            self.fields["batch"].required = True

    def clean_phone(self):
        phone = self.cleaned_data["phone"].strip()
        if not phone.isdigit():
            raise forms.ValidationError("Phone number must contain digits only.")
        if len(phone) != 11:
            raise forms.ValidationError("Phone number must be exactly 11 digits.")
        if not phone.startswith("01"):
            raise forms.ValidationError("Phone number must start with 01.")
        return phone