/** 竣工验收共享类型与接口：列表按单据聚合，概览按「验收项目 × 承接单位」分组。 */
export type AcceptRow = Record<string, string | number | null>

export interface OverviewCard {
  label: string
  value: number | null
  unit?: string
}

export interface OverviewIssue {
  提交序号: number | null
  字段: string
  问题: string
}

export interface OverviewInvalidDoc {
  验收单号: string
  验收项目: string
  承接单位: string
  问题: OverviewIssue[]
}

export interface OverviewGroup {
  验收项目: string
  承接单位: string
  passed: number
  rework: number
  pending: number
  rework_count: number
  avg_days: number | null
  pass_rate: number | null
}

export interface AcceptOverview {
  range: string
  start: string | null
  end: string | null
  cards: OverviewCard[]
  groups: OverviewGroup[]
  invalid_docs: OverviewInvalidDoc[]
  total_docs: number
}

export interface AcceptDocument {
  验收单号: string
  验收项目: string
  承接单位: string
  关联施工: string
  status: string
  latest: AcceptRow
  rework_count: number
  submit_count: number
  issues: OverviewIssue[]
  items: AcceptRow[]
}

export const RANGE_OPTIONS = [
  { key: 'month', label: '本月' },
  { key: 'quarter', label: '近三个月' },
  { key: 'year', label: '本年度' },
  { key: 'all', label: '全部时间' },
]
