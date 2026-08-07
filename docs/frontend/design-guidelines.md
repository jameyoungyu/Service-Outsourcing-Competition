# IndusOpt 工模智优 - 工业软件视觉与交互设计规范 (Design Guidelines)

**文档版本**：`v0.1.0`  
**适用阶段**：阶段 0（需求与设计冻结）  
**责任角色**：Gemini (前端与可视化架构师)  

---

## 1. 设计哲学 (Design Philosophy)

IndusOpt 是一款面向流程工业控制与系统辨识工程的技术软件，视觉与交互设计遵循以下三大原则：

1. **专业、克制与高信息密度 (Professional & Information-Dense)**：
   * 采用干净利落的工业中性色调，避免娱乐化大面积绚丽渐变或无意义的发光拟态。
   * 优先显示关键参数、量纲单位（如 `s`, `dB`, `%`）、数据版本号与算法判定证据。
2. **算法显性化与可置信度 (Verifiable & Explainable)**：
   * 所有算法操作必须提供“处理前 vs 处理后”对比或“算法参数 + 判定标准”卡片，拒绝盲盒式交互。
   * 数据修改（截取、剔除变量、重采样）必须显示具体受影响的行数与比例。
3. **清晰的实时响应与状态感 (Explicit Real-Time Feedback)**：
   * 工业长耗时算法（如 Optuna 寻优、大文件诊断）必须展示真实步骤、当前 Trial 序号与已用耗时，严禁使用虚假固定百分比进度条。

---

## 2. 颜色系统与设计 Token (Color Palette & Tokens)

设计风格主打**高端工业浅色调模式 (Light Industrial Workspace)**，兼顾高对比度与长久阅读舒适度。

### 2.1 色彩定义

```css
:root {
  /* 品牌主色 (Industrial Navy Blue) - 沉稳专业 */
  --color-primary: #1E6091;
  --color-primary-hover: #184E77;
  --color-primary-light: #E8F1F5;

  /* 辅助视觉色 (Accent Slate Green) - 代表验证通过与最佳指标 */
  --color-success: #2A9D8F;
  --color-success-bg: #E8F6F4;

  /* 警告色 (Amber) - 代表共线性高、缺失率高、待人工确认 */
  --color-warning: #E9C46A;
  --color-warning-dark: #D4A373;
  --color-warning-bg: #FFF9E6;

  /* 危险/异常色 (Industrial Red/Coral) - 代表点剔除、错误、矩阵奇异 */
  --color-danger: #E76F51;
  --color-danger-bg: #FDF0ED;

  /* 中性背景色与表面色 (Backgrounds & Cards) */
  --bg-app: #F4F6F8;             /* 主界面窗口背景 */
  --bg-surface: #FFFFFF;         /* 卡片与面板背景 */
  --bg-sidebar: #1A212D;         /* 左侧导航栏 (深色暗标) */
  --bg-subtle: #F8F9FA;          /* 表格表头与次要区域 */

  /* 文字与边框色彩 (Text & Borders) */
  --text-primary: #1A1D20;       /* 主标题与核心数值 */
  --text-secondary: #5A626A;     /* 次要标签与正文 */
  --text-muted: #8D96A0;         /* 禁用与弱提示 */
  --border-light: #E2E7EC;       /* 卡片分割线 */
  --border-active: #1E6091;      /* 聚焦线 */

  /* 辅助可视化调色板 (Chart Series Colors) */
  --chart-series-y: #1E6091;     /* 实测值 y(t) - 深蓝 */
  --chart-series-yhat: #E76F51;  /* 辨识预测值 y_hat(t) - 珊瑚红 */
  --chart-series-u1: #2A9D8F;    /* 输入变量 u1 - 墨绿 */
  --chart-series-u2: #F4A261;    /* 输入变量 u2 - 橙黄 */
  --chart-series-u3: #9B5DE5;    /* 输入变量 u3 - 紫罗兰 */
  --chart-bg-highlight: rgba(30, 96, 145, 0.12); /* 动态区间高亮背景 */
}
```

---

## 3. 字体与高信息密度排版 (Typography)

* **字体族 (Font Family)**：
  ```css
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
  font-mono: "JetBrains Mono", "Fira Code", Consolas, Monaco, monospace;
  ```
* **字号与行高**：
  * **页标题 (Page Header)**: 20px / 28px, Bold (`--text-primary`)
  * **卡片标题 (Section Header)**: 15px / 22px, Semi-Bold
  * **表格与正文 (Body Text)**: 13px / 20px, Regular
  * **次要标签与元数据 (Meta / Unit)**: 12px / 16px, Regular (`--text-secondary`)
  * **代码与公式变量 (Mono / Math)**: 13px, Monospace (所有变量名 $u_1, y, \tau$、数据版本号 `V1_Cleaned` 必须统一以等宽或斜体渲染)

---

## 4. 图表与可视化设计规范 (ECharts Guidelines)

1. **坐标轴与单位**：
   * 所有时序图 X 轴必须标明单位（如 `Time (s)` 或 `Timestamp`）。
   * Y 轴必须具备物理量纲标签或标准化说明，保留最大 4 位有效小数。
2. **交互与缩放**：
   * 所有时序折线图默认开启 ECharts `dataZoom` 工具（支持鼠标滚轮与底部滑条联动）。
   * 鼠标 Hover 弹出 Tooltip 时，必须按列对齐显示当前时间点所有变量的具体数值与单位。
3. **阈值与参考线**：
   * 诊断图中需绘制明确的辅助线（例如：VIF 图画出 `VIF = 10` 的红色虚线警戒线；SNR 图画出 `SNR = 15dB` 阈值线）。
4. **性能下采样 (Downsampling)**：
   * 若数据行数 $N > 10,000$，前端 ECharts 自动启用 `sampling: 'lttb'` (Largest-Triangle-Three-Buckets) 算法，确保渲染卡顿率小于 16ms/帧，同时不失真真实动态峰值。

---

## 5. 微交互与微动画规范 (Micro-Interactions)

1. **过渡时间**：
   * 页面与选项卡切换：150ms - 200ms ease-in-out 淡入淡出。
   * 折叠抽屉与 Agent 对话面板滑出：250ms cubic-bezier(0.4, 0, 0.2, 1)。
2. **加载组件 (Loaders)**：
   * 数据分析卡片加载时，优先使用**骨架屏 (Skeleton Screens)** 呈现场景轮廓，避免无脑全局 Spinner 遮挡。
   * 长任务（如 Optuna 寻优）顶部状态栏展示带真实步数的模态进度条，显示 `[Trial 14/50 - 最优 FIT: 85.2% - 已用 12.4s]`。
3. **按钮与反馈**：
   * 关键不可逆算法按钮（如 `[应用清洗并覆盖当前视图]`）点击后进入 Loading 状态，禁用重复提交。
   * 复制数据版本号或 API 请求 ID 时弹出 Toast：`[已复制版本号 V2_Cleaned 到剪贴板]`（停留 2 秒）。
