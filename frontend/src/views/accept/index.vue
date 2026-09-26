<template>
  <section class="page" data-module="accept">
    <header class="page-head">
      <div>
        <h2>竣工验收管理</h2>
        <p class="page-desc">维护验收单，围绕验收单号、关联施工、验收项目、验收标准做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记验收单</button>
        <button class="btn" type="button" @click="exportRows">导出竣工验收清单</button>
      </div>
    </header>

    <section class="overview-section">
      <header class="overview-head">
        <h3>结论概览</h3>
        <div class="period-bar">
          <button
            v-for="option in periodOptions"
            :key="option.key"
            class="btn period-btn"
            :class="{ primary: periodKey === option.key }"
            type="button"
            @click="switchPeriod(option.key)"
          >
            {{ option.label }}
          </button>
          <template v-if="periodKey === 'custom'">
            <input v-model="customStart" type="date" aria-label="开始日期" />
            <span class="period-sep">至</span>
            <input v-model="customEnd" type="date" aria-label="结束日期" />
            <button class="btn" type="button" @click="applyCustomPeriod">应用</button>
          </template>
        </div>
      </header>

      <div class="stat-row">
        <article v-for="item in overviewCards" :key="item.label" class="stat-card">
          <span class="stat-label">{{ item.label }}</span>
          <strong class="stat-value">{{ item.value }}</strong>
        </article>
      </div>

      <table class="data-table">
        <thead>
          <tr>
            <th v-for="column in overviewColumns" :key="column">{{ column }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="group in overviewGroups" :key="`${group.验收项目}-${group.承接单位}`">
            <td>{{ group.验收项目 }}</td>
            <td>{{ group.承接单位 }}</td>
            <td>{{ group.已通过 }}</td>
            <td>{{ group.需返工 }}</td>
            <td>{{ group.待验收 }}</td>
            <td>{{ group.返工次数 }}</td>
            <td>{{ group.平均验收天数 ?? '—' }}</td>
          </tr>
          <tr v-if="!overviewGroups.length">
            <td :colspan="overviewColumns.length" class="empty-state">当前时间段内没有可统计的验收单</td>
          </tr>
        </tbody>
      </table>

      <div v-if="excluded.length" class="warn-box">
        <strong>以下单据不合规，未纳入统计：</strong>
        <ul>
          <li v-for="item in excluded" :key="item.验收单号">{{ item.提示 }}</li>
        </ul>
      </div>
      <p class="overview-rule">{{ overviewRule }}</p>
    </section>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td class="row-actions">
            <button class="link" type="button" @click="openDetail(row)">详情</button>
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无竣工验收数据，可先登记验收单</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条竣工验收记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type StatCard = { label: string; value: string | number }
type OverviewGroup = {
  验收项目: string
  承接单位: string
  已通过: number
  需返工: number
  待验收: number
  返工次数: number
  平均验收天数: number | null
}
type ExcludedItem = { 验收单号: string; 不合规项: string; 提示: string }

const ENDPOINT = '/api/accept'
const columns = ["验收单号", "关联施工", "验收项目", "验收标准", "验收结论", "验收人员", "验收日期", "验收状态"]
const actions = ["开始验收", "确认通过", "下发返工"]
const overviewColumns = ["验收项目", "承接单位", "已通过", "需返工", "待验收", "返工次数", "平均验收天数"]
const periodOptions = [
  { key: 'all', label: '全部' },
  { key: 'month', label: '近30天' },
  { key: 'quarter', label: '近90天' },
  { key: 'custom', label: '自定义' },
] as const

const router = useRouter()

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

const overviewCards = ref<StatCard[]>([
  { label: '已通过', value: 0 },
  { label: '需返工', value: 0 },
  { label: '待验收', value: 0 },
  { label: '返工次数', value: 0 },
  { label: '平均验收天数', value: 0 },
])
const overviewGroups = ref<OverviewGroup[]>([])
const excluded = ref<ExcludedItem[]>([])
const overviewRule = ref('')
const periodKey = ref<string>('all')
const customStart = ref('')
const customEnd = ref('')

function formatDay(day: Date): string {
  const month = String(day.getMonth() + 1).padStart(2, '0')
  const date = String(day.getDate()).padStart(2, '0')
  return `${day.getFullYear()}-${month}-${date}`
}

function currentPeriod(): { start?: string; end?: string } {
  const today = new Date()
  if (periodKey.value === 'month') {
    const start = new Date(today)
    start.setDate(start.getDate() - 29)
    return { start: formatDay(start), end: formatDay(today) }
  }
  if (periodKey.value === 'quarter') {
    const start = new Date(today)
    start.setDate(start.getDate() - 89)
    return { start: formatDay(start), end: formatDay(today) }
  }
  if (periodKey.value === 'custom') {
    const period: { start?: string; end?: string } = {}
    if (customStart.value) period.start = customStart.value
    if (customEnd.value) period.end = customEnd.value
    return period
  }
  return {}
}

function switchPeriod(key: string) {
  periodKey.value = key
  if (key !== 'custom') {
    void reloadOverview()
  }
}

function applyCustomPeriod() {
  void reloadOverview()
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '验收单登记入口尚未接入审批流'
}

function openDetail(row: Row) {
  void router.push(`/accept/${row.id}`)
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    if (!response.ok) {
      throw new Error('竣工验收动作未生效，请稍后重试')
    }
    await Promise.all([reload(), reloadOverview()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '竣工验收操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('验收单列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '竣工验收列表读取失败'
  }
}

async function reloadOverview() {
  const period = currentPeriod()
  const query = new URLSearchParams()
  if (period.start) query.set('start', period.start)
  if (period.end) query.set('end', period.end)
  const suffix = query.toString() ? `?${query.toString()}` : ''
  try {
    const response = await request(`${ENDPOINT}/overview${suffix}`)
    if (!response.ok) {
      throw new Error('结论概览读取失败')
    }
    const payload = await response.json()
    overviewCards.value = payload.cards ?? []
    overviewGroups.value = payload.groups ?? []
    excluded.value = payload.excluded ?? []
    overviewRule.value = payload.rule ? `统计口径：${payload.rule}` : ''
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '结论概览读取失败'
  }
}

onMounted(() => {
  void reload()
  void reloadOverview()
})
</script>
