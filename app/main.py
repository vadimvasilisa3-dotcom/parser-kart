from __future__ import annotations

import io
import zipfile
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from scraper.url_utils import is_org_url, normalize_org_url, resolve_org_url

from .config import AUTO_CLEANUP_AFTER_ZIP, MAX_MENU_ITEMS_DEFAULT, MAX_PHOTOS_DEFAULT, MAX_REVIEWS_DEFAULT, SCRAPE_MENU, SCRAPE_PHOTOS, SCRAPE_REVIEWS, STATIC_DIR
from .cleanup import cleanup_job_output
from .database import count_collected_orgs, create_job, get_job, init_db, list_jobs
from .dedupe import build_scope_key
from .jobs import job_runner

app = FastAPI(title="Парсер карт", version="0.2.0")


def _coerce_limit(value: object, default: int) -> int:
  """JSON null/пустое значение → дефолт (иначе 422 и [object Object] в UI)."""
  if value is None or value == "":
    return default
  try:
    return int(value)
  except (TypeError, ValueError):
    return default


class StartJobRequest(BaseModel):
    category: str | None = None
    city: str | None = None
    custom_query: str | None = None
    max_results: int = Field(default=10, ge=1, le=500)
    filter_no_website: bool = False
    filter_no_social: bool = False
    filter_no_phone: bool = False
    filter_no_photos: bool = False
    filter_no_reviews: bool = False
    filter_no_menu: bool = False
    filter_mode: str = Field(default="any", pattern="^(any|all)$")
    scrape_photos: bool = True
    scrape_reviews: bool = True
    scrape_menu: bool = True
    max_photos: int = Field(default=MAX_PHOTOS_DEFAULT, ge=1, le=10)
    max_reviews: int = Field(default=MAX_REVIEWS_DEFAULT, ge=0, le=50)
    max_menu_items: int = Field(default=MAX_MENU_ITEMS_DEFAULT, ge=0, le=200)
    dedupe: bool = True

    @field_validator("max_photos", mode="before")
    @classmethod
    def _max_photos(cls, v: object) -> int:
        return _coerce_limit(v, MAX_PHOTOS_DEFAULT)

    @field_validator("max_reviews", mode="before")
    @classmethod
    def _max_reviews(cls, v: object) -> int:
        return _coerce_limit(v, MAX_REVIEWS_DEFAULT)

    @field_validator("max_menu_items", mode="before")
    @classmethod
    def _max_menu_items(cls, v: object) -> int:
        return _coerce_limit(v, MAX_MENU_ITEMS_DEFAULT)


class OrgUrlJobRequest(BaseModel):
    org_url: str = Field(min_length=10)
    scrape_photos: bool = True
    scrape_reviews: bool = True
    scrape_menu: bool = True
    max_photos: int = Field(default=MAX_PHOTOS_DEFAULT, ge=1, le=10)
    max_reviews: int = Field(default=MAX_REVIEWS_DEFAULT, ge=0, le=50)
    max_menu_items: int = Field(default=MAX_MENU_ITEMS_DEFAULT, ge=0, le=200)

    @field_validator("max_photos", mode="before")
    @classmethod
    def _max_photos(cls, v: object) -> int:
        return _coerce_limit(v, MAX_PHOTOS_DEFAULT)

    @field_validator("max_reviews", mode="before")
    @classmethod
    def _max_reviews(cls, v: object) -> int:
        return _coerce_limit(v, MAX_REVIEWS_DEFAULT)

    @field_validator("max_menu_items", mode="before")
    @classmethod
    def _max_menu_items(cls, v: object) -> int:
        return _coerce_limit(v, MAX_MENU_ITEMS_DEFAULT)


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/collected/count")
def collected_count(
    category: str | None = None,
    city: str | None = None,
    custom_query: str | None = None,
) -> dict:
    scope_key = build_scope_key(category, city, custom_query)
    return {"scope_key": scope_key, "count": count_collected_orgs(scope_key)}


def _org_url_job_options(body: OrgUrlJobRequest) -> dict:
    return {
        "scrape_photos": body.scrape_photos,
        "scrape_reviews": body.scrape_reviews,
        "scrape_menu": body.scrape_menu,
        "max_photos": body.max_photos,
        "max_reviews": body.max_reviews,
        "max_menu_items": body.max_menu_items,
        "dedupe": False,
    }


@app.post("/api/jobs")
def start_job(body: StartJobRequest, background_tasks: BackgroundTasks) -> dict:
    query = body.custom_query or ""
    if is_org_url(query.strip()):
        return start_job_by_url(
            OrgUrlJobRequest(
                org_url=query.strip(),
                scrape_photos=body.scrape_photos,
                scrape_reviews=body.scrape_reviews,
                scrape_menu=body.scrape_menu,
                max_photos=body.max_photos,
                max_reviews=body.max_reviews,
                max_menu_items=body.max_menu_items,
            ),
            background_tasks,
        )
    if not query and not body.category and not body.city:
        raise HTTPException(400, "Укажите категорию и город или произвольный запрос")

    filters = {
        "no_website": body.filter_no_website,
        "no_social": body.filter_no_social,
        "no_phone": body.filter_no_phone,
        "no_photos": body.filter_no_photos,
        "no_reviews": body.filter_no_reviews,
        "no_menu": body.filter_no_menu,
        "mode": body.filter_mode,
    }
    options = {
        "scrape_photos": body.scrape_photos,
        "scrape_reviews": body.scrape_reviews,
        "scrape_menu": body.scrape_menu,
        "max_photos": body.max_photos,
        "max_reviews": body.max_reviews,
        "max_menu_items": body.max_menu_items,
        "dedupe": body.dedupe,
    }
    job_id = create_job(query, body.category, body.city, body.max_results, filters, options)
    background_tasks.add_task(job_runner.start, job_id)
    return {"job_id": job_id}


@app.post("/api/jobs/by-url")
def start_job_by_url(body: OrgUrlJobRequest, background_tasks: BackgroundTasks) -> dict:
    raw_url = body.org_url.strip()
    if not is_org_url(raw_url):
        raise HTTPException(
            400,
            "Нужна ссылка на организацию Яндекс.Карт (…/maps/org/…, ?oid=…, mode=poi с poi[uri] или …/maps/-/…)",
        )
    org_url = resolve_org_url(raw_url)
    options = {
        "org_url": org_url,
        "raw_org_url": raw_url,
        "single_org": True,
        **_org_url_job_options(body),
    }
    job_id = create_job(org_url, None, None, 1, {}, options)
    background_tasks.add_task(job_runner.start, job_id)
    return {"job_id": job_id, "org_url": org_url}


@app.get("/api/jobs")
def jobs_history() -> list[dict]:
    return list_jobs()


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str) -> dict:
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, "Задача не найдена")
    return job


def _job_file(job_id: str, field: str, label: str) -> FileResponse:
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, "Задача не найдена")
    path = job.get(field)
    if not path or not Path(path).is_file():
        raise HTTPException(404, f"{label} ещё не готов")
    return FileResponse(path, filename=Path(path).name)


@app.get("/api/jobs/{job_id}/excel")
def job_excel(job_id: str):
    return _job_file(job_id, "excel_path", "Excel")


@app.get("/api/jobs/{job_id}/json")
def job_json(job_id: str):
    return _job_file(job_id, "json_path", "JSON")


@app.get("/api/jobs/{job_id}/prompt")
def job_prompt(job_id: str):
    return _job_file(job_id, "prompt_path", "PROMPT.md")


@app.get("/api/jobs/{job_id}/agent-prompt")
def job_agent_prompt(job_id: str):
    return _job_file(job_id, "agent_prompt_path", "AGENT_WEBSITE.md")


@app.get("/api/jobs/{job_id}/archive")
def job_archive(job_id: str, background_tasks: BackgroundTasks):
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, "Задача не найдена")
    if job.get("files_cleaned"):
        raise HTTPException(410, "Файлы уже удалены с сервера — используйте ранее скачанный ZIP")
    output_dir = job.get("output_dir")
    if not output_dir or not Path(output_dir).is_dir():
        raise HTTPException(404, "Архив ещё не готов")

    buf = io.BytesIO()
    base = Path(output_dir)
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in base.rglob("*"):
            if path.is_file():
                zf.write(path, arcname=str(path.relative_to(base)))
    buf.seek(0)
    filename = f"parser-kart_{job_id[:8]}.zip"
    if AUTO_CLEANUP_AFTER_ZIP:
        background_tasks.add_task(cleanup_job_output, job_id, str(base))
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
