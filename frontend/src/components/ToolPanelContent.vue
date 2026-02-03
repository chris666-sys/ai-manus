<template>
  <!-- 工具面板内容：标题 + 工具信息 + 具体工具视图 -->
  <div class="bg-[var(--background-gray-main)] sm:bg-[var(--background-menu-white)] sm:rounded-[22px] shadow-[0px_0px_8px_0px_rgba(0,0,0,0.02)] border border-black/8 dark:border-[var(--border-light)] flex h-full w-full">
    <div class="flex-1 min-w-0 p-4 flex flex-col h-full">
      <!-- 面板标题栏 -->
      <div class="flex items-center gap-2 w-full">
        <div class="text-[var(--text-primary)] text-lg font-semibold flex-1">{{ $t('Manus Computer') }}</div>
        <button
          class="w-7 h-7 relative rounded-md inline-flex items-center justify-center gap-2.5 cursor-pointer hover:bg-[var(--fill-tsp-gray-main)]">
          <Minimize2 class="w-5 h-5 text-[var(--icon-tertiary)]" @click="hide" />
        </button>
      </div>
      <!-- 当前工具简介（图标 + 名称 + 调用摘要） -->
      <div v-if="toolInfo" class="flex items-center gap-2 mt-2">
        <div
          class="w-[40px] h-[40px] bg-[var(--fill-tsp-gray-main)] rounded-lg flex items-center justify-center flex-shrink-0">
          <component :is="toolInfo.icon" :size="28" />
        </div>
        <div class="flex-1 flex flex-col gap-1 min-w-0">
          <div class="text-[12px] text-[var(--text-tertiary)]">{{ $t('Manus is using') }} <span
              class="text-[var(--text-secondary)]">{{ toolInfo.name }}</span></div>
          <div title="{{ toolInfo.function }} {{ toolInfo.functionArg }}"
            class="max-w-[100%] w-[max-content] truncate text-[13px] rounded-full inline-flex items-center px-[10px] py-[3px] border border-[var(--border-light)] bg-[var(--fill-tsp-gray-main)] text-[var(--text-secondary)]">
            {{ toolInfo.function }}<span
              class="flex-1 min-w-0 px-1 ml-1 text-[12px] font-mono max-w-full text-ellipsis overflow-hidden whitespace-nowrap text-[var(--text-tertiary)]"><code>{{ toolInfo.functionArg }}</code></span>
          </div>
        </div>
      </div>
      <!-- 工具详情容器（动态切换 tool view） -->
      <div
        class="flex flex-col rounded-[12px] overflow-hidden bg-[var(--background-gray-main)] border border-[var(--border-dark)] dark:border-black/30 shadow-[0px_4px_32px_0px_rgba(0,0,0,0.04)] flex-1 min-h-0 mt-[16px]">
        <!-- 根据 toolInfo.view 动态渲染工具视图 -->
        <component v-if="toolInfo" :is="toolInfo.view" :live="live" :sessionId="sessionId"
          :toolContent="toolContent" :isShare="isShare" />
        <!-- 非实时模式下显示“跳转到实时”按钮 -->
        <div class="mt-auto flex w-full items-center gap-2 px-4 h-[44px] relative" v-if="!realTime">
          <button
            class="h-10 px-3 border border-[var(--border-main)] flex items-center gap-1 bg-[var(--background-white-main)] hover:bg-[var(--background-gray-main)] shadow-[0px_5px_16px_0px_var(--shadow-S),0px_0px_1.25px_0px_var(--shadow-S)] rounded-full cursor-pointer absolute left-[50%] translate-x-[-50%]"
            style="bottom: calc(100% + 10px);" @click="jumpToRealTime">
            <PlayIcon :size="16" />
            <span class="text-[var(--text-primary)] text-sm font-medium">{{ $t('Jump to live') }}</span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { toRef } from 'vue';
import { Minimize2, PlayIcon } from 'lucide-vue-next';
import type { ToolContent } from '@/types/message';
import { useToolInfo } from '@/composables/useTool';

const props = defineProps<{
  sessionId?: string;
  realTime: boolean;
  toolContent: ToolContent;
  live: boolean;
  isShare: boolean;
}>();

// 从 toolContent 计算工具图标/名称/函数摘要/视图组件
const { toolInfo } = useToolInfo(toRef(props, 'toolContent'));

const emit = defineEmits<{
  (e: 'jumpToRealTime'): void,
  (e: 'hide'): void
}>();

// 通知父组件隐藏面板
const hide = () => {
  emit('hide');
};


// 通知父组件跳回实时视角
const jumpToRealTime = () => {
  emit('jumpToRealTime');
};
</script>
