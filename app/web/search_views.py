"""Global search across syllabi, packages, and standalone generation jobs."""
from flask import Blueprint, render_template, request
from flask_login import login_required, current_user
from app.models.syllabus import Syllabus
from app.models.generation_job import GenerationJob
from app.models.material_package import MaterialPackage
from app.models.review import MaterialReview

search_web_bp = Blueprint("search_web", __name__, url_prefix="/search")


@search_web_bp.route("/")
@login_required
def search():
    query = request.args.get("q", "").strip()
    results = {"syllabi": [], "packages": [], "jobs": []}

    if query:
        org_id = current_user.organization_id

        results["syllabi"] = Syllabus.query.filter(
            Syllabus.organization_id == org_id,
            Syllabus.title.ilike(f"%{query}%")
        ).order_by(Syllabus.created_at.desc()).limit(20).all()

        matching_syllabus_ids = [s.id for s in Syllabus.query.filter(
            Syllabus.organization_id == org_id,
            Syllabus.title.ilike(f"%{query}%")
        ).all()]

        packages = MaterialPackage.query.filter(
            MaterialPackage.organization_id == org_id,
            MaterialPackage.syllabus_id.in_(matching_syllabus_ids)
        ).order_by(MaterialPackage.created_at.desc()).limit(20).all() if matching_syllabus_ids else []

        for pkg in packages:
            syllabus = Syllabus.query.get(pkg.syllabus_id)
            review = MaterialReview.query.filter_by(package_id=pkg.id).first()
            results["packages"].append({"package": pkg, "title": syllabus.title if syllabus else "Unknown", "review": review})

        standalone_jobs = GenerationJob.query.filter(
            GenerationJob.organization_id == org_id,
            GenerationJob.package_id.is_(None),
            GenerationJob.syllabus_id.in_(matching_syllabus_ids)
        ).order_by(GenerationJob.created_at.desc()).limit(20).all() if matching_syllabus_ids else []

        for job in standalone_jobs:
            syllabus = Syllabus.query.get(job.syllabus_id)
            review = MaterialReview.query.filter_by(generation_job_id=job.id).first()
            results["jobs"].append({"job": job, "title": syllabus.title if syllabus else "Unknown", "review": review})

        package_docs = GenerationJob.query.filter(
            GenerationJob.organization_id == org_id,
            GenerationJob.package_id.isnot(None),
            GenerationJob.document_subtype.ilike(f"%{query.replace(' ', '_')}%")
        ).order_by(GenerationJob.created_at.desc()).limit(20).all()

        for job in package_docs:
            syllabus = Syllabus.query.get(job.syllabus_id)
            results["jobs"].append({"job": job, "title": syllabus.title if syllabus else "Unknown", "review": None, "is_package_doc": True})

    return render_template("search/results.html", query=query, results=results)