// 七星彩选号委员会 Workflow
// 4人(无形态侦探)提名 → 对抗验证 → 首席裁定
export const meta = {
  name: 'qxc-committee-pick',
  description: '七星彩四人委员会选号：趋势猎手/遗漏判官/结构大师/博弈鬼才 按位对抗验证→收敛→裁定',
  phases: [
    { title: '数据准备', detail: '读取 qxc_draws.csv' },
    { title: '独立提名', detail: '4 Agent 并行，各提名前6+后1' },
    { title: '对抗验证', detail: '每人审核所有对手→自证→收敛检查，最多5轮' },
    { title: '首席裁定', detail: '综合裁定最终前6+后1' },
  ],
};

const NOMINATION_SCHEMA = {
  type: 'object',
  properties: {
    d1: { type: 'string' }, d2: { type: 'string' }, d3: { type: 'string' }, d4: { type: 'string' }, d5: { type: 'string' }, d6: { type: 'string' },
    special: { type: 'string', description: '后区0-14' },
    reasoning: { type: 'string' },
  },
  required: ['d1', 'd2', 'd3', 'd4', 'd5', 'd6', 'special', 'reasoning'],
};

const REVIEW_ONE_SCHEMA = {
  type: 'object',
  properties: {
    target: { type: 'string' },
    agree_positions: { type: 'array', items: { type: 'string' } },
    disagree_positions: { type: 'array', items: { type: 'string' } },
    critique: { type: 'string' },
    suggest_replace: { type: 'string' },
  },
  required: ['target', 'agree_positions', 'disagree_positions', 'critique'],
};

const DEFENSE_SCHEMA = {
  type: 'object',
  properties: {
    role: { type: 'string' },
    adjustments_made: { type: 'array', items: { type: 'string' } },
    new_pick: { type: 'object', properties: { d1: { type: 'string' }, d2: { type: 'string' }, d3: { type: 'string' }, d4: { type: 'string' }, d5: { type: 'string' }, d6: { type: 'string' }, special: { type: 'string' } } },
    defense: { type: 'string' },
    concessions: { type: 'string' },
  },
  required: ['role', 'adjustments_made', 'new_pick', 'defense', 'concessions'],
};

// 七星彩跳过形态侦探（无连号/重号约束，允许重复数字）
const ROLES = [
  { name: '趋势猎手', agentType: 'trend-hunter' },
  { name: '遗漏判官', agentType: 'gap-judge' },
  { name: '结构大师', agentType: 'struct-master' },
  { name: '博弈鬼才', agentType: 'game-theorist' },
];
const N = ROLES.length;
const MAX_ROUNDS = 5;
const CONVERGE_THRESHOLD = 4; // 7位中至少4位被3+人同意

// ══ Phase 1 ══
phase('数据准备');
const dataContext = await agent(
  `读取 data/processed/qxc_draws.csv：
1. 全历史期数，最新一期期号 + 开奖号码（前区d1-d6各0-9 + 后区special 0-14）
2. 近50期每位(d1-d6)的0-9频次 + special的0-14频次（按位分别统计）
3. 每位的当前遗漏期数
4. 近50期前区重复数字频率、奇偶比/大小比(0-4小/5-9大)
5. 后区special 0-14的冷热分布`,
  { label: '数据准备', phase: '数据准备', model: 'haiku' }
);
log('数据就绪');

// ══ Phase 2: 4人并行提名 ══
phase('独立提名');
let picks = await parallel(
  ROLES.map(role => () =>
    agent(
      `## 七星彩选号（前区d1-d6各0-9 + 后区special 0-14，前区允许重复）\n## 数据\n${dataContext}\n\n作为${role.name}，按位独立分析，每位取最优数字。提名：d1-d6 + special，每位附理由。`,
      { label: role.name, phase: '独立提名', agentType: role.agentType, schema: NOMINATION_SCHEMA }
    )
  )
);
picks = picks.filter(Boolean);
log(`提名完成：${picks.length}/4 人`);

// ══ Phase 3: 对抗验证循环 ══
phase('对抗验证');
let round = 0, converged = false;
const allDebates = [];

while (round < MAX_ROUNDS && !converged) {
  round++;
  log(`━━━ 第 ${round} 轮 ━━━`);

  const reviewMeta = [], reviewTasks = [];
  for (let i = 0; i < N; i++) {
    for (let j = 0; j < N; j++) {
      if (i === j) continue;
      const reviewer = ROLES[i], target = ROLES[j];
      reviewMeta.push({ reviewerIdx: i, targetIdx: j, reviewerName: reviewer.name, targetName: target.name });
      reviewTasks.push(() =>
        agent(
          `你是${reviewer.name}，提名：${picks[i].d1}${picks[i].d2}${picks[i].d3}${picks[i].d4}${picks[i].d5}${picks[i].d6} + ${picks[i].special}

🔥 严厉审核 ${target.name}：${picks[j].d1}${picks[j].d2}${picks[j].d3}${picks[j].d4}${picks[j].d5}${picks[j].d6} + ${picks[j].special}

别客气！按位怼：
1. 同意≥2个位置 —— 数据说话
2. 反对≥1个位置 —— 狠狠批！
3. 建议替换

⚠️ 拿数据砸！🎭 保持人设！📢 中文口语像吵架。`,
          { label: `${reviewer.name}→${target.name}`, phase: '对抗验证', agentType: reviewer.agentType, schema: REVIEW_ONE_SCHEMA }
        )
      );
    }
  }
  const allReviewResults = await parallel(reviewTasks);
  const reviewsAboutEach = ROLES.map(() => []);
  for (let k = 0; k < reviewMeta.length; k++) {
    const rev = allReviewResults[k];
    if (rev) { const { targetName, reviewerName } = reviewMeta[k]; const idx = ROLES.findIndex(r => r.name === targetName); reviewsAboutEach[idx].push({ from: reviewerName, ...rev }); }
  }
  const defenseTasks = ROLES.map((role, i) => {
    const aboutMe = reviewsAboutEach[i];
    const reviewsText = aboutMe.map(r => `【${r.from}】同意位:${r.agree_positions.join(',')} | 反对位:${r.disagree_positions.join(',')} | ${r.critique}`).join('\n');
    const cur = picks[i];
    return () => agent(
      `你是${role.name}。当前提名：${cur.d1}${cur.d2}${cur.d3}${cur.d4}${cur.d5}${cur.d6} + ${cur.special}

⚔️ 有人对你开火！
${reviewsText}

按位反击：
1. 每个被反对的位置，用数据狠狠怼回去
2. 多人同怼同一个位置？认真想。坚信就死保
3. 输出最终前6+后1

🎭 保持人设！中文口语像吵架。`,
      { label: `${role.name}自证`, phase: '对抗验证', agentType: role.agentType, schema: DEFENSE_SCHEMA }
    );
  });
  const allDefenses = await parallel(defenseTasks);
  const newPicks = [];
  for (let i = 0; i < N; i++) {
    const defense = allDefenses[i], cur = picks[i];
    if (defense?.new_pick?.d1) {
      allDebates.push({ round, role: ROLES[i].name, defense: defense.defense, concessions: defense.concessions, adjustments: defense.adjustments_made });
      const np = defense.new_pick;
      newPicks.push({ d1: np.d1, d2: np.d2, d3: np.d3, d4: np.d4, d5: np.d5, d6: np.d6, special: np.special, reasoning: cur.reasoning });
    } else { newPicks.push(cur); }
  }
  picks = newPicks;

  let consensusPositions = 0;
  for (const pos of ['d1', 'd2', 'd3', 'd4', 'd5', 'd6', 'special']) {
    const vals = picks.map(p => p[pos]);
    const counts = {}; for (const v of vals) counts[v] = (counts[v] || 0) + 1;
    if (Math.max(...Object.values(counts)) >= 3) consensusPositions++;
  }
  log(`收敛: ${consensusPositions}/7位共识(≥3票)`);
  if (consensusPositions >= CONVERGE_THRESHOLD) { converged = true; log(`✅ 第${round}轮收敛！`); }
}

// ══ Phase 4 ══
phase('首席裁定');
const finalRuling = await agent(
  `你是七星彩选号委员会首席裁判。${round}轮后${converged ? '已收敛' : '未完全收敛'}。
最终方案：${picks.map((p, i) => `${ROLES[i].name}: ${p.d1}${p.d2}${p.d3}${p.d4}${p.d5}${p.d6}+${p.special}`).join(' | ')}
裁定最终前6+后1，标注来源+贡献统计。`,
  { label: '首席裁定', phase: '首席裁定', model: 'opus', effort: 'high' }
);

return { ruling: finalRuling, round, converged, finalPicks: picks.map((p, i) => ({ role: ROLES[i].name, d1: p.d1, d2: p.d2, d3: p.d3, d4: p.d4, d5: p.d5, d6: p.d6, special: p.special })), debates: allDebates };
