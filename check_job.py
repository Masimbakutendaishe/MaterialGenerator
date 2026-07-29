from app import create_app
from app.models.generation_job import GenerationJob

app = create_app()
with app.app_context():
    job = GenerationJob.query.get("d6e9bb6f-3d8b-4437-a5f6-5aa8b01e5e2e")
    if job is None:
        print("JOB NOT FOUND")
    else:
        print("status:", job.status)
        print("error_message:", job.error_message)
        print("task_id:", job.task_id)
