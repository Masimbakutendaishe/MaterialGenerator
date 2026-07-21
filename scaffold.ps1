# Run from inside seta-material-generator/ with venv active

$dirs = @(
    "app\models",
    "app\api",
    "app\services",
    "app\tasks",
    "app\templates",
    "app\static\css",
    "app\static\js",
    "app\utils",
    "migrations",
    "tests\unit",
    "tests\integration",
    "docker",
    "scripts"
)

foreach ($d in $dirs) {
    New-Item -ItemType Directory -Force -Path $d | Out-Null
}

$files = @{
    "app\__init__.py"                       = "# App factory — create_app()"
    "app\config.py"                         = "# Config classes: DevelopmentConfig, TestingConfig, ProductionConfig"
    "app\extensions.py"                     = "# db, migrate, jwt, limiter, celery instances (no circular imports)"

    "app\models\__init__.py"                = ""
    "app\models\organization.py"            = "# Organization model (tenant, branding)"
    "app\models\user.py"                    = "# User model, roles"
    "app\models\syllabus.py"                = "# Syllabus, SyllabusUnit models"
    "app\models\material.py"                = "# Textbook, Presentation, MaterialSection models"
    "app\models\generation_job.py"          = "# GenerationJob model (async status tracking)"
    "app\models\design_profile.py"          = "# DesignProfile model (structure/template choices)"

    "app\api\__init__.py"                   = ""
    "app\api\auth.py"                       = "# Login, token refresh endpoints"
    "app\api\organizations.py"              = "# Org CRUD endpoints"
    "app\api\syllabus.py"                   = "# Syllabus upload/type-in/AI-generate endpoints"
    "app\api\materials.py"                  = "# Material generation trigger + status + download endpoints"
    "app\api\admin.py"                      = "# Superadmin: org provisioning"

    "app\services\__init__.py"              = ""
    "app\services\ai_service.py"            = "# Wraps Anthropic API calls, prompt templates"
    "app\services\syllabus_service.py"      = "# Parse/normalize/generate syllabi"
    "app\services\document_service.py"      = "# Builds .docx from structured content"
    "app\services\presentation_service.py"  = "# Builds .pptx from structured content"
    "app\services\image_service.py"         = "# Sources/generates images and diagrams"
    "app\services\storage_service.py"       = "# S3/MinIO upload + presigned URL abstraction"

    "app\tasks\__init__.py"                 = ""
    "app\tasks\generation_tasks.py"         = "# Celery tasks: generate_textbook, generate_slides"

    "app\utils\__init__.py"                 = ""
    "app\utils\validators.py"               = "# Input validation helpers"
    "app\utils\security.py"                 = "# Password hashing, token helpers"

    "tests\unit\__init__.py"                = ""
    "tests\integration\__init__.py"         = ""

    "scripts\seed_data.py"                  = "# Creates a demo org/user for local testing"

    "docker\Dockerfile"                     = "# Container build for the Flask app"
    "docker\docker-compose.yml"             = "# postgres, redis, minio (already created earlier if you followed the guide)"
    "docker\nginx.conf"                     = "# Reverse proxy config (later, for production)"

    "celery_worker.py"                      = "# Celery entrypoint"
    "wsgi.py"                               = "# Flask entrypoint (gunicorn target)"
    "manage.py"                             = "# CLI commands: flask db, seed, etc."
    "README.md"                             = "# SETA/QCTO Material Generator"
    ".gitignore"                            = "venv/`n__pycache__/`n*.pyc`n.env`ninstance/`n*.log"
}

foreach ($f in $files.Keys) {
    if (-not (Test-Path $f)) {
        Set-Content -Path $f -Value $files[$f] -Encoding utf8
    }
}

Write-Host "Scaffold created." -ForegroundColor Green
