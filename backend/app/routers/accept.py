"""竣工验收接口：维护验收单，覆盖开始验收、确认通过、下发返工等动作，并提供结论概览。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.accept import RANGE_PRESETS, AcceptService

router = APIRouter(prefix="/api/accept", tags=["竣工验收"])

service = AcceptService()

LIST_FIELDS = ["验收单号", "关联施工", "承接单位", "验收项目", "验收标准", "验收结论", "验收人员", "报验日期", "验收日期", "返工次数", "提交次数"]
STATUSES = ["待验收", "验收中", "已通过", "需返工"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按验收单号检索"),
    status: str | None = Query(default=None, description="待验收、验收中、已通过、需返工"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按验收单号与状态过滤竣工验收列表；同一验收单只出现一行（最新一次提交）。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/overview")
def overview(
    range: str = Query(default="month", description="时间段：month/quarter/year/all/custom"),
    start: str | None = Query(default=None, description="自定义开始日期，range=custom 时生效"),
    end: str | None = Query(default=None, description="自定义结束日期，range=custom 时生效"),
) -> dict[str, Any]:
    """结论概览：按验收项目与承接单位给出通过/返工/待验收件数、返工次数与平均验收天数。

    验收结论缺失的单据不进入统计，并在返回的 invalid_docs 里指出具体不合规项。
    """
    if range not in RANGE_PRESETS and range != "custom":
        raise HTTPException(status_code=400, detail=f"时间段「{range}」不支持，请用 month/quarter/year/all/custom")
    return service.overview(range_key=range, start=start, end=end)


@router.get("/doc/{doc_no}")
def get_document(doc_no: str) -> dict[str, Any]:
    """按验收单号读取整单：最新提交加全部提交/复验历史。"""
    doc = service.get_document(doc_no)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"验收单 {doc_no} 不存在或已归档")
    return {
        "验收单号": doc["验收单号"],
        "验收项目": doc["验收项目"],
        "承接单位": doc["承接单位"],
        "关联施工": doc["关联施工"],
        "status": doc["status"],
        "latest": doc["latest"],
        "rework_count": doc["rework_count"],
        "submit_count": doc["submit_count"],
        "issues": doc["issues"],
        "items": doc["items"],
    }


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条提交行明细；不存在时给出可读的错误说明。"""
    doc = service.find_doc_by_row_id(entry_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"验收单 {entry_id} 不存在或已归档")
    return doc["latest"]


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一张验收单，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        if missing == ["验收单号"]:
            return ActionResult(ok=False, message="验收单号已存在，同一单据的重新报验请走「重新报验」动作")
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="验收单已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条验收单执行开始验收、确认通过、下发返工、重新报验；不允许的动作会被拦下并说明原因。"""
    values = payload.values
    action = str(values.get("action") or "").strip()
    conclusion = str(values.get("验收结论") or "").strip()
    entry, message = service.run_action(entry_id, action, conclusion=conclusion)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.get("/export/data")
def export_entries() -> dict[str, Any]:
    """导出竣工验收清单：返回当前全部单据（按验收单号聚合后的最新提交）。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "accept", "total": total, "items": items}
