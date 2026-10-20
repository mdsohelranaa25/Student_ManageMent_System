from django.db import models

SEMESTER_CHOICES = [(i, f"{i}") for i in range(1, 9)]

DAY_CHOICES = [
    ("sun", "Sunday"),
    ("mon", "Monday"),
    ("tue", "Tuesday"),
    ("wed", "Wednesday"),
    ("thu", "Thursday"),
]


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


class Routine(models.Model):
    batch = models.ForeignKey("Batch", on_delete=models.CASCADE, related_name="routines")
    day = models.CharField(max_length=3, choices=DAY_CHOICES)
    time_slot = models.ForeignKey("TimeSlot", on_delete=models.CASCADE)
    room = models.ForeignKey("Room", on_delete=models.CASCADE)
    course = models.ForeignKey("Course", on_delete=models.CASCADE)

    class Meta:
        ordering = ["day", "time_slot__order"]
        constraints = [
            models.UniqueConstraint(fields=["batch", "day", "time_slot"], name="batch_day_slot_unique"),
            models.UniqueConstraint(fields=["room", "day", "time_slot"], name="room_day_slot_unique"),
        ]

    def __str__(self):
        return f"{self.batch} - {self.get_day_display()} {self.time_slot} - {self.course.code}"
    
class ExamRoutine(models.Model):
    course = models.ForeignKey("Course", on_delete=models.CASCADE, related_name="exams")
    date = models.DateField()
    time_slot = models.ForeignKey("TimeSlot", on_delete=models.CASCADE)
    room = models.ForeignKey("Room", on_delete=models.CASCADE)
    created_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL,
        limit_choices_to={"role__in": ["teacher", "admin"]},
    )

    class Meta:
        ordering = ["date", "time_slot__order"]
        constraints = [
            models.UniqueConstraint(fields=["room", "date", "time_slot"], name="exam_room_date_slot_unique"),
        ]

    def __str__(self):
        return f"{self.course.code} exam - {self.date} {self.time_slot}"   
class Announcement(models.Model):
    teacher = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE,
        limit_choices_to={"role": "teacher"}, related_name="announcements",
    )
    course = models.ForeignKey("Course", on_delete=models.CASCADE)
    batch = models.ForeignKey("Batch", on_delete=models.CASCADE)
    text = models.TextField()
    image = models.ImageField(upload_to="announcements/", null=True, blank=True)
    attachment = models.FileField(upload_to="announcements/files/", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.course.code} - {self.batch} - {self.created_at:%d %b %Y}"


class AnnouncementComment(models.Model):
    announcement = models.ForeignKey(Announcement, on_delete=models.CASCADE, related_name="comments")
    student = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, limit_choices_to={"role": "student"},
    )
    text = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.student.username}: {self.text[:30]}"
class SemesterResult(models.Model):
    student = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE,
        limit_choices_to={"role": "student"}, related_name="semester_results",
    )
    semester = models.PositiveSmallIntegerField(choices=SEMESTER_CHOICES)
    gpa = models.DecimalField(max_digits=3, decimal_places=2)
    cgpa = models.DecimalField(max_digits=3, decimal_places=2)
    published_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["semester"]
        constraints = [
            models.UniqueConstraint(fields=["student", "semester"], name="one_result_per_student_semester"),
        ]

    def __str__(self):
        return f"{self.student.username} - Semester {self.semester} - GPA {self.gpa}"


class CourseGrade(models.Model):
    semester_result = models.ForeignKey(SemesterResult, on_delete=models.CASCADE, related_name="course_grades")
    course = models.ForeignKey("Course", on_delete=models.CASCADE)
    grade = models.CharField(max_length=5)
    grade_point = models.DecimalField(max_digits=3, decimal_places=2)

    def __str__(self):
        return f"{self.course.code} - {self.grade}"