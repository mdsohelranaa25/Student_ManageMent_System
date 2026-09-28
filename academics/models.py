from django.db import models


class Batch(models.Model):
    """A batch is identified by its admission year, e.g. 2023-24."""

    name = models.CharField(
        max_length=20, unique=True, help_text="Admission year, e.g. 2023-24"
    )
    is_running = models.BooleanField(
        default=True, help_text="Untick when this batch has finished."
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-name"]
        verbose_name_plural = "batches"

    def __str__(self):
        return self.name