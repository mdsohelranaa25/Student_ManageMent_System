import csv
import io
import re
from decimal import Decimal, ROUND_HALF_UP
import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from django.db.models import Q
from django.utils import timezone

from accounts.models import User
from .models import Batch, Course, CourseGrade, SemesterResult, StudentCourseMark


# Bangladesh University (UGC) Standard Grading Scale
GRADE_SCALE = [
    ("A+", Decimal("4.00")),
    ("A",  Decimal("3.75")),
    ("A-", Decimal("3.50")),
    ("B+", Decimal("3.25")),
    ("B",  Decimal("3.00")),
    ("B-", Decimal("2.75")),
    ("C+", Decimal("2.50")),
    ("C",  Decimal("2.25")),
    ("D",  Decimal("2.00")),
    ("F",  Decimal("0.00")),
]
GRADE_POINT_MAP = dict(GRADE_SCALE)


def calculate_ugc_grade(total_marks):
    """
    Given total_marks (out of 100, Decimal or float),
    returns (letter_grade, grade_point).
    """
    if total_marks is None:
        return "", None
    try:
        val = float(total_marks)
    except (ValueError, TypeError):
        return "", None

    # UGC standard boundaries
    if val >= 80.0:
        return "A+", Decimal("4.00")
    elif val >= 75.0:
        return "A", Decimal("3.75")
    elif val >= 70.0:
        return "A-", Decimal("3.50")
    elif val >= 65.0:
        return "B+", Decimal("3.25")
    elif val >= 60.0:
        return "B", Decimal("3.00")
    elif val >= 55.0:
        return "B-", Decimal("2.75")
    elif val >= 50.0:
        return "C+", Decimal("2.50")
    elif val >= 45.0:
        return "C", Decimal("2.25")
    elif val >= 40.0:
        return "D", Decimal("2.00")
    else:
        return "F", Decimal("0.00")


def normalize_code(code_str):
    """
    Strips non-alphanumeric chars and converts to uppercase.
    'ICT 1101', 'ict-1101', ' ICT 1101 ' -> 'ICT1101'
    """
    if not code_str:
        return ""
    return re.sub(r"[^A-Za-z0-9]", "", str(code_str)).upper()


def find_course_by_code(code_str):
    """
    Finds a Course object matching code_str case-insensitively,
    ignoring whitespace and punctuation.
    """
    if not code_str:
        return None
    raw = str(code_str).strip()
    # 1. Exact match
    c = Course.objects.filter(code__iexact=raw).first()
    if c:
        return c
    # 2. Normalized match
    norm = normalize_code(raw)
    for c in Course.objects.all():
        if normalize_code(c.code) == norm:
            return c
    return None


def resolve_semester_from_course_code(code_str):
    """
    Decodes semester automatically from course code digits:
    First 2 digits = Year (1-4) and Semester in that year (1-2).
    Semester = (Year - 1) * 2 + Semester.
    E.g.
      11 -> Year 1, Sem 1 -> Semester 1
      12 -> Year 1, Sem 2 -> Semester 2
      21 -> Year 2, Sem 1 -> Semester 3
      22 -> Year 2, Sem 2 -> Semester 4
      31 -> Year 3, Sem 1 -> Semester 5
      32 -> Year 3, Sem 2 -> Semester 6
      41 -> Year 4, Sem 1 -> Semester 7
      42 -> Year 4, Sem 2 -> Semester 8
    """
    if not code_str:
        return None
    digits = re.findall(r"\d+", str(code_str))
    if digits and len(digits[0]) >= 2:
        try:
            y, s = int(digits[0][0]), int(digits[0][1])
            if 1 <= y <= 4 and 1 <= s <= 2:
                return (y - 1) * 2 + s
        except ValueError:
            pass
    return None


def normalize_batch_name(batch_str):
    if not batch_str:
        return ""
    return re.sub(r"[^0-9]", "", str(batch_str))


def find_batch_by_name(batch_str):
    """
    Finds a Batch object matching name flexibly:
    '2023-24', ' 2023 - 24 ', '2023-2024', 'Batch 2023-24'.
    """
    if not batch_str:
        return None
    raw = str(batch_str).strip()
    # 1. Exact or case-insensitive
    b = Batch.objects.filter(name__iexact=raw).first()
    if b:
        return b
    # 2. Whitespace-stripped
    cleaned = re.sub(r"\s+", "", raw)
    for b in Batch.objects.all():
        if re.sub(r"\s+", "", b.name) == cleaned:
            return b
    # 3. Look for 4-digit start year e.g. '2023' in '2023-24'
    digits = re.findall(r"\d{4}", raw)
    if digits:
        year = digits[0]
        b = Batch.objects.filter(name__startswith=year).first()
        if b:
            return b
    return None


def resolve_batch_from_reg(reg_str):
    """
    In this university:
    Registration number's first 4 digits indicate admission/session year.
    E.g. 2024... indicates 2023-24 batch.
         2025... indicates 2024-25 batch.
         2023... indicates 2022-23 batch.
    """
    if not reg_str:
        return None
    cleaned = re.sub(r"[^0-9]", "", str(reg_str))
    if len(cleaned) >= 4:
        try:
            first4 = int(cleaned[:4])
            # Target name like '2023-24'
            target_name = f"{first4 - 1}-{str(first4)[2:]}"
            b = Batch.objects.filter(name__icontains=target_name).first()
            if b:
                return b
            # Fallback: check starts with first4
            b = Batch.objects.filter(name__startswith=str(first4)).first()
            if b:
                return b
        except ValueError:
            pass
    return None


def find_student_by_roll_and_batch(roll, batch):
    """
    Locates a student uniquely by roll number within a specific batch.
    """
    if roll is None or not batch:
        return None
    try:
        roll_int = int(str(roll).strip())
    except (ValueError, TypeError):
        return None
    return User.objects.filter(role="student", batch=batch, roll=roll_int).first()


def find_student_by_registration(reg_str):
    """
    Locates a student uniquely by registration number.
    Handles extra spacing and format variations.
    """
    if not reg_str:
        return None
    cleaned = str(reg_str).strip()
    s = User.objects.filter(role="student", registration_no__iexact=cleaned).first()
    if s:
        return s
    # Try digits only
    digits_only = re.sub(r"[^0-9]", "", cleaned)
    if digits_only:
        s = User.objects.filter(role="student", registration_no__iexact=digits_only).first()
        if s:
            return s
        # Or username matching
        s = User.objects.filter(role="student", username__iexact=digits_only).first()
        if s:
            return s
    return None


def _clean_val(v):
    if v is None:
        return ""
    s = str(v).strip()
    if s.lower() in ("none", "null", "nan", "-", "--", "n/a", "na", "nil"):
        return ""
    return s


def _extract_rows_from_file(uploaded_file):
    """
    Reads all raw rows from an uploaded .xlsx, .xls or .csv file.
    Returns list of lists: [[cell1, cell2, ...], ...]
    """
    if hasattr(uploaded_file, "seek"):
        uploaded_file.seek(0)
    filename = getattr(uploaded_file, "name", "file.xlsx").lower()
    raw_rows = []

    # Attempt Excel parsing first if .xlsx, .xls or unspecified
    if not filename.endswith(".csv"):
        try:
            wb = openpyxl.load_workbook(uploaded_file, data_only=True)
            sheet = wb.active
            for row in sheet.iter_rows(values_only=True):
                if row is not None and any(v is not None and str(v).strip() != "" for v in row):
                    raw_rows.append([_clean_val(c) for c in row])
            if raw_rows:
                return raw_rows
        except Exception:
            if hasattr(uploaded_file, "seek"):
                uploaded_file.seek(0)

    # CSV fallback / parsing
    content = uploaded_file.read()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")
    reader = csv.reader(io.StringIO(text))
    for row in reader:
        if row and any(str(c).strip() != "" for c in row):
            raw_rows.append([_clean_val(c) for c in row])

    return raw_rows


def parse_incourse_file(uploaded_file, target_batch=None, target_course=None):
    """
    Parses an Incourse Marks file.
    Batch and Course Unit are selected from the web interface.
    Excel format:
      Col 1: Roll (e.g. 1987)
      Col 2: Incourse Marks (e.g. 32.5)
      (Row 1 may optionally be headers: 'Roll', 'Marks')
    """
    raw_rows = _extract_rows_from_file(uploaded_file)
    if not raw_rows:
        return {"batch": target_batch, "course": target_course, "rows": [], "errors": ["File is empty."]}

    detected_batch = target_batch
    detected_course = target_course

    # If course or batch not selected in form, try to detect from top rows as fallback
    for row in raw_rows[:10]:
        if not detected_course:
            for cell in row:
                found_c = find_course_by_code(cell)
                if found_c:
                    detected_course = found_c
                    break
        if not detected_batch:
            for cell in row:
                found_b = find_batch_by_name(cell)
                if found_b:
                    detected_batch = found_b
                    break

    if not detected_batch:
        return {
            "batch": None,
            "course": detected_course,
            "rows": [],
            "errors": ["Please select the Target Batch from the dropdown before uploading."]
        }

    if not detected_course:
        return {
            "batch": detected_batch,
            "course": None,
            "rows": [],
            "errors": ["Please select the Course Unit from the dropdown before uploading."]
        }

    # Automatically resolve semester from course code (e.g. 1101 -> 1, 2200 -> 4)
    semester = detected_course.semester or resolve_semester_from_course_code(detected_course.code)

    # Detect header row
    header_idx = -1
    col_roll = 0
    col_mark = 1

    for r_idx, row in enumerate(raw_rows[:10]):
        norm_cells = [re.sub(r"[^a-z0-9]", "", str(c).lower()) for c in row]
        r_found = -1
        m_found = -1
        for idx, nc in enumerate(norm_cells):
            if nc in ("roll", "rollno", "studentroll", "id", "classroll", "studentno") or (len(nc) <= 12 and "roll" in nc):
                r_found = idx
            elif nc in ("mark", "marks", "incourse", "incoursemarks", "incoursemark", "obtainedmarks", "total", "score") or (len(nc) <= 22 and "incourse" in nc):
                m_found = idx

        if r_found != -1 and m_found != -1 and len(norm_cells[r_found]) <= 15 and len(norm_cells[m_found]) <= 25:
            header_idx = r_idx
            col_roll = r_found
            col_mark = m_found
            break

    # If header found, data starts right after header. Otherwise assume Row 0 is data.
    start_idx = header_idx + 1 if header_idx != -1 else 0

    max_incourse = detected_course.incourse_max
    parsed_rows = []
    errors = []
    warnings = []

    for r_idx in range(start_idx, len(raw_rows)):
        row = raw_rows[r_idx]
        if not row or col_roll >= len(row) or col_mark >= len(row):
            continue

        raw_roll = row[col_roll].strip()
        raw_mark = row[col_mark].strip()
        if not raw_roll and not raw_mark:
            continue

        # Skip header if it was not detected earlier
        clean_norm = re.sub(r"[^a-z]", "", raw_roll.lower())
        if clean_norm in ("roll", "rollno", "student"):
            continue

        try:
            roll_int = int(re.sub(r"[^0-9]", "", raw_roll))
        except (ValueError, TypeError):
            continue

        try:
            mark_dec = Decimal(str(float(raw_mark))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        except (ValueError, TypeError):
            mark_dec = None

        student = find_student_by_roll_and_batch(roll_int, detected_batch)
        status = "ok"
        msg = ""

        if not student:
            status = "error"
            msg = f"Roll {roll_int} was not found in Batch {detected_batch.name}."
            warnings.append(msg)
        elif mark_dec is None:
            status = "error"
            msg = f"Invalid mark format for Roll {roll_int}: '{raw_mark}'"
            warnings.append(msg)
        elif max_incourse > 0 and mark_dec > max_incourse:
            status = "warning"
            msg = f"Mark ({mark_dec}) exceeds standard maximum incourse of {max_incourse} for this course."
            warnings.append(msg)

        parsed_rows.append({
            "roll": roll_int,
            "mark": mark_dec,
            "raw_mark": raw_mark,
            "student": student,
            "status": status,
            "message": msg,
        })

    return {
        "batch": detected_batch,
        "course": detected_course,
        "semester": semester,
        "rows": parsed_rows,
        "errors": errors,
        "warnings": warnings,
    }


def parse_final_file(uploaded_file, target_batch=None, target_course=None):
    """
    Parses a Final Exam Marks file.
    Course Unit and Batch are selected from the web interface.
    Excel format:
      Col 1: Registration No (e.g. 20243660771)
      Col 2: Final Marks (e.g. 51.0)
      (Row 1 may optionally be headers: 'Registration No', 'Marks')
    """
    raw_rows = _extract_rows_from_file(uploaded_file)
    if not raw_rows:
        return {"course": target_course, "batch": target_batch, "rows": [], "errors": ["File is empty."]}

    detected_course = target_course
    detected_batch = target_batch

    # Fallback scan
    for row in raw_rows[:10]:
        if not detected_course:
            for cell in row:
                found_c = find_course_by_code(cell)
                if found_c:
                    detected_course = found_c
                    break
        if not detected_batch:
            for cell in row:
                found_b = find_batch_by_name(cell)
                if found_b:
                    detected_batch = found_b
                    break

    if not detected_course:
        return {
            "course": None,
            "batch": detected_batch,
            "rows": [],
            "errors": ["Please select the Course Unit from the dropdown before uploading."]
        }

    # Automatically resolve semester from course code (e.g. 1101 -> 1, 2200 -> 4)
    semester = detected_course.semester or resolve_semester_from_course_code(detected_course.code)

    # Detect header row
    header_idx = -1
    col_reg = 0
    col_mark = 1

    for r_idx, row in enumerate(raw_rows[:10]):
        norm_cells = [re.sub(r"[^a-z0-9]", "", str(c).lower()) for c in row]
        reg_found = -1
        m_found = -1
        for idx, nc in enumerate(norm_cells):
            if nc in ("reg", "registration", "registrationno", "regno", "studentid", "id") or (len(nc) <= 15 and "reg" in nc):
                reg_found = idx
            elif nc in ("mark", "marks", "final", "finalmarks", "finalmark", "obtainedmarks", "score", "total") or (len(nc) <= 22 and "final" in nc):
                m_found = idx

        if reg_found != -1 and m_found != -1 and len(norm_cells[reg_found]) <= 18 and len(norm_cells[m_found]) <= 25:
            header_idx = r_idx
            col_reg = reg_found
            col_mark = m_found
            break

    start_idx = header_idx + 1 if header_idx != -1 else 0

    max_final = detected_course.final_max
    parsed_rows = []
    errors = []
    warnings = []

    for r_idx in range(start_idx, len(raw_rows)):
        row = raw_rows[r_idx]
        if not row or col_reg >= len(row) or col_mark >= len(row):
            continue

        raw_reg = row[col_reg].strip()
        raw_mark = row[col_mark].strip()
        if not raw_reg and not raw_mark:
            continue

        clean_reg = re.sub(r"[^a-zA-Z0-9]", "", raw_reg)
        if not clean_reg:
            continue

        # Skip header if encountered
        clean_norm = re.sub(r"[^a-z]", "", raw_reg.lower())
        if clean_norm in ("reg", "registration", "registrationno", "studentid"):
            continue

        try:
            mark_dec = Decimal(str(float(raw_mark))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        except (ValueError, TypeError):
            mark_dec = None

        student = find_student_by_registration(clean_reg)
        if not student and detected_batch:
            # Fallback 1: match username within detected batch
            student = User.objects.filter(role="student", batch=detected_batch, username__iexact=clean_reg).first()
            # Fallback 2: match roll if clean_reg is purely a roll number
            if not student and clean_reg.isdigit():
                try:
                    student = User.objects.filter(role="student", batch=detected_batch, roll=int(clean_reg)).first()
                except ValueError:
                    pass

        batch = None
        if student and student.batch:
            batch = student.batch
        elif detected_batch:
            batch = detected_batch
            if student and not student.batch:
                student.batch = detected_batch
                student.save(update_fields=["batch"])
        else:
            batch = resolve_batch_from_reg(clean_reg)
            if student and batch and not student.batch:
                student.batch = batch
                student.save(update_fields=["batch"])

        if student and not student.registration_no:
            student.registration_no = clean_reg
            student.save(update_fields=["registration_no"])

        status = "ok"
        msg = ""

        if not student:
            status = "error"
            msg = f"Registration ID {raw_reg} was not found in the student database."
            warnings.append(msg)
        elif detected_batch and student.batch and student.batch_id != detected_batch.id:
            status = "error"
            msg = f"Student with Reg {raw_reg} belongs to Batch {student.batch.name}, not selected Batch {detected_batch.name}."
            warnings.append(msg)
        elif mark_dec is None:
            status = "error"
            msg = f"Invalid mark format for Reg {raw_reg}: '{raw_mark}'"
            warnings.append(msg)
        elif max_final > 0 and mark_dec > max_final:
            status = "warning"
            msg = f"Mark ({mark_dec}) exceeds standard final maximum of {max_final} for this course."
            warnings.append(msg)

        parsed_rows.append({
            "reg": clean_reg,
            "raw_reg": raw_reg,
            "mark": mark_dec,
            "raw_mark": raw_mark,
            "student": student,
            "batch": batch,
            "status": status,
            "message": msg,
        })

    if not detected_batch:
        for pr in parsed_rows:
            if pr.get("batch"):
                detected_batch = pr["batch"]
                break

    return {
        "course": detected_course,
        "batch": detected_batch,
        "semester": semester,
        "rows": parsed_rows,
        "errors": errors,
        "warnings": warnings,
    }


def save_parsed_incourse_marks(parsed_data, user):
    """
    Persists parsed incourse marks into StudentCourseMark.
    """
    batch = parsed_data["batch"]
    course = parsed_data["course"]
    rows = parsed_data["rows"]
    now = timezone.now()

    success_count = 0
    updated_count = 0

    for item in rows:
        if item["status"] not in ("ok", "warning") or not item["student"] or item["mark"] is None:
            continue
        student = item["student"]
        mark_val = item["mark"]

        scm, created = StudentCourseMark.objects.get_or_create(
            student=student,
            course=course,
            defaults={
                "batch": batch or student.batch,
                "semester": course.semester,
                "incourse_marks": mark_val,
                "incourse_uploaded_by": user,
                "incourse_uploaded_at": now,
            }
        )
        if not created:
            scm.incourse_marks = mark_val
            scm.incourse_uploaded_by = user
            scm.incourse_uploaded_at = now
            if not scm.batch and (batch or student.batch):
                scm.batch = batch or student.batch
            if not scm.semester:
                scm.semester = course.semester
            scm.save()
            updated_count += 1
        else:
            scm.save()
            success_count += 1

    return success_count, updated_count


def save_parsed_final_marks(parsed_data, user):
    """
    Persists parsed final marks into StudentCourseMark.
    Combines with incourse_marks to compute UGC letter grade and grade point.
    """
    course = parsed_data["course"]
    rows = parsed_data["rows"]
    now = timezone.now()

    success_count = 0
    updated_count = 0

    for item in rows:
        if item["status"] not in ("ok", "warning") or not item["student"] or item["mark"] is None:
            continue
        student = item["student"]
        batch = item["batch"] or student.batch
        mark_val = item["mark"]

        scm, created = StudentCourseMark.objects.get_or_create(
            student=student,
            course=course,
            defaults={
                "batch": batch,
                "semester": course.semester,
                "final_marks": mark_val,
                "final_uploaded_by": user,
                "final_uploaded_at": now,
            }
        )
        if not created:
            scm.final_marks = mark_val
            scm.final_uploaded_by = user
            scm.final_uploaded_at = now
            if not scm.batch and batch:
                scm.batch = batch
            scm.save()
            updated_count += 1
        else:
            scm.save()
            success_count += 1

    return success_count, updated_count


def generate_sample_incourse_workbook(batch, course):
    """
    Creates a pure 2-column Excel template for Incourse upload:
      Row 1: Roll | Incourse Marks
      Row 2+: <student roll> | <blank>
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Incourse Marks"

    font_white_bold = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    col_head_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")  # Navy
    border_thin = Border(
        left=Side(style="thin", color="CBD5E1"),
        right=Side(style="thin", color="CBD5E1"),
        top=Side(style="thin", color="CBD5E1"),
        bottom=Side(style="thin", color="CBD5E1"),
    )

    # Row 1: Simple 2-column header only
    c1 = ws.cell(row=1, column=1, value="Roll")
    c1.font = font_white_bold
    c1.fill = col_head_fill
    c1.alignment = Alignment(horizontal="center", vertical="center")
    c1.border = border_thin

    c2 = ws.cell(row=1, column=2, value="Incourse Marks")
    c2.font = font_white_bold
    c2.fill = col_head_fill
    c2.alignment = Alignment(horizontal="center", vertical="center")
    c2.border = border_thin
    ws.row_dimensions[1].height = 24

    # Populate students of the target batch
    students = []
    if batch:
        students = (
            list(User.objects.filter(role="student", batch=batch).exclude(roll__isnull=True).order_by("roll")) +
            list(User.objects.filter(role="student", batch=batch, roll__isnull=True).order_by("username"))
        )

    row_num = 2
    for s in students:
        r_cell = ws.cell(row=row_num, column=1, value=s.roll or "")
        r_cell.alignment = Alignment(horizontal="center")
        r_cell.border = border_thin

        m_cell = ws.cell(row=row_num, column=2, value="")
        m_cell.alignment = Alignment(horizontal="center")
        m_cell.border = border_thin
        row_num += 1

    ws.column_dimensions["A"].width = 16
    ws.column_dimensions["B"].width = 20

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output


def generate_sample_final_workbook(batch, course):
    """
    Creates a pure 2-column Excel template for Final Exam upload:
      Row 1: Registration No | Final Marks
      Row 2+: <student registration_no> | <blank>
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Final Exam Marks"

    font_white_bold = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    col_head_fill = PatternFill(start_color="065F46", end_color="065F46", fill_type="solid")  # Emerald
    border_thin = Border(
        left=Side(style="thin", color="CBD5E1"),
        right=Side(style="thin", color="CBD5E1"),
        top=Side(style="thin", color="CBD5E1"),
        bottom=Side(style="thin", color="CBD5E1"),
    )

    # Row 1: Simple 2-column header only
    c1 = ws.cell(row=1, column=1, value="Registration No")
    c1.font = font_white_bold
    c1.fill = col_head_fill
    c1.alignment = Alignment(horizontal="center", vertical="center")
    c1.border = border_thin

    c2 = ws.cell(row=1, column=2, value="Final Marks")
    c2.font = font_white_bold
    c2.fill = col_head_fill
    c2.alignment = Alignment(horizontal="center", vertical="center")
    c2.border = border_thin
    ws.row_dimensions[1].height = 24

    # Populate students
    students = []
    if batch:
        students = (
            list(User.objects.filter(role="student", batch=batch).exclude(registration_no__isnull=True).order_by("registration_no")) +
            list(User.objects.filter(role="student", batch=batch, registration_no__isnull=True).order_by("username"))
        )
    elif course:
        students = list(User.objects.filter(role="student", batch__current_semester=course.semester).order_by("registration_no"))

    row_num = 2
    for s in students:
        r_cell = ws.cell(row=row_num, column=1, value=s.registration_no or s.username)
        r_cell.alignment = Alignment(horizontal="center")
        r_cell.border = border_thin

        m_cell = ws.cell(row=row_num, column=2, value="")
        m_cell.alignment = Alignment(horizontal="center")
        m_cell.border = border_thin
        row_num += 1

    ws.column_dimensions["A"].width = 22
    ws.column_dimensions["B"].width = 20

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output


def generate_consolidated_batch_workbook(batch, semester):
    """
    Generates a consolidated spreadsheet of the entire batch for a semester.
    Student-wise rows with columns for each course:
      [Incourse, Final, Total, Grade, GP]
    Plus total credits & semester GPA.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"Batch {batch.name} Sem {semester}"

    courses = list(Course.objects.filter(semester=semester).order_by("code"))
    students = list(User.objects.filter(role="student", batch=batch).order_by("roll", "username"))

    # Fills & Fonts
    top_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
    sec_fill = PatternFill(start_color="334155", end_color="334155", fill_type="solid")
    th_fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")
    tot_fill = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid")
    font_white_title = Font(name="Calibri", size=13, bold=True, color="FFFFFF")
    font_white_sub = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
    font_bold = Font(name="Calibri", size=10, bold=True)
    font_regular = Font(name="Calibri", size=10)
    border_thin = Border(
        left=Side(style="thin", color="CBD5E1"),
        right=Side(style="thin", color="CBD5E1"),
        top=Side(style="thin", color="CBD5E1"),
        bottom=Side(style="thin", color="CBD5E1"),
    )

    total_cols = 3 + len(courses) * 5 + 3  # Roll, Reg, Name + 5 per course + Credits, GPA, CGPA

    # Title Row
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=total_cols)
    ws["A1"] = f"CONSOLIDATED SEMESTER EVALUATION · BATCH {batch.name} · SEMESTER {semester}"
    ws["A1"].font = font_white_title
    ws["A1"].fill = top_fill
    ws["A1"].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 28

    # Row 2 & 3: Course Headers (Merged over 5 subcolumns each)
    ws.merge_cells("A2:A3")
    ws["A2"] = "Roll"
    ws.merge_cells("B2:B3")
    ws["B2"] = "Registration No"
    ws.merge_cells("C2:C3")
    ws["C2"] = "Student Name"

    for cell in ("A2", "B2", "C2"):
        ws[cell].font = font_white_sub
        ws[cell].fill = sec_fill
        ws[cell].alignment = Alignment(horizontal="center", vertical="center")
        ws[cell].border = border_thin

    curr_col = 4
    for c in courses:
        start_c = curr_col
        end_c = curr_col + 4
        ws.merge_cells(start_row=2, start_column=start_c, end_row=2, end_column=end_c)
        c_title = f"{c.code} ({c.credit} Cr)"
        ws.cell(row=2, column=start_c, value=c_title).font = font_white_sub
        ws.cell(row=2, column=start_c).fill = sec_fill
        ws.cell(row=2, column=start_c).alignment = Alignment(horizontal="center", vertical="center")

        sub_heads = ["Incourse", "Final", "Total", "Grade", "GP"]
        for i, sh in enumerate(sub_heads):
            cell = ws.cell(row=3, column=start_c + i, value=sh)
            cell.font = font_bold
            cell.fill = th_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = border_thin

        curr_col += 5

    # Overall summary headers
    ws.merge_cells(start_row=2, start_column=curr_col, end_row=3, end_column=curr_col)
    ws.cell(row=2, column=curr_col, value="Credits").font = font_white_sub
    ws.cell(row=2, column=curr_col).fill = sec_fill
    ws.cell(row=2, column=curr_col).alignment = Alignment(horizontal="center", vertical="center")
    ws.cell(row=2, column=curr_col).border = border_thin

    ws.merge_cells(start_row=2, start_column=curr_col + 1, end_row=3, end_column=curr_col + 1)
    ws.cell(row=2, column=curr_col + 1, value="Sem GPA").font = font_white_sub
    ws.cell(row=2, column=curr_col + 1).fill = sec_fill
    ws.cell(row=2, column=curr_col + 1).alignment = Alignment(horizontal="center", vertical="center")
    ws.cell(row=2, column=curr_col + 1).border = border_thin

    ws.merge_cells(start_row=2, start_column=curr_col + 2, end_row=3, end_column=curr_col + 2)
    ws.cell(row=2, column=curr_col + 2, value="CGPA").font = font_white_sub
    ws.cell(row=2, column=curr_col + 2).fill = sec_fill
    ws.cell(row=2, column=curr_col + 2).alignment = Alignment(horizontal="center", vertical="center")
    ws.cell(row=2, column=curr_col + 2).border = border_thin

    # Cache existing marks in a dict: (student_id, course_id) -> StudentCourseMark
    marks_map = {}
    for scm in StudentCourseMark.objects.filter(batch=batch, semester=semester).select_related("student", "course"):
        marks_map[(scm.student_id, scm.course_id)] = scm

    # Cache published SemesterResult
    sem_res_map = {}
    for sr in SemesterResult.objects.filter(student__batch=batch, semester=semester):
        sem_res_map[sr.student_id] = sr

    row_idx = 4
    for s in students:
        ws.cell(row=row_idx, column=1, value=s.roll or "").alignment = Alignment(horizontal="center")
        ws.cell(row=row_idx, column=2, value=s.registration_no or s.username).alignment = Alignment(horizontal="center")
        ws.cell(row=row_idx, column=3, value=s.first_name or s.username)

        for col_i in range(1, 4):
            ws.cell(row=row_idx, column=col_i).border = border_thin

        c_col = 4
        total_pts = Decimal("0.00")
        total_crs = Decimal("0.00")

        for c in courses:
            scm = marks_map.get((s.id, c.id))
            inc = scm.incourse_marks if (scm and scm.incourse_marks is not None) else ""
            fin = scm.final_marks if (scm and scm.final_marks is not None) else ""
            tot = scm.total_marks if (scm and scm.total_marks is not None) else ""
            grd = scm.grade if (scm and scm.grade) else ""
            gp = scm.grade_point if (scm and scm.grade_point is not None) else ""

            if scm and scm.grade_point is not None:
                total_pts += c.credit * scm.grade_point
                total_crs += c.credit

            vals = [inc, fin, tot, grd, gp]
            for i, v in enumerate(vals):
                cell = ws.cell(row=row_idx, column=c_col + i, value=v)
                cell.alignment = Alignment(horizontal="center")
                cell.border = border_thin
                if i in (2, 3):  # Total and Grade bold
                    cell.font = font_bold
            c_col += 5

        # Calculations
        sr = sem_res_map.get(s.id)
        if sr:
            sem_gpa = sr.gpa
            cgpa_val = sr.cgpa
        elif total_crs > 0:
            sem_gpa = (total_pts / total_crs).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            cgpa_val = ""
        else:
            sem_gpa = ""
            cgpa_val = ""

        c_cell = ws.cell(row=row_idx, column=c_col, value=float(total_crs) if total_crs else "")
        c_cell.alignment = Alignment(horizontal="center")
        c_cell.border = border_thin

        gpa_cell = ws.cell(row=row_idx, column=c_col + 1, value=float(sem_gpa) if sem_gpa != "" else "")
        gpa_cell.alignment = Alignment(horizontal="center")
        gpa_cell.border = border_thin
        gpa_cell.font = font_bold
        gpa_cell.fill = tot_fill

        cgpa_cell = ws.cell(row=row_idx, column=c_col + 2, value=float(cgpa_val) if cgpa_val != "" else "")
        cgpa_cell.alignment = Alignment(horizontal="center")
        cgpa_cell.border = border_thin
        cgpa_cell.font = font_bold

        row_idx += 1

    # Widths
    ws.column_dimensions["A"].width = 10
    ws.column_dimensions["B"].width = 18
    ws.column_dimensions["C"].width = 24
    for c_idx in range(4, total_cols + 1):
        col_letter = get_column_letter(c_idx)
        ws.column_dimensions[col_letter].width = 10

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output
