from django.db import models


class Attendance(models.Model):
    STATUS_CHOICES = [("P", "Present"), ("A", "Absent")]

    student = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE,
        limit_choices_to={"role": "student"}, related_name="attendance_records",
    )
    course = models.ForeignKey("academics.Course", on_delete=models.CASCADE)
    date = models.DateField()
    status = models.CharField(max_length=1, choices=STATUS_CHOICES, default="P")
    marked_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="attendance_marked", limit_choices_to={"role__in": ["teacher", "admin"]},
    )

    class Meta:
        ordering = ["-date"]
        constraints = [
            models.UniqueConstraint(fields=["student", "course", "date"], name="attendance_once_per_day"),
        ]

    def __str__(self):
        return f"{self.student.username} - {self.course.code} - {self.date} - {self.get_status_display()}"