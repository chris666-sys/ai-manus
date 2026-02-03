<template>
  <!-- 右侧工具面板：根据工具事件展示详细视图 -->
  <div
    ref="toolPanelRef"
    v-if="visible"
    :class="{
      'h-full w-full top-0 ltr:right-0 rtl:left-0 z-50 fixed sm:sticky sm:top-0 sm:right-0 sm:h-[100vh] sm:ml-3 sm:py-3 sm:mr-4': isShow,
      'h-full overflow-hidden': !isShow 
    }"
    :style="{ 'width': isShow ? `${parentSize/2}px` : '0px', 'opacity': isShow ? '1' : '0', 'transition': '0.2s ease-in-out' }">
    <div class="h-full" :style="{ 'width': isShow ? '100%' : '0px' }">
      <!-- 仅在显示状态且有工具内容时渲染详情 -->
      <ToolPanelContent v-if="isShow && toolContent" :sessionId="sessionId" :realTime="realTime" :toolContent="toolContent" :live="live" :isShare="isShare" @hide="hideToolPanel" @jumpToRealTime="jumpToRealTime" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import type { ToolContent } from '../types/message'
import ToolPanelContent from './ToolPanelContent.vue'
import { useResizeObserver } from '../composables/useResizeObserver'
import { eventBus } from '../utils/eventBus'
import { EVENT_SHOW_FILE_PANEL, EVENT_SHOW_TOOL_PANEL } from '../constants/event'

// 面板容器引用，用于观察尺寸变化
const toolPanelRef = ref<HTMLElement>()
// 观察父容器宽度，用于动态计算面板宽度
const { size: parentSize } = useResizeObserver(toolPanelRef, {
  target: 'parent',
  property: 'width'
})

// 面板状态
const isShow = ref(false)
const live = ref(false)
const toolContent = ref<ToolContent>()
const visible = ref(true)

const emit = defineEmits<{
  (e: 'jumpToRealTime'): void
}>()

defineProps<{
  sessionId?: string
  realTime: boolean
  isShare: boolean
}>()

// 显示工具面板：设置内容并展示
const showToolPanel = (content: ToolContent, isLive: boolean = false) => {
  eventBus.emit(EVENT_SHOW_TOOL_PANEL)
  visible.value = true
  toolContent.value = content
  isShow.value = true
  live.value = isLive
}

// 隐藏面板（不销毁内容）
const hideToolPanel = () => {
  isShow.value = false
}

// 转发“回到实时”事件给父组件
const jumpToRealTime = () => {
  emit('jumpToRealTime')
}

onMounted(() => {
  // 文件面板显示时隐藏工具面板，避免遮挡
  eventBus.on(EVENT_SHOW_FILE_PANEL, () => {
    visible.value = false
  })
})

onUnmounted(() => {
  eventBus.off(EVENT_SHOW_FILE_PANEL)
})

// 暴露给父组件的控制方法
defineExpose({
  showToolPanel,
  hideToolPanel,
  isShow
})
</script>
