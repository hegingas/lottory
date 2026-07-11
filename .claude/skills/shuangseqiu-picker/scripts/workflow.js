// 双色球选号委员会 Workflow
// 五人独立提名 → 交叉辩论 → 首席裁定
export const meta = {
  name: 'ssq-committee-pick',
  description: '双色球五人委员会选号：趋势猎手/遗漏判官/结构大师/形态侦探/博弈鬼才 独立提名+交叉辩论+首席裁定',
  phases: [
    { title: '数据准备', detail: '读取 ssq_draws.csv 提取上期+近50期数据' },
    { title: '独立提名', detail: '5 个 Agent 并行分析，各自提名一注' },
    { title: '交叉辩论', detail: '每人点评一位对手 + 自辩' },
    { title: '首席裁定', detail: '综合 5 人提名+辩论，裁定最终一注' },
  ],
};

// ── 提名结构 ──
const NOMINATION_SCHEMA = {
  type: 'object',
  properties: {
    reds: { type: 'array', items: { type: 'string' }, description: '红球6码，升序' },
    blue: { type: 'string', description: '蓝球1码' },
    reasoning: { type: 'string', description: '每个号的选号理由（含数据引用）' },
  },
  required: ['reds', 'blue', 'reasoning'],
};

// ── 辩论结构 ──
const DEBATE_SCHEMA = {
  type: 'object',
  properties: {
    target: { type: 'string', description: '被点评的委员名' },
    agree_numbers: { type: 'array', items: { type: 'string' }, description: '同意的号码' },
    disagree_numbers: { type: 'array', items: { type: 'string' }, description: '反对的号码' },
    critique: { type: 'string', description: '点评理由（引用数据）' },
    self_defense: { type: 'string', description: '自辩：针对自己方案的弱点用数据回应' },
  },
  required: ['target', 'agree_numbers', 'disagree_numbers', 'critique', 'self_defense'],
};

// ── 五人角色定义 ──
const ROLES = [
  { name: '趋势猎手', agentType: 'trend-hunter', color: 'blue' },
  { name: '遗漏判官', agentType: 'gap-judge', color: 'red' },
  { name: '结构大师', agentType: 'struct-master', color: 'green' },
  { name: '形态侦探', agentType: 'pattern-spy', color: 'purple' },
  { name: '博弈鬼才', agentType: 'game-theorist', color: 'orange' },
];

// ═══════════════════════════════════════════════
// Phase 1: 数据准备
// ═══════════════════════════════════════════════
phase('数据准备');

const DATA_PROMPT = `读取 data/processed/ssq_draws.csv：
1. 全历史期数，最新一期期号+开奖号码
2. 近50期所有红球和蓝球的频次
3. 每个红球01-33和蓝球01-16的当前遗漏期数
4. 近50期奇偶比/大小比/和值分布

将以上数据返回为结构化摘要。`;

const dataContext = await agent(DATA_PROMPT, {
  label: '数据准备',
  phase: '数据准备',
  model: 'haiku',
});

log(`数据就绪：${dataContext.slice(0, 100)}...`);

// ═══════════════════════════════════════════════
// Phase 2: 五人并行独立提名
// ═══════════════════════════════════════════════
phase('独立提名');

const NOMINATION_PROMPT = (role, data) => `
## 数据背景
${data}

## 你的任务
作为${role.name}，按你的专属方法论分析数据，提名一注双色球号码（红球6码+蓝球1码）。

每个号码必须附带数据支撑的理由。输出红球升序排列。
`;

const nominations = await parallel(
  ROLES.map(role => () =>
    agent(NOMINATION_PROMPT(role, dataContext), {
      label: role.name,
      phase: '独立提名',
      agentType: role.agentType,
      schema: NOMINATION_SCHEMA,
    })
  )
);

// 过滤掉 null（被跳过的 agent）
const validNominations = nominations.filter(Boolean);
log(`提名完成：${validNominations.length}/5 人提交`);

// ═══════════════════════════════════════════════
// Phase 3: 交叉辩论
// ═══════════════════════════════════════════════
phase('交叉辩论');

const allNominationsSummary = validNominations
  .map((n, i) => `${ROLES[i].name}: 红球 ${n.reds.join(' ')} | 蓝球 ${n.blue}`)
  .join('\n');

const DEBATE_PROMPT = (role, ownPick, othersSummary) => `
## 全部提名方案
${othersSummary}

## 你的任务
作为${role.name}，你的提名是：红球 ${ownPick.reds.join(' ')} | 蓝球 ${ownPick.blue}

请完成两项：
1. **选一位其他委员点评**：指出你同意哪些号（至少2个）、反对哪些号（至少1个），必须引用数据
2. **自辩**：针对你的方案中最可能被攻击的弱点，用数据回应
`;

const debates = await parallel(
  validNominations.map((nom, i) => () =>
    agent(DEBATE_PROMPT(ROLES[i], nom, allNominationsSummary), {
      label: `辩论:${ROLES[i].name}`,
      phase: '交叉辩论',
      agentType: ROLES[i].agentType,
      schema: DEBATE_SCHEMA,
    })
  )
);

const validDebates = debates.filter(Boolean);
log(`辩论完成：${validDebates.length}/5 人参与`);

// ═══════════════════════════════════════════════
// Phase 4: 首席裁定
// ═══════════════════════════════════════════════
phase('首席裁定');

const CHIEF_PROMPT = `
你是双色球选号委员会的**首席裁判**。你不参与提名，只做裁定。

## 五人提名
${validNominations.map((n, i) => `${ROLES[i].name}: 红球 ${n.reds.join(' ')} | 蓝球 ${n.blue} | 理由: ${n.reasoning.slice(0, 200)}`).join('\n\n')}

## 辩论摘要
${validDebates.map(d => `${d.target}: 同意[${d.agree_numbers.join(',')}] 反对[${d.disagree_numbers.join(',')}] | 点评: ${d.critique.slice(0, 200)} | 自辩: ${d.self_defense.slice(0, 200)}`).join('\n\n')}

## 裁定要求
1. 统计每个号码被提名次数（共识号）
2. 综合各方观点，裁定最终一注（红6+蓝1）
3. 必须满足：至少一组连号 + 与上期重叠1-2个号
4. 说明每个选定号的来源（采纳了哪位委员的观点）
5. 输出贡献统计（每位委员入选了几个号）

最终号码直接决定，不考虑委员面子。
`;

const finalRuling = await agent(CHIEF_PROMPT, {
  label: '首席裁定',
  phase: '首席裁定',
  model: 'opus',
  effort: 'high',
});

// ═══════════════════════════════════════════════
// 返回结果
// ═══════════════════════════════════════════════
return {
  nominations: validNominations.map((n, i) => ({
    role: ROLES[i].name,
    reds: n.reds,
    blue: n.blue,
    reasoning: n.reasoning,
  })),
  debates: validDebates.map((d, i) => ({
    from: ROLES[i].name,
    ...d,
  })),
  finalRuling,
};
