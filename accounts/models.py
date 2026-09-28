from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """
    One table for everyone (admin, teacher, student).
    `username` is the unique login ID that the system generates on approval.
    """

    ROLE_CHOICES = [
        ("admin", "Admin"),
        ("teacher", "Teacher"),
        ("student", "Student"),
    ]

    email = models.EmailField(unique=True)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default="student")
    phone = models.CharField(max_length=20, blank=True)
    # Only students have a batch. Teachers/admins leave it empty.
    batch = models.ForeignKey(
        "academics.Batch",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="students",
    )

    def save(self, *args, **kwargs):
        # accounts made with `createsuperuser` are always admins
        if self.is_superuser:
            self.role = "admin"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"


class Application(models.Model):
    """A student/teacher application waiting for the admin's decision."""

    ROLE_CHOICES = [("student", "Student"), ("teacher", "Teacher")]
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    ]

    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    name = models.CharField(max_length=150)
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    # students only
    batch = models.ForeignKey(
        "academics.Batch", null=True, blank=True, on_delete=models.SET_NULL
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    # the account created when the admin approves
    user = models.OneToOneField(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="application"
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.role}, {self.status})"


class PasswordResetCode(models.Model):
    """6-digit forgot-password code. Stored hashed, expires, limited attempts."""

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    code_hash = models.CharField(max_length=128)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Reset code for {self.user.username}"