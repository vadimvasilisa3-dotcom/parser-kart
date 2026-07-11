"""Удаление файлов сбора с диска (после скачивания ZIP)."""
from __future__ import annotations

import shutil
from pathlib import Path

from .database import append_log, update_job


def cleanup_job_output(job_id: str, output_dir: str) -> None:
    path = Path(output_dir)
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    update_job(
        job_id,
        output_dir="",
        excel_path="",
        json_path="",
        prompt_path="",
        agent_prompt_path="",
        files_cleaned=1,
        message="ZIP скачан — файлы удалены с сервера",
    )
    append_log(job_id, "Файлы сбора удалены с сервера (освобождение диска)")
