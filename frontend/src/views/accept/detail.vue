<template>
  <section class="page" data-module="accept">
    <header class="page-head">
      <div>
        <h2>验收单详情</h2>
        <p class="page-desc">查看单条验收单的完整信息，返回列表后概览与统计会重新读取，保持一致。</p>
      </div>
      <div class="page-actions">
        <button class="btn" type="button" @click="goBack">返回列表</button>
      </div>
    </header>

    <p v-if="errorMessage" class="error-text">{{ errorMessage }}</p>

    <div v-if="entry" class="detail-grid">
      <div v-for="field in detailFields" :key="field" class="detail-item">
        <span class="detail-label">{{ field }}</span>
        <span class="detail-value">{{ entry[field] ?? '—' }}</span>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { request } from '@/api/client'

type Entry = Record<string, string | number | boolean | null>

const ENDPOINT = '/api/accept'
const detailFields = [
  '验收单号', '关联施工', '验收项目', '验收标准', '验收结论',
  '验收人员', '登记日期', '验收日期', '返工次数', '验收状态',
]

const route = useRoute()
const router = useRouter()

const entry = ref<Entry | null>(null)
const errorMessage = ref('')

function goBack() {
  void router.push('/accept')
}

async function loadEntry() {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${route.params.id}`)
    if (!response.ok) {
      const payload = await response.json().catch(() => null)
      throw new Error(payload?.detail ?? '验收单读取失败')
    }
    entry.value = await response.json()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '验收单读取失败'
  }
}

onMounted(loadEntry)
</script>
