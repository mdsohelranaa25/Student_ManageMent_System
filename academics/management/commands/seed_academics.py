from django.core.management.base import BaseCommand

from academics.models import Course, Room, TimeSlot

ROOMS = ["Lab 1", "Lab 2", "Lab 3", "Lab 4", "Hardware Lab"]

TIME_SLOTS = [
    ("8:30-9:50", 1),
    ("10:00-11:20", 2),
    ("11:30-12:50", 3),
    ("2:00-3:20", 4),
    ("3:30-4:50", 5),
]

# (code, title, credit, semester)
COURSES = [
    ("ICT 1101", "Structured Programming Language", 3.0, 1),
    ("ICT 1103", "Electrical Circuits", 3.0, 1),
    ("ICT 1105", "Physics", 3.0, 1),
    ("ICT 1107", "Engineering Mathematics-I", 3.0, 1),
    ("ICT 1109", "Communicative English", 3.0, 1),
    ("ICT 1102", "Structured Programming Language Lab", 1.5, 1),
    ("ICT 1104", "Electrical Circuits Lab", 1.5, 1),
    ("ICT 1106", "Soft Skills Development Lab", 1.5, 1),
    ("ICT 1100", "Course Viva", 0.5, 1),

    ("ICT 1201", "Electronic Devices and Circuits", 3.0, 2),
    ("ICT 1203", "Object Oriented Programming", 3.0, 2),
    ("ICT 1205", "Engineering Mathematics-II", 3.0, 2),
    ("ICT 1207", "Discrete Mathematics", 3.0, 2),
    ("ICT 1209", "Bangladesh Studies", 3.0, 2),
    ("ICT 1202", "Electronic Devices and Circuits Lab", 1.5, 2),
    ("ICT 1204", "Object Oriented Programming Lab", 1.5, 2),
    ("ICT 1200", "Project Work - I and Course Viva", 1.0, 2),

    ("ICT 2101", "Data Structures", 3.0, 3),
    ("ICT 2103", "Digital Logic Design", 3.0, 3),
    ("ICT 2105", "Data Communication and Computer Networks", 3.0, 3),
    ("ICT 2107", "Numerical Analysis for Engineers", 3.0, 3),
    ("ICT 2109", "Statistics and Probability for Engineers", 3.0, 3),
    ("ICT 2102", "Data Structures Lab", 1.5, 3),
    ("ICT 2104", "Digital Logic Design Lab", 1.5, 3),
    ("ICT 2106", "Data Communication and Computer Networks Lab", 1.5, 3),
    ("ICT 2100", "Course Viva", 0.5, 3),

    ("ICT 2201", "Algorithm Analysis and Design", 3.0, 4),
    ("ICT 2203", "Analog and Digital Communication", 3.0, 4),
    ("ICT 2205", "Engineering Mathematics-III", 3.0, 4),
    ("ICT 2207", "Financial and Managerial Accounting", 3.0, 4),
    ("ICT 2209", "Innovation and Entrepreneurship", 3.0, 4),
    ("ICT 2202", "Algorithm Analysis and Design Lab", 1.5, 4),
    ("ICT 2204", "Analog and Digital Communication Lab", 1.5, 4),
    ("ICT 2200", "Project Work - II and Course Viva", 1.0, 4),

    ("ICT 3101", "Operating Systems", 3.0, 5),
    ("ICT 3103", "Database Management System", 3.0, 5),
    ("ICT 3105", "Software Engineering Theories and Practices", 3.0, 5),
    ("ICT 3107", "ICT Business Analytics and Data Visualization", 3.0, 5),
    ("ICT 3109", "Principles of Economics", 3.0, 5),
    ("ICT 3102", "Operating Systems Lab", 1.5, 5),
    ("ICT 3104", "Database Management System Lab", 1.5, 5),
    ("ICT 3106", "Software Engineering Theories and Practices Lab", 1.0, 5),
    ("ICT 3100", "Course Viva", 0.5, 5),

    ("ICT 3201", "Internet and Web Technology", 3.0, 6),
    ("ICT 3203", "Artificial Intelligence and Neural Networks", 3.0, 6),
    ("ICT 3205", "Software Architecture and Design Pattern", 3.0, 6),
    ("ICT 3207", "Information and Data Security", 3.0, 6),
    ("ICT 3209", "Smart Sensors and Internet of Things", 3.0, 6),
    ("ICT 3202", "Internet and Web Technology Lab", 1.5, 6),
    ("ICT 3204", "Artificial Intelligence and Neural Networks Lab", 1.5, 6),
    ("ICT 3206", "Software Architecture and Design Pattern Lab", 1.5, 6),
    ("ICT 3200", "Project Work - III and Course Viva", 1.0, 6),

    ("ICT 4100", "Internship", 18.0, 7),
    ("ICT 4101", "Cloud Computing and Web Services", 3.0, 7),
    ("ICT 4102", "Cloud Computing and Web Services Lab", 1.5, 7),
    ("ICT 4103", "Mobile Application Development", 3.0, 7),
    ("ICT 4104", "Mobile Application Development Lab", 1.5, 7),
    ("ICT 4105", "Computer Vision and Robotics", 3.0, 7),
    ("ICT 4106", "Computer Vision and Robotics Lab", 1.5, 7),
    ("ICT 4107", "Cyber Security and ICT Auditing", 3.0, 7),
    ("ICT 4108", "Cyber Security and ICT Auditing Lab", 1.5, 7),
    ("ICT 4109", "Cryptography and Network Security", 3.0, 7),
    ("ICT 4110", "Cryptography and Network Security Lab", 1.5, 7),
    ("ICT 4111", "Computer Network Service and Management", 3.0, 7),
    ("ICT 4112", "Computer Network Service and Management Lab", 1.5, 7),
    ("ICT 4113", "Big Data Analytics and Application", 3.0, 7),
    ("ICT 4114", "Big Data Analytics and Application Lab", 1.5, 7),
    ("ICT 4115", "Human Computer Interaction", 3.0, 7),
    ("ICT 4116", "Human Computer Interaction Lab", 1.5, 7),
    ("ICT 4117", "Software Verification and Validation", 3.0, 7),
    ("ICT 4118", "Software Verification and Validation Lab", 1.5, 7),
    ("ICT 4119", "Computer Architecture and Microprocessor", 3.0, 7),
    ("ICT 4120", "Computer Architecture and Microprocessor Lab", 1.5, 7),

    ("ICT 4201", "Software Project Management", 3.0, 8),
    ("ICT 4203", "Machine Learning", 3.0, 8),
    ("ICT 4205", "Software Documentation and Quality Assurance", 3.0, 8),
    ("ICT 4202", "Software Project Management Lab", 1.5, 8),
    ("ICT 4200", "Research Project", 5.0, 8),
    ("ICT 4207", "Natural Language Processing", 3.0, 8),
    ("ICT 4209", "Parallel and Distributed System", 3.0, 8),
    ("ICT 4211", "Data Mining and Knowledge Discovery", 3.0, 8),
    ("ICT 4213", "Digital Image Processing", 3.0, 8),
    ("ICT 4215", "Digital Healthcare and Informatics", 3.0, 8),
    ("ICT 4217", "Simulation and Optimization Techniques", 3.0, 8),
    ("ICT 4219", "Wireless and Cellular Networks", 3.0, 8),
    ("ICT 4221", "Embedded System Design", 3.0, 8),
    ("ICT 4223", "Research Methodology", 3.0, 8),
    ("ICT 4225", "Digital Forensic", 3.0, 8),
    ("ICT 4227", "Optical Fiber Communication", 3.0, 8),
    ("ICT 4229", "Microwave Engineering and Satellite Communication", 3.0, 8),
    ("ICT 4231", "Multimedia Communication", 3.0, 8),
    ("ICT 4233", "Introduction to 3D Modeling and Design", 3.0, 8),
    ("ICT 4235", "Enterprise Resource Planning and Systems", 3.0, 8),
    ("ICT 4237", "Augmented Reality", 3.0, 8),
    ("ICT 4239", "Applied Data Science", 3.0, 8),
    ("ICT 4241", "Human Centered Design Method", 3.0, 8),
    ("ICT 4243", "IT Professional and Ethics", 3.0, 8),
    ("ICT 4245", "ICT Risk Management and Disaster Control", 3.0, 8),
    ("ICT 4247", "Contemporary Course on ICT - I", 3.0, 8),
    ("ICT 4249", "Contemporary Course on ICT - II", 3.0, 8),
]


class Command(BaseCommand):
    help = "Seed Rooms, TimeSlots, and Courses from the IIT-JU syllabus"

    def handle(self, *args, **options):
        for name in ROOMS:
            _, created = Room.objects.get_or_create(name=name)
            self.stdout.write(f"Room {name}: {'created' if created else 'already exists'}")

        for label, order in TIME_SLOTS:
            _, created = TimeSlot.objects.get_or_create(label=label, defaults={"order": order})
            self.stdout.write(f"TimeSlot {label}: {'created' if created else 'already exists'}")

        for code, title, credit, semester in COURSES:
            _, created = Course.objects.get_or_create(
                code=code,
                defaults={"title": title, "credit": credit, "semester": semester},
            )
            self.stdout.write(f"Course {code}: {'created' if created else 'already exists'}")

        self.stdout.write(self.style.SUCCESS("Seeding complete."))