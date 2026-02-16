"""
Shell Service Implementation - Async Version
"""
import os
import subprocess
import uuid
import getpass
import socket
import logging
import asyncio
import re
from typing import Dict, Any, Optional, List, Tuple
from app.models.shell import (
    ShellExecResult, ShellViewResult, ShellWaitResult,
    ShellWriteResult, ShellKillResult, ShellTask, ConsoleRecord
)
from app.core.exceptions import AppException, ResourceNotFoundException, BadRequestException

# Set up logger
logger = logging.getLogger(__name__)

class ShellService:
    # Store active shell sessions
    active_shells: Dict[str, Dict[str, Any]] = {}
    
    # Store shell tasks
    shell_tasks: Dict[str, ShellTask] = {}

    def _remove_ansi_escape_codes(self, text: str) -> str:
        """Remove ANSI escape codes from text"""
        # Pattern to match ANSI escape sequences
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        return ansi_escape.sub('', text)

    def _get_display_path(self, path: str) -> str:
        """Get the path for display, replacing user home directory with ~"""
        home_dir = os.path.expanduser("~")
        logger.debug(f"Home directory: {home_dir} , path: {path}")
        if path.startswith(home_dir):
            return path.replace(home_dir, "~", 1)
        return path

    def _format_ps1(self, exec_dir: str) -> str:
        """Format the command prompt"""
        username = getpass.getuser()
        hostname = socket.gethostname()
        display_dir = self._get_display_path(exec_dir)
        return f"{username}@{hostname}:{display_dir} $"

    async def _create_process(self, command: str, exec_dir: str) -> asyncio.subprocess.Process:
        """
        创建新的异步子进程，在指定目录下通过 bash 执行命令。

        Args:
            command: 要执行的 shell 命令字符串。
            exec_dir: 子进程的工作目录（cwd）。

        Returns:
            asyncio.subprocess.Process: 已启动的子进程实例，stdout/stderr 通过 PIPE 可读。
        """
        logger.debug(f"Creating process for command: {command} in directory: {exec_dir}")
        return await asyncio.create_subprocess_shell(
            command,
            executable="/bin/bash",           # 使用 bash 解析并执行命令
            cwd=exec_dir,                     # 进程工作目录
            stdout=asyncio.subprocess.PIPE,   # 标准输出通过管道读取
            stderr=asyncio.subprocess.STDOUT, # 标准错误重定向到 stdout，便于统一读取
            stdin=asyncio.subprocess.PIPE,    # 标准输入管道（当前未用于写入）
            limit=1024 * 1024                 # 流缓冲区大小 1MB
        )

    async def _start_output_reader(self, session_id: str, process: asyncio.subprocess.Process):
        """Start a coroutine to continuously read process output and store it"""
        logger.debug(f"Starting output reader for session: {session_id}")
        while True:
            if process.stdout:
                try:
                    buffer = await process.stdout.read(128)
                    if not buffer:
                        # Process output ended
                        break
                    
                    output = buffer.decode('utf-8')
                    # 将输出追加到会话的完整输出字符串中
                    shell = self.active_shells.get(session_id)
                    if shell:
                        shell["output"] += output
                        # 同时将输出追加到控制台历史中最新一条记录（最后一条）的输出字段
                        # 这样每条命令的输出就能被正确关联到对应的 ConsoleRecord 中
                        if shell["console"]:
                            shell["console"][-1].output += output
                except Exception as e:
                    logger.error(f"Error reading process output: {str(e)}", exc_info=True)
                    break
            else:
                break
        
        logger.debug(f"Output reader for session {session_id} has finished")

    async def exec_command(self, session_id: str, exec_dir: Optional[str], command: str) -> ShellExecResult:
        """
        在指定 shell 会话中异步执行命令。

        支持新建会话与复用已有会话：新建时创建子进程并注册会话；
        已有会话时先终止旧进程（若仍在运行），再创建新进程并更新会话信息。
        会尝试等待进程结束（最多 5 秒），若超时则返回 running 状态，由调用方后续轮询或等待。

        Args:
            session_id: 会话唯一标识，用于区分不同 shell 会话。
            exec_dir: 命令工作目录，为 None 时使用当前用户主目录。
            command: 要执行的 shell 命令字符串。

        Returns:
            ShellExecResult: 包含 session_id、command、status（completed/running）、
                若已完成则含 returncode 和 output，若超时则仅含 running 状态。

        Raises:
            BadRequestException: exec_dir 所指目录不存在时抛出。
            AppException: 执行过程中发生其他异常时抛出，附带 session_id 与 command。

        shell的数据格式示例
        shell = {
            "process": <asyncio.subprocess.Process object>,
            "exec_dir": "/home/user/project",
            "output": "xxxxxxxxxx任意字符、文件路径等",
            "console": [
                ConsoleRecord(
                    ps1="user@host:/home/user/project $",
                    command="ls",
                    output="file1.txt\nfile2.txt\n"
                ),
                ConsoleRecord(
                    ps1="user@host:/home/user/project $",
                    command="pwd",
                    output="/home/user/project\n"
                )
            ]
        }
        """
        logger.info(f"Executing command in session {session_id}: {command}")

        # 未指定工作目录时，使用当前用户主目录
        if not exec_dir:
            exec_dir = os.path.expanduser("~")
        # 校验工作目录是否存在，不存在则直接报错
        if not os.path.exists(exec_dir):
            logger.error(f"Directory does not exist: {exec_dir}")
            raise BadRequestException(f"Directory does not exist: {exec_dir}")

        try:
            # 生成当前环境的命令行提示符（如 user@host:~ $），用于控制台展示
            ps1 = self._format_ps1(exec_dir)

            # 分支一：该 session_id 尚未存在，视为新会话，需要创建新进程并登记
            if session_id not in self.active_shells:
                logger.debug(f"Creating new shell session: {session_id}")
                process = await self._create_process(command, exec_dir)
                self.active_shells[session_id] = {
                    "process": process,
                    "exec_dir": exec_dir,
                    "output": "",
                    # 控制台历史：首条为当前命令（提示符+命令），output 由 _start_output_reader 后续写入
                    "console": [ConsoleRecord(ps1=ps1, command=command, output="")]
                }
                # 启动后台协程持续读取该进程的 stdout，并写入会话的 output 与最新一条 console 记录
                asyncio.create_task(self._start_output_reader(session_id, process))
            else:
                # 分支二：该 session_id 已存在，在已有会话中执行新命令（会替换掉当前会话正在跑的进程）
                logger.debug(f"Using existing shell session: {session_id}")
                shell = self.active_shells[session_id]
                old_process = shell["process"]

                # 若上一轮进程尚未退出，先尝试优雅终止（SIGTERM），超时 1 秒后强制 kill
                if old_process.returncode is None:
                    logger.debug(f"Terminating previous process in session: {session_id}")
                    try:
                        old_process.terminate()
                        await asyncio.wait_for(old_process.wait(), timeout=1)
                    except Exception:
                        # 优雅退出失败（超时或异常），则强制杀死进程
                        logger.warning(f"Forcefully killing process in session: {session_id}")
                        old_process.kill()

                # 为新命令创建新的子进程
                process = await self._create_process(command, exec_dir)

                # 用新进程和新工作目录更新会话元数据，并清空上一轮输出
                self.active_shells[session_id]["process"] = process
                self.active_shells[session_id]["exec_dir"] = exec_dir
                self.active_shells[session_id]["output"] = ""

                # 追加一条新的控制台记录（命令与 PS1），输出先为空，由 _start_output_reader 后续追加
                shell["console"].append(ConsoleRecord(ps1=ps1, command=command, output=""))

                # 同样启动输出读取协程，将新进程的 stdout 写入当前会话
                asyncio.create_task(self._start_output_reader(session_id, process))

            # 尝试在限定时间内等待进程结束（此处为 5 秒），以便能立即返回“已完成”的结果
            try:
                logger.debug(f"Waiting for process completion in session: {session_id}")
                wait_result = await self.wait_for_process(session_id, seconds=5)
                if wait_result.returncode is not None:
                    # 进程已在 5 秒内结束，通过 view_shell 拉取当前会话的完整输出并返回已完成结果
                    logger.debug(f"Process completed with code: {wait_result.returncode}")
                    view_result = await self.view_shell(session_id)

                    return ShellExecResult(
                        session_id=session_id,
                        command=command,
                        status="completed",
                        returncode=wait_result.returncode,
                        output=view_result.output,
                    )
            except BadRequestException:
                # 等待超时或会话无效（如 wait_for_process 内部抛 BadRequestException），视为进程仍在运行
                logger.debug(f"Process still running after timeout in session: {session_id}")
                pass
            except Exception as e:
                # 其他异常（如网络、内部错误）仅打日志，不中断流程，下面会返回 running
                logger.warning(f"Exception while waiting for process: {str(e)}")
                pass

            # 进程未在 5 秒内结束，或等待过程出现异常：返回“运行中”状态，调用方可轮询 view_shell / wait_for_process
            console = self.get_console_records(session_id)

            return ShellExecResult(
                session_id=session_id,
                command=command,
                status="running",
            )
        except Exception as e:
            logger.error(f"Command execution failed: {str(e)}", exc_info=True)
            raise AppException(
                message=f"Command execution failed: {str(e)}",
                data={"session_id": session_id, "command": command}
            )

    async def view_shell(self, session_id: str, console: bool = False) -> ShellViewResult:
        """
        异步查看指定 shell 会话的当前内容。

        返回该会话迄今为止的完整标准输出（去除 ANSI 转义码），
        并可根据参数决定是否附带按条划分的控制台历史（每条含 ps1、命令与输出）。

        Args:
            session_id: 会话唯一标识。
            console: 是否在结果中包含控制台记录列表（每条为 ConsoleRecord）。
                    True 时返回 get_console_records(session_id) 的结果，便于前端按条渲染。

        Returns:
            ShellViewResult: 包含 output（去 ANSI 的完整输出）、session_id、以及可选的 console 列表。

        Raises:
            ResourceNotFoundException: 当 session_id 对应的会话不存在时抛出。
        """
        logger.debug(f"Viewing shell content for session: {session_id}")
        if session_id not in self.active_shells:
            logger.error(f"Session ID not found: {session_id}")
            raise ResourceNotFoundException(f"Session ID does not exist: {session_id}")

        shell = self.active_shells[session_id]

        # 取出会话当前累积的原始输出，并去掉 ANSI 转义序列，便于纯文本展示或存储
        raw_output = shell["output"]
        clean_output = self._remove_ansi_escape_codes(raw_output)

        # 仅当调用方需要时，才拉取“按条”的控制台历史（每条含 ps1、command、output）
        if console:
            console = self.get_console_records(session_id)
        else:
            console = None

        return ShellViewResult(
            output=clean_output,
            session_id=session_id,
            console=console
        )

    def get_console_records(self, session_id: str) -> List[ConsoleRecord]:
        """
        Get command console records for the specified session (this method doesn't need to be async)
        """
        logger.debug(f"Getting console records for session: {session_id}")
        if session_id not in self.active_shells:
            logger.error(f"Session ID not found: {session_id}")
            raise ResourceNotFoundException(f"Session ID does not exist: {session_id}")
        
        # Get raw console records and filter ANSI escape codes
        raw_console = self.active_shells[session_id]["console"]
        clean_console = []
        for record in raw_console:
            clean_record = ConsoleRecord(
                ps1=record.ps1,
                command=record.command,
                output=self._remove_ansi_escape_codes(record.output)
            )
            clean_console.append(clean_record)
        
        return clean_console

    async def wait_for_process(self, session_id: str, seconds: Optional[int] = None) -> ShellWaitResult:
        """
        Asynchronously wait for the process in the specified shell session to return
        """
        logger.debug(f"Waiting for process in session: {session_id}, timeout: {seconds}s")
        if session_id not in self.active_shells:
            logger.error(f"Session ID not found: {session_id}")
            raise ResourceNotFoundException(f"Session ID does not exist: {session_id}")
        
        shell = self.active_shells[session_id]
        process = shell["process"]
        
        try:
            # Asynchronously wait for process to complete
            if seconds is None:
                seconds = 60
            await asyncio.wait_for(process.wait(), timeout=seconds)
            
            logger.info(f"Process completed with return code: {process.returncode}")
            return ShellWaitResult(
                returncode=process.returncode
            )
        except asyncio.TimeoutError:
            logger.warning(f"Process wait timeout expired: {seconds}s")
            raise BadRequestException(f"Wait timeout: {seconds} seconds")
        except Exception as e:
            logger.error(f"Failed to wait for process: {str(e)}", exc_info=True)
            raise AppException(message=f"Failed to wait for process: {str(e)}")

    async def write_to_process(self, session_id: str, input_text: str, press_enter: bool) -> ShellWriteResult:
        """
        Asynchronously write input to the process in the specified shell session
        """
        logger.debug(f"Writing to process in session: {session_id}, press_enter: {press_enter}")
        if session_id not in self.active_shells:
            logger.error(f"Session ID not found: {session_id}")
            raise ResourceNotFoundException(f"Session ID does not exist: {session_id}")
        
        shell = self.active_shells[session_id]
        process = shell["process"]
        
        try:
            # Check if the process is still running
            if process.returncode is not None:
                logger.error(f"Process has already terminated, cannot write input")
                raise BadRequestException("Process has ended, cannot write input")
            
            # Prepare input data
            if press_enter:
                input_data = f"{input_text}\n".encode()
            else:
                input_data = input_text.encode()
            
            # Add input to output and console records
            input_str = input_data.decode('utf-8')
            shell["output"] += input_str
            if shell["console"]:
                shell["console"][-1].output += input_str
            
            # Asynchronously write input
            process.stdin.write(input_data)
            await process.stdin.drain()
            
            logger.info(f"Successfully wrote input to process")
            
            return ShellWriteResult(
                status="success"
            )
        except Exception as e:
            logger.error(f"Failed to write input: {str(e)}", exc_info=True)
            raise AppException(message=f"Failed to write input: {str(e)}")

    async def kill_process(self, session_id: str) -> ShellKillResult:
        """
        Asynchronously terminate the process in the specified shell session
        """
        logger.info(f"Killing process in session: {session_id}")
        if session_id not in self.active_shells:
            logger.error(f"Session ID not found: {session_id}")
            raise ResourceNotFoundException(f"Session ID does not exist: {session_id}")
        
        shell = self.active_shells[session_id]
        process = shell["process"]
        
        try:
            # Check if the process is still running
            if process.returncode is None:
                # Try to terminate gracefully
                logger.debug(f"Attempting to terminate process gracefully")
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=3)
                except asyncio.TimeoutError:
                    # If graceful termination fails, force kill
                    logger.warning(f"Forcefully killing the process")
                    process.kill()
                    await process.wait()
                
                logger.info(f"Process terminated with return code: {process.returncode}")
                return ShellKillResult(
                    status="terminated",
                    returncode=process.returncode
                )
            else:
                logger.info(f"Process was already terminated with return code: {process.returncode}")
                return ShellKillResult(
                    status="already_terminated",
                    returncode=process.returncode
                )
        except Exception as e:
            logger.error(f"Failed to kill process: {str(e)}", exc_info=True)
            raise AppException(message=f"Failed to terminate process: {str(e)}")

    def create_session_id(self) -> str:
        """
        Create a new session ID (this method doesn't need to be async)
        """
        session_id = str(uuid.uuid4())
        logger.debug(f"Created new session ID: {session_id}")
        return session_id

shell_service = ShellService()