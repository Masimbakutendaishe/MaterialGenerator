# Creates a demo org/user for local testing
"""Seeds the database with a demo organization, admin user, and sample syllabi for quick testing.
Run with: python scripts/seed_data.py

Safe to run multiple times — checks for existing data before creating duplicates.
"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app
from app.extensions import db
from app.models.organization import Organization
from app.models.user import User
from app.models.syllabus import Syllabus

DEMO_ORG_NAME = "Demo Training Institute"
DEMO_ADMIN_EMAIL = "admin@demo.co.za"
DEMO_ADMIN_PASSWORD = "DemoPass123!"

SAMPLE_SYLLABI = [
    {
        "title": "Basic Fire Safety in the Workplace",
        "seta": "MERSETA",
        "nqf_level": "2",
        "units": [
            {
                "name": "Unit 1: Understanding Fire Hazards",
                "outcomes": [
                    "Identify common causes of workplace fires",
                    "Recognize fire hazard warning signs and classifications",
                ],
            },
            {
                "name": "Unit 2: Fire Prevention Measures",
                "outcomes": [
                    "Apply correct storage procedures for flammable materials",
                    "Conduct basic fire hazard housekeeping checks",
                ],
            },
            {
                "name": "Unit 3: Emergency Response",
                "outcomes": [
                    "Operate a fire extinguisher correctly using the PASS technique",
                    "Follow workplace fire evacuation procedures",
                ],
            },
        ],
    },
    {
        "title": "Introduction to Occupational Health and Safety",
        "seta": "MERSETA",
        "nqf_level": "3",
        "units": [
            {
                "name": "Unit 1: OHS Legal Framework",
                "outcomes": [
                    "Explain key provisions of the Occupational Health and Safety Act",
                    "Identify employer and employee responsibilities under OHS law",
                ],
            },
            {
                "name": "Unit 2: Hazard Identification and Risk Assessment",
                "outcomes": [
                    "Conduct a basic workplace hazard identification walk-through",
                    "Apply a simple risk assessment matrix",
                ],
            },
        ],
    },
]


def seed():
    app = create_app()
    with app.app_context():
        org = Organization.query.filter_by(name=DEMO_ORG_NAME).first()
        if org:
            print(f"Organization '{DEMO_ORG_NAME}' already exists (id: {org.id}) — skipping creation.")
        else:
            org = Organization(name=DEMO_ORG_NAME, plan="pay_per_use")
            db.session.add(org)
            db.session.flush()
            print(f"Created organization '{DEMO_ORG_NAME}' (id: {org.id})")

        admin = User.query.filter_by(email=DEMO_ADMIN_EMAIL).first()
        if admin:
            print(f"User '{DEMO_ADMIN_EMAIL}' already exists — skipping creation.")
        else:
            admin = User(organization_id=org.id, email=DEMO_ADMIN_EMAIL, role="org_admin")
            admin.set_password(DEMO_ADMIN_PASSWORD)
            db.session.add(admin)
            print(f"Created admin user '{DEMO_ADMIN_EMAIL}'")

        db.session.commit()

        existing_titles = {s.title for s in Syllabus.query.filter_by(organization_id=org.id).all()}
        for sample in SAMPLE_SYLLABI:
            if sample["title"] in existing_titles:
                print(f"Syllabus '{sample['title']}' already exists — skipping.")
                continue

            syllabus = Syllabus(
                organization_id=org.id,
                created_by_user_id=admin.id,
                title=sample["title"],
                source="typed",
                content={"units": sample["units"]},
                accreditation_info={"seta": sample["seta"], "nqf_level": sample["nqf_level"]},
            )
            db.session.add(syllabus)
            print(f"Created syllabus '{sample['title']}'")

        db.session.commit()

        print("\n--- Seed complete ---")
        print(f"Login with: {DEMO_ADMIN_EMAIL} / {DEMO_ADMIN_PASSWORD}")
        print(f"Organization ID: {org.id}")


if __name__ == "__main__":
    seed()