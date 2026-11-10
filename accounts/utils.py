import csv
import io
import re
import secrets
import string

from django.core.mail import send_mail
from django.db.models import Q
from academics.models import Batch
from .models import User


def generate_password(length=10):
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def generate_reset_code():
    return f"{secrets.randbelow(1000000):06d}"


def _normalize_header(h):
    if h is None:
        return ""
    return re.sub(r"[^a-z0-9]", "", str(h).lower())


def _clean_val(v):
    if v is None:
        return ""
    s = str(v).strip()
    if s.lower() in ("none", "null", "nan", "-", "--", "n/a", "na", "nil"):
        return ""
    return s


def _format_phone(phone_str):
    if not phone_str:
        return ""
    digits = re.sub(r"[^0-9]", "", str(phone_str))
    # In Excel, Bangladeshi numbers like 018... often lose the leading 0 (e.g. 1863359400)
    if len(digits) == 10 and digits.startswith("1"):
        digits = "0" + digits
    return digits


def parse_user_rows_from_file(uploaded_file):
    """
    Parses rows from either an .xlsx or a .csv uploaded file.
    Standardizes columns: role, name, email, phone, batch, roll, reg.

    CORE AUTO-DETECTION RULE:
      - Registration number na thaka mane Teacher!
      - If Registration Number (reg) is empty/blank -> Auto-identified as 'teacher'.
      - If Registration Number (reg) is present -> Auto-identified as 'student'.
    """
    if hasattr(uploaded_file, "seek"):
        uploaded_file.seek(0)

    filename = uploaded_file.name.lower()
    raw_rows = []

    if filename.endswith(".xlsx") or filename.endswith(".xls"):
        import openpyxl
        wb = openpyxl.load_workbook(uploaded_file, data_only=True)
        sheet = wb.active
        headers = None
        for row in sheet.iter_rows(values_only=True):
            if not row or all(v is None or str(v).strip() == "" for v in row):
                continue
            if headers is None:
                headers = [_normalize_header(c) for c in row if c is not None]
                continue
            # Ensure row matches headers length even if trailing cells are blank
            row_list = list(row) + [None] * max(0, len(headers) - len(row))
            row_dict = {}
            for h, val in zip(headers, row_list):
                if h:
                    row_dict[h] = _clean_val(val)
            raw_rows.append(row_dict)
    else:
        # CSV parsing (handles UTF-8, UTF-8 BOM, and Latin-1)
        content = uploaded_file.read()
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = content.decode("latin-1")

        reader = csv.reader(io.StringIO(text))
        headers = None
        for row in reader:
            if not row or all(str(v).strip() == "" for v in row):
                continue
            if headers is None:
                headers = [_normalize_header(c) for c in row if c is not None]
                continue
            row_list = list(row) + [""] * max(0, len(headers) - len(row))
            row_dict = {}
            for h, val in zip(headers, row_list):
                if h:
                    row_dict[h] = _clean_val(val)
            raw_rows.append(row_dict)

    standardized = []
    for r in raw_rows:
        std = {
            "role": "",
            "name": "",
            "email": "",
            "phone": "",
            "batch": "",
            "roll": "",
            "reg": "",
        }
        for k, v in r.items():
            cleaned_v = _clean_val(v)
            if k in ("role", "type", "usertype", "designation", "position", "category"):
                std["role"] = cleaned_v.lower()
            elif k in ("name", "fullname", "studentname", "teachername", "facultyname", "names"):
                std["name"] = cleaned_v
            elif k in ("email", "emailaddress", "mail", "gmail", "emailid"):
                std["email"] = cleaned_v
            elif k in ("phone", "mobile", "phonenumber", "contact", "number", "cell", "cellnumber", "contactno", "mobileno", "contactnumber"):
                std["phone"] = _format_phone(cleaned_v)
            elif k in ("batch", "session", "admissionyear", "classbatch", "batchname"):
                std["batch"] = cleaned_v
            elif k in ("roll", "rollno", "rollnumber", "classroll", "classrollno"):
                std["roll"] = cleaned_v
            elif k in ("reg", "regno", "registration", "registrationno", "registrationnumber", "studentid", "regnumber", "id", "studentreg", "regnum", "registrationnum"):
                std["reg"] = cleaned_v

        # --- AUTO DETECTION LOGIC ---
        # Registration number na thaka mane Teacher!
        if std["role"] and any(term in std["role"] for term in ["teach", "faculty", "prof", "lectur", "sir", "madam"]):
            std["role"] = "teacher"
        elif std["role"] and any(term in std["role"] for term in ["student", "pupil"]):
            std["role"] = "student"
        elif not std["reg"]:
            std["role"] = "teacher"
        else:
            std["role"] = "student"

        # Teachers don't have batch, roll, or reg
        if std["role"] == "teacher":
            std["batch"] = ""
            std["roll"] = ""
            std["reg"] = ""

        standardized.append(std)

    return standardized


# Backwards compatibility alias
parse_student_rows_from_file = parse_user_rows_from_file


def import_users_from_file(uploaded_file, request=None):
    """
    Reads user rows (Students and Teachers) from Excel/CSV.
    Auto-detects whether each row is a Teacher or a Student:
      - If Registration Number (Reg) is empty -> Teacher (Login ID is Email).
      - If Registration Number (Reg) is present -> Student (Login ID is Reg No).
    Handles both new accounts (creates & emails credentials) and existing accounts (updates profiles).
    """
    rows = parse_user_rows_from_file(uploaded_file)

    created_students = []
    created_teachers = []
    errors = []

    domain = "localhost:8000"
    if request:
        domain = request.get_host()
    protocol = "https" if (request and request.is_secure()) else "http"
    login_url = f"{protocol}://{domain}/accounts/login/"

    for idx, r in enumerate(rows, start=2):  # line 1 was headers
        name = _clean_val(r.get("name", ""))
        email = _clean_val(r.get("email", "")).lower()
        phone = _format_phone(_clean_val(r.get("phone", "")))
        batch_name = _clean_val(r.get("batch", ""))
        roll_raw = _clean_val(r.get("roll", ""))
        reg = _clean_val(r.get("reg", ""))

        # ABSOLUTE DECISION RULE:
        # Registration number na thaka mane Teacher!
        explicit_role = _clean_val(r.get("role", "")).lower()
        if explicit_role and any(term in explicit_role for term in ["teach", "faculty", "prof", "lectur", "sir", "madam"]):
            role = "teacher"
        elif explicit_role and any(term in explicit_role for term in ["student", "pupil"]):
            role = "student"
        elif not reg:
            role = "teacher"
        else:
            role = "student"

        if not name or not email:
            errors.append({
                "row": idx,
                "role": role.capitalize(),
                "name": name or "(empty)",
                "email": email or "(empty)",
                "identifier": reg or email or "(empty)",
                "error": "Name and Email are required.",
            })
            continue

        # Look for existing user by email or registration number
        lookup_q = Q(email__iexact=email)
        if reg:
            lookup_q |= Q(username__iexact=reg)
        existing_user = User.objects.filter(lookup_q).first()

        # If user is admin/superuser, protect it from modification
        if existing_user and (existing_user.is_superuser or existing_user.role == "admin"):
            errors.append({
                "row": idx,
                "role": role.capitalize(),
                "name": name,
                "email": email,
                "identifier": reg or email,
                "error": "This email belongs to an Administrator account and cannot be overwritten.",
            })
            continue

        # ==========================================
        # 1. PROCESS TEACHER (Reg number is empty)
        # ==========================================
        if role == "teacher":
            username = email

            if existing_user:
                # Update existing teacher profile
                try:
                    existing_user.first_name = name
                    if phone:
                        existing_user.phone = phone
                    existing_user.role = "teacher"
                    existing_user.batch = None
                    existing_user.roll = None
                    existing_user.registration_no = None
                    # If username is not email, try updating username to email if available
                    if existing_user.username.lower() != email:
                        if not User.objects.filter(username__iexact=email).exclude(id=existing_user.id).exists():
                            existing_user.username = email
                    existing_user.save()

                    created_teachers.append({
                        "row": idx,
                        "role": "Teacher",
                        "name": name,
                        "username": existing_user.username,
                        "email": email,
                        "phone": existing_user.phone or "-",
                        "email_sent": False,
                        "status": "Updated Existing Profile",
                    })
                except Exception as e:
                    errors.append({
                        "row": idx,
                        "role": "Teacher",
                        "name": name,
                        "email": email,
                        "identifier": email,
                        "error": f"Failed to update existing teacher: {str(e)}",
                    })
                continue

            # Check if username is taken
            if User.objects.filter(username__iexact=username).exists():
                errors.append({
                    "row": idx,
                    "role": "Teacher",
                    "name": name,
                    "email": email,
                    "identifier": username,
                    "error": f"A user with Login ID / Email '{username}' already exists.",
                })
                continue

            # Create brand-new Teacher
            password = generate_password(10)
            try:
                user = User.objects.create_user(
                    username=username,
                    email=email,
                    password=password,
                    role="teacher",
                    phone=phone,
                    batch=None,
                    roll=None,
                    registration_no=None,
                    first_name=name,
                )

                email_sent = False
                email_error = None
                try:
                    subject = "Welcome to IIT JU Faculty Portal - Your Account Credentials"
                    message = (
                        f"Dear {name},\n\n"
                        f"Your faculty account has been successfully created on the IIT Jahangirnagar University Portal.\n\n"
                        f"Your Official Login Credentials:\n"
                        f"-----------------------------------------\n"
                        f"Portal URL       : {login_url}\n"
                        f"Login ID (Email) : {email}  (Use your email address to log in)\n"
                        f"Password         : {password}\n"
                        f"Role             : Teacher / Faculty Member\n"
                        f"Contact Phone    : {phone if phone else 'N/A'}\n"
                        f"-----------------------------------------\n\n"
                        f"Please sign in to your dashboard to manage courses, class routines, student attendance, semester results, and announcements.\n"
                        f"Courses and academic assignments are managed by Department Administration.\n"
                        f"You may update your password at any time from your profile settings.\n\n"
                        f"Warm regards,\n"
                        f"Institute of Information Technology (IIT)\n"
                        f"Jahangirnagar University, Savar, Dhaka-1342"
                    )
                    send_mail(subject, message, None, [email], fail_silently=False)
                    email_sent = True
                except Exception as mail_err:
                    email_error = str(mail_err)

                created_teachers.append({
                    "row": idx,
                    "role": "Teacher",
                    "name": name,
                    "username": username,
                    "email": email,
                    "phone": phone or "-",
                    "email_sent": email_sent,
                    "email_error": email_error,
                    "status": "Created & Emailed",
                })
            except Exception as e:
                errors.append({
                    "row": idx,
                    "role": "Teacher",
                    "name": name,
                    "email": email,
                    "identifier": email,
                    "error": f"Failed to create teacher user: {str(e)}",
                })

        # ==========================================
        # 2. PROCESS STUDENT (Reg number is present)
        # ==========================================
        else:
            if not reg:
                errors.append({
                    "row": idx,
                    "role": "Student",
                    "name": name,
                    "email": email,
                    "identifier": "(empty)",
                    "error": "Registration Number (Reg) is required as it serves as the student's Login ID.",
                })
                continue

            username = reg

            # Batch resolution
            batch = None
            if batch_name:
                batch, _ = Batch.objects.get_or_create(
                    name=batch_name,
                    defaults={"is_running": True}
                )

            # Roll resolution
            roll = None
            if roll_raw:
                digits = re.sub(r"[^0-9]", "", roll_raw)
                if digits:
                    roll = int(digits)

            if existing_user:
                # Update existing student profile
                try:
                    existing_user.first_name = name
                    if phone:
                        existing_user.phone = phone
                    if batch:
                        existing_user.batch = batch
                    if roll is not None:
                        existing_user.roll = roll
                    existing_user.registration_no = reg
                    existing_user.role = "student"
                    if existing_user.username != reg:
                        if not User.objects.filter(username__iexact=reg).exclude(id=existing_user.id).exists():
                            existing_user.username = reg
                    existing_user.save()

                    created_students.append({
                        "row": idx,
                        "role": "Student",
                        "name": name,
                        "username": existing_user.username,
                        "email": email,
                        "batch": batch.name if batch else "-",
                        "roll": roll if roll is not None else "-",
                        "reg": reg,
                        "phone": existing_user.phone or "-",
                        "email_sent": False,
                        "status": "Updated Existing Profile",
                    })
                except Exception as e:
                    errors.append({
                        "row": idx,
                        "role": "Student",
                        "name": name,
                        "email": email,
                        "identifier": reg,
                        "error": f"Failed to update existing student: {str(e)}",
                    })
                continue

            # Check if username is taken
            if User.objects.filter(username__iexact=username).exists():
                errors.append({
                    "row": idx,
                    "role": "Student",
                    "name": name,
                    "email": email,
                    "identifier": username,
                    "error": f"A student with Registration No / Login ID '{username}' already exists in the database.",
                })
                continue

            # Create brand-new Student
            password = generate_password(10)
            try:
                user = User.objects.create_user(
                    username=username,
                    email=email,
                    password=password,
                    role="student",
                    phone=phone,
                    batch=batch,
                    roll=roll,
                    registration_no=reg,
                    first_name=name,
                )

                email_sent = False
                email_error = None
                try:
                    subject = "Welcome to IIT JU Student Portal - Your Account Credentials"
                    message = (
                        f"Dear {name},\n\n"
                        f"Your student account has been successfully created on the IIT Jahangirnagar University Portal.\n\n"
                        f"Your Official Login Credentials:\n"
                        f"-----------------------------------------\n"
                        f"Portal URL       : {login_url}\n"
                        f"Registration No  : {reg}\n"
                        f"Login ID         : {username}  (Use your Registration No to log in)\n"
                        f"Password         : {password}\n"
                        f"Batch            : {batch.name if batch else 'N/A'}\n"
                        f"Class Roll No    : {roll if roll is not None else 'N/A'}\n"
                        f"-----------------------------------------\n\n"
                        f"Please log in to your dashboard to view class schedules, attendance, results, and notices.\n"
                        f"You may change your password anytime from your dashboard.\n\n"
                        f"Important Notice: Your Registration Number, Roll, and Batch are officially locked.\n\n"
                        f"Warm regards,\n"
                        f"Institute of Information Technology (IIT)\n"
                        f"Jahangirnagar University, Savar, Dhaka-1342"
                    )
                    send_mail(subject, message, None, [email], fail_silently=False)
                    email_sent = True
                except Exception as mail_err:
                    email_error = str(mail_err)

                created_students.append({
                    "row": idx,
                    "role": "Student",
                    "name": name,
                    "username": username,
                    "email": email,
                    "batch": batch.name if batch else "-",
                    "roll": roll if roll is not None else "-",
                    "reg": reg,
                    "phone": phone or "-",
                    "email_sent": email_sent,
                    "email_error": email_error,
                    "status": "Created & Emailed",
                })
            except Exception as e:
                errors.append({
                    "row": idx,
                    "role": "Student",
                    "name": name,
                    "email": email,
                    "identifier": reg,
                    "error": f"Failed to create student user: {str(e)}",
                })

    return {
        "total_rows": len(rows),
        "success_count": len(created_students) + len(created_teachers),
        "student_count": len(created_students),
        "teacher_count": len(created_teachers),
        "created_students": created_students,
        "created_teachers": created_teachers,
        "errors": errors,
        "error_count": len(errors),
    }


# Backwards compatibility alias
import_students_from_file = import_users_from_file
