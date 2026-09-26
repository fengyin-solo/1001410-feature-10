"""竣工验收业务规则：状态流转、字段校验与结论概览口径都收在这里。

一张验收单可能经历多次「提交→返工→重新报验→复验」，每次提交在仓库里是一行。
对外（列表、详情、概览）一律以验收单号聚合：
- 列表一行一张单，取最新一次提交；
- 同一单概览只统计一次，返工后通过的不再重复计入通过数；
- 返工次数看这张单全部历史行里「需返工」的行数；
- 平均验收天数只对已通过单计算：最终通过日 − 最早报验日。
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.store import store

MODULE = "accept"
REQUIRED_FIELDS = ["验收单号", "关联施工", "验收项目", "承接单位"]
STATUS_ORDER = ["待验收", "验收中", "已通过", "需返工"]
ACTION_RULES = {"开始验收": "验收中", "确认通过": "已通过", "下发返工": "需返工"}
NEGATIVE_ACTIONS = []
# 已下过结论的状态：这些提交行必须带验收结论，否则单据不合规、不进统计。
CONCLUDED_STATUSES = {"已通过", "需返工"}
PENDING_STATUSES = {"待验收", "验收中"}

# 概览支持的时间段：key -> (距今天的天数下界, 文案)；None 表示不做时间过滤。
RANGE_PRESETS = {
    "month": ("本月", None),
    "quarter": ("近三个月", 90),
    "year": ("本年度", None),
    "all": ("全部时间", None),
}


def _parse_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _month_bounds(today: date) -> tuple[date, date]:
    start = today.replace(day=1)
    next_month = start.replace(day=28) + timedelta(days=4)
    return start, next_month - timedelta(days=next_month.day)


def _year_bounds(today: date) -> tuple[date, date]:
    return today.replace(month=1, day=1), today.replace(month=12, day=31)


def resolve_range(
    range_key: str,
    *,
    start: str | None = None,
    end: str | None = None,
    today: date | None = None,
) -> tuple[date | None, date | None]:
    """把时间段标识或自定义起止日期换算成闭区间，口径集中在这一处。"""
    today = today or date.today()
    if range_key == "custom":
        return _parse_date(start), _parse_date(end)
    if range_key == "month":
        return _month_bounds(today)
    if range_key == "quarter":
        return today - timedelta(days=90), today
    if range_key == "year":
        return _year_bounds(today)
    return None, None


class AcceptService:
    # ---- 单据聚合 -------------------------------------------------------

    def _documents(self) -> list[dict[str, Any]]:
        """把提交行按验收单号聚合成单据，每张单带最新提交、历史行与合规问题。"""
        rows = store.rows(MODULE)
        groups: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            no = str(row.get("验收单号") or "").strip()
            groups.setdefault(no, []).append(row)

        documents: list[dict[str, Any]] = []
        for no, items in groups.items():
            items.sort(
                key=lambda r: (
                    _parse_date(r.get("报验日期")) or date.min,
                    int(r.get("id", 0)),
                )
            )
            latest = items[-1]
            project = str(latest.get("验收项目") or "").strip()
            unit = str(latest.get("承接单位") or "").strip()
            documents.append(
                {
                    "验收单号": no,
                    "验收项目": project,
                    "承接单位": unit,
                    "关联施工": str(latest.get("关联施工") or "").strip(),
                    "status": latest.get("status"),
                    "latest": latest,
                    "items": items,
                    "rework_count": sum(1 for row in items if row.get("status") == "需返工"),
                    "submit_count": len(items),
                    "issues": self._compliance_issues(no, project, unit, items),
                }
            )
        documents.sort(key=lambda doc: doc["验收单号"])
        return documents

    @staticmethod
    def _compliance_issues(
        no: str, project: str, unit: str, items: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """找出单据里不能进入统计的不合规项，定位到具体哪一次提交、缺了什么。"""
        issues: list[dict[str, Any]] = []
        if not no:
            issues.append({"提交序号": None, "字段": "验收单号", "问题": "验收单号缺失，无法去重"})
        if not project:
            issues.append({"提交序号": len(items), "字段": "验收项目", "问题": "验收项目缺失，无法归入概览分组"})
        if not unit:
            issues.append({"提交序号": len(items), "字段": "承接单位", "问题": "承接单位缺失，无法归入概览分组"})
        for index, row in enumerate(items, start=1):
            if row.get("status") in CONCLUDED_STATUSES and not str(row.get("验收结论") or "").strip():
                issues.append(
                    {
                        "提交序号": index,
                        "字段": "验收结论",
                        "问题": f"第{index}次提交状态为「{row.get('status')}」但验收结论缺失",
                    }
                )
        return issues

    @staticmethod
    def _effective_date(doc: dict[str, Any]) -> date | None:
        """单据归属时间段：优先取最新提交的验收日期，尚未验收则取报验日期。"""
        latest = doc["latest"]
        return _parse_date(latest.get("验收日期")) or _parse_date(latest.get("报验日期"))

    @staticmethod
    def _accept_days(doc: dict[str, Any]) -> float | None:
        """已通过单的验收天数：最终通过日 − 最早报验日。"""
        if doc["status"] != "已通过":
            return None
        passed = next(
            (row for row in reversed(doc["items"]) if row.get("status") == "已通过"),
            None,
        )
        if passed is None:
            return None
        end = _parse_date(passed.get("验收日期"))
        start = _parse_date(doc["items"][0].get("报验日期"))
        if end is None or start is None:
            return None
        return float((end - start).days)

    # ---- 列表与详情 -----------------------------------------------------

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        """列表按单据返回（同一验收单只出现一行，取最新提交）。"""
        docs = self._documents()
        if keyword:
            docs = [doc for doc in docs if keyword in doc["验收单号"]]
        if status:
            docs = [doc for doc in docs if doc["status"] == status]
        total = len(docs)
        start = max(page - 1, 0) * size
        return [self._list_row(doc) for doc in docs[start:start + size]], total

    def _list_row(self, doc: dict[str, Any]) -> dict[str, Any]:
        latest = dict(doc["latest"])
        latest.update(
            {
                "验收项目": doc["验收项目"],
                "承接单位": doc["承接单位"],
                "返工次数": doc["rework_count"],
                "提交次数": doc["submit_count"],
                "不合规": bool(doc["issues"]),
            }
        )
        return latest

    def get_document(self, doc_no: str) -> dict[str, Any] | None:
        for doc in self._documents():
            if doc["验收单号"] == doc_no:
                return doc
        return None

    def find_doc_by_row_id(self, entry_id: int) -> dict[str, Any] | None:
        row = store.find(MODULE, entry_id)
        if row is None:
            return None
        no = str(row.get("验收单号") or "").strip()
        return self.get_document(no)

    # ---- 登记与状态流转 -------------------------------------------------

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        no = str(values["验收单号"]).strip()
        if any(str(row.get("验收单号") or "").strip() == no for row in rows):
            return None, ["验收单号"]
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["验收标准"] = values.get("验收标准", "")
        entry["验收结论"] = str(values.get("验收结论") or "").strip()
        entry["验收人员"] = str(values.get("验收人员") or "").strip()
        entry["报验日期"] = str(values.get("报验日期") or "").strip() or date.today().isoformat()
        entry["验收日期"] = str(values.get("验收日期") or "").strip()
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(
        self,
        entry_id: int,
        action: str,
        *,
        conclusion: str = "",
    ) -> tuple[dict[str, Any] | None, str]:
        doc = self.find_doc_by_row_id(entry_id)
        if doc is None:
            return None, f"验收单 {entry_id} 不存在或已归档"
        latest = doc["latest"]
        current = latest["status"]

        if action == "重新报验":
            if current != "需返工":
                return None, "只有「需返工」的验收单可以重新报验"
            rows = store.rows(MODULE)
            resubmit = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
            for field in ("验收单号", "关联施工", "承接单位", "验收项目", "验收标准"):
                resubmit[field] = latest.get(field, "")
            resubmit.update(
                {
                    "验收结论": "",
                    "验收人员": "",
                    "报验日期": date.today().isoformat(),
                    "验收日期": "",
                    "status": "待验收",
                    "pending": True,
                    "abnormal": False,
                }
            )
            rows.append(resubmit)
            return resubmit, "返工整改完成，已重新提交验收"

        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于竣工验收可执行范围"

        if action == "开始验收":
            if current != "待验收":
                return None, f"当前状态为「{current}」，无需再开始验收"
            latest["验收人员"] = latest.get("验收人员") or "值班验收员"
        elif action == "确认通过":
            if current == "待验收":
                return None, "验收尚未开始，不能直接确认通过"
            latest["验收结论"] = str(conclusion or "").strip() or "验收合格，同意通过"
            latest["验收日期"] = str(latest.get("验收日期") or "").strip() or date.today().isoformat()
        elif action == "下发返工":
            if current not in ("验收中", "需返工"):
                return None, f"当前状态为「{current}」，不能下发返工"
            latest["验收结论"] = str(conclusion or "").strip() or "验收不合格，需返工整改"
            latest["验收日期"] = str(latest.get("验收日期") or "").strip() or date.today().isoformat()

        target = ACTION_RULES[action]
        latest["status"] = target
        latest["pending"] = target in PENDING_STATUSES
        latest["abnormal"] = target == "需返工"
        return latest, f"验收单已{action}"

    # ---- 结论概览 -------------------------------------------------------

    def overview(
        self,
        *,
        range_key: str = "month",
        start: str | None = None,
        end: str | None = None,
    ) -> dict[str, Any]:
        """按时间段统计各「验收项目 × 承接单位」的通过/返工/待验收件数。

        不合规单据整单剔除，并在 invalid_docs 里指出是哪一项不合规。
        """
        begin, finish = resolve_range(range_key, start=start, end=end)
        groups: dict[tuple[str, str], dict[str, Any]] = {}
        invalid_docs: list[dict[str, Any]] = []
        passed_days: list[float] = []
        rework_total = 0

        for doc in self._documents():
            if doc["issues"]:
                invalid_docs.append(
                    {
                        "验收单号": doc["验收单号"] or f"行 {doc['latest'].get('id')}",
                        "验收项目": doc["验收项目"] or "未填写",
                        "承接单位": doc["承接单位"] or "未填写",
                        "问题": doc["issues"],
                    }
                )
                continue
            day = self._effective_date(doc)
            if day is None or (begin and day < begin) or (finish and day > finish):
                continue

            key = (doc["验收项目"], doc["承接单位"])
            bucket = groups.setdefault(
                key,
                {
                    "验收项目": doc["验收项目"],
                    "承接单位": doc["承接单位"],
                    "passed": 0,
                    "rework": 0,
                    "pending": 0,
                    "rework_count": 0,
                    "days": [],
                },
            )
            status = doc["status"]
            if status == "已通过":
                bucket["passed"] += 1
                days = self._accept_days(doc)
                if days is not None:
                    bucket["days"].append(days)
                    passed_days.append(days)
            elif status == "需返工":
                bucket["rework"] += 1
            else:
                bucket["pending"] += 1
            bucket["rework_count"] += doc["rework_count"]
            rework_total += doc["rework_count"]

        rows_out: list[dict[str, Any]] = []
        totals = {"passed": 0, "rework": 0, "pending": 0}
        for bucket in groups.values():
            days = bucket.pop("days")
            bucket["avg_days"] = round(sum(days) / len(days), 1) if days else None
            concluded = bucket["passed"] + bucket["rework"]
            bucket["pass_rate"] = round(bucket["passed"] / concluded, 4) if concluded else None
            rows_out.append(bucket)
            totals["passed"] += bucket["passed"]
            totals["rework"] += bucket["rework"]
            totals["pending"] += bucket["pending"]

        # 返工多的排前面，再按已通过数、项目名稳定排序，方便看出哪些单位反复返工。
        rows_out.sort(
            key=lambda item: (-item["rework_count"], -item["rework"], -item["passed"], item["验收项目"])
        )
        doc_total = totals["passed"] + totals["rework"] + totals["pending"]
        cards = [
            {"label": "纳入统计单据", "value": doc_total},
            {"label": "已通过", "value": totals["passed"]},
            {"label": "需返工", "value": totals["rework"]},
            {"label": "待验收", "value": totals["pending"]},
            {"label": "累计返工次数", "value": rework_total},
            {
                "label": "平均验收天数",
                "value": round(sum(passed_days) / len(passed_days), 1) if passed_days else None,
                "unit": "天",
            },
        ]
        return {
            "range": range_key,
            "start": begin.isoformat() if begin else None,
            "end": finish.isoformat() if finish else None,
            "cards": cards,
            "groups": rows_out,
            "invalid_docs": invalid_docs,
            "total_docs": doc_total,
        }
