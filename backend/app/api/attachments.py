"""附件列表与下载（下载路径限定在 data/ 目录内）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import ATTACHMENT_DIR
from ..database import get_db
from ..models import Attachment
from .. import schemas

router = APIRouter(prefix="/attachments", tags=["attachments"])


@router.get("", response_model=list[schemas.AttachmentOut])
def list_attachments(
    task_id: int | None = None,
    parse_status: str | None = None,
    db: Session = Depends(get_db),
):
    stmt = select(Attachment).order_by(Attachment.id.desc())
    if task_id is not None:
        stmt = stmt.where(Attachment.task_id == task_id)
    if parse_status:
        stmt = stmt.where(Attachment.parse_status == parse_status)
    return list(db.execute(stmt).scalars())


@router.get("/{attachment_id}/download")
def download_attachment(attachment_id: int, db: Session = Depends(get_db)):
    row = db.get(Attachment, attachment_id)
    if row is None or not row.file_path:
        raise HTTPException(404, "附件不存在或尚未下载完成")

    # file_path 相对 data/ 目录，校验解析后不得越界
    target = (ATTACHMENT_DIR / row.file_path.removeprefix("attachments/").removeprefix("/")).resolve()
    try:
        target.relative_to(ATTACHMENT_DIR.resolve())
    except ValueError:
        raise HTTPException(400, "非法文件路径")
    if not target.exists():
        raise HTTPException(404, "文件已被移动或删除")

    return FileResponse(
        target,
        filename=row.filename or target.name,
        media_type="application/octet-stream",
    )
