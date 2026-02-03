<template>
  <!-- 计划面板：展示任务进度与步骤列表 -->
  <div class="[&:not(:empty)]:pb-2 bg-[var(--background-gray-main)] rounded-[22px_22px_0px_0px]">
    <div v-if="isExpanded"
      class="border border-black/8 dark:border-[var(--border-main)] bg-[var(--background-menu-white)] rounded-[16px] sm:rounded-[12px] shadow-[0px_0px_1px_0px_rgba(0,_0,_0,_0.05),_0px_8px_32px_0px_rgba(0,_0,_0,_0.04)] z-99 flex flex-col py-4">
      <div class="flex px-4 mb-4 w-full">
        <div class="flex items-start ml-auto">
          <div class="flex items-center justify-center gap-2">
            <!-- 展开状态下的收起按钮 -->
            <div @click="togglePanel"
              class="flex h-7 w-7 items-center justify-center cursor-pointer hover:bg-[var(--fill-tsp-gray-main)] rounded-md">
              <ChevronDown class="text-[var(--icon-tertiary)]" :size="16" />
            </div>
          </div>
        </div>
      </div>
      <div class="px-4">
        <div class="bg-[var(--fill-tsp-gray-main)] rounded-lg pt-4 pb-2">
          <!-- 进度条头部 -->
          <div class="flex justify-between w-full px-4">
            <span class="text-[var(--text-primary)] font-bold">{{ $t('Task Progress') }}</span>
            <div class="flex items-center gap-3">
              <span class="text-xs text-[var(--text-tertiary)]">{{ planProgress }}</span>
            </div>
          </div>
          <!-- 步骤列表：滚动区域 -->
          <div class="max-h-[min(calc(100vh-360px),400px)] overflow-y-auto">
            <div v-for="step in plan.steps" :key="step.id"
              class="flex items-start gap-2.5 w-full px-4 py-2 truncate">
              <!-- 完成显示对勾，否则显示时钟 -->
              <StepSuccessIcon v-if="step.status === 'completed'" />
              <Clock v-else class="relative top-[2px] flex-shrink-0" :size="16" />
              <div class="flex flex-col w-full gap-[2px] truncate">
                <!-- 步骤描述 -->
                <div class="text-sm truncate" :title="step.description"
                  style="color: var(--text-primary);">
                  {{ step.description }}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
    <!-- 收起态：仅显示当前步骤与进度 -->
    <div v-if="!isExpanded" @click="togglePanel"
      class="flex flex-row items-start justify-between pe-3 relative clickable border border-black/8 dark:border-[var(--border-main)] bg-[var(--background-menu-white)] rounded-[16px] sm:rounded-[12px] shadow-[0px_0px_1px_0px_rgba(0,_0,_0,_0.05),_0px_8px_32px_0px_rgba(0,_0,_0,_0.04)] z-99">
      <div class="flex-1 min-w-0 relative overflow-hidden">
        <div class="w-full" style="height: 36px; --offset: -36px;">
          <div class="w-full">
            <div class="flex items-start gap-2.5 w-full px-4 py-2 truncate">
              <StepSuccessIcon v-if="isCompleted" />
              <Clock v-else class="relative top-[2px] flex-shrink-0" :size="16" />
              <div class="flex flex-col w-full gap-[2px] truncate">
                <!-- 当前进行中的步骤描述 -->
                <div class="text-sm truncate" :title="currentStep" style="color: var(--text-tertiary);">
                  {{ currentStep }}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
      <!-- 展开按钮 -->
      <button
        class="flex h-full cursor-pointer justify-center gap-2 hover:opacity-80 flex-shrink-0 items-start py-2.5">
        <span class="text-xs text-[var(--text-tertiary)] hidden sm:flex">{{ planProgress }}</span>
        <ChevronUp class="text-[var(--icon-tertiary)]" :size="16" />
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { ChevronUp, ChevronDown, Clock } from 'lucide-vue-next';
import StepSuccessIcon from './icons/StepSuccessIcon.vue';
import type { PlanEventData } from '../types/event';

interface Props {
  plan: PlanEventData;
}

const props = defineProps<Props>();

const { t } = useI18n();

// 是否展开计划面板
const isExpanded = ref(false);

// 切换展开/收起状态
const togglePanel = () => {
  isExpanded.value = !isExpanded.value;
};

// 计算完成进度（completed/total）
const planProgress = computed((): string => {
  const completedSteps = props.plan?.steps.filter(step => step.status === 'completed').length ?? 0;
  return `${completedSteps} / ${props.plan?.steps.length ?? 1}`;
});

// 是否全部完成
const isCompleted = computed((): boolean => {
  return props.plan?.steps.every(step => step.status === 'completed') ?? false;
});

// 当前步骤：优先返回 running/pending 的描述
const currentStep = computed((): string => {
  for (const step of props.plan?.steps ?? []) {
    if (step.status === 'running' || step.status === 'pending') {
      return step.description;
    }
  }
  return t('Task Completed');
});
</script>

<style scoped>
.\[\&\:not\(\:empty\)\]\:pb-2:not(:empty) {
  padding-bottom: .5rem;
}
</style> 