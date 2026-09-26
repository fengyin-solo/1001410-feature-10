"""竣工验收接口：维护验收单，覆盖开始验收、确认通过、下发返工等动作。"""
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.accept import AcceptService

router = APIRouter(prefix="/api/accept", tags=["竣工验收"])

service = AcceptService()

LIST_FIELDS = ["验收单号", "关联施工", "验收项目", "验收标准", "验收结论", "验收人员", "验收日期", "验收状态"]
STATUSES = ["待验收", "验收中", "已通过", "需返工"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按验收单号检索"),
    status: str | None = Query(default=None, description="待验收、验收中、已通过、需返工"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按验收单号与状态过滤竣工验收列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/overview")
def accept_overview(
    start: str | None = Query(default=None, description="统计起始日期，格式 YYYY-MM-DD"),
    end: str | None = Query(default=None, description="统计截止日期，格式 YYYY-MM-DD"),
) -> dict[str, Any]:
    """结论概览：按验收项目与承接单位汇总通过、返工、待验收件数，支持按时间段切换。"""
    try:
        start_day = date.fromisoformat(start) if start else None
        end_day = date.fromisoformat(end) if end else None
    except ValueError:
        raise HTTPException(status_code=400, detail="时间段格式应为 YYYY-MM-DD")
    if start_day and end_day and start_day > end_day:
        raise HTTPException(status_code=400, detail="开始日期不能晚于结束日期")
    return service.overview(start=start_day, end=end_day)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出竣工验收清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "accept", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条验收单明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"验收单 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条验收单，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="验收单已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条验收单执行开始验收、确认通过、下发返工；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
