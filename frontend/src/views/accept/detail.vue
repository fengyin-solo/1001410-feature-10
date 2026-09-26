<template>
  <section class="page" data-module="accept-detail">
    <header class="page-head">
      <div>
        <h2>验收单详情 · {{ doc?.验收单号 ?? route.params.no }}</h2>
        <p class="page-desc">展示一张验收单的最新状态与全部提交/复验历史；动作执行后本页与列表概览口径同步更新。</p>
      </div>
      <div class="page-actions">
        <button class="btn" type="button" @click="goBack">返回验收单列表</button>
      </div>
    </header>

    <div v-if="errorMessage" class="error-banner">{{ errorMessage }}</div>

    <template v-if="doc">
      <div class="stat-row">
        <article class="stat-card">
          <span class="stat-label">当前状态</span>
          <strong class="stat-value" :class="statusClass">{{ doc.status }}</strong>
        </article>
        <article class="stat-card">
          <span class="stat-label">返工次数</span>
          <strong class="stat-value">{{ doc.rework_count }}</strong>
        </article>
        <article class="stat-card">
          <span class="stat-label">提交次数</span>
          <strong class="stat-value">{{ doc.submit_count }}</strong>
        </article>
        <article class="stat-card">
          <span class="stat-label">承接单位</span>
          <strong class="stat-value text-value">{{ doc.承接单位 }}</strong>
        </article>
      </div>

      <div v-if="doc.issues.length" class="invalid-box">
        <strong>本单存在不合规项，不会进入结论概览统计：</strong>
        <ul>
          <li v-for="issue in doc.issues" :key="issue.字段">
            <span class="invalid-reason">{{ issue.字段 }} — {{ issue.问题 }}</span>
          </li>
        </ul>
      </div>

      <div class="detail-grid">
        <div v-for="field in metaFields" :key="field" class="detail-item">
          <span class="detail-label">{{ field }}</span>
          <span class="detail-value">{{ doc.latest[field] || '—' }}</span>
        </div>
      </div>

      <div class="action-bar">
        <button
          v-for="action in availableActions"
          :key="action"
          class="btn"
          :class="{ primary: action === '确认通过', danger: action === '下发返工' }"
          type="button"
          @click="runAction(action)"
        >
          {{ action }}
        </button>
      </div>

      <h3 class="history-title">提交 / 复验历史（同一验收单多次提交）</h3>
      <table class="data-table">
        <thead>
          <tr>
            <th>提交序号</th>
            <th>状态</th>
            <th>验收结论</th>
            <th>验收人员</th>
            <th>报验日期</th>
            <th>验收日期</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(item, index) in doc.items" :key="String(item.id)" :class="{ latest: item.id === doc.latest.id }">
            <td>第 {{ index + 1 }} 次<span v-if="item.id === doc.latest.id" class="latest-tag">最新</span></td>
            <td>{{ item.status }}</td>
            <td>
              <span v-if="!item['验收结论'] && item.status !== '待验收'" class="missing-cell">结论缺失</span>
              <template v-else>{{ item['验收结论'] || '—' }}</template>
            </td>
            <td>{{ item['验收人员'] || '—' }}</td>
            <td>{{ item['报验日期'] || '—' }}</td>
            <td>{{ item['验收日期'] || '—' }}</td>
          </tr>
        </tbody>
      </table>
    </template>

    <footer class="page-foot">
      <span v-if="actionMessage" class="action-message">{{ actionMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { request } from '@/api/client'
import type { AcceptDocument } from './shared'

const ENDPOINT = '/api/accept'
const route = useRoute()
const router = useRouter()

const doc = ref<AcceptDocument | null>(null)
const errorMessage = ref('')
const actionMessage = ref('')

const metaFields = ['关联施工', '验收项目', '验收标准', '验收结论', '验收人员', '报验日期', '验收日期']

const NEXT_ACTIONS: Record<string, string[]> = {
  '待验收': ['开始验收'],
  '验收中': ['确认通过', '下发返工'],
  '需返工': ['重新报验'],
  '已通过': [],
}
const availableActions = computed(() => NEXT_ACTIONS[doc.value?.status ?? ''] ?? [])

const statusClass = computed(() => {
  switch (doc.value?.status) {
    case '已通过':
      return 'status-pass'
    case '需返工':
      return 'status-rework'
    default:
      return 'status-pending'
  }
})

function goBack() {
  void router.push('/accept')
}

async function runAction(action: string) {
  if (!doc.value) return
  errorMessage.value = ''
  actionMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${doc.value.latest.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    const payload = await response.json().catch(() => null)
    if (!response.ok || payload?.ok === false) {
      throw new Error(payload?.message ?? '动作未生效，请稍后重试')
    }
    actionMessage.value = payload?.message ?? '操作成功'
    // 重新报验会产生新的提交行，整单重新拉取，历史表与状态卡随之刷新。
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '竣工验收操作失败'
  }
}

async function reload() {
  try {
    const response = await request(`${ENDPOINT}/doc/${encodeURIComponent(String(route.params.no))}`)
    if (!response.ok) {
      const payload = await response.json().catch(() => null)
      throw new Error(payload?.detail ?? '验收单读取失败')
    }
    doc.value = (await response.json()) as AcceptDocument
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '验收单读取失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.text-value { font-size: 15px; }
.status-pass { color: #067647; }
.status-rework { color: #b42318; }
.status-pending { color: #b54708; }
.detail-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px 16px;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 14px 16px;
  margin-bottom: 12px;
}
.detail-item { display: flex; flex-direction: column; gap: 2px; font-size: 13px; }
.detail-label { color: var(--muted); font-size: 12px; }
.action-bar { display: flex; gap: 8px; margin-bottom: 16px; }
.btn.danger { color: #b42318; border-color: #fda29b; }
.history-title { font-size: 14px; margin: 8px 0; }
.latest { background: #f0f7ff; }
.latest-tag {
  display: inline-block;
  margin-left: 6px;
  font-size: 11px;
  color: var(--brand);
  border: 1px solid var(--brand);
  border-radius: 4px;
  padding: 0 4px;
}
.missing-cell { color: #b42318; }
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
.invalid-reason { color: #b42318; }
.error-banner {
  border: 1px solid #fda29b;
  background: #fef3f2;
  color: #b42318;
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 12px;
  font-size: 13px;
}
.action-message { color: #067647; }
</style>
