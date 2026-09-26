<template>
  <section class="overview-panel">
    <div class="filter-bar range-bar">
      <div class="range-tabs" role="tablist">
        <button
          v-for="option in RANGE_OPTIONS"
          :key="option.key"
          type="button"
          class="btn"
          :class="{ primary: range === option.key }"
          @click="switchRange(option.key)"
        >
          {{ option.label }}
        </button>
        <button type="button" class="btn" :class="{ primary: range === 'custom' }" @click="range = 'custom'">
          自定义
        </button>
      </div>
      <label v-if="range === 'custom'" class="filter-item">
        <span>开始日期</span>
        <input v-model="customStart" type="date" />
      </label>
      <label v-if="range === 'custom'" class="filter-item">
        <span>结束日期</span>
        <input v-model="customEnd" type="date" />
      </label>
      <button v-if="range === 'custom'" class="btn" type="button" @click="reload">应用时间段</button>
      <span v-if="rangeLabel" class="range-hint">统计口径：{{ rangeLabel }}</span>
    </div>

    <div class="stat-row">
      <article v-for="card in overview?.cards ?? []" :key="card.label" class="stat-card">
        <span class="stat-label">{{ card.label }}</span>
        <strong class="stat-value">{{ card.value === null ? '—' : card.value }}<small v-if="card.unit">{{ card.unit }}</small></strong>
      </article>
    </div>

    <div v-if="overview && overview.invalid_docs.length" class="invalid-box">
      <strong>有 {{ overview.invalid_docs.length }} 张验收单不合规，未进入统计：</strong>
      <ul>
        <li v-for="doc in overview.invalid_docs" :key="doc.验收单号">
          <span class="invalid-no">{{ doc.验收单号 }}</span>
          （{{ doc.验收项目 }} · {{ doc.承接单位 }}）：
          <span v-for="issue in doc.问题" :key="issue.字段" class="invalid-reason">
            {{ issue.字段 }} — {{ issue.问题 }}；
          </span>
        </li>
      </ul>
    </div>

    <table class="data-table overview-table">
      <thead>
        <tr>
          <th>验收项目</th>
          <th>承接单位</th>
          <th>已通过（件）</th>
          <th>需返工（件）</th>
          <th>待验收（件）</th>
          <th>返工次数</th>
          <th>通过率</th>
          <th>平均验收天数</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="group in overview?.groups ?? []" :key="`${group.验收项目}-${group.承接单位}`">
          <td>{{ group.验收项目 }}</td>
          <td>{{ group.承接单位 }}</td>
          <td class="num passed">{{ group.passed }}</td>
          <td class="num rework">{{ group.rework }}</td>
          <td class="num pending">{{ group.pending }}</td>
          <td class="num">{{ group.rework_count }}</td>
          <td>{{ formatRate(group.pass_rate) }}</td>
          <td>{{ group.avg_days === null ? '—' : `${group.avg_days} 天` }}</td>
        </tr>
        <tr v-if="overview && !overview.groups.length">
          <td colspan="8" class="empty-state">该时间段内没有可统计的合规验收单</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>同一验收单只统计一次；返工后重新提交通过的不重复计入通过数，返工次数按全部提交历史累计。</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'
import { RANGE_OPTIONS, type AcceptOverview } from './shared'

const ENDPOINT = '/api/accept/overview'

const overview = ref<AcceptOverview | null>(null)
const errorMessage = ref('')
const range = ref('month')
const customStart = ref('')
const customEnd = ref('')

const rangeLabel = ref('')

function formatRate(value: number | null): string {
  if (value === null) return '—'
  return `${(value * 100).toFixed(1)}%`
}

function switchRange(key: string) {
  range.value = key
  void reload()
}

async function reload() {
  errorMessage.value = ''
  const params = new URLSearchParams({ range: range.value })
  if (range.value === 'custom') {
    if (!customStart.value || !customEnd.value) {
      errorMessage.value = '自定义时间段需要同时选择开始日期和结束日期'
      return
    }
    params.set('start', customStart.value)
    params.set('end', customEnd.value)
  }
  try {
    const response = await request(`${ENDPOINT}?${params.toString()}`)
    if (!response.ok) {
      throw new Error('结论概览读取失败')
    }
    overview.value = (await response.json()) as AcceptOverview
    const preset = RANGE_OPTIONS.find((item) => item.key === overview.value?.range)
    if (preset) {
      rangeLabel.value = `${preset.label}（${overview.value.start ?? ''} 至 ${overview.value.end ?? '今'}）`
    } else if (overview.value.range === 'custom') {
      rangeLabel.value = `${overview.value.start ?? ''} 至 ${overview.value.end ?? ''}`
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '结论概览读取失败'
  }
}

defineExpose({ reload })

onMounted(reload)
</script>

<style scoped>
.range-bar { align-items: center; }
.range-tabs { display: flex; gap: 6px; }
.range-hint { color: var(--muted); font-size: 12px; }
.overview-table .num { text-align: right; font-variant-numeric: tabular-nums; }
.overview-table .passed { color: #067647; font-weight: 600; }
.overview-table .rework { color: #b42318; font-weight: 600; }
.overview-table .pending { color: #b54708; font-weight: 600; }
.stat-value small { font-size: 12px; font-weight: 400; color: var(--muted); margin-left: 2px; }
.invalid-box {
  border: 1px solid #fda29b;
  background: #fef3f2;
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 12px;
  font-size: 13px;
  color: #7a271a;
}
.invalid-box ul { margin: 6px 0 0; padding-left: 18px; }
.invalid-box li { margin: 2px 0; }
.invalid-no { font-weight: 600; }
.invalid-reason { color: #b42318; }
</style>
