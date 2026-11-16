import re
from decimal import Decimal
from django.db import models

SEMESTER_CHOICES = [(i, f"{i}") for i in range(1, 9)]

DAY_CHOICES = [
    ("sun", "Sunday"),
    ("mon", "Monday"),
    ("tue", "Tuesday"),
    ("wed", "Wednesday"),
    ("thu", "Thursday"),
]

PASTEL_PALETTES = [
    {"bg": "#E0F2FE", "text": "#0369A1", "border": "#BAE6FD", "accent": "#0284C7"},  # Sky
    {"bg": "#FEF3C7", "text": "#B45309", "border": "#FDE68A", "accent": "#D97706"},  # Amber
    {"bg": "#DCFCE7", "text": "#15803D", "border": "#BBF7D0", "accent": "#16A34A"},  # Emerald
    {"bg": "#F3E8FF", "text": "#7E22CE", "border": "#E9D5FF", "accent": "#9333EA"},  # Purple
    {"bg": "#FFE4E6", "text": "#BE123C", "border": "#FECDD3", "accent": "#E11D48"},  # Rose
    {"bg": "#E0E7FF", "text": "#4338CA", "border": "#C7D2FE", "accent": "#4F46E5"},  # Indigo
    {"bg": "#CCFBF1", "text": "#0F766E", "border": "#99F6E4", "accent": "#0D9488"},  # Teal
    {"bg": "#FFEDD5", "text": "#C2410C", "border": "#FED7AA", "accent": "#EA580C"},  # Orange
    {"bg": "#FCE7F3", "text": "#9D174D", "border": "#FBCFE8", "accent": "#DB2777"},  # Pink
    {"bg": "#EDE9FE", "text": "#5B21B6", "border": "#DDD6FE", "accent": "#7C3AED"},  # Violet
    {"bg": "#E2E8F0", "text": "#334155", "border": "#CBD5E1", "accent": "#475569"},  # Slate
    {"bg": "#FEF9C3", "text": "#A16207", "border": "#FEF08A", "accent": "#CA8A04"},  # Yellow
    {"bg": "#ECFDF5", "text": "#047857", "border": "#A7F3D0", "accent": "#059669"},  # Mint
    {"bg": "#FEE2E2", "text": "#B91C1C", "border": "#FECACA", "accent": "#DC2626"},  # Light Red
    {"bg": "#CFFAFE", "text": "#0E7490", "border": "#A5F3FC", "accent": "#0891B2"},  # Cyan
    {"bg": "#FAE8FF", "text": "#86198F", "border": "#F5D0FE", "accent": "#A21CAF"},  # Fuchsia
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
    color = models.CharField(
        max_length=50, blank=True, default="",
        help_text="Custom hex color or light color preset for schedule grid view"
    )

    class Meta:
        ordering = ["semester", "code"]

    def __str__(self):
        return f"{self.code} - {self.title}"

    @property
    def course_type(self):
        title_lower = (self.title or "").lower()
        code_lower = (self.code or "").lower()
        if "viva" in title_lower or "viva" in code_lower:
            return "viva"
        if "lab" in title_lower or "sessional" in title_lower or "practical" in title_lower or float(self.credit) <= 1.5:
            return "lab"
        return "theory"

    @property
    def incourse_max(self):
        t = self.course_type
        if t == "viva":
            return 0
        elif t == "lab":
            return 60
        return 40

    @property
    def final_max(self):
        t = self.course_type
        if t == "viva":
            return 100
        elif t == "lab":
            return 40
        return 60

    def get_color_info(self):
        if self.color:
            return {
                "bg": self.color,
                "text": "#0F172A",
                "border": "rgba(0, 0, 0, 0.12)",
                "accent": "#0F172A"
            }
        clean = re.sub(r"[^A-Za-z0-9]", "", self.code or str(self.id))
        hash_val = sum(ord(c) * (i + 1) for i, c in enumerate(clean))
        return PASTEL_PALETTES[hash_val % len(PASTEL_PALETTES)]

    @property
    def color_bg(self):
        return self.get_color_info()["bg"]

    @property
    def color_text(self):
        return self.get_color_info()["text"]

    @property
    def color_border(self):
        return self.get_color_info()["border"]

    @property
    def color_accent(self):
        return self.get_color_info()["accent"]

    @property
    def routine_style(self):
        info = self.get_color_info()
        return f"background-color: {info['bg']}; border-color: {info['border']}; border-left: 4px solid {info['accent']}; color: {info['text']};"


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
    incourse_marks = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    final_marks = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    total_marks = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    def __str__(self):
        return f"{self.course.code} - {self.grade}"


class StudentCourseMark(models.Model):
    """
    Holds draft and published subject marks before and after final semester publication.
    Enables two-stage upload:
      1. Incourse Marks (by Batch + Course Code + Roll)
      2. Final Marks (by Course Code + Registration Number)
    """
    student = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        limit_choices_to={"role": "student"},
        related_name="course_marks",
    )
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="student_marks")
    batch = models.ForeignKey(Batch, on_delete=models.CASCADE, related_name="course_marks")
    semester = models.PositiveSmallIntegerField(choices=SEMESTER_CHOICES)

    incourse_marks = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    final_marks = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    total_marks = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    grade = models.CharField(max_length=5, blank=True)
    grade_point = models.DecimalField(max_digits=3, decimal_places=2, null=True, blank=True)

    is_incourse_published = models.BooleanField(default=False)
    is_final_published = models.BooleanField(default=False)

    incourse_uploaded_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="incourse_uploads"
    )
    final_uploaded_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="final_uploads"
    )
    incourse_uploaded_at = models.DateTimeField(null=True, blank=True)
    final_uploaded_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["batch", "semester", "student__roll", "course__code"]
        constraints = [
            models.UniqueConstraint(fields=["student", "course"], name="unique_student_course_mark"),
        ]

    def save(self, *args, **kwargs):
        from .marks_utils import calculate_ugc_grade
        if self.course.course_type == "viva":
            if self.final_marks is not None:
                self.incourse_marks = Decimal("0.00")
                self.total_marks = self.final_marks
                self.grade, self.grade_point = calculate_ugc_grade(self.total_marks)
        elif self.incourse_marks is not None and self.final_marks is not None:
            self.total_marks = self.incourse_marks + self.final_marks
            self.grade, self.grade_point = calculate_ugc_grade(self.total_marks)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.student.username} - {self.course.code}: In {self.incourse_marks}, Fin {self.final_marks}"

class OfficialNotice(models.Model):
    """Public department notices displayed on the home page for everyone."""
    title = models.CharField(max_length=200, help_text="Notice headline")
    content = models.TextField(help_text="Detailed notice text")
    attachment = models.FileField(upload_to="official_notices/", null=True, blank=True, help_text="PDF or document attachment")
    is_pinned = models.BooleanField(default=False, help_text="Pin to the top of notice board")
    is_active = models.BooleanField(default=True, help_text="Show on home page")
    created_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        limit_choices_to={"role": "admin"},
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_pinned", "-created_at"]

    def __str__(self):
        return self.title
