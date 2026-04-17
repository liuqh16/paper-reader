# paper-reader-insights

`paper-reader-insights` 是给 `paper-reader` 增加的 insights 层：

- 不再停留在单篇论文解读
- 而是把整堆论文和 prompt 结果重新组织成三类产物：
  - `dynamic survey / 研究时间线`
  - `trend radar / momentum dashboard`
  - `opportunity map / research gap report`

当前实现基于已有的本地索引和 prompt markdown，做一层可解释、可追踪的信号抽取：

- 读取 `docs/papers/.paper_reader_index.json`
- 读取 `docs/papers/.paper_reader_done_index.json`
- 读取 `docs/papers/.paper-reader-ai/` 下已有的 prompt 结果
- 为每篇论文抽取主题、方法路线、benchmark / dataset / evaluation signal、gap signal
- 生成多份 markdown 和一份结构化 json

## 目录结构

```text
paper-reader-insights/
├── README.md
├── output/
├── paper_reader_insights/
│   ├── __init__.py
│   ├── __main__.py
│   ├── analysis.py
│   ├── cli.py
│   ├── loader.py
│   ├── models.py
│   └── taxonomy.py
└── tests/
```

## 运行

从仓库根目录执行：

```bash
PYTHONPATH=paper-reader-insights python3 -m paper_reader_insights \
  --library-root docs/papers \
  --output-dir paper-reader-insights/output
```

默认会生成：

- `paper-reader-insights/output/insights-overview.md`
- `paper-reader-insights/output/dynamic-survey.md`
- `paper-reader-insights/output/momentum-dashboard.md`
- `paper-reader-insights/output/opportunity-map.md`
- `paper-reader-insights/output/insights.json`

## 当前设计边界

这版先做的是 **grounded insight extraction**，重点是：

- 先把已有论文堆压缩成可读的 insight artifact
- 输出尽量基于本地 prompt 结果里已经存在的证据
- 用规则/信号抽取保证可控、可验证

它还不是最终的 AutoResearch insight engine。后续自然可继续往下接：

- 更细的 topic clustering
- LLM-assisted synthesis
- agenda / hypothesis generation
- arena compiler / execution bridge
