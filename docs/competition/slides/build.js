const pptxgen = require("pptxgenjs");

// Industrial instrumentation palette: deep control-room navy, teal, signal amber.
const INK = "0F2436";
const NAVY = "17384F";
const TEAL = "1C7293";
const TEAL_LT = "3E93B4";
const AMBER = "E39A2B";
const RUST = "C0553B";
const PAPER = "F4F6F8";
const CARD = "FFFFFF";
const TXT = "1A2733";
const MUTE = "5E7183";
const INV_MUTE = "A9BECD";

const HEAD = "Microsoft YaHei";
const BODY = "Microsoft YaHei";

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.3 x 7.5
pres.author = "IndusOpt";
pres.title = "IndusOpt 工模智优 — A14 参赛答辩";

const W = 13.3;
const H = 7.5;
const M = 0.7;

function darkSlide() {
  const s = pres.addSlide();
  s.background = { color: INK };
  return s;
}
function lightSlide() {
  const s = pres.addSlide();
  s.background = { color: PAPER };
  return s;
}

// Section number in a filled circle — the repeated motif across every content slide.
function badge(s, n, color) {
  s.addShape(pres.ShapeType.ellipse, {
    x: M,
    y: 0.52,
    w: 0.52,
    h: 0.52,
    fill: { color: color || TEAL },
  });
  s.addText(String(n), {
    x: M,
    y: 0.52,
    w: 0.52,
    h: 0.52,
    align: "center",
    valign: "middle",
    fontFace: HEAD,
    fontSize: 18,
    bold: true,
    color: "FFFFFF",
    margin: 0,
  });
}

function title(s, text, sub) {
  s.addText(text, {
    x: M + 0.75,
    y: 0.44,
    w: W - M * 2 - 0.75,
    h: 0.7,
    fontFace: HEAD,
    fontSize: 30,
    bold: true,
    color: TXT,
    margin: 0,
    valign: "middle",
  });
  if (sub) {
    s.addText(sub, {
      x: M + 0.75,
      y: 1.14,
      w: W - M * 2 - 0.75,
      h: 0.42,
      fontFace: BODY,
      fontSize: 14,
      color: MUTE,
      margin: 0,
      valign: "middle",
    });
  }
}

function card(s, opt) {
  s.addShape(pres.ShapeType.roundRect, {
    x: opt.x,
    y: opt.y,
    w: opt.w,
    h: opt.h,
    rectRadius: 0.08,
    fill: { color: opt.fill || CARD },
    line: { color: opt.line || "E2E8ED", width: 1 },
    shadow: { type: "outer", angle: 90, offset: 2, blur: 8, color: "9FB0BE", opacity: 0.25 },
  });
}

/* ---------------------------------------------------------------- 1 title */
{
  const s = darkSlide();
  s.addShape(pres.ShapeType.ellipse, {
    x: 9.4,
    y: -1.9,
    w: 6.2,
    h: 6.2,
    fill: { color: TEAL, transparency: 78 },
  });
  s.addShape(pres.ShapeType.ellipse, {
    x: 10.9,
    y: 3.4,
    w: 3.6,
    h: 3.6,
    fill: { color: AMBER, transparency: 84 },
  });

  s.addText("2026「数字马力杯」浙江省大学生服务外包创新应用大赛 · 赛题 A14（和利时）", {
    x: M,
    y: 1.25,
    w: 9.6,
    h: 0.36,
    fontFace: BODY,
    fontSize: 13,
    color: INV_MUTE,
    margin: 0,
  });
  s.addText("IndusOpt 工模智优", {
    x: M,
    y: 1.75,
    w: 10.2,
    h: 1.0,
    fontFace: HEAD,
    fontSize: 48,
    bold: true,
    color: "FFFFFF",
    margin: 0,
  });
  s.addText("基于 Agent 的流程工业建模数据智能优选与闭环寻优系统", {
    x: M,
    y: 2.78,
    w: 10.2,
    h: 0.6,
    fontFace: HEAD,
    fontSize: 21,
    color: TEAL_LT,
    margin: 0,
  });

  s.addText("不问「这段数据质量多好」，问「这段数据能给模型带来多少新信息」。", {
    x: M,
    y: 3.95,
    w: 9.4,
    h: 0.5,
    fontFace: BODY,
    fontSize: 17,
    italic: true,
    color: AMBER,
    margin: 0,
  });

  const stats = [
    ["14.3%", "的数据达到全量精度"],
    ["28.5×", "指标区分度差距"],
    ["233", "项后端自动化测试"],
  ];
  stats.forEach(([big, small], i) => {
    const x = M + i * 3.15;
    s.addText(big, {
      x,
      y: 5.05,
      w: 2.9,
      h: 0.7,
      fontFace: HEAD,
      fontSize: 34,
      bold: true,
      color: "FFFFFF",
      margin: 0,
    });
    s.addText(small, {
      x,
      y: 5.75,
      w: 2.9,
      h: 0.4,
      fontFace: BODY,
      fontSize: 12,
      color: INV_MUTE,
      margin: 0,
    });
  });

  s.addText("V1.0  ·  全部数字均为实测，含对本方案不利的结果", {
    x: M,
    y: 6.55,
    w: 10,
    h: 0.35,
    fontFace: BODY,
    fontSize: 11,
    color: "6E8798",
    margin: 0,
  });
  s.addNotes(
    "开场：这套系统解决的是赛题原文点出的痛点——有效辨识样本被海量稳态数据淹没。" +
      "我们想强调的一点是：全部结论都是实测的，并且我们把对自己不利的结果也一起提交。"
  );
}

/* ------------------------------------------------------------- 2 problem */
{
  const s = lightSlide();
  badge(s, "01");
  title(s, "问题：有效样本被稳态淹没", "赛题原文：真正富含动态价值的有效辨识样本被海量稳态数据淹没");

  card(s, { x: M, y: 1.85, w: 5.9, h: 4.55 });
  s.addText("装置绝大多数时间运行在稳态", {
    x: M + 0.4,
    y: 2.15,
    w: 5.1,
    h: 0.45,
    fontFace: HEAD,
    fontSize: 18,
    bold: true,
    color: TXT,
    margin: 0,
  });
  s.addText(
    [
      { text: "输入不动，输出也不动。", options: { bullet: true, breakLine: true } },
      { text: "这类样本增加行数，却不增加信息。", options: { bullet: true, breakLine: true } },
      {
        text: "真正能确定模型参数的，是短暂的动态片段：一次阀位调整、一次负荷升降、一次工况切换。",
        options: { bullet: true },
      },
    ],
    {
      x: M + 0.4,
      y: 2.7,
      w: 5.1,
      h: 1.7,
      fontFace: BODY,
      fontSize: 14,
      color: TXT,
      margin: 0,
      paraSpaceAfter: 10,
      lineSpacingMultiple: 1.15,
    }
  );

  s.addShape(pres.ShapeType.roundRect, {
    x: M + 0.4,
    y: 4.55,
    w: 5.1,
    h: 1.6,
    rectRadius: 0.06,
    fill: { color: "EAF1F5" },
    line: { color: "D3E0E8", width: 1 },
  });
  s.addText("而且激励往往不均匀", {
    x: M + 0.62,
    y: 4.72,
    w: 4.7,
    h: 0.36,
    fontFace: HEAD,
    fontSize: 15,
    bold: true,
    color: NAVY,
    margin: 0,
  });
  s.addText(
    "操作员在不同时期调整不同的阀，显眼的大动作集中在少数变量上。这是真实历史数据的常态，不是特例。",
    {
      x: M + 0.62,
      y: 5.12,
      w: 4.7,
      h: 0.95,
      fontFace: BODY,
      fontSize: 13,
      color: MUTE,
      margin: 0,
      lineSpacingMultiple: 1.15,
    }
  );

  const rights = [
    ["人工圈选", "靠工程师翻趋势图。慢、不可复现、结果因人而异。"],
    ["加权质量评分", "对滑动窗口算能量、信噪比、响应关联度，加权求和取前 K 段。"],
  ];
  rights.forEach(([h, d], i) => {
    const y = 1.85 + i * 1.35;
    card(s, { x: 7.0, y, w: 5.6, h: 1.15 });
    s.addShape(pres.ShapeType.ellipse, {
      x: 7.25,
      y: y + 0.35,
      w: 0.42,
      h: 0.42,
      fill: { color: MUTE },
    });
    s.addText(String(i + 1), {
      x: 7.25,
      y: y + 0.35,
      w: 0.42,
      h: 0.42,
      align: "center",
      valign: "middle",
      fontFace: HEAD,
      fontSize: 14,
      bold: true,
      color: "FFFFFF",
      margin: 0,
    });
    s.addText(h, {
      x: 7.85,
      y: y + 0.18,
      w: 4.5,
      h: 0.34,
      fontFace: HEAD,
      fontSize: 15,
      bold: true,
      color: TXT,
      margin: 0,
    });
    s.addText(d, {
      x: 7.85,
      y: y + 0.52,
      w: 4.5,
      h: 0.5,
      fontFace: BODY,
      fontSize: 12,
      color: MUTE,
      margin: 0,
    });
  });

  card(s, { x: 7.0, y: 4.55, w: 5.6, h: 1.85, fill: NAVY, line: NAVY });
  s.addText("多数队伍会走第二条路", {
    x: 7.3,
    y: 4.78,
    w: 5.0,
    h: 0.38,
    fontFace: HEAD,
    fontSize: 16,
    bold: true,
    color: AMBER,
    margin: 0,
  });
  s.addText("赛题任务清单本身就写着这套特征——按字面实现，各队作品会高度同质化。", {
    x: 7.3,
    y: 5.2,
    w: 5.0,
    h: 1.0,
    fontFace: BODY,
    fontSize: 13.5,
    color: "DCE8F0",
    margin: 0,
    lineSpacingMultiple: 1.2,
  });
  s.addNotes("这一页交代问题和现有做法。重点是最后一块：赛题清单本身就是实现说明书，按字面做会同质化。");
}

/* ---------------------------------------------------- 3 what we measured */
{
  const s = lightSlide();
  badge(s, "02", RUST);
  title(s, "我们把「标准答案」实现了一遍，然后发现它不成立", "10 组随机种子，异构激励场景 S6");

  card(s, { x: M, y: 1.9, w: 6.0, h: 2.35, fill: "FBEEE9", line: "F0D2C7" });
  s.addText("加权质量分 与 只看输入能量：没有区别", {
    x: M + 0.35,
    y: 2.12,
    w: 5.3,
    h: 0.4,
    fontFace: HEAD,
    fontSize: 17,
    bold: true,
    color: RUST,
    margin: 0,
  });
  s.addText(
    [
      { text: "14.81%", options: { fontSize: 36, bold: true, color: RUST } },
      { text: "  对  ", options: { fontSize: 15, color: MUTE } },
      { text: "14.82%", options: { fontSize: 36, bold: true, color: MUTE } },
    ],
    { x: M + 0.35, y: 2.58, w: 5.4, h: 0.9, fontFace: HEAD, margin: 0, valign: "middle" }
  );
  s.addText("参数相对误差 · 两者都秩亏 · 稳态增益被估成接近零", {
    x: M + 0.35,
    y: 3.5,
    w: 5.3,
    h: 0.4,
    fontFace: BODY,
    fontSize: 13,
    color: MUTE,
    margin: 0,
  });

  card(s, { x: M, y: 4.45, w: 6.0, h: 1.95, fill: CARD });
  s.addText("问题不在于特征选得不够全", {
    x: M + 0.35,
    y: 4.68,
    w: 5.3,
    h: 0.36,
    fontFace: HEAD,
    fontSize: 16,
    bold: true,
    color: TXT,
    margin: 0,
  });
  s.addText(
    "而在于「逐窗口独立打分」这个形式本身：评分公式里没有任何一项，能表达「这个窗口和已经选中的窗口在讲同一件事」。",
    {
      x: M + 0.35,
      y: 5.1,
      w: 5.3,
      h: 1.1,
      fontFace: BODY,
      fontSize: 14,
      color: TXT,
      margin: 0,
      lineSpacingMultiple: 1.25,
    }
  );

  s.addChart(
    pres.ChartType.bar,
    [
      {
        name: "参数相对误差 (%)",
        labels: ["全量数据", "能量启发式", "完整加权分", "本方案"],
        values: [3.25, 14.82, 14.81, 3.49],
      },
    ],
    {
      x: 7.05,
      y: 1.9,
      w: 5.55,
      h: 4.5,
      barDir: "col",
      chartColors: [MUTE, RUST, RUST, TEAL],
      varyColors: true,
      showTitle: true,
      title: "等样本预算下的参数误差（越低越好）",
      titleFontFace: HEAD,
      titleFontSize: 13,
      titleColor: TXT,
      showValue: true,
      dataLabelPosition: "outEnd",
      dataLabelFontFace: BODY,
      dataLabelFontSize: 12,
      dataLabelColor: TXT,
      dataLabelFormatCode: '0.00"%"',
      showLegend: false,
      catAxisLabelFontFace: BODY,
      catAxisLabelFontSize: 12,
      catAxisLabelColor: TXT,
      valAxisLabelColor: MUTE,
      valAxisLabelFontSize: 10,
      valGridLine: { color: "E4EAEF", size: 1 },
      catGridLine: { style: "none" },
      valAxisMaxVal: 18,
      barGapWidthPct: 55,
    }
  );
  s.addNotes(
    "这一页是我们最想讲的发现。我们把赛题清单里的加权分按规范原样实现，作为对照基线。" +
      "结果它和只看输入能量没有区别——所以问题不在特征，在形式。"
  );
}

/* -------------------------------------------------------- 4 our approach */
{
  const s = lightSlide();
  badge(s, "03");
  title(s, "我们的做法：用信息量代替经验权重", "最大化 Fisher 信息矩阵的对数行列式");

  card(s, { x: M, y: 1.9, w: 12.0 - M + 0.6, h: 1.5, fill: NAVY, line: NAVY });
  s.addText("J(S) = log det( λI + Σ ΦᵀΦ )", {
    x: M + 0.4,
    y: 2.08,
    w: 5.6,
    h: 0.6,
    fontFace: "Cambria",
    fontSize: 26,
    bold: true,
    color: AMBER,
    margin: 0,
    valign: "middle",
  });
  s.addText("这个准则天然表达信息冗余：一个与已选片段重复的窗口，增量增益接近零。", {
    x: M + 0.4,
    y: 2.68,
    w: 11.0,
    h: 0.5,
    fontFace: BODY,
    fontSize: 14,
    color: "DCE8F0",
    margin: 0,
  });

  const items = [
    ["门控先于信息准则", "含尖峰或大段缺失的窗口「信息量」往往极高。不合格窗口在参与信息比较之前就被剔除，每条拒绝理由都被记录。", TEAL],
    ["增量增益以 bit 计", "「这段数据教了模型多少」是物理量，不是无量纲评分。增益低于阈值即停，不用稳态窗口凑满预算。", TEAL],
    ["惰性贪心加速", "候选求值减少 4.5–4.8 倍，且逐窗口结果与朴素贪心完全一致（有测试断言）。", TEAL],
    ["不主张全局最优", "1−1/e 近似保证只在单调子模、等长窗口、仅基数约束时成立。我们不把它表述为最优性。", AMBER],
  ];
  items.forEach(([h, d, c], i) => {
    const x = M + (i % 2) * 6.25;
    const y = 3.7 + Math.floor(i / 2) * 1.45;
    card(s, { x, y, w: 5.85, h: 1.25 });
    s.addShape(pres.ShapeType.ellipse, { x: x + 0.28, y: y + 0.34, w: 0.4, h: 0.4, fill: { color: c } });
    s.addText(h, {
      x: x + 0.85,
      y: y + 0.16,
      w: 4.8,
      h: 0.34,
      fontFace: HEAD,
      fontSize: 15,
      bold: true,
      color: TXT,
      margin: 0,
    });
    s.addText(d, {
      x: x + 0.85,
      y: y + 0.5,
      w: 4.8,
      h: 0.66,
      fontFace: BODY,
      fontSize: 11.5,
      color: MUTE,
      margin: 0,
      lineSpacingMultiple: 1.1,
    });
  });
  s.addNotes("核心算法一页讲完。最后一块特意写「不主张全局最优」——近似保证是有前提的，我们不夸大。");
}

/* ------------------------------------------------------------- 5 pipeline */
{
  const s = lightSlide();
  badge(s, "04");
  title(s, "完整闭环：一句自然语言驱动全流程", "Agent 解析意图 → 白名单计划 → 静态合规校验 → 调度真实算法 → 汇报结论");

  const steps = [
    ["01", "上传与规整", "CSV 上传、时间规整、清洗；原始数据不可覆盖，派生版本血缘"],
    ["02", "优选", "质量门控 + D-最优信息增益选段"],
    ["03", "补偿与降维", "预白化互相关时滞估计、共线性诊断"],
    ["04", "辨识与评价", "ARX 辨识、先验硬约束、一步 + 自由仿真双口径"],
    ["05", "闭环与交付", "分级寻优、策略热启动、溯源报告、数据集导出"],
  ];
  steps.forEach(([n, h, d], i) => {
    const x = M + i * 2.46;
    card(s, { x, y: 2.0, w: 2.25, h: 3.0 });
    s.addShape(pres.ShapeType.ellipse, {
      x: x + 0.9,
      y: 2.28,
      w: 0.46,
      h: 0.46,
      fill: { color: i === 1 ? AMBER : TEAL },
    });
    s.addText(n, {
      x: x + 0.9,
      y: 2.28,
      w: 0.46,
      h: 0.46,
      align: "center",
      valign: "middle",
      fontFace: HEAD,
      fontSize: 13,
      bold: true,
      color: "FFFFFF",
      margin: 0,
    });
    s.addText(h, {
      x: x + 0.2,
      y: 2.9,
      w: 1.85,
      h: 0.5,
      align: "center",
      fontFace: HEAD,
      fontSize: 14,
      bold: true,
      color: TXT,
      margin: 0,
    });
    s.addText(d, {
      x: x + 0.2,
      y: 3.45,
      w: 1.85,
      h: 1.4,
      align: "center",
      fontFace: BODY,
      fontSize: 11,
      color: MUTE,
      margin: 0,
      lineSpacingMultiple: 1.15,
    });
    if (i < steps.length - 1) {
      s.addText("›", {
        x: x + 2.13,
        y: 3.2,
        w: 0.45,
        h: 0.5,
        align: "center",
        valign: "middle",
        fontFace: HEAD,
        fontSize: 22,
        bold: true,
        color: TEAL_LT,
        margin: 0,
      });
    }
  });

  card(s, { x: M, y: 5.25, w: 12.0 - M + 0.6, h: 1.15, fill: "EAF1F5", line: "D3E0E8" });
  s.addText("「提取 1 号塔高信噪比的动态数据，处理共线性后，通过闭环寻优找出最佳模型数据」", {
    x: M + 0.4,
    y: 5.42,
    w: 11.0,
    h: 0.42,
    fontFace: HEAD,
    fontSize: 15,
    bold: true,
    color: NAVY,
    margin: 0,
  });
  s.addText(
    "大模型负责提议，不负责授权：它生成的计划要通过与规则计划完全相同的白名单与合规校验；未配置大模型时系统完整可用。",
    {
      x: M + 0.4,
      y: 5.84,
      w: 11.0,
      h: 0.4,
      fontFace: BODY,
      fontSize: 12.5,
      color: MUTE,
      margin: 0,
    }
  );
  s.addNotes("演示时就用这一句话跑通全流程。强调离线可用——赛场可能没有网络。");
}

/* ------------------------------------------------------- 6 metric choice */
{
  const s = lightSlide();
  badge(s, "05");
  title(s, "我们没有照做的地方：模型评价口径", "赛题字面要求用一步预测 FIT 做闭环目标函数");

  card(s, { x: M, y: 1.9, w: 6.1, h: 2.15, fill: CARD });
  s.addText("一个「很好」的坏模型", {
    x: M + 0.35,
    y: 2.1,
    w: 5.4,
    h: 0.38,
    fontFace: HEAD,
    fontSize: 17,
    bold: true,
    color: TXT,
    margin: 0,
  });
  s.addText(
    [
      { text: "参数误差 15%、稳态增益完全错误、设计矩阵秩亏", options: { bullet: true, breakLine: true } },
      { text: "它的一步预测 FIT 仍有 96.5，只比最优模型低 0.5 分", options: { bullet: true } },
    ],
    {
      x: M + 0.35,
      y: 2.55,
      w: 5.4,
      h: 1.3,
      fontFace: BODY,
      fontSize: 13.5,
      color: TXT,
      margin: 0,
      paraSpaceAfter: 8,
      lineSpacingMultiple: 1.15,
    }
  );

  card(s, { x: M, y: 4.25, w: 6.1, h: 2.15, fill: NAVY, line: NAVY });
  s.addText("原因", {
    x: M + 0.35,
    y: 4.45,
    w: 5.4,
    h: 0.34,
    fontFace: HEAD,
    fontSize: 16,
    bold: true,
    color: AMBER,
    margin: 0,
  });
  s.addText(
    "工业过程输出强自相关。一步预测用的是实测的上一时刻输出——模型只要「抄上一时刻」就能拿高分，输入通道估错几乎不受惩罚。",
    {
      x: M + 0.35,
      y: 4.86,
      w: 5.4,
      h: 1.3,
      fontFace: BODY,
      fontSize: 13.5,
      color: "DCE8F0",
      margin: 0,
      lineSpacingMultiple: 1.2,
    }
  );

  s.addText("28.5×", {
    x: 7.15,
    y: 1.95,
    w: 5.4,
    h: 1.1,
    fontFace: HEAD,
    fontSize: 62,
    bold: true,
    color: TEAL,
    margin: 0,
  });
  s.addText("自由仿真 FIT 的区分度，是一步预测 FIT 的 28.5 倍", {
    x: 7.15,
    y: 3.0,
    w: 5.4,
    h: 0.45,
    fontFace: BODY,
    fontSize: 14,
    color: MUTE,
    margin: 0,
  });

  s.addChart(
    pres.ChartType.bar,
    [
      {
        name: "同一组模型下的指标跨度（个点）",
        labels: ["一步预测 FIT", "自由仿真 FIT"],
        values: [0.54, 15.27],
      },
    ],
    {
      x: 7.05,
      y: 3.55,
      w: 5.55,
      h: 2.85,
      barDir: "bar",
      chartColors: [MUTE, TEAL],
      varyColors: true,
      showTitle: false,
      showValue: true,
      dataLabelPosition: "outEnd",
      dataLabelFontFace: BODY,
      dataLabelFontSize: 13,
      dataLabelColor: TXT,
      showLegend: false,
      catAxisLabelFontFace: BODY,
      catAxisLabelFontSize: 12,
      catAxisLabelColor: TXT,
      valAxisLabelColor: MUTE,
      valAxisLabelFontSize: 10,
      valGridLine: { color: "E4EAEF", size: 1 },
      catGridLine: { style: "none" },
      valAxisMaxVal: 18,
      barGapWidthPct: 60,
    }
  );
  s.addNotes(
    "赛题要求用一步预测 FIT，我们改成自由仿真 FIT，并给出了不照做的实测理由。" +
      "一步预测 FIT 我们没有删掉，降级为过拟合诊断量。"
  );
}

/* ------------------------------------------------------ 7 trust by design */
{
  const s = lightSlide();
  badge(s, "06");
  title(s, "可信性不是承诺，是机制", "系统给出的每一个数字，都要能追到它是怎么算出来的");

  const blocks = [
    [
      "报告里的数字，大模型一个都不许写",
      "大模型只能输出占位符，由渲染器绑定真实运行记录。含裸数字的草稿被拒绝并要求重写，连续 3 次不合规回退模板化结论。",
      TEAL,
    ],
    [
      "Agent 计划受静态合规校验",
      "工具白名单、执行图无环、时序合法、高影响操作门控，产出可机器复核的签名证明。计划由谁生成不重要，校验对谁都一样。",
      TEAL,
    ],
    [
      "系统能当场检验自己的主张",
      "产品内置「一键自评测基准」：点一次按钮实时重算全部技术主张，没有任何数字是缓存的或写死的。主张不成立，表格立刻显示。",
      AMBER,
    ],
  ];
  blocks.forEach(([h, d, c], i) => {
    const x = M + i * 4.15;
    card(s, { x, y: 2.0, w: 3.85, h: 2.85 });
    s.addShape(pres.ShapeType.ellipse, { x: x + 0.3, y: 2.3, w: 0.44, h: 0.44, fill: { color: c } });
    s.addText(String(i + 1), {
      x: x + 0.3,
      y: 2.3,
      w: 0.44,
      h: 0.44,
      align: "center",
      valign: "middle",
      fontFace: HEAD,
      fontSize: 14,
      bold: true,
      color: "FFFFFF",
      margin: 0,
    });
    s.addText(h, {
      x: x + 0.3,
      y: 2.9,
      w: 3.25,
      h: 0.7,
      fontFace: HEAD,
      fontSize: 15,
      bold: true,
      color: TXT,
      margin: 0,
      lineSpacingMultiple: 1.1,
    });
    s.addText(d, {
      x: x + 0.3,
      y: 3.65,
      w: 3.25,
      h: 1.05,
      fontFace: BODY,
      fontSize: 11.5,
      color: MUTE,
      margin: 0,
      lineSpacingMultiple: 1.15,
    });
  });

  card(s, { x: M, y: 5.1, w: 12.0 - M + 0.6, h: 1.3, fill: "EAF1F5", line: "D3E0E8" });
  s.addText("一个实际发生的例子", {
    x: M + 0.4,
    y: 5.28,
    w: 11.0,
    h: 0.36,
    fontFace: HEAD,
    fontSize: 15,
    bold: true,
    color: NAVY,
    margin: 0,
  });
  s.addText(
    "补入完整加权分对照后，S3 场景的排名把我们的主口径挤到了第三位。报告如实写了下来，没有删掉这组对照。",
    {
      x: M + 0.4,
      y: 5.68,
      w: 11.0,
      h: 0.5,
      fontFace: BODY,
      fontSize: 13,
      color: MUTE,
      margin: 0,
    }
  );
  s.addNotes("这一页是我们和其他队伍最不一样的地方：可信性做成了机制，而且我们主动展示对自己不利的结果。");
}

/* ------------------------------------------------- 8 unfavourable results */
{
  const s = darkSlide();
  s.addShape(pres.ShapeType.ellipse, {
    x: 10.6,
    y: -1.4,
    w: 5.0,
    h: 5.0,
    fill: { color: RUST, transparency: 86 },
  });
  s.addText("我们同时提交对自己不利的结果", {
    x: M,
    y: 0.62,
    w: 11.0,
    h: 0.72,
    fontFace: HEAD,
    fontSize: 30,
    bold: true,
    color: "FFFFFF",
    margin: 0,
    valign: "middle",
  });
  s.addText("一个只报喜的对照实验，说明不了任何问题", {
    x: M,
    y: 1.34,
    w: 11.0,
    h: 0.42,
    fontFace: BODY,
    fontSize: 14,
    color: AMBER,
    margin: 0,
  });

  const rows = [
    ["同构激励下本方案排在末位", "4.80% vs 加权分 3.75%、全量 3.76%", "价值在于「不会崩」而非「永远最优」：这里差 1 个百分点，异构激励下差 11 个百分点加秩亏"],
    ["预算太小时本方案同样秩亏", "预算/窗长 ≤ 2.3 时失效", "不是准则失灵，是预算不足。已作为提示写进产品，不让工程师在不知情时拿到秩亏模型"],
    ["内容寻址缓存命中率仅 1.7%", "未量化阈值时更是 0%", "真正的节省来自分级搜索（摊薄 24 倍）。据实上报，不把收益错误归因"],
    ["预白化时滞 4 胜 1 负 1 平", "6 个通道，占优但非全胜", "系统性偏差被消除才是它的价值，不是每个通道都赢"],
  ];
  rows.forEach(([h, m, d], i) => {
    const y = 2.0 + i * 1.15;
    s.addShape(pres.ShapeType.roundRect, {
      x: M,
      y,
      w: 12.0 - M + 0.6,
      h: 1.0,
      rectRadius: 0.06,
      fill: { color: NAVY },
      line: { color: "22475F", width: 1 },
    });
    s.addText(h, {
      x: M + 0.32,
      y: y + 0.13,
      w: 4.1,
      h: 0.36,
      fontFace: HEAD,
      fontSize: 14,
      bold: true,
      color: "FFFFFF",
      margin: 0,
    });
    s.addText(m, {
      x: M + 0.32,
      y: y + 0.5,
      w: 4.1,
      h: 0.34,
      fontFace: BODY,
      fontSize: 11.5,
      color: RUST === "C0553B" ? "E08D74" : RUST,
      margin: 0,
    });
    s.addText(d, {
      x: M + 4.6,
      y: y + 0.16,
      w: 7.4,
      h: 0.7,
      fontFace: BODY,
      fontSize: 12.5,
      color: "C6D6E2",
      margin: 0,
      valign: "middle",
      lineSpacingMultiple: 1.12,
    });
  });

  s.addText("原始数据与可复现脚本：docs/experiments/（EXP-1.1 / EXP-2.1 / EXP-3.0）", {
    x: M,
    y: 6.72,
    w: 11.0,
    h: 0.35,
    fontFace: BODY,
    fontSize: 11.5,
    color: "6E8798",
    margin: 0,
  });
  s.addNotes("这一页不要跳过。评委问不利结果的时候，我们已经先说了，而且每一条都给了工程解释。");
}

/* --------------------------------------------------------- 9 sensitivity */
{
  const s = lightSlide();
  badge(s, "07");
  title(s, "结论不是单点巧合：200 个工作点", "5 种窗口长度 × 4 档样本预算 × 5 组种子 × 2 类激励场景");

  s.addChart(
    pres.ChartType.bar,
    [
      {
        name: "参数误差最优次数（共 20 个工作点）",
        labels: ["本方案", "能量启发式", "完整加权分"],
        values: [18, 2, 0],
      },
      {
        name: "设计矩阵满秩的工作点数",
        labels: ["本方案", "能量启发式", "完整加权分"],
        values: [16, 1, 2],
      },
    ],
    {
      x: M,
      y: 2.0,
      w: 7.1,
      h: 4.4,
      barDir: "col",
      chartColors: [TEAL, AMBER],
      showTitle: true,
      title: "S6 异构激励：20 个工作点上的胜出与满秩次数",
      titleFontFace: HEAD,
      titleFontSize: 13,
      titleColor: TXT,
      showValue: true,
      dataLabelPosition: "outEnd",
      dataLabelFontFace: BODY,
      dataLabelFontSize: 12,
      dataLabelColor: TXT,
      showLegend: true,
      legendPos: "b",
      legendFontFace: BODY,
      legendFontSize: 11,
      legendColor: MUTE,
      catAxisLabelFontFace: BODY,
      catAxisLabelFontSize: 12,
      catAxisLabelColor: TXT,
      valAxisLabelColor: MUTE,
      valAxisLabelFontSize: 10,
      valGridLine: { color: "E4EAEF", size: 1 },
      catGridLine: { style: "none" },
      valAxisMaxVal: 22,
      barGapWidthPct: 45,
    }
  );

  card(s, { x: 8.05, y: 2.0, w: 4.55, h: 2.1, fill: CARD });
  s.addText("同构激励 S3", {
    x: 8.35,
    y: 2.2,
    w: 3.95,
    h: 0.36,
    fontFace: HEAD,
    fontSize: 16,
    bold: true,
    color: TXT,
    margin: 0,
  });
  s.addText("20 个工作点全部满秩，无任何策略崩溃。预算 ≥10% 后三者基本无法区分。", {
    x: 8.35,
    y: 2.62,
    w: 3.95,
    h: 1.2,
    fontFace: BODY,
    fontSize: 12.5,
    color: MUTE,
    margin: 0,
    lineSpacingMultiple: 1.2,
  });

  card(s, { x: 8.05, y: 4.3, w: 4.55, h: 2.1, fill: "FBEEE9", line: "F0D2C7" });
  s.addText("本方案的失效边界", {
    x: 8.35,
    y: 4.5,
    w: 3.95,
    h: 0.36,
    fontFace: HEAD,
    fontSize: 16,
    bold: true,
    color: RUST,
    margin: 0,
  });
  s.addText(
    "预算/窗长 ≤ 2.3 时本方案同样秩亏，分界干净无交叉。已写进产品：选出窗口少于 3 个即提示，但不阻断。",
    {
      x: 8.35,
      y: 4.92,
      w: 3.95,
      h: 1.3,
      fontFace: BODY,
      fontSize: 12.5,
      color: TXT,
      margin: 0,
      lineSpacingMultiple: 1.2,
    }
  );
  s.addNotes("敏感性扫描是为了回答「你们是不是只在一个参数上调好了」。顺带找到了我们自己的失效边界。");
}

/* ------------------------------------------------------------ 10 quality */
{
  const s = lightSlide();
  badge(s, "08");
  title(s, "工程完成度", "全部门禁通过，可复现");

  const stats = [
    ["233", "后端自动化测试", TEAL],
    ["9", "前端 E2E（真实浏览器）", TEAL],
    ["69", "源文件 Ruff + Mypy 全通过", TEAL],
    ["23", "OpenAPI 3.1.0 端点", TEAL],
  ];
  stats.forEach(([big, small, c], i) => {
    const x = M + i * 3.1;
    card(s, { x, y: 2.0, w: 2.85, h: 1.75 });
    s.addText(big, {
      x: x + 0.25,
      y: 2.22,
      w: 2.35,
      h: 0.75,
      fontFace: HEAD,
      fontSize: 40,
      bold: true,
      color: c,
      margin: 0,
    });
    s.addText(small, {
      x: x + 0.25,
      y: 3.0,
      w: 2.35,
      h: 0.6,
      fontFace: BODY,
      fontSize: 12,
      color: MUTE,
      margin: 0,
      lineSpacingMultiple: 1.1,
    });
  });

  card(s, { x: M, y: 4.0, w: 6.0, h: 2.4, fill: NAVY, line: NAVY });
  s.addText("一个只有端到端测试才能发现的缺陷", {
    x: M + 0.35,
    y: 4.22,
    w: 5.3,
    h: 0.38,
    fontFace: HEAD,
    fontSize: 16,
    bold: true,
    color: AMBER,
    margin: 0,
  });
  s.addText(
    "曾经 185 个测试全绿，而真实用户路径完全不可用——上传的 CSV 一律被拒绝。数值列筛选用了 numeric，而解析器发出的是 integer / float；基准测试走的是另一条加载路径，所以测试全过。",
    {
      x: M + 0.35,
      y: 4.68,
      w: 5.3,
      h: 1.5,
      fontFace: BODY,
      fontSize: 12.5,
      color: "DCE8F0",
      margin: 0,
      lineSpacingMultiple: 1.2,
    }
  );

  const rights = [
    ["离线优先", "Docker Compose 单机栈；未配置大模型时系统完整可用"],
    ["长任务后台化", "RQ Worker 执行寻优；队列不可用时回退同步并说明路径"],
    ["尚未完成", "公开工业数据集外部验证、Compose 实机启动验证——如实列出"],
  ];
  rights.forEach(([h, d], i) => {
    const y = 4.0 + i * 0.82;
    card(s, { x: 7.05, y, w: 5.55, h: 0.72, fill: i === 2 ? "FBEEE9" : CARD, line: i === 2 ? "F0D2C7" : "E2E8ED" });
    s.addText(h, {
      x: 7.3,
      y: y + 0.06,
      w: 1.7,
      h: 0.6,
      fontFace: HEAD,
      fontSize: 13,
      bold: true,
      color: i === 2 ? RUST : TXT,
      margin: 0,
      valign: "middle",
    });
    s.addText(d, {
      x: 9.05,
      y: y + 0.06,
      w: 3.4,
      h: 0.6,
      fontFace: BODY,
      fontSize: 11,
      color: MUTE,
      margin: 0,
      valign: "middle",
      lineSpacingMultiple: 1.1,
    });
  });
  s.addNotes("工程完成度。左下角那个缺陷值得讲——它是我们后来加端到端验收测试的直接原因。");
}

/* --------------------------------------------------------------- 11 close */
{
  const s = darkSlide();
  s.addShape(pres.ShapeType.ellipse, {
    x: -1.6,
    y: 3.6,
    w: 5.4,
    h: 5.4,
    fill: { color: TEAL, transparency: 82 },
  });
  s.addShape(pres.ShapeType.ellipse, {
    x: 10.2,
    y: -1.5,
    w: 4.6,
    h: 4.6,
    fill: { color: AMBER, transparency: 88 },
  });

  s.addText("我们认为最值得看的一点", {
    x: M,
    y: 1.55,
    w: 11.4,
    h: 0.55,
    fontFace: BODY,
    fontSize: 17,
    color: TEAL_LT,
    margin: 0,
  });
  s.addText("评委不需要相信我们的 PPT，\n点一下按钮就能验证。", {
    x: M,
    y: 2.25,
    w: 11.4,
    h: 1.9,
    fontFace: HEAD,
    fontSize: 40,
    bold: true,
    color: "FFFFFF",
    margin: 0,
    lineSpacingMultiple: 1.25,
  });
  s.addText(
    "多数作品无法证明自己的预处理起了作用——真实工厂数据没有真值，只能展示「曲线拟合上了」。本项目自带仿真基准与完整真值，因此可以在产品内部当场重算全部技术主张，并且把对自己不利的结果一起显示出来。",
    {
      x: M,
      y: 4.35,
      w: 10.4,
      h: 1.4,
      fontFace: BODY,
      fontSize: 15,
      color: "C6D6E2",
      margin: 0,
      lineSpacingMultiple: 1.3,
    }
  );

  s.addText("IndusOpt 工模智优  ·  V1.0  ·  赛题 A14", {
    x: M,
    y: 6.35,
    w: 11.4,
    h: 0.4,
    fontFace: HEAD,
    fontSize: 14,
    bold: true,
    color: AMBER,
    margin: 0,
  });
  s.addNotes("收尾。把「一键自评测基准」当场演示一次，比任何一页 PPT 都有说服力。");
}

pres
  .writeFile({ fileName: "IndusOpt-A14-答辩.pptx" })
  .then((f) => console.log("wrote", f));
