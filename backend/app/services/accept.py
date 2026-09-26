"""竣工验收业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.store import store

MODULE = "accept"
REQUIRED_FIELDS = ["验收单号", "关联施工", "验收项目"]
OPTIONAL_FIELDS = ["验收标准", "验收结论", "验收人员", "验收日期", "登记日期"]
STATUS_ORDER = ["待验收", "验收中", "已通过", "需返工"]
ACTION_RULES = {"开始验收": "验收中", "确认通过": "已通过", "下发返工": "需返工"}
NEGATIVE_ACTIONS = []
CONCLUDED_STATUSES = ("已通过", "需返工")
PENDING_STATUSES = ("待验收", "验收中")
OVERVIEW_RULE = (
    "同一验收单号只统计最新一次提交；返工后重新提交不重复计入通过数；"
    "已出结论（已通过/需返工）但验收结论缺失的单据不进入统计，并在不合规清单中提示。"
)


def _parse_day(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


class AcceptService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("验收单号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS + OPTIONAL_FIELDS})
        if not str(entry.get("登记日期") or "").strip():
            entry["登记日期"] = date.today().isoformat()
        entry["返工次数"] = _to_int(values.get("返工次数"))
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"验收单 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于竣工验收可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        if action == "下发返工":
            entry["返工次数"] = _to_int(entry.get("返工次数")) + 1
        if action == "确认通过" and not str(entry.get("验收日期") or "").strip():
            entry["验收日期"] = date.today().isoformat()
        return entry, f"验收单已{action}"

    def overview(self, *, start: date | None = None, end: date | None = None) -> dict[str, Any]:
        """结论概览：按验收项目与承接单位汇总通过、返工、待验收件数及返工次数、平均验收天数。"""
        scoped = [row for row in store.rows(MODULE) if self._in_period(row, start, end)]

        # 同一验收单号只统计一次：保留最新提交的一条，返工次数按单号累加。
        latest: dict[str, dict[str, Any]] = {}
        rework_by_no: dict[str, int] = {}
        order: list[str] = []
        for row in scoped:
            no = str(row.get("验收单号") or "").strip() or f"未编号-{row.get('id')}"
            if no not in latest:
                order.append(no)
                latest[no] = row
            elif int(row.get("id", 0)) > int(latest[no].get("id", 0)):
                latest[no] = row
            rework_by_no[no] = rework_by_no.get(no, 0) + _to_int(row.get("返工次数"))

        contractors = {
            str(work.get("施工编号") or "").strip(): str(work.get("承接单位") or "").strip()
            for work in store.rows("work")
            if str(work.get("施工编号") or "").strip()
        }

        groups: dict[tuple[str, str], dict[str, Any]] = {}
        excluded: list[dict[str, Any]] = []
        all_days: list[int] = []
        totals = {"已通过": 0, "需返工": 0, "待验收": 0, "返工次数": 0}
        for no in order:
            row = latest[no]
            status = str(row.get("status") or "")
            missing = []
            if not str(row.get("验收项目") or "").strip():
                missing.append("验收项目")
            if status in CONCLUDED_STATUSES and not str(row.get("验收结论") or "").strip():
                missing.append("验收结论")
            if missing:
                excluded.append({
                    "验收单号": no,
                    "不合规项": "、".join(missing),
                    "提示": f"验收单 {no} 缺少{'、'.join(missing)}，未纳入统计",
                })
                continue

            project = str(row.get("验收项目")).strip()
            contractor = contractors.get(str(row.get("关联施工") or "").strip()) or "未关联单位"
            key = (project, contractor)
            group = groups.setdefault(key, {
                "验收项目": project,
                "承接单位": contractor,
                "已通过": 0,
                "需返工": 0,
                "待验收": 0,
                "返工次数": 0,
                "_days": [],
            })
            bucket = "已通过" if status == "已通过" else "需返工" if status == "需返工" else "待验收"
            group[bucket] += 1
            totals[bucket] += 1
            group["返工次数"] += rework_by_no[no]
            totals["返工次数"] += rework_by_no[no]
            days = self._accept_days(row)
            if status == "已通过" and days is not None:
                group["_days"].append(days)
                all_days.append(days)

        group_rows = []
        for group in groups.values():
            days = group.pop("_days")
            group["平均验收天数"] = round(sum(days) / len(days), 1) if days else None
            group_rows.append(group)
        group_rows.sort(key=lambda item: (item["验收项目"], item["承接单位"]))

        cards = [
            {"label": "已通过", "value": totals["已通过"]},
            {"label": "需返工", "value": totals["需返工"]},
            {"label": "待验收", "value": totals["待验收"]},
            {"label": "返工次数", "value": totals["返工次数"]},
            {"label": "平均验收天数", "value": round(sum(all_days) / len(all_days), 1) if all_days else 0},
        ]
        return {
            "period": {
                "start": start.isoformat() if start else None,
                "end": end.isoformat() if end else None,
            },
            "cards": cards,
            "groups": group_rows,
            "excluded": excluded,
            "rule": OVERVIEW_RULE,
        }

    @staticmethod
    def _in_period(row: dict[str, Any], start: date | None, end: date | None) -> bool:
        if start is None and end is None:
            return True
        day = _parse_day(row.get("验收日期")) or _parse_day(row.get("登记日期"))
        if day is None:
            return False
        if start is not None and day < start:
            return False
        if end is not None and day > end:
            return False
        return True

    @staticmethod
    def _accept_days(row: dict[str, Any]) -> int | None:
        begin = _parse_day(row.get("登记日期"))
        finish = _parse_day(row.get("验收日期"))
        if begin is None or finish is None:
            return None
        return max((finish - begin).days, 0)
