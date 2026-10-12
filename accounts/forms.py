from django import forms

from .models import Application, User


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

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("An account already exists with this email.")
        return email


class ForgotPasswordForm(forms.Form):
    identifier = forms.CharField(
        label="Username or Email",
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Your username or Gmail"}),
    )


class SetNewPasswordForm(forms.Form):
    new_password = forms.CharField(
        label="New Password",
        widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "At least 8 characters"}),
    )
    confirm_password = forms.CharField(
        label="Confirm Password",
        widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "Retype password"}),
    )

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("new_password")
        p2 = cleaned.get("confirm_password")
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError("Passwords do not match.")
        if p1 and len(p1) < 8:
            raise forms.ValidationError("Password must be at least 8 characters.")
        return cleaned


class ProfilePictureForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["profile_picture"]
        widgets = {
            "profile_picture": forms.FileInput(attrs={"accept": "image/*"}),
        }


        