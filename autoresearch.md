# AutoResearch Downstream Imagination

你现在已经把 AutoResearch 的前两层做得很扎实了：

- 上游：发现 / 收集
- 中游：筛选 / 结构化解读 / prompt process

真正的下一步，就是进入下游：从大量论文和解读结果里提炼出真正有价值的 insight，并进一步推动 hypothesis、experiment design 和自动化实验执行。

## 一、Insight 层：从论文堆里抽出真正有价值的认识

下游最核心的三类 insight 是：

1. 历史上的研究脉络
2. 当前的 momentum
3. 接下来的方向、gap 和机会

### 1. 历史上的研究脉络

关注的问题包括：

- 一个领域是怎么一步一步演化过来的
- 哪些论文是奠基点，哪些是转折点，哪些只是局部优化
- 某条技术路线为什么会出现、为什么会替代上一代方法
- 某些今天看起来理所当然的做法，是怎么变成主流的

这一层的产物很像：

- dynamic survey
- 研究时间线
- 范式演化图

### 2. 哪里有 momentum

关注的问题包括：

- 哪些 topic 最近增长很快
- 哪些方法路线突然开始被大量 follow
- 哪些 benchmark / dataset / evaluation setup 变成了新的焦点
- 哪些看似边缘的小方向开始快速聚集信号

这一层的产物更像：

- trend radar
- momentum dashboard
- 过去 30 / 60 / 90 天的研究热区

### 3. 接下来的方向、gap 和机会

关注的问题包括：

- 哪些问题还没有被解决
- 哪些 claim 被反复说，但证据薄弱
- 哪些方向虽然火，但其实已经开始拥挤
- 哪些方向研究少，但可能回报很高
- 哪些不同领域之间存在可迁移的方法空白

这一层的产物更像：

- opportunity map
- research gap report
- next-bet memo

这一步的核心不是“多读几篇”，而是“知道什么值得做”。

## 二、Agenda 层：把 insight 变成研究议程

光有 insight 还不够，下一步是把它们变成 research agenda。

系统不只是说：

- 这里有趋势
- 那里有 gap

而是进一步说：

- 这些 gap 里面，哪个最值得优先做
- 哪个能最快验证
- 哪个需要大资源，哪个适合小步快跑
- 哪些问题可以并行推进，哪些必须先解决前置问题

因此 AutoResearch 可以生成一种产物：

- Research Agenda
  - 本周 / 本月最值得跟进的 3-5 个问题
  - 每个问题为什么重要
  - 它和当前 momentum 的关系
  - 它的验证路径是什么
  - 成本、风险、潜在上限分别是什么

这已经不是“论文阅读结果”，而是“研究规划结果”。

## 三、Hypothesis 层：从机会变成可验证命题

再往下一层，系统要学会自动提出 hypothesis。

不是只说：

- “video agent 最近升温”
- “tool use evaluation 还有 gap”

而是变成：

- “如果把 planning 和 retrieval 分离，某类 long-horizon task 的稳定性会提高”
- “当前多数方法 improvement 来自 benchmark-specific adaptation，而不是通用能力提升”
- “领域 A 的训练 / 推理技巧迁移到领域 B 可能有超预期效果”

也就是说，AutoResearch 未来不只是产出总结，而是产出：

- 可检验的研究命题
- 每个命题背后的证据链
- 与现有文献的支持 / 冲突关系

这会让系统开始从 information system 变成 scientific reasoning system。

## 四、Experiment Design 层：从 hypothesis 变成实验设计

在自动运行实验之前，还差一层非常关键的能力：自动设计实验。

AutoResearch 可以自动生成：

- 最小可验证实验
- 对照组和 baseline
- 使用哪个 dataset / benchmark
- 评估指标
- 失败标准
- 成功标准
- 可能的 confounders
- 复现实验的简化版本
- 快速 sanity check 实验

也就是说，先不是让系统直接“做科研”，而是先让它非常擅长做：

- experiment brief
- experiment plan
- experiment prioritization

这是连接 insight 和 execution 的桥。

## 五、Execution 层：自动跑实验

这里就接上实验执行器了。

可选执行器包括：

- Mind Lab 的 MinT
- ThinkingMachine Lab 的 Tinker

它们可以被看作 AutoResearch 的“执行器”或者“实验 worker”。

于是完整链路变成：

- 文献与中游解读 -> insight
- insight -> agenda
- agenda -> hypothesis
- hypothesis -> experiment design
- experiment design -> MinT / Tinker 执行
- execution result -> 回流到知识库
- 更新 insight 和下一轮 agenda

这就形成了研究闭环。

## 六、结果回灌：让系统越来越像一个真正的研究体

如果实验只是跑出去，没有回流，那系统仍然是不完整的。

因此还需要：

- 自动读取实验日志、指标、失败信息
- 自动判断 hypothesis 是被支持、削弱，还是部分成立
- 自动把结果挂回对应的主题、时间线、领域图谱
- 自动更新“当前 momentum”和“下一步建议”

这样系统就不只是读别人的工作，而是：

- 读别人的工作
- 组织自己的判断
- 跑自己的实验
- 再更新自己的研究地图

这时它就更像一个研究引擎了。

## 七、如果继续想象，AutoResearch 还能做什么

除了三大 insight 和实验执行之外，还可以继续扩展很多能力：

### 1. 研究地图生成器

- 自动构建某个 domain 的方法树、问题树、数据集树
- 不只是时间线，而是结构图谱

### 2. 争议点探测器

- 自动找出文献里说法不一致的点
- 哪些地方存在冲突证据
- 哪些结论其实不稳

### 3. 研究成熟度评估

- 一个方向是 exploratory、accelerating、crowded，还是 saturated
- 这对“值不值得投入”非常重要

### 4. 迁移机会发现器

- 某领域成熟的方法，在哪个邻近领域还没有被好好用过
- 这类 cross-domain transfer 往往最有机会

### 5. 反常识机会发现

- 不是追热，而是找被低估的方向
- 哪些方向论文少，但 signal quality 高
- 哪些方向热度高，但真实进展慢

### 6. 自动生成 lab notebook / research memo

- 每周自动生成一次研究团队 briefing
- 每个 domain 一份 live memo
- 每个 hypothesis 一份证据摘要

### 7. 自动构造“下一步阅读计划”

- 为了验证某个 hypothesis，还缺哪几篇关键论文没读
- 系统自动把阅读和实验衔接起来

### 8. 自动形成组合研究策略

- 不只是一个方向，而是一组组合：
  - 一个高风险高收益
  - 一个低成本快验证
  - 一个跟进主流趋势
  - 一个逆向冷门方向

这个对真正推进研究很有价值。

## 八、如果把 AutoResearch 看成一个未来产品，它可能有几种形态

### 模式 A：Research Intelligence System

重点是 insight，为人提供研究情报和决策支持。

### 模式 B：Research Planner

重点是 agenda、priority、hypothesis、experiment design，为团队做研究规划。

### 模式 C：Autonomous Research Operator

重点是自动调用 MinT / Tinker 跑实验，为研究推进做闭环执行。

### 模式 D：Research OS

把 reading、thinking、planning、experiment、memory 都整合在一起。

这是最远的想象，但也最值得。

## 九、如果围绕“什么是有价值的事情”，AutoResearch 最终要回答什么

它最终要回答的，不该只是“什么论文重要”，而是：

- 这个领域过去是怎么走到今天的
- 现在真正有势能的东西是什么
- 哪些只是噪音，哪些是信号
- 哪些问题值得投入
- 哪些问题可以被快速验证
- 哪些实验最值得先跑
- 哪些结果会改变我们对领域的理解

这比“再多读 100 篇论文”更高级。

## 十、一个自然的三阶段路线图

如果现在只是继续想象，而不落到执行，可以先把未来路线分成三段：

### 第一段：Insight Engine

- 历史脉络
- momentum
- gap / opportunity
- domain map

### 第二段：Research Planner

- hypothesis generation
- agenda construction
- experiment design
- reading-to-action pipeline

### 第三段：Autonomous Executor

- 调用 MinT / Tinker
- 自动跑实验
- 结果回灌
- 研究闭环

这三段非常自然，而且每一段都能独立产出价值。

## 十一、结合 karpathy/autoresearch 之后的更新理解

在阅读 `karpathy/autoresearch` 之后，一个非常重要的修正是：

**Execution 不是“让系统自己随便做实验”，而是把系统放进一个设计得非常好的、强约束的实验竞技场。**

这和之前更偏抽象的 AutoResearch 想象相比，多了几个非常具体、非常关键的原则。

### 1. 真正应该被程序化的，不只是实验代码，而是“研究组织程序”

`karpathy/autoresearch` 的核心并不只是让 agent 改 `train.py`，而是：

- 人类主要写的是 `program.md`
- agent 根据 `program.md` 进入一个持续实验循环
- 真正被不断迭代的，不只是模型代码，也是研究组织方式本身

这意味着 AutoResearch 未来应该有两层“程序”：

- **object-level program**
  - 具体实验对象怎么改
  - 例如改模型、调参数、换数据处理方式、改 workflow
- **meta-level program**
  - 研究代理如何提出想法、如何记录、如何保留、如何回滚、如何持续推进

也就是说，AutoResearch 不只是要输出 hypothesis 和 experiment design，
它还要有一种能够驱动 agent swarm 或执行器持续工作的“research org code”。

### 2. Execution 必须被限制在非常清晰的 action surface 内

`karpathy/autoresearch` 最聪明的一点，是把 action surface 收得极窄：

- 只允许改 `train.py`
- 不允许改 `prepare.py`
- 不允许改 evaluation harness
- 不允许加新依赖
- 目标只有一个：让 `val_bpb` 更低

这说明对于 AutoResearch 来说，execution 想要可靠，必须是 **arena-based execution**，而不是开放世界随意行动。

也就是说，未来 AutoResearch 不该直接说：

- “去做一个研究项目吧”

而应该说：

- 在这个任务定义里行动
- 只能动这些文件 / 模块 / 参数
- 指标是什么
- 时间预算是什么
- 可接受的资源边界是什么
- 哪些东西是只读的 ground truth

所以我们未来要设计的 execution，不是一套通用大脑，而是一系列 **research arenas**：

- literature arena
- benchmark arena
- reproduction arena
- ablation arena
- agent workflow arena
- product-prototype arena

每个 arena 都应该有：

- 可编辑面
- 固定评估器
- 固定预算
- 明确 keep / discard 规则

### 3. Execution 的基本单位应该是“短回路实验”

`karpathy/autoresearch` 另一个关键点是：

- 每轮实验时间固定
- 很短
- 可比较
- 可批量
- 可回滚

这给我们一个很重要的启发：

**下游研究自动化不应该默认从“大而完整的研究项目”开始，而应该从短回路、低成本、可比较的微实验开始。**

所以 AutoResearch 的 execution 设计，应该优先支持：

- 5 分钟到 30 分钟级别的 quick experiment
- 可直接比较的标准化输出
- 失败成本很低的 trial loop
- 高频迭代，而不是低频豪赌

换句话说，系统应当优先成为：

- hypothesis grinder
- rapid validation engine

而不是一上来就幻想 full autonomous scientist。

### 4. “keep / discard / crash” 这种结果协议极其重要

`karpathy/autoresearch` 把实验结果压缩成非常简单的状态：

- keep
- discard
- crash

这是 execution 层非常重要的思想。

因为自动研究系统如果没有一个极简而稳定的决策协议，就会越来越混乱。

所以未来 AutoResearch 的实验结果，也应该有统一协议，例如：

- **keep**
  - 明显支持 hypothesis
  - 或者带来明确性能 / 质量 / 简化收益
- **discard**
  - 没有改善
  - 改善不足以覆盖复杂度成本
- **crash**
  - 运行失败
  - 设计本身不可执行
- **ambiguous**
  - 结果不清楚，需要更大实验
- **promote**
  - 值得从 quick experiment 升级到完整项目

这样一来，系统不是单纯地产生日志，而是在持续做研究资产管理。

### 5. Execution 不是“完成任务”，而是“持续推进分支”

`karpathy/autoresearch` 的 loop 非常像 branch advancement：

- 如果实验好，就向前推进分支
- 如果实验差，就 reset 回去
- 研究过程本身是一种 search

这意味着我们对 AutoResearch 的 execution 想象，也应该从“任务完成器”改成“分支搜索器”。

未来可以把一个研究主题看成一棵搜索树：

- 根节点：某个机会 / gap
- 中间节点：某个 hypothesis
- 子节点：某种实验实现
- 叶子节点：结果与判断

然后 execution 系统做的是：

- 选择下一个值得扩展的节点
- 运行一个 bounded experiment
- 决定是否保留这个分支
- 继续向有前景的方向推进

也就是说，execution 更像：

- guided search
- branch-and-bound research
- evolutionary experimentation

而不是普通 workflow automation。

### 6. 人类未来写的，可能主要不是 prompt，而是 arena spec / org spec

在 `karpathy/autoresearch` 里，最重要的“代码”之一其实是 `program.md`。

对应到你的 AutoResearch，我觉得未来人类可能主要写三类东西：

- **insight prompt / synthesis prompt**
  - 用于生成历史脉络、momentum、gap
- **arena spec**
  - 定义某类实验的边界、预算、指标、可编辑对象
- **org spec**
  - 定义 agent 怎么循环、怎么记录、怎么升级、怎么回滚

这比单纯管理 Prompt 更高一层。

所以你当前的 Prompt manager，未来可能会扩展成：

- Prompt Manager
- Arena Manager
- Research Org Manager

### 7. Execution 应该分层，不同层调用不同执行器

之前我们把 MinT / Tinker 当作实验执行器，现在结合 `karpathy/autoresearch`，我觉得更清楚了：

并不是所有 execution 都该直接调用 MinT / Tinker。

更合理的是做一个分层 execution stack：

- **Layer 1: Insight execution**
  - 聚类、时间线、趋势分析、gap detection
  - 主要是文本 / 知识处理
- **Layer 2: Planning execution**
  - hypothesis generation
  - experiment plan generation
  - priority ranking
- **Layer 3: Sandboxed experiment execution**
  - 小规模 quick experiment
  - bounded code edits
  - bounded evaluation
- **Layer 4: External lab execution**
  - 通过 MinT / Tinker 跑更完整的实验
  - 用于更大资源、更长时长、更复杂环境

也就是说：

- AutoResearch 自己负责形成研究判断和 experiment spec
- MinT / Tinker 更像是下游 compute lab / execution substrate
- 中间还应该有一层 execution compiler，把 hypothesis 编译成可执行 arena

### 8. 以后最值得做的 execution，不是“万能执行”，而是“可验证执行”

这是我读完 `karpathy/autoresearch` 后最强的感受。

真正有价值的 execution 不是：

- 系统看起来很 autonomous

而是：

- 它做的每一步都在可验证边界内
- 它产出的结果是可比较、可保留、可回滚的
- 它能持续推进，而不是偶尔做一个花哨 demo

所以 execution 的第一原则应该是：

- bounded
- reproducible
- comparable
- revertible
- accumulative

### 9. 这会反过来改变上游和中游的设计

如果下游 execution 想按 arena 来跑，那么中游 paper analysis 也不能只是“写得很好的摘要”，而应该为 execution 准备结构化变量。

例如未来对每篇论文，系统最好还能提取：

- 它属于哪个 domain / subdomain
- 它解决的核心 problem
- 它的 novelty 类型
- 它依赖哪些 benchmark / dataset / metric
- 它的方法是否容易复现
- 它有哪些可做 quick ablation 的点
- 它有哪些 unresolved claims
- 它更适合进入哪种 arena

这样一来，PaperReader + prompt processing 的结果，就不仅能用于 insight，也能直接编译成后续 experiment candidates。

### 10. 更新后的 AutoResearch 总体图景

结合 `karpathy/autoresearch` 之后，我觉得 AutoResearch 更准确的未来图景是：

- **PaperReader / Source layer**
  - 收集论文
  - 解析论文
  - 形成结构化研究记忆

- **Insight engine**
  - 历史脉络
  - momentum
  - gap / opportunity
  - domain evolution

- **Research planner**
  - research agenda
  - hypothesis generation
  - experiment candidate generation
  - prioritization

- **Execution compiler**
  - 把 hypothesis 翻译成 arena spec
  - 决定这个问题该在哪种 arena 里验证
  - 决定是 quick local loop 还是外部 lab execution

- **Execution arenas**
  - bounded local loop
  - benchmarked sandbox
  - reproduction loop
  - workflow / agent loop
  - external lab execution (MinT / Tinker)

- **Research memory update**
  - keep / discard / crash / promote
  - 更新时间线、趋势图、机会图、研究地图

## 十二、对 execution 的更新结论

所以，经过 `karpathy/autoresearch` 的启发，execution 这部分我会明确改成下面这句话：

**Execution 不是“自动去做实验”，而是“把研究问题编译到受约束、可比较、可回滚的实验竞技场里，持续推进有效分支”。**

这比原来更具体，也更现实。

换句话说，未来 AutoResearch 最值得构建的 execution，不是一个模糊的 autonomous scientist，而是一个：

- insight-driven
- hypothesis-producing
- arena-compiled
- branch-advancing
- result-updating

的研究执行系统。
