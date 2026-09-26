<template>
  <section class="page" data-module="accept">
    <header class="page-head">
      <div>
        <h2>竣工验收管理</h2>
        <p class="page-desc">维护验收单与验收结论；结论概览按验收项目、承接单位汇总通过、返工与待验收情况。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记验收单</button>
        <button class="btn" type="button" @click="exportRows">导出竣工验收清单</button>
      </div>
    </header>

    <div class="view-tabs">
      <button type="button" class="view-tab" :class="{ active: tab === 'list' }" @click="tab = 'list'">验收单列表</button>
      <button type="button" class="view-tab" :class="{ active: tab === 'overview' }" @click="switchOverview">结论概览</button>
    </div>

    <OverviewPanel v-if="tab === 'overview'" ref="overviewRef" />

    <template v-else>
      <div class="stat-row">
        <article v-for="item in stats" :key="item.label" class="stat-card">
          <span class="stat-label">{{ item.label }}</span>
          <strong class="stat-value">{{ item.value }}</strong>
        </article>
      </div>

      <form class="filter-bar" @submit.prevent="reload">
        <label v-for="field in filterFields" :key="field" class="filter-item">
          <span>{{ field }}</span>
          <input v-model="filters[field]" :placeholder="`按${field}检索`" />
        </label>
        <label class="filter-item">
          <span>验收状态</span>
          <select v-model="filters.status">
            <option value="">全部状态</option>
            <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
          </select>
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
            <td v-for="column in columns" :key="column">
              <RouterLink v-if="column === '验收单号'" class="link" :to="`/accept/doc/${row[column]}`">{{ row[column] }}</RouterLink>
              <span v-else-if="column === '验收结论' && !row[column]" class="missing-cell">
                缺失<em v-if="row.status === '需返工'">（不进概览）</em>
              </span>
              <template v-else>{{ row[column] ?? '—' }}</template>
            </td>
            <td class="row-actions">
              <RouterLink class="link" :to="`/accept/doc/${row['验收单号']}`">详情</RouterLink>
              <button
                v-for="action in actionsFor(row.status)"
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
        <span>共 {{ total }} 张验收单（同一验收单多次提交只显示最新一次）</span>
        <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
      </footer>
    </template>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'
import OverviewPanel from './OverviewPanel.vue'
import type { AcceptOverview, AcceptRow } from './shared'

const ENDPOINT = '/api/accept'
const columns = ['验收单号', '关联施工', '承接单位', '验收项目', '验收结论', '验收人员', '报验日期', '验收日期', '返工次数']
const statuses = ['待验收', '验收中', '已通过', '需返工']
// 状态机里合法的下一步动作，避免对已通过单再点一次确认。
const NEXT_ACTIONS: Record<string, string[]> = {
  '待验收': ['开始验收'],
  '验收中': ['确认通过', '下发返工'],
  '需返工': ['重新报验'],
  '已通过': [],
}

const rows = ref<AcceptRow[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = ['验收单号', '关联施工', '验收项目']
const tab = ref<'list' | 'overview'>('list')
const overviewRef = ref<InstanceType<typeof OverviewPanel> | null>(null)
const stats = ref([
  { label: '待验收单据', value: 0 },
  { label: '本月通过数', value: 0 },
  { label: '需返工项数', value: 0 },
  { label: '本月累计返工次数', value: 0 },
])

function actionsFor(status: unknown): string[] {
  return NEXT_ACTIONS[String(status)] ?? []
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function switchOverview() {
  tab.value = 'overview'
  // 概览面板是切过来时才挂载的，挂载后会自行拉取；这里兜底再刷一次，保证数字最新。
  requestAnimationFrame(() => void overviewRef.value?.reload())
}

function exportRows() {
  window.open(`${ENDPOINT}/export/data`, '_blank')
}

function openCreate() {
  errorMessage.value = '验收单登记入口尚未接入审批流'
}

async function runAction(action: string, row: AcceptRow) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok || payload?.ok === false) {
      throw new Error(payload?.message ?? '竣工验收动作未生效，请稍后重试')
    }
    // 动作可能新增了重新报验的提交行，列表与统计卡一起重拉，保持口径一致。
    await Promise.all([reload(), loadStats()])
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '竣工验收操作失败'
  }
}

async function loadStats() {
  // 统计卡与结论概览共用同一个口径接口，避免列表数字和概览对不上。
  try {
    const [allRes, monthRes] = await Promise.all([
      request(`${ENDPOINT}/overview?range=all`),
      request(`${ENDPOINT}/overview?range=month`),
    ])
    if (!allRes.ok || !monthRes.ok) return
    const all = (await allRes.json()) as AcceptOverview
    const month = (await monthRes.json()) as AcceptOverview
    const card = (data: AcceptOverview, label: string) => data.cards.find((item) => item.label === label)?.value ?? 0
    stats.value = [
      { label: '待验收单据', value: Number(card(all, '待验收')) },
      { label: '本月通过数', value: Number(card(month, '已通过')) },
      { label: '需返工项数', value: Number(card(all, '需返工')) },
      { label: '本月累计返工次数', value: Number(card(month, '累计返工次数')) },
    ]
  } catch {
    // 统计卡只是辅助信息，拉取失败不影响列表本身。
  }
}

async function reload() {
  errorMessage.value = ''
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(filters.value)) {
    if (!value) continue
    // 后端按验收单号做关键字检索；项目/施工编号作为附加过滤参数保留。
    params.set(key === '验收单号' ? 'keyword' : key, value)
  }
  try {
    const response = await request(`${ENDPOINT}?${params.toString()}`)
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

// 不做 keep-alive：从详情返回时组件重新挂载，列表、统计卡全部按服务端最新状态重拉。
onMounted(() => {
  void reload()
  void loadStats()
})
</script>

<style scoped>
.view-tabs { display: flex; gap: 8px; margin-bottom: 12px; }
.view-tab {
  border: 1px solid var(--border);
  background: #fff;
  border-radius: 6px 6px 0 0;
  padding: 8px 16px;
  cursor: pointer;
  font-size: 13px;
}
.view-tab.active { background: var(--brand); border-color: var(--brand); color: #fff; }
.missing-cell { color: #b42318; font-size: 12px; }
.missing-cell em { color: var(--muted); font-style: normal; }
</style>
