# paper-reader

一个面向本地论文库的轻量阅读器，支持 PDF / Word 文档管理、浏览器内阅读、Prompt 批量分析、离线阅读包导出、外部论文来源归档，以及后台任务处理。

## 主要功能

- 本地论文库：自动扫描 `PDF / .doc / .docx`
- 左侧紧凑论文列表，右侧大阅读区
- PDF 在线阅读、`.docx` 文本预览、`.doc` 原文件打开
- Prompt 管理：可配置多个 Prompt，结果落盘为本地 Markdown
- 后台任务队列：自动处理新论文，也可批量补跑历史论文
- 离线阅读包：导出原论文 + Markdown + 本地 HTML 阅读器
- 个人已读流程：每个用户都可以把论文标记为“已读”，只影响自己的列表视图
- Sources 页面：浏览外部抓取的论文归档，支持按天打包下载或一键导入主阅读器
- 登录保护：进入阅读器前需要用户名和密码

## 默认配置

### 服务地址

- Host: `0.0.0.0`
- Port: `8000`

### 默认数据目录

所有论文和运行数据默认都保存在：

- `/vePFS-Mindverse/share/paper-reader/`

其中主要子目录为：

- `/vePFS-Mindverse/share/paper-reader/library/`：主论文库、Prompt 结果、设置和索引
- `/vePFS-Mindverse/share/paper-reader/sources/huggingface_daily/`：Sources 页面使用的外部抓取归档

放进 `library/` 的 PDF / Word 文件会被自动扫描识别。这样把运行目录放到共享盘后，团队成员就能围绕同一份论文库、同一套 Prompt 结果和同一批 Sources 数据协作。

### 默认登录信息

- 用户名：`admin`
- 密码：`paperpaperreaderreader12678`

安全限制：

- 连续输错密码 3 次后，会锁定 5 分钟

### 使用 `.env` 覆盖登录信息

如果项目根目录存在 `.env`，系统会优先读取其中的登录配置；一旦配置了 `.env`，默认用户名和密码将不再生效。

可配置项：

- `PAPER_READER_LOGIN_USERNAME`
- `PAPER_READER_LOGIN_PASSWORD`

示例：

```dotenv
PAPER_READER_LOGIN_USERNAME=admin
PAPER_READER_LOGIN_PASSWORD=replace-with-your-own-password
```

说明：

- `.env` 已被 `.gitignore` 忽略，不会默认提交到 Git
- 建议在部署后立即用你自己的密码覆盖默认密码
- 不要把你自己的真实密码写进 README 或提交到 GitHub

## 环境准备

建议使用 Python 3.11+。

### 1) 创建虚拟环境

```bash
python3 -m venv .venv
```

### 2) 安装依赖

```bash
.venv/bin/pip install -r requirements.txt
```

## 如何启动

### 方式一：直接启动

```bash
.venv/bin/python run.py
```

如果你希望使用自定义登录信息，建议先在项目根目录创建 `.env`：

```bash
cat > .env <<'EOF'
PAPER_READER_LOGIN_USERNAME=admin
PAPER_READER_LOGIN_PASSWORD=replace-with-your-own-password
EOF
```

启动后访问：

- 本机：`http://127.0.0.1:8000`
- 局域网其他机器：`http://<你的机器IP>:8000`

### 方式二：在 tmux 中启动

如果你希望服务在后台持续运行，推荐用 tmux：

```bash
tmux new-session -d -s paper-reader 'cd /path/to/paper-reader && .venv/bin/python run.py'
```

查看状态：

```bash
tmux attach -t paper-reader
```

停止服务：

```bash
tmux kill-session -t paper-reader
```

## 项目结构

```text
paper-reader/
├── run.py
├── paper-reader-source/        # 外部来源抓取子项目
├── requirements.txt
├── src/paper_reader/
│   ├── app.py
│   ├── task_queue.py
│   ├── ai_summary.py
│   ├── prompt_manager.py
│   ├── offline_package.py
│   ├── source_archive.py
│   ├── static/
│   └── templates/
└── tests/

/vePFS-Mindverse/share/paper-reader/
├── library/                    # 主论文库（默认）
└── sources/huggingface_daily/  # 外部来源归档（默认）
```

## 论文库说明

支持格式：

- `.pdf`
- `.doc`
- `.docx`

说明：

- `.pdf`：浏览器内联阅读
- `.docx`：会提取文本并做浏览器预览
- `.doc`：通常不直接内联渲染，但仍可索引并打开原文件

## Prompt 批量补跑

“历史论文批量补跑”面板默认只显示 **你还没标记为已读的论文**。

如果你希望把已完成论文也纳入批量列表，可以在该面板中勾选：

- `把我已读的论文也加入这次批量生成`

这样就会把你自己已经标记为已读、但又想重新处理的论文一起显示出来。

## Sources 页面

系统现在支持一个独立的 `Sources` 页面，用来浏览外部归档的论文来源数据。

当前已接入：

- Hugging Face Daily Papers

在主阅读器底部工具区可以进入 `Sources` 页面。这个页面支持：

- 按年 / 月 / 日浏览抓取归档
- 查看每天保存下来的论文列表
- 打包下载某一天选中的 PDF
- 把选中的论文直接导入主阅读器

导入后的目标目录默认是：

- `Sources/HuggingFace/YYYY/MM/DD/`

如果阅读器里启用了自动 Prompt，那么从 `Sources` 导入的论文也会自动进入后台任务队列。

### Sources 数据目录

默认会从下面这个目录读取外部归档数据：

- `/vePFS-Mindverse/share/paper-reader/sources/huggingface_daily/`

这个目录位于仓库外，因此不会提交到 GitHub。

### Hugging Face 抓取子项目

仓库里包含一个单独的子项目：

- `paper-reader-source/`

它负责：

- 抓取 Hugging Face Daily Papers
- 按天保存 manifest
- 下载对应 PDF 到本地归档目录

直接运行一次采集：

```bash
PYTHONPATH=paper-reader-source python3 -m paper_reader_source.service \
  --data-dir /vePFS-Mindverse/share/paper-reader/sources/huggingface_daily \
  --run-on-start --once
```

长期运行定时服务：

```bash
PYTHONPATH=paper-reader-source python3 -m paper_reader_source.service \
  --data-dir /vePFS-Mindverse/share/paper-reader/sources/huggingface_daily
```

或者直接用仓库里自带的脚本：

```bash
paper-reader-source/scripts/run_huggingface_daily_service.sh
```

当前调度规则：

- 时区：`Asia/Shanghai`
- 每天执行时间：`18:30`
- 默认保留 `upvotes >= 5` 的论文

## 手动扫描 Paper 文件夹

如果你经常直接在文件系统里操作论文目录，比如：

- 手动复制 PDF 进去
- 在系统文件管理器里重命名文件
- 删除某些论文

可以在页面的“文件管理”区域点击：

- `快速扫描 Paper 文件夹`

这个功能的设计目标是：

- 只做文件扫描和目录更新
- 不自动运行任何 Prompt
- 不调用任何 AI 模型
- 不做重型、耗时的解析

也就是说，它更适合在你手动改动了论文目录之后，快速让网页里的论文列表同步更新。

## 离线阅读包

可以导出一个 zip 包，里面包含：

- 原始 PDF / Word 文件
- 已生成的 Markdown 结果
- 一个可离线打开的 `index.html`

解压后，直接双击 `index.html` 即可离线阅读。

## 测试

运行测试：

```bash
.venv/bin/python -m unittest tests.test_app
```

## 开发备注

- 默认运行数据现在写到 `/vePFS-Mindverse/share/paper-reader/`，不会跟随仓库提交
- 日志目录 `logs/` 默认不会提交到 Git
- 运行过程中生成的本地状态文件也已加入 `.gitignore`
