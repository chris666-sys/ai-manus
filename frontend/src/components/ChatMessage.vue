<template>
  <!-- 用户消息：显示用户发送的文本内容与时间戳（右侧对齐） -->
  <div v-if="message.type === 'user'" class="flex w-full flex-col items-end justify-end gap-1 group mt-3">
    <!-- 时间戳仅在 hover 可见，减少视觉干扰 -->
    <div class="flex items-end">
      <div class="flex items-center justify-end gap-[2px] invisible group-hover:visible">
        <div class="float-right transition text-[12px] text-[var(--text-tertiary)] invisible group-hover:visible">
          {{ relativeTime(message.content.timestamp) }}
        </div>
      </div>
    </div>
    <!-- 气泡宽度限制在 90%，避免超宽影响可读性 -->
    <div class="flex max-w-[90%] relative flex-col gap-2 items-end">
      <div
        class="relative flex items-center rounded-[12px] overflow-hidden bg-[var(--fill-white)] dark:bg-[var(--fill-tsp-white-main)] p-3 ltr:rounded-br-none rtl:rounded-bl-none border border-[var(--border-main)] dark:border-0"
        v-html="renderMarkdown(messageContent.content)">
      </div>
    </div>
  </div>
  <!-- 助手消息：显示模型回复的 Markdown 内容与时间戳（左侧对齐） -->
  <div v-else-if="message.type === 'assistant'" class="flex flex-col gap-2 w-full group mt-3">
    <!-- 头像与品牌标识 -->
    <div class="flex items-center justify-between h-7 group">
      <div class="flex items-center gap-[3px]">
        <Bot :size="24" class="w-6 h-6" />
        <ManusTextIcon />
      </div>
      <!-- 时间戳 hover 展示 -->
      <div class="flex items-center gap-[2px] invisible group-hover:visible">
        <div class="float-right transition text-[12px] text-[var(--text-tertiary)] invisible group-hover:visible">
          {{ relativeTime(message.content.timestamp) }}
        </div>
      </div>
    </div>
    <!-- Markdown 文本区：支持代码块与深色模式样式 -->
    <div
      class="max-w-none p-0 m-0 prose prose-sm sm:prose-base dark:prose-invert [&_pre:not(.shiki)]:!bg-[var(--fill-tsp-white-light)] [&_pre:not(.shiki)]:text-[var(--text-primary)] text-base text-[var(--text-primary)]"
      v-html="renderMarkdown(messageContent.content)"></div>
  </div>
  <!-- 单条工具调用消息：只渲染一条工具调用气泡 -->
  <ToolUse v-else-if="message.type === 'tool'" :tool="toolContent" @click="handleToolClick(toolContent)" />
  <!-- 计划步骤消息：标题 + 折叠区 + 步骤内多条工具调用 -->
  <div v-else-if="message.type === 'step'" class="flex flex-col">
    <!-- 步骤标题栏：展示状态图标、描述、时间戳，并支持展开/收起 -->
    <div class="text-sm w-full clickable flex gap-2 justify-between group/header truncate text-[var(--text-primary)]"
      data-event-id="HNtP7XOMUOhPemItd2EkK2">
      <div class="flex flex-row gap-2 justify-center items-center truncate">
        <!-- 未完成显示空心圆，完成显示对勾 -->
        <div v-if="stepContent.status !== 'completed'"
          class="w-4 h-4 flex-shrink-0 flex items-center justify-center border border-[var(--border-dark)] rounded-[15px]">
        </div>
        <div v-else
          class="w-4 h-4 flex-shrink-0 flex items-center justify-center border-[var(--border-dark)] rounded-[15px] bg-[var(--text-disable)] dark:bg-[var(--fill-tsp-white-dark)] border-0">
          <CheckIcon class="text-[var(--icon-white)] dark:text-[var(--icon-white-tsp)]" :size="10" />
        </div>
        <!-- 步骤描述（支持 Markdown） -->
        <div class="truncate font-medium markdown-content"
          v-html="stepContent.description ? renderMarkdown(stepContent.description) : ''">
        </div>
        <!-- 展开/收起按钮：仅影响当前 step -->
        <span class="flex-shrink-0 flex" @click="isExpanded = !isExpanded;">
          <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
            class="lucide lucide-chevron-down transition-transform duration-300 w-4 h-4"
            :class="{ 'rotate-180': isExpanded }">
            <path d="m6 9 6 6 6-6"></path>
          </svg>
        </span>
      </div>
      <!-- 步骤级时间戳 -->
      <div class="float-right transition text-[12px] text-[var(--text-tertiary)] invisible group-hover/header:visible">
        {{ relativeTime(message.content.timestamp) }}
      </div>
    </div>
    <!-- 步骤主体：左侧虚线表示步骤执行流程 -->
    <div class="flex">
      <!-- 竖向虚线用于强调 step 与 tool 列表的层级关系 -->
      <div class="w-[24px] relative">
        <div class="border-l border-dashed border-[var(--border-dark)] absolute start-[8px] top-0 bottom-0"
          style="height: calc(100% + 14px);"></div>
      </div>
      <div
        class="flex flex-col gap-3 flex-1 min-w-0 overflow-hidden pt-2 transition-[max-height,opacity] duration-150 ease-in-out"
        :class="{ 'max-h-[100000px] opacity-100': isExpanded, 'max-h-0 opacity-0': !isExpanded }">
        <!-- 步骤内的工具调用列表 -->
        <ToolUse v-for="(tool, index) in stepContent.tools" :key="index" :tool="tool" @click="handleToolClick(tool)" />
      </div>
    </div>
  </div>
  <!-- 附件消息：上传文件展示 -->
  <AttachmentsMessage v-else-if="message.type === 'attachments'" :content="attachmentsContent"/>
</template>

<script setup lang="ts">
import ManusTextIcon from './icons/ManusTextIcon.vue';
import { Message, MessageContent, AttachmentsContent } from '../types/message';
import ToolUse from './ToolUse.vue';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import { CheckIcon } from 'lucide-vue-next';
import { computed, ref } from 'vue';
import { ToolContent, StepContent } from '../types/message';
import { useRelativeTime } from '../composables/useTime';
import { Bot } from 'lucide-vue-next';
import AttachmentsMessage from './AttachmentsMessage.vue';


const props = defineProps<{
  message: Message;
  sessionId?: string;
}>();

const emit = defineEmits<{
  (e: 'toolClick', tool: ToolContent): void;
}>();

// 将工具点击事件抛给父组件（用于打开右侧 ToolPanel）
const handleToolClick = (tool: ToolContent) => {
  emit('toolClick', tool);
};

// 对不同消息类型做结构化访问（避免模板里重复类型断言）
// 这些 computed 根据 message.type 对应的 content 结构做强制类型转换
// 这样模板中可以直接用 stepContent/messageContent/toolContent 等属性
const stepContent = computed(() => props.message.content as StepContent);
const messageContent = computed(() => props.message.content as MessageContent);
const toolContent = computed(() => props.message.content as ToolContent);
const attachmentsContent = computed(() => props.message.content as AttachmentsContent);

// 控制步骤内容的展开/收起
const isExpanded = ref(true);

// 用于展示“xx分钟前”等相对时间
const { relativeTime } = useRelativeTime();

// 将 Markdown 渲染成安全 HTML，避免 XSS
const renderMarkdown = (text: string) => {
  if (typeof text !== 'string') return '';
  // 先由 marked 生成 HTML，再用 DOMPurify 做安全清洗
  const html = marked(text) as string;
  return DOMPurify.sanitize(html);
};
</script>

<style>
.duration-300 {
  animation-duration: .3s;
}

.duration-300 {
  transition-duration: .3s;
}
</style>
