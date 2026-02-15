# 基础镜像：Ubuntu 22.04
FROM docker.m.daocloud.io/library/ubuntu:22.04

# 安装过程中避免交互式提示
ENV DEBIAN_FRONTEND=noninteractive

# 设置主机名为 sandbox
ENV HOSTNAME=sandbox

# 配置 apt 源使用阿里云镜像
RUN sed -i 's|http://archive.ubuntu.com/ubuntu/|http://mirrors.aliyun.com/ubuntu/|g' /etc/apt/sources.list && \
    sed -i 's|http://security.ubuntu.com/ubuntu/|http://mirrors.aliyun.com/ubuntu/|g' /etc/apt/sources.list && \
    sed -i 's|http://ports.ubuntu.com/ubuntu-ports/|http://mirrors.aliyun.com/ubuntu-ports/|g' /etc/apt/sources.list

# 更新并安装基础工具
RUN apt-get update && apt-get install -y \
    sudo \
    bc \
    curl \
    wget \
    gnupg \
    software-properties-common \
    xvfb \
    x11vnc \
    xterm \
    socat \
    supervisor \
    websockify \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

    # sudo：权限管理工具
    # bc：计算器工具
    # curl：HTTP 客户端工具
    # wget：下载工具
    # gnupg：GPG 加密工具，用于验证签名和密钥管理
    # software-properties-common：软件源管理工具，用于添加 PPA 源
    # xvfb：X11 虚拟显示服务器，提供无头图形环境
    # x11vnc：VNC 服务器，用于远程桌面访问
    # xterm：终端模拟器
    # socat：网络工具，用于端口转发
    # supervisor：进程管理工具，用于管理和监控多个服务
    # websockify：WebSocket 代理工具，将 VNC 转换为 WebSocket 协议

# 创建 ubuntu 用户并授予 sudo 权限，配置无密码 sudo
RUN useradd -m -d /home/ubuntu -s /bin/bash ubuntu && \
    echo "ubuntu ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/ubuntu

# 安装 Python 3.10.12
# 添加 deadsnakes/ppa 源
# 安装 Python 3.10、venv、dev 包和 pip
# 设置 python3 指向 Python 3.10
# update-alternatives： Debian/Ubuntu 的替代方案管理工具，用于管理同一命令的多个版本
# 1：优先级（数字越大优先级越高），当有多个版本时，优先级高的会被选为默认
RUN add-apt-repository ppa:deadsnakes/ppa && \
    apt-get update && \
    apt-get install -y python3.10 python3.10-venv python3.10-dev python3-pip && \
    update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.10 1 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 配置 pip 使用阿里云镜像
RUN pip3 config set global.index-url https://mirrors.aliyun.com/pypi/simple/

# 安装 Node.js 20.18.0
# 添加 NodeSource GPG 密钥
# 添加 NodeSource 20.x 源
# 安装 nodejs
RUN mkdir -p /etc/apt/keyrings && \
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg && \
    echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" | tee /etc/apt/sources.list.d/nodesource.list && \
    apt-get update && \
    apt-get install -y nodejs && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 配置 npm 使用阿里云镜像
RUN npm config set registry https://registry.npmmirror.com

# 安装 Google Chrome
RUN add-apt-repository ppa:xtradeb/apps -y && \
    apt-get update && \
    apt-get install -y chromium  --no-install-recommends && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 安装中文字体和语言支持
RUN apt-get update && apt-get install -y \
    fonts-noto-cjk \
    fonts-noto-color-emoji \
    language-pack-zh-hans \
    locales \
    && locale-gen zh_CN.UTF-8 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

    # fonts-noto-cjk \          # 中文字体
    # fonts-noto-color-emoji \  # Emoji 字体
    # language-pack-zh-hans \   # 简体中文语言包
    # locales \                 # 本地化工具
    # && locale-gen zh_CN.UTF-8 \  # 生成中文 locale

# 设置默认本地化环境（已注释）
#ENV LANG=zh_CN.UTF-8 \
#    LANGUAGE=zh_CN:zh \
#    LC_ALL=zh_CN.UTF-8

# 设置工作目录
WORKDIR /app

# 复制项目文件（先复制依赖文件以利用缓存）
COPY requirements.txt .

# 安装 Python 依赖
RUN pip3 install --no-cache-dir -r requirements.txt

# 把整个项目根目录（即 sandbox/ 下的所有内容）复制到容器里的 /app
COPY . .

# 配置 supervisor：将 supervisord.conf 复制到 Supervisor 的配置目录，使 Supervisor 能够读取并管理沙盒环境中的多个服务进程
# ------------------------------------------------------------------
# 将 supervisord.conf 复制到 /etc/supervisor/conf.d/app.conf
# /etc/supervisor/conf.d/ 是 supervisor 读取配置的标准目录
# app.conf 是配置文件名
# Supervisor 会读取 /etc/supervisor/conf.d/ 下的 .conf 文件：
#   - 可以放置多个配置文件
#   - 每个文件定义不同的程序组或服务
#   - 文件名通常为 .conf 结尾
# 为什么需要这个配置？
#   - 进程管理：Supervisor 统一管理多个服务，包括 Xvfb、Chrome、socat、x11vnc、websockify 和 FastAPI 应用
#   - 环境变量：设置 UVI_ARGS 和 CHROME_ARGS 环境变量，方便在运行时传递参数
#   - 优先级：设置各个服务的优先级，确保服务按顺序启动
#   - 自动重启：服务异常退出时自动重启
#   - 日志管理：统一收集和管理日志
#   - 启动顺序：可控制服务启动顺序和依赖关系
# 执行时机？
#   - 构建镜像时：文件被复制到镜像中
#   - 容器启动时：Supervisor 会自动读取 /etc/supervisor/conf.d/ 下的 .conf 文件，并启动相应的服务
# ------------------------------------------------------------------
# 实际生效的配置来自 /app/supervisord.conf（由上面的 COPY . . 已复制到 /app/），
# 容器启动时 CMD 使用：supervisord -n -c /app/supervisord.conf，因此只读取该文件。
# 不再复制到 /etc/supervisor/conf.d/，避免与“只读 /app/supervisord.conf”的语义重复。
COPY supervisord.conf /etc/supervisor/conf.d/app.conf

# 暴露端口
EXPOSE 8080 9222 5900 5901

ENV UVI_ARGS=""
ENV CHROME_ARGS=""

# 使用 supervisor 启动所有服务
# 使用 supervisor 启动所有服务，-n 表示nodaemon（前台运行），-c 指定配置文件
# supervisor是主进程，所以要用 -n 确保其在前台运行
CMD ["supervisord", "-n", "-c", "/app/supervisord.conf"] 
