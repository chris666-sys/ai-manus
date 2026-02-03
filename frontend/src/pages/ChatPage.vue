<template>
  <!-- 外层滚动容器：统一处理滚动与跟随逻辑 -->
  <SimpleBar ref="simpleBarRef" @scroll="handleScroll">
    <div ref="chatContainerRef" class="relative flex flex-col h-full flex-1 min-w-0 px-5">
      <!-- 顶部工具栏（粘性头部）：包含侧栏按钮、标题、分享、文件列表 -->
      <div ref="observerRef"
        class="sm:min-w-[390px] flex flex-row items-center justify-between pt-3 pb-1 gap-1 sticky top-0 z-10 bg-[var(--background-gray-main)] flex-shrink-0">
        <div class="flex items-center flex-1">
          <div class="relative flex items-center">
            <!-- 左侧面板收起时显示的“展开”按钮 -->
            <div @click="toggleLeftPanel" v-if="!isLeftPanelShow"
              class="flex h-7 w-7 items-center justify-center cursor-pointer rounded-md hover:bg-[var(--fill-tsp-gray-main)]">
              <PanelLeft class="size-5 text-[var(--icon-secondary)]" />
            </div>
          </div>
        </div>
        <div class="max-w-full sm:max-w-[768px] sm:min-w-[390px] flex w-full flex-col gap-[4px] overflow-hidden">
          <!-- 标题与右侧操作区 -->
          <div
            class="text-[var(--text-primary)] text-lg font-medium w-full flex flex-row items-center justify-between flex-1 min-w-0 gap-2">
            <div class="flex flex-row items-center gap-[6px] flex-1 min-w-0">
              <!-- 会话标题（由 title 事件更新） -->
              <span class="whitespace-nowrap text-ellipsis overflow-hidden">
                {{ title }}
              </span>
            </div>
            <div class="flex items-center gap-2 flex-shrink-0">
              <!-- 分享弹层入口 -->
              <span class="relative flex-shrink-0" aria-expanded="false" aria-haspopup="dialog">
                <Popover>
                  <PopoverTrigger>
                    <!-- 分享按钮 -->
                    <button
                      class="h-8 px-3 rounded-[100px] inline-flex items-center gap-1 clickable outline outline-1 outline-offset-[-1px] outline-[var(--border-btn-main)] hover:bg-[var(--fill-tsp-white-light)] me-1.5">
                      <ShareIcon color="var(--icon-secondary)" />
                      <span class="text-[var(--text-secondary)] text-sm font-medium">{{ t('Share') }}</span>
                    </button>
                  </PopoverTrigger>
                  <PopoverContent>
                    <!-- 分享弹层：私密/公开模式切换与复制链接 -->
                    <div
                      class="w-[400px] flex flex-col rounded-2xl bg-[var(--background-menu-white)] shadow-[0px_8px_32px_0px_var(--shadow-S),0px_0px_0px_1px_var(--border-light)]"
                      style="max-width: calc(-16px + 100vw);">
                      <div class="flex flex-col pt-[12px] px-[16px] pb-[16px]">
                        <!-- 私密模式：仅自己可见 -->
                        <div @click="handleShareModeChange('private')"
                          :class="{'pointer-events-none opacity-50': sharingLoading}"
                          class="flex items-center gap-[10px] px-[8px] -mx-[8px] py-[8px] rounded-[8px] clickable hover:bg-[var(--fill-tsp-white-main)]">
                          <div
                            :class="shareMode === 'private' ? 'bg-[var(--Button-primary-black)]' : 'bg-[var(--fill-tsp-white-dark)]'"
                            class="w-[32px] h-[32px] rounded-[8px] flex items-center justify-center">
                            <Lock :size="16" :stroke="shareMode === 'private' ? 'var(--text-onblack)' : 'var(--icon-primary)'" :stroke-width="2" /></div>
                          <div class="flex flex-col flex-1 min-w-0">
                            <div class="text-sm font-medium text-[var(--text-primary)]">{{ t('Private Only') }}</div>
                            <div class="text-[13px] text-[var(--text-tertiary)]">{{ t('Only visible to you') }}</div>
                          </div><Check :size="20" :class="shareMode === 'private' ? 'ml-auto' : 'ml-auto invisible'" :color="shareMode === 'private' ? 'var(--icon-primary)' : 'var(--icon-tertiary)'" />
                        </div>
                        <!-- 公开模式：任何人凭链接可见 -->
                        <div @click="handleShareModeChange('public')"
                          :class="{'pointer-events-none opacity-50': sharingLoading}"
                          class="flex items-center gap-[10px] px-[8px] -mx-[8px] py-[8px] rounded-[8px] clickable hover:bg-[var(--fill-tsp-white-main)]">
                          <div
                            :class="shareMode === 'public' ? 'bg-[var(--Button-primary-black)]' : 'bg-[var(--fill-tsp-white-dark)]'"
                            class="w-[32px] h-[32px] rounded-[8px] flex items-center justify-center">
                            <Globe :size="16" :stroke="shareMode === 'public' ? 'var(--text-onblack)' : 'var(--icon-primary)'" :stroke-width="2" /></div>
                          <div class="flex flex-col flex-1 min-w-0">
                            <div class="text-sm font-medium text-[var(--text-primary)]">{{ t('Public Access') }}</div>
                            <div class="text-[13px] text-[var(--text-tertiary)]">{{ t('Anyone with the link can view') }}</div>
                          </div><Check :size="20" :class="shareMode === 'public' ? 'ml-auto' : 'ml-auto invisible'" :color="shareMode === 'public' ? 'var(--icon-primary)' : 'var(--icon-tertiary)'" />
                        </div>
                        <div class="border-t border-[var(--border-main)] mt-[4px]"></div>
                        
                        <!-- 私密模式下显示“立即分享”按钮 -->
                        <div v-if="shareMode === 'private'">
                          <button @click.stop="handleInstantShare"
                            :disabled="sharingLoading"
                            class="inline-flex items-center justify-center whitespace-nowrap font-medium transition-colors hover:opacity-90 active:opacity-80 bg-[var(--Button-primary-black)] text-[var(--text-onblack)] h-[36px] px-[12px] rounded-[10px] gap-[6px] text-sm min-w-16 mt-[16px] w-full disabled:opacity-50 disabled:cursor-not-allowed"
                            data-tabindex="" tabindex="-1">
                            <div v-if="sharingLoading" class="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                            <Link v-else :size="16" stroke="currentColor" :stroke-width="2" />
                            {{ sharingLoading ? t('Sharing...') : t('Share Instantly') }}
                          </button>
                        </div>
                        
                        <!-- 公开模式下显示“复制链接”按钮 -->
                        <div v-else>
                          <button @click.stop="handleCopyLink"
                            :class="linkCopied ? 'inline-flex items-center justify-center whitespace-nowrap font-medium transition-colors active:opacity-80 bg-[var(--Button-primary-white)] text-[var(--text-primary)] hover:opacity-70 active:hover-60 h-[36px] px-[12px] rounded-[10px] gap-[6px] text-sm min-w-16 mt-[16px] w-full border border-[var(--border-btn-main)] shadow-none' : 'inline-flex items-center justify-center whitespace-nowrap font-medium transition-colors hover:opacity-90 active:opacity-80 bg-[var(--Button-primary-black)] text-[var(--text-onblack)] h-[36px] px-[12px] rounded-[10px] gap-[6px] text-sm min-w-16 mt-[16px] w-full'"
                            data-tabindex="" tabindex="-1">
                            <Link v-if="!linkCopied" :size="16" stroke="currentColor" :stroke-width="2" />
                            <Check v-else :size="16" color="var(--text-primary)" />
                            {{ linkCopied ? t('Link Copied') : t('Copy Link') }}
                          </button>
                        </div>
                      </div>
                    </div>
                  </PopoverContent>
                </Popover>
              </span>
              <!-- 文件列表入口 -->
              <button @click="handleFileListShow"
                class="p-[5px] flex items-center justify-center hover:bg-[var(--fill-tsp-white-dark)] rounded-lg cursor-pointer">
                <FileSearch class="text-[var(--icon-secondary)]" :size="18" />
              </button>
            </div>
          </div>
          <div class="w-full flex justify-between items-center">
          </div>
        </div>
        <div class="flex-1"></div>
      </div>
      <!-- 内容区：聊天记录 + 输入框 -->
      <div class="mx-auto w-full max-w-full sm:max-w-[768px] sm:min-w-[390px] flex flex-col flex-1">
        <!-- 消息列表 -->
        <div class="flex flex-col w-full gap-[12px] pb-[80px] pt-[12px] flex-1 overflow-y-auto">
          <ChatMessage v-for="(message, index) in messages" :key="index" :message="message"
            @toolClick="handleToolClick" />

          <!-- Loading indicator -->
          <LoadingIndicator v-if="isLoading" :text="$t('Thinking')" />
        </div>

        <!-- 输入区：跟随按钮 + Plan 面板 + 输入框 -->
        <div class="flex flex-col bg-[var(--background-gray-main)] sticky bottom-0">
          <!-- 未跟随时显示“回到底部”按钮 -->
          <button @click="handleFollow" v-if="!follow"
            class="flex items-center justify-center w-[36px] h-[36px] rounded-full bg-[var(--background-white-main)] hover:bg-[var(--background-gray-main)] clickable border border-[var(--border-main)] shadow-[0px_5px_16px_0px_var(--shadow-S),0px_0px_1.25px_0px_var(--shadow-S)] absolute -top-20 left-1/2 -translate-x-1/2">
            <ArrowDown class="text-[var(--icon-primary)]" :size="20" />
          </button>
          <!-- 计划面板（有 plan 才显示） -->
          <PlanPanel v-if="plan && plan.steps.length > 0" :plan="plan" />
          <!-- 输入框：提交/停止/附件 -->
          <ChatBox v-model="inputMessage" :rows="1" @submit="handleSubmit" :isRunning="isLoading" @stop="handleStop"
            :attachments="attachments" />
        </div>
      </div>
    </div>
    <!-- 右侧工具面板：用于展示工具实时详情 -->
    <ToolPanel ref="toolPanel" :size="toolPanelSize" :sessionId="sessionId" :realTime="realTime" 
      :isShare="false"
      @jumpToRealTime="jumpToRealTime" />
  </SimpleBar>
</template>

<script setup lang="ts">
// 页面职责：聊天主页面（SSE 流、消息列表、工具面板、分享入口）
import SimpleBar from '../components/SimpleBar.vue';
import { ref, onMounted, watch, nextTick, onUnmounted, reactive, toRefs } from 'vue';
import { useRouter, onBeforeRouteUpdate } from 'vue-router';
import { useI18n } from 'vue-i18n';
import ChatBox from '../components/ChatBox.vue';
import ChatMessage from '../components/ChatMessage.vue';
import * as agentApi from '../api/agent';
import { Message, MessageContent, ToolContent, StepContent, AttachmentsContent } from '../types/message';
import {
  StepEventData,
  ToolEventData,
  MessageEventData,
  ErrorEventData,
  TitleEventData,
  PlanEventData,
  AgentSSEEvent,
} from '../types/event';
import ToolPanel from '../components/ToolPanel.vue'
import PlanPanel from '../components/PlanPanel.vue';
import { ArrowDown, FileSearch, PanelLeft, Lock, Globe, Link, Check } from 'lucide-vue-next';
import ShareIcon from '@/components/icons/ShareIcon.vue';
import { showErrorToast, showSuccessToast } from '../utils/toast';
import type { FileInfo } from '../api/file';
import { useLeftPanel } from '../composables/useLeftPanel'
import { useSessionFileList } from '../composables/useSessionFileList'
import { useFilePanel } from '../composables/useFilePanel'
import { copyToClipboard } from '../utils/dom'
import { SessionStatus } from '../types/response';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import LoadingIndicator from '@/components/ui/LoadingIndicator.vue';

// 路由/国际化/面板相关 hooks
const router = useRouter()
const { t } = useI18n()
const { toggleLeftPanel, isLeftPanelShow } = useLeftPanel()
const { showSessionFileList } = useSessionFileList()
const { hideFilePanel } = useFilePanel()

// 初始状态工厂：便于 reset 与路由切换时重置
const createInitialState = () => ({
  inputMessage: '',
  isLoading: false,
  sessionId: undefined as string | undefined,
  messages: [] as Message[],
  toolPanelSize: 0,
  realTime: true,
  follow: true,
  title: t('New Chat'),
  plan: undefined as PlanEventData | undefined,
  lastNoMessageTool: undefined as ToolContent | undefined,
  lastMessageTool: undefined as ToolContent | undefined,
  lastTool: undefined as ToolContent | undefined,
  lastEventId: undefined as string | undefined,
  cancelCurrentChat: null as (() => void) | null,
  attachments: [] as FileInfo[],
  shareMode: 'private' as 'private' | 'public', // Default to private mode
  linkCopied: false,
  sharingLoading: false // Loading state for share operations
});

// 创建响应式状态（统一管理页面数据）
const state = reactive(createInitialState());

// 从响应式状态中解构为 refs，便于模板和逻辑使用
const {
  inputMessage,
  isLoading,
  sessionId,
  messages,
  toolPanelSize,
  realTime,
  follow,
  title,
  plan,
  lastNoMessageTool,
  lastTool,
  lastEventId,
  cancelCurrentChat,
  attachments,
  shareMode,
  linkCopied,
  sharingLoading
} = toRefs(state);

// 非状态型 refs：不随 reset 重置（DOM/组件引用）
const toolPanel = ref<InstanceType<typeof ToolPanel>>()
const simpleBarRef = ref<InstanceType<typeof SimpleBar>>();
const observerRef = ref<HTMLDivElement>();
const chatContainerRef = ref<HTMLDivElement>();

// 重置页面状态：取消 SSE、恢复初始值
const resetState = () => {
  // Cancel any existing chat connection
  if (cancelCurrentChat.value) {
    cancelCurrentChat.value();
  }

  // Reset reactive state to initial values
  Object.assign(state, createInitialState());
};

// 监听消息变化：如果处于 follow 模式就自动滚动到底部
watch(messages, async () => {
  await nextTick();
  if (follow.value) {
    simpleBarRef.value?.scrollToBottom();
  }
}, { deep: true });



// 获取最后一条 step 消息（用于将工具挂到当前步骤下）
const getLastStep = (): StepContent | undefined => {
  return messages.value.filter(message => message.type === 'step').pop()?.content as StepContent;
}

// 处理 message 事件：插入到消息列表，附件则追加一条 attachments 消息
const handleMessageEvent = (messageData: MessageEventData) => {
  messages.value.push({
    type: messageData.role,
    content: {
      ...messageData
    } as MessageContent,
  });

  if (messageData.attachments?.length > 0) {
    messages.value.push({
      type: 'attachments',
      content: {
        ...messageData
      } as AttachmentsContent,
    });
  }
}

// 处理工具事件（tool）：
// 1) 同 tool_call_id 视为同一次调用，直接合并更新
// 2) 若当前 step 正在 running，则工具挂到 step.tools 下
// 3) 否则作为独立 tool 消息插入
// 4) 非 message 工具会更新 lastNoMessageTool，并在实时模式下打开右侧面板
const handleToolEvent = (toolData: ToolEventData) => {
  const lastStep = getLastStep(); // 当前最后一个 step（如果有）
  let toolContent: ToolContent = {
    ...toolData // 展开浅拷贝，避免直接修改原始事件对象
  }
  // 同 tool_call_id 视为同一次调用，更新已有记录
  if (lastTool.value && lastTool.value.tool_call_id === toolContent.tool_call_id) {
    Object.assign(lastTool.value, toolContent);
  } else {
    // step 运行中：工具挂在该 step 下，否则作为独立消息显示
    if (lastStep?.status === 'running') {
      lastStep.tools.push(toolContent);
    } else {
      messages.value.push({
        type: 'tool',
        content: toolContent,
      });
    }
    lastTool.value = toolContent; // 记录最新工具调用
  }
  // 非 message 工具：更新 lastNoMessageTool，并在实时模式下打开右侧面板
  // 见 frontend/src/constants/tool.ts 的映射
  // toolContent.name 常见值：shell/file/browser/search/message/mcp
  if (toolContent.name !== 'message') {
    lastNoMessageTool.value = toolContent;
    if (realTime.value) {
      toolPanel.value?.showToolPanel(toolContent, true);
    }
  }
}

// 处理 step 事件：
// - pending：等待处理
// - running：新增 step 消息并初始化 tools[]
// - completed：更新最后 step 状态
// - failed：结束 loading
const handleStepEvent = (stepData: StepEventData) => {
  const lastStep = getLastStep(); // 获取当前最后一个 step
  if (stepData.status === 'running') {
    // 新步骤开始：插入 step 消息并初始化工具列表
    messages.value.push({
      type: 'step',
      content: {
        ...stepData,
        tools: []
      } as StepContent,
    });
  } else if (stepData.status === 'completed') {
    // 步骤完成：更新最后一个 step 的状态
    if (lastStep) {
      lastStep.status = stepData.status;
    }
  } else if (stepData.status === 'failed') {
    // 步骤失败：停止 loading
    isLoading.value = false;
  }
}

// 处理 error 事件：展示错误消息并停止 loading
const handleErrorEvent = (errorData: ErrorEventData) => {
  isLoading.value = false;
  messages.value.push({
    type: 'assistant',
    content: {
      content: errorData.error,
      timestamp: errorData.timestamp
    } as MessageContent,
  });
}

// 处理 title 事件：更新会话标题
const handleTitleEvent = (titleData: TitleEventData) => {
  title.value = titleData.title;
}

// 处理 plan 事件：更新计划面板
const handlePlanEvent = (planData: PlanEventData) => {
  plan.value = planData;
}

// SSE 主分发入口：按 event 类型路由到各自处理函数
const handleEvent = (event: AgentSSEEvent) => {
  if (event.event === 'message') {
    handleMessageEvent(event.data as MessageEventData);
  } else if (event.event === 'tool') {
    handleToolEvent(event.data as ToolEventData);
  } else if (event.event === 'step') {
    handleStepEvent(event.data as StepEventData);
  } else if (event.event === 'done') {
    //isLoading.value = false;
  } else if (event.event === 'wait') {
    // TODO: handle wait event
  } else if (event.event === 'error') {
    handleErrorEvent(event.data as ErrorEventData);
  } else if (event.event === 'title') {
    handleTitleEvent(event.data as TitleEventData);
  } else if (event.event === 'plan') {
    handlePlanEvent(event.data as PlanEventData);
  }
  lastEventId.value = event.data.event_id;
}

// 提交输入框内容
const handleSubmit = () => {
  chat(inputMessage.value, attachments.value);
}

// 发起聊天并建立 SSE 连接
const chat = async (message: string = '', files: FileInfo[] = []) => {
  if (!sessionId.value) return;

  // 启动新会话前先取消旧的 SSE 连接
  if (cancelCurrentChat.value) {
    cancelCurrentChat.value();
    cancelCurrentChat.value = null;
  }

  if (message.trim()) {
    // 先把用户消息插入本地列表，提升即时反馈
    messages.value.push({
      type: 'user',
      content: {
        content: message,
        timestamp: Math.floor(Date.now() / 1000)
      } as MessageContent,
    });
  }

  if (files.length > 0) {
    messages.value.push({
      type: 'attachments',
      content: {
        role: 'user',
        attachments: files
      } as AttachmentsContent,
    });
  }

  // 发送消息时自动开启 follow 模式（自动滚动到底部）
  follow.value = true;

  // 清空输入框并进入 loading 状态
  inputMessage.value = '';
  isLoading.value = true;

  try {
    // 建立 SSE 连接并保存取消函数
    cancelCurrentChat.value = await agentApi.chatWithSession(
      sessionId.value,
      message,
      lastEventId.value,
      files.map((file: FileInfo) => ({file_id : file.file_id, 
                                        filename : file.filename})),
      {
        // SSE 连接成功
        onOpen: () => {
          console.log('Chat opened');
          isLoading.value = true;
        },
        onMessage: ({ event, data }) => {
          // SSE 返回的 event/data 经过类型断言后交给统一处理入口
          // 这里的 event 是事件类型（message/tool/step/plan...）
          // data 是对应事件的 payload（已在 client.ts 中 JSON.parse）
          handleEvent({
            event: event as AgentSSEEvent['event'],
            data: data as AgentSSEEvent['data']
          });
        },
        // SSE 正常关闭
        onClose: () => {
          console.log('Chat closed');
          isLoading.value = false;
          // 连接正常关闭时清理取消函数
          if (cancelCurrentChat.value) {
            cancelCurrentChat.value = null;
          }
        },
        // SSE 异常关闭
        onError: (error) => {
          console.error('Chat error:', error);
          isLoading.value = false;
          // 出错时清理取消函数
          if (cancelCurrentChat.value) {
            cancelCurrentChat.value = null;
          }
        }
      }
    );
  } catch (error) {
    console.error('Chat error:', error);
    isLoading.value = false;
    cancelCurrentChat.value = null;
  }
}

// 恢复历史会话：拉取事件并重放到本地状态
const restoreSession = async () => {
  if (!sessionId.value) { // 无 sessionId 时直接提示错误
    showErrorToast(t('Session not found'));
    return;
  }
  const session = await agentApi.getSession(sessionId.value); // 拉取会话详情（含历史事件）
  shareMode.value = session.is_shared ? 'public' : 'private'; // 根据会话共享状态初始化分享模式
  realTime.value = false; // 回放历史事件时关闭 realTime，避免触发实时工具面板逻辑
  for (const event of session.events) {
    handleEvent(event); // 逐条回放到 messages/plan/title 等状态
  }
  realTime.value = true; // 回放结束后恢复 realTime
  if (session.status === SessionStatus.RUNNING || session.status === SessionStatus.PENDING) {
    await chat();
  }
  agentApi.clearUnreadMessageCount(sessionId.value); // 清空未读计数（避免列表红点残留）
}

// 路由切换：清理面板与状态，加载新会话
onBeforeRouteUpdate((to, _, next) => {
  toolPanel.value?.hideToolPanel(); // 路由切换前先关闭右侧面板，避免旧会话残留
  hideFilePanel();
  resetState(); // 重置页面状态（清理消息、取消 SSE 等）
  if (to.params.sessionId) { // 路由切换到已有会话（通过 sessionId 定位）
    messages.value = []; // 切换到新的会话：清空消息
    sessionId.value = String(to.params.sessionId) as string; // 设置新的 sessionId
    restoreSession(); // 恢复新会话：拉取历史事件并回放到本地状态
  }
  next();
})

// 初始化：进入页面时恢复或启动会话
onMounted(() => {
  hideFilePanel(); // 初始化时先收起文件面板
  const routeParams = router.currentRoute.value.params; // 读取路由参数
  if (routeParams.sessionId) {
    sessionId.value = String(routeParams.sessionId) as string; // URL 中包含 sessionId：直接切换到该会话
    // 通常是在别的页面/入口创建会话后，通过路由跳转把首条用户输入带过来，让 ChatPage 一进入就自动发起一次 chat()
    const message = history.state?.message; // history.state 是浏览器 History API 的临时状态，用于跨路由传递一次性数据
    const files: FileInfo[] = history.state?.files; // 从 history.state 取可能的附件
    history.replaceState({}, document.title); // 读取后清空 state，避免刷新/再次进入时重复发送同一条消息
    if (message) {
      chat(message, files); // 表示“新创建会话后带着首条用户输入进来”，立即发起一次任务，直接发起一次对话
    } else {
      restoreSession(); // 无初始消息：恢复历史会话；表示“只是打开已有会话”，走 restoreSession() 回放历史。
    }
  }
});

// 组件销毁：停止 SSE，避免泄漏
onUnmounted(() => {
  if (cancelCurrentChat.value) {
    cancelCurrentChat.value();
    cancelCurrentChat.value = null;
  }
})

// 判断是否为“最近一次非 message 工具”
const isLastNoMessageTool = (tool: ToolContent) => {
  return tool.tool_call_id === lastNoMessageTool.value?.tool_call_id;
}

// 判断工具是否“可视为实时”：正在调用或最近 5 分钟内的最后一次工具
// 用来判断 某个工具调用是否“算作实时”，从而决定右侧工具面板是否显示为实时视图（比如 VNC 实时画面或轮询更新）
const isLiveTool = (tool: ToolContent) => {
  if (tool.status === 'calling') { // 正在调用 → 直接算实时
    return true;
  }
  if (!isLastNoMessageTool(tool)) { // 不是最近一次非 message 工具 → 不算实时
    return false;
  }
  if (tool.timestamp > Date.now() - 5 * 60 * 1000) { // 最近 5 分钟内的最后一次工具 → 算实时
    return true;
  }
  return false;
}

// 点击工具：打开右侧 ToolPanel 并切换到非实时回放
const handleToolClick = (tool: ToolContent) => {
  realTime.value = false; // 点击某条工具调用即切换为“回看模式”：展示当时内容/结果，不再跟随最新实时事件（工具面板会出现“Jump to live”）
  if (sessionId.value) { // 确认已有会话再展示右侧面板
    toolPanel.value?.showToolPanel(tool, isLiveTool(tool)); // 打开工具面板，是否实时由 isLiveTool 判断
  }
}

// 跳回实时：恢复 realTime 并展示最后一次工具
const jumpToRealTime = () => {
  realTime.value = true; // 切回实时模式（跟随最新工具事件）
  if (lastNoMessageTool.value) { // 如果有最近一次非 message 工具
    toolPanel.value?.showToolPanel(lastNoMessageTool.value, isLiveTool(lastNoMessageTool.value)); // 展示最近工具并按实时状态渲染
  }
}

// 手动回到底部，并开启 follow
const handleFollow = () => {
  follow.value = true;
  simpleBarRef.value?.scrollToBottom();
}

// 滚动时更新 follow 状态（是否已经到底）
const handleScroll = (_: Event) => {
  follow.value = simpleBarRef.value?.isScrolledToBottom() ?? false;
}

// 停止当前任务（通知后端）
const handleStop = () => {
  if (sessionId.value) {
    agentApi.stopSession(sessionId.value);
  }
}

// 打开会话文件列表
const handleFileListShow = () => {
  showSessionFileList()
}

// 分享相关逻辑
const handleShareModeChange = async (mode: 'private' | 'public') => {
  if (!sessionId.value || sharingLoading.value) return;
  
  // If mode is same as current, no need to call API
  if (shareMode.value === mode) {
    linkCopied.value = false;
    return;
  }
  
  try {
    sharingLoading.value = true;
    
    if (mode === 'public') {
      await agentApi.shareSession(sessionId.value);
    } else {
      await agentApi.unshareSession(sessionId.value);
    }
    
    shareMode.value = mode;
    linkCopied.value = false;
  } catch (error) {
    console.error('Error changing share mode:', error);
    showErrorToast(t('Failed to change sharing settings'));
  } finally {
    sharingLoading.value = false;
  }
}

// 私密模式下的一键分享：切换到 public
const handleInstantShare = async () => {
  if (!sessionId.value) return;
  
  try {
    sharingLoading.value = true;
    await agentApi.shareSession(sessionId.value);
    shareMode.value = 'public';
    linkCopied.value = false;
  } catch (error) {
    console.error('Error sharing session:', error);
    showErrorToast(t('Failed to share session'));
  } finally {
    sharingLoading.value = false;
  }
}

// 复制分享链接（public 模式）
const handleCopyLink = async () => {
  if (!sessionId.value) return;
  
  const shareUrl = `${window.location.origin}/share/${sessionId.value}`;
  
  try {
    const success = await copyToClipboard(shareUrl);
    
    if (success) {
      linkCopied.value = true;
      setTimeout(() => {
        linkCopied.value = false;
      }, 3000);
      showSuccessToast(t('Link copied to clipboard'));
    } else {
      showErrorToast(t('Failed to copy link'));
    }
  } catch (error) {
    console.error('Error copying share link:', error);
    showErrorToast(t('Failed to copy link'));
  }
}
</script>

<style scoped>
</style>
