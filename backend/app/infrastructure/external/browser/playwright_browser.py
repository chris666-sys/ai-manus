from typing import Dict, Any, Optional, List
from playwright.async_api import async_playwright, Browser, Page
import asyncio
from markdownify import markdownify
from app.infrastructure.external.llm.openai_llm import OpenAILLM
from app.core.config import get_settings
from app.domain.models.tool_result import ToolResult
import logging

# 本模块日志
logger = logging.getLogger(__name__)

class PlaywrightBrowser:
    """基于 Playwright 的浏览器客户端，提供浏览器操作的具体实现"""
    
    def __init__(self, cdp_url: str):
        """初始化浏览器客户端
        
        Args:
            cdp_url: Chrome DevTools Protocol 连接地址
        """
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.playwright = None
        self.llm = OpenAILLM()
        self.settings = get_settings()
        self.cdp_url = cdp_url
        
    async def initialize(self):
        """初始化并确保浏览器资源可用（含重试逻辑）"""
        # 重试逻辑
        max_retries = 5
        retry_delay = 1  # 初始等待 1 秒
        for attempt in range(max_retries):
            try:
                self.playwright = await async_playwright().start()
                # 通过 CDP 连接已有 Chrome 实例
                self.browser = await self.playwright.chromium.connect_over_cdp(self.cdp_url)
                # 获取所有浏览器上下文
                contexts = self.browser.contexts
                if contexts and len(contexts[0].pages) == 1:
                    # 判断是否为初始页（根据 URL）
                    page = contexts[0].pages[0]
                    page_url = await page.evaluate("window.location.href")
                    if (
                        page_url == "about:blank" or 
                        page_url == "chrome://newtab/" or 
                        page_url == "chrome://new-tab-page/" or 
                        not page_url
                    ):
                        # 仅在初始页且只有一个标签页时复用该页
                        self.page = page
                    else:
                        # 非初始页则新建页面
                        self.page = await contexts[0].new_page()
                else:
                    # 其他情况新建页面
                    context = contexts[0] if contexts else await self.browser.new_context()
                    self.page = await context.new_page()
                return True
            except Exception as e:
                # 清理失败时占用的资源
                await self.cleanup()
                
                # 达到最大重试次数则返回失败
                if attempt == max_retries - 1:
                    logger.error(f"Initialization failed (retried {max_retries} times): {e}")
                    return False
                
                # 否则按指数退避增加等待时间，最多等待 10 秒
                retry_delay = min(retry_delay * 2, 10)
                logger.warning(f"Initialization failed, will retry in {retry_delay} seconds: {e}")
                await asyncio.sleep(retry_delay)

    async def cleanup(self):
        """清理 Playwright 资源：先关闭所有标签页，再关闭浏览器"""
        try:
            # 若浏览器存在，先关闭所有标签页
            if self.browser:
                contexts = self.browser.contexts
                if contexts:
                    for context in contexts:
                        pages = context.pages
                        for page in pages:
                            # 避免重复关闭 self.page
                            if page != self.page or (self.page and not self.page.is_closed()):
                                await page.close()
            
            # 确保当前页已关闭（若存在且未关闭）
            if self.page and not self.page.is_closed():
                await self.page.close()
                
            if self.browser:
                await self.browser.close()
                
            if self.playwright:
                await self.playwright.stop()
                
        except Exception as e:
            logger.error(f"Error occurred when cleaning up resources: {e}")
        finally:
            # 重置引用
            self.page = None
            self.browser = None
            self.playwright = None
    
    async def _ensure_browser(self):
        """确保浏览器已启动"""
        if not self.browser or not self.page:
            if not await self.initialize():
                raise Exception("Unable to initialize browser resources")
    
    async def _ensure_page(self):
        """确保页面已创建，并同步为当前活动标签页（最右侧标签页）"""
        await self._ensure_browser()
        if not self.page:
            self.page = await self.browser.new_page()
        else:
            contexts = self.browser.contexts
            if contexts:
                current_context = contexts[0]
                pages = current_context.pages
                
                if pages:
                    # 取最右侧标签页（通常为最近打开的页面）
                    rightmost_page = pages[-1]
                    if self.page != rightmost_page:
                        self.page = rightmost_page
    
    async def wait_for_page_load(self, timeout: int = 15) -> bool:
        """等待页面加载完成，最多等待指定时长
        
        Args:
            timeout: 最大等待时间（秒），默认 15 秒
            
        Returns:
            bool: 是否成功等到页面完全加载
        """
        await self._ensure_page()
        
        start_time = asyncio.get_event_loop().time()
        check_interval = 5  # 每 5 秒检查一次
        
        while asyncio.get_event_loop().time() - start_time < timeout:
            # 检查页面是否已完全加载
            is_loaded = await self.page.evaluate("""() => {
                return document.readyState === 'complete';
            }""")
            
            if is_loaded:
                return True
                
            await asyncio.sleep(check_interval)
        
        # 超时，页面未加载完成
        return False
    
    async def _extract_content(self) -> Dict[str, Any]:
        """从当前页面提取可见内容并转为 Markdown（经 LLM 整理）"""

        # 在页面内执行 JS，获取视口内元素
        visible_content = await self.page.evaluate("""() => {
            const visibleElements = [];
            const viewportHeight = window.innerHeight;
            const viewportWidth = window.innerWidth;
            
            // Get all potentially relevant elements
            const elements = document.querySelectorAll('body *');
            
            for (const element of elements) {
                // Check if the element is in the viewport and visible
                const rect = element.getBoundingClientRect();
                
                // Element must have some dimensions
                if (rect.width === 0 || rect.height === 0) continue;
                
                // Element must be within the viewport
                if (
                    rect.bottom < 0 || 
                    rect.top > viewportHeight ||
                    rect.right < 0 || 
                    rect.left > viewportWidth
                ) continue;
                
                // Check if the element is visible (not hidden by CSS)
                const style = window.getComputedStyle(element);
                if (
                    style.display === 'none' || 
                    style.visibility === 'hidden' || 
                    style.opacity === '0'
                ) continue;
                
                // If it's a text node or meaningful element, add it to the results
                if (
                    element.innerText || 
                    element.tagName === 'IMG' || 
                    element.tagName === 'INPUT' || 
                    element.tagName === 'BUTTON'
                ) {
                    visibleElements.push(element.outerHTML);
                }
            }
            
            // Build HTML containing these visible elements
            return '<div>' + visibleElements.join('') + '</div>';
        }""")

        # 转为 Markdown
        markdown_content = markdownify(visible_content)

        # 限制内容最大长度为 50000 字符，避免超出 LLM 的 token 限制
        max_content_length = min(50000, len(markdown_content))
        response = await self.llm.ask([{
            "role": "system",
            "content": "You are a professional web page information extraction assistant. Please extract all information from the current page content and convert it to Markdown format."
        },
        {
            "role": "user",
            "content": markdown_content[:max_content_length]
        }
        ])
        
        return response.get("content", "")
    
    async def view_page(self) -> ToolResult:
        """查看当前页面视口内可见元素并转换为 Markdown 格式"""
        # 确保页面已创建
        await self._ensure_page()
        
        # 等待页面完全加载，最多等待15秒
        await self.wait_for_page_load()
        
        # 首先更新交互式元素缓存
        interactive_elements = await self._extract_interactive_elements()
        
        # 返回包含交互式元素和页面内容的工具结果
        return ToolResult(
            success=True,
            data={
                "interactive_elements": interactive_elements,
                "content": await self._extract_content(),
            }
        )
    
    async def _extract_interactive_elements(self) -> List[str]:
        """提取当前页面视口内可见的交互元素，返回格式为 index:<tag>text</tag> 的列表"""
        await self._ensure_page()
        
        # 清空当前页缓存，保证拿到最新元素列表
        self.page.interactive_elements_cache = []
        
        # 在页面内执行 JS，获取视口内的交互元素
        interactive_elements = await self.page.evaluate("""() => {
            const interactiveElements = [];
            const viewportHeight = window.innerHeight;
            const viewportWidth = window.innerWidth;
            
            // Get all potentially relevant interactive elements
            const elements = document.querySelectorAll('button, a, input, textarea, select, [role="button"], [tabindex]:not([tabindex="-1"])');
            
            let validElementIndex = 0; // For generating consecutive indices
            
            for (let i = 0; i < elements.length; i++) {
                const element = elements[i];
                // Check if the element is in the viewport and visible
                const rect = element.getBoundingClientRect();
                
                // Element must have some dimensions
                if (rect.width === 0 || rect.height === 0) continue;
                
                // Element must be within the viewport
                if (
                    rect.bottom < 0 || 
                    rect.top > viewportHeight ||
                    rect.right < 0 || 
                    rect.left > viewportWidth
                ) continue;
                
                // Check if the element is visible (not hidden by CSS)
                const style = window.getComputedStyle(element);
                if (
                    style.display === 'none' || 
                    style.visibility === 'hidden' || 
                    style.opacity === '0'
                ) continue;
                
                
                // Get element type and text
                let tagName = element.tagName.toLowerCase();
                let text = '';
                
                if (element.value && ['input', 'textarea', 'select'].includes(tagName)) {
                    text = element.value;
                    
                    // Add label and placeholder information for input elements
                    if (tagName === 'input') {
                        // Get associated label text
                        let labelText = '';
                        if (element.id) {
                            const label = document.querySelector(`label[for="${element.id}"]`);
                            if (label) {
                                labelText = label.innerText.trim();
                            }
                        }
                        
                        // Look for parent or sibling label
                        if (!labelText) {
                            const parentLabel = element.closest('label');
                            if (parentLabel) {
                                labelText = parentLabel.innerText.trim().replace(element.value, '').trim();
                            }
                        }
                        
                        // Add label information
                        if (labelText) {
                            text = `[Label: ${labelText}] ${text}`;
                        }
                        
                        // Add placeholder information
                        if (element.placeholder) {
                            text = `${text} [Placeholder: ${element.placeholder}]`;
                        }
                    }
                } else if (element.innerText) {
                    text = element.innerText.trim().replace(/\\s+/g, ' ');
                } else if (element.alt) { // For image buttons
                    text = element.alt;
                } else if (element.title) { // For elements with title
                    text = element.title;
                } else if (element.placeholder) { // For placeholder text
                    text = `[Placeholder: ${element.placeholder}]`;
                } else if (element.type) { // For input type
                    text = `[${element.type}]`;
                    
                    // Add label and placeholder information for text-less input elements
                    if (tagName === 'input') {
                        // Get associated label text
                        let labelText = '';
                        if (element.id) {
                            const label = document.querySelector(`label[for="${element.id}"]`);
                            if (label) {
                                labelText = label.innerText.trim();
                            }
                        }
                        
                        // Look for parent or sibling label
                        if (!labelText) {
                            const parentLabel = element.closest('label');
                            if (parentLabel) {
                                labelText = parentLabel.innerText.trim();
                            }
                        }
                        
                        // Add label information
                        if (labelText) {
                            text = `[Label: ${labelText}] ${text}`;
                        }
                        
                        // Add placeholder information
                        if (element.placeholder) {
                            text = `${text} [Placeholder: ${element.placeholder}]`;
                        }
                    }
                } else {
                    text = '[No text]';
                }
                
                // Maximum limit on text length to keep it clear
                if (text.length > 100) {
                    text = text.substring(0, 97) + '...';
                }
                
                // Only add data-manus-id attribute to elements that meet the conditions
                element.setAttribute('data-manus-id', `manus-element-${validElementIndex}`);
                                                        
                // Build selector - using only data-manus-id
                const selector = `[data-manus-id="manus-element-${validElementIndex}"]`;
                
                // Add element information to the array
                interactiveElements.push({
                    index: validElementIndex,  // Use consecutive index
                    tag: tagName,
                    text: text,
                    selector: selector
                });
                
                validElementIndex++; // Increment valid element counter
            }
            
            return interactiveElements;
        }""")
        
        # 更新缓存
        self.page.interactive_elements_cache = interactive_elements
        
        # 按指定格式组装元素信息
        formatted_elements = []
        for el in interactive_elements:
            formatted_elements.append(f"{el['index']}:<{el['tag']}>{el['text']}</{el['tag']}>")
        
        return formatted_elements
    
    async def navigate(self, url: str, timeout: Optional[int] = 15000) -> ToolResult:
        """跳转到指定 URL
        
        Args:
            url: 要访问的 URL
            timeout: 导航超时（毫秒），默认 15000（15 秒）
        """
        await self._ensure_page()
        try:
            # 页面即将变化，清空交互元素缓存
            self.page.interactive_elements_cache = []
            try:
                await self.page.goto(url, timeout=timeout)
            except Exception as e:
                logger.warning(f"Failed to navigate to {url}: {str(e)}")
            return ToolResult(
                success=True,
                data={
                    "interactive_elements": await self._extract_interactive_elements(),
                }
            )
        except Exception as e:
            return ToolResult(success=False, message=f"Failed to navigate to {url}: {str(e)}")
    
    async def restart(self, url: str) -> ToolResult:
        """重启浏览器并跳转到指定 URL"""
        await self.cleanup()
        return await self.navigate(url)

    
    async def _get_element_by_index(self, index: int) -> Optional[Any]:
        """根据索引用 data-manus-id 选择器获取元素
        
        Args:
            index: 元素索引
            
        Returns:
            找到的元素，未找到则返回 None
        """
        # 检查是否有缓存的交互元素
        if not hasattr(self.page, 'interactive_elements_cache') or not self.page.interactive_elements_cache or index >= len(self.page.interactive_elements_cache):
            return None
        
        selector = f'[data-manus-id="manus-element-{index}"]'
        return await self.page.query_selector(selector)
    
    async def click(
        self,
        index: Optional[int] = None,
        coordinate_x: Optional[float] = None,
        coordinate_y: Optional[float] = None
    ) -> ToolResult:
        """点击元素：可按索引点击交互元素，或按坐标点击"""
        await self._ensure_page()
        if coordinate_x is not None and coordinate_y is not None:
            await self.page.mouse.click(coordinate_x, coordinate_y)
        elif index is not None:
            try:
                element = await self._get_element_by_index(index)
                if not element:
                    return ToolResult(success=False, message=f"Cannot find interactive element with index {index}")
                
                # 检查元素是否可见
                is_visible = await self.page.evaluate("""(element) => {
                    if (!element) return false;
                    const rect = element.getBoundingClientRect();
                    const style = window.getComputedStyle(element);
                    return !(
                        rect.width === 0 || 
                        rect.height === 0 || 
                        style.display === 'none' || 
                        style.visibility === 'hidden' || 
                        style.opacity === '0'
                    );
                }""", element)
                
                if not is_visible:
                    # 尝试滚动到元素位置
                    await self.page.evaluate("""(element) => {
                        if (element) {
                            element.scrollIntoView({behavior: 'smooth', block: 'center'});
                        }
                    }""", element)
                    await asyncio.sleep(1)
                
                await element.click(timeout=5000)
            except Exception as e:
                return ToolResult(success=False, message=f"Failed to click element: {str(e)}")
        return ToolResult(success=True)
    
    async def input(
        self,
        text: str,
        press_enter: bool,
        index: Optional[int] = None,
        coordinate_x: Optional[float] = None,
        coordinate_y: Optional[float] = None
    ) -> ToolResult:
        """输入文本：可按索引在指定元素输入，或先按坐标点击再输入；可选是否按回车"""
        await self._ensure_page()
        if coordinate_x is not None and coordinate_y is not None:
            await self.page.mouse.click(coordinate_x, coordinate_y)
            await self.page.keyboard.type(text)
        elif index is not None:
            try:
                element = await self._get_element_by_index(index)
                if not element:
                    return ToolResult(success=False, message=f"Cannot find interactive element with index {index}")
                
                try:
                    await element.fill("")
                    await element.type(text)
                except Exception as e:
                    # fill 失败时改为先点击再键盘输入
                    await element.click()
                    await self.page.keyboard.type(text)
            except Exception as e:
                return ToolResult(success=False, message=f"Failed to input text: {str(e)}")
        
        if press_enter:
            await self.page.keyboard.press("Enter")
        return ToolResult(success=True)
    
    async def move_mouse(
        self,
        coordinate_x: float,
        coordinate_y: float
    ) -> ToolResult:
        """将鼠标移动到指定坐标"""
        await self._ensure_page()
        await self.page.mouse.move(coordinate_x, coordinate_y)
        return ToolResult(success=True)
    
    async def press_key(self, key: str) -> ToolResult:
        """模拟按下指定按键"""
        await self._ensure_page()
        await self.page.keyboard.press(key)
        return ToolResult(success=True)
    
    async def select_option(
        self,
        index: int,
        option: int
    ) -> ToolResult:
        """在下拉框中按索引选择选项"""
        await self._ensure_page()
        try:
            element = await self._get_element_by_index(index)
            if not element:
                return ToolResult(success=False, message=f"Cannot find selector element with index {index}")
            
            await element.select_option(index=option)
            return ToolResult(success=True)
        except Exception as e:
            return ToolResult(success=False, message=f"Failed to select option: {str(e)}")
    
    async def scroll_up(
        self,
        to_top: Optional[bool] = None
    ) -> ToolResult:
        """向上滚动页面；to_top 为 True 时滚动到顶部"""
        await self._ensure_page()
        if to_top:
            await self.page.evaluate("window.scrollTo(0, 0)")
        else:
            await self.page.evaluate("window.scrollBy(0, -window.innerHeight)")
        return ToolResult(success=True)
    
    async def scroll_down(
        self,
        to_bottom: Optional[bool] = None
    ) -> ToolResult:
        """向下滚动页面；to_bottom 为 True 时滚动到底部"""
        await self._ensure_page()
        if to_bottom:
            await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        else:
            await self.page.evaluate("window.scrollBy(0, window.innerHeight)")
        return ToolResult(success=True)
    
    async def screenshot(
        self,
        full_page: Optional[bool] = False
    ) -> bytes:
        """对当前页面截图
        
        Args:
            full_page: 是否截取整页，False 则仅截取当前视口
            
        Returns:
            bytes: PNG 截图二进制数据
        """
        await self._ensure_page()
        
        screenshot_options = {
            "full_page": full_page,
            "type": "png"
        }
        
        return await self.page.screenshot(**screenshot_options)
    
    async def console_exec(self, javascript: str) -> ToolResult:
        """在页面上下文中执行 JavaScript 代码"""
        await self._ensure_page()
        result = await self.page.evaluate(javascript)
        return ToolResult(success=True, data={"result": result})
    
    async def console_view(self, max_lines: Optional[int] = None) -> ToolResult:
        """查看控制台输出，可选只取最近 max_lines 行"""
        await self._ensure_page()
        logs = await self.page.evaluate("""() => {
            return window.console.logs || [];
        }""")
        if max_lines is not None:
            logs = logs[-max_lines:]
        return ToolResult(success=True, data={"logs": logs})
