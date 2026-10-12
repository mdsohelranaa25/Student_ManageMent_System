from django.db import models

SEMESTER_CHOICES = [(i, f"{i}") for i in range(1, 9)]


class Batch(models.Model):
    """A batch is identified by its admission year, e.g. 2023-24."""

    name = models.CharField(
        max_length=20, unique=True, help_text="Admission year, e.g. 2023-24"
    )
    is_running = models.BooleanField(
        default=True, help_text="Untick when this batch has finished."
    )
    current_semester = models.PositiveSmallIntegerField(
        choices=SEMESTER_CHOICES,
        null=True,
        blank=True,
        help_text="Which semester (1-8) this batch is currently taking.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-name"]
        verbose_name_plural = "batches"

    def __str__(self):
        return self.name


class Course(models.Model):
    code = models.CharField(max_length=20, unique=True)
    title = models.CharField(max_length=150)
    credit = models.DecimalField(max_digits=3, decimal_places=1)
    semester = models.PositiveSmallIntegerField(choices=SEMESTER_CHOICES)
    teacher = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        limit_choices_to={"role": "teacher"},
        related_name="courses_taught",
    )

    class Meta:
        ordering = ["semester", "code"]

    def __str__(self):
        return f"{self.code} - {self.title}"


class Room(models.Model):
    name = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.name


class TimeSlot(models.Model):
    label = models.CharField(max_length=20, unique=True, help_text="e.g. 8:30-9:50")
    order = models.PositiveSmallIntegerField(
        unique=True, help_text="1 to 5, for sorting in the day's order"
    )

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return self.label