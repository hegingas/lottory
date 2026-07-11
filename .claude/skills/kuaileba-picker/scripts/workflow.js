// 快乐八选号委员会 Workflow
// 4人(无形态侦探)提名 → 对抗验证 → 首席裁定
export const meta = {
  name: 'kl8-committee-pick',
  description: '快乐八四人委员会选号：趋势猎手/遗漏判官/结构大师/博弈鬼才 对抗验证→收敛→裁定',
  phases: [
    { title: '数据准备', detail: '读取 kl8_draws.csv' },
    { title: '独立提名', detail: '4 Agent 并行，各提名选十10码' },
    { title: '对抗验证', detail: '每人审核所有对手→自证→收敛检查，最多5轮' },
    { title: '首席裁定', detail: '综合裁定最终10码' },
  ],
};

const NOMINATION_SCHEMA = {
  type: 'object',
  properties: {
    numbers: { type: 'array', items: { type: 'string' }, description: '选十10码升序' },
    reasoning: { type: 'string' },
  },
  required: ['numbers', 'reasoning'],
};

const REVIEW_ONE_SCHEMA = {
  type: 'object',
  properties: {
    target: { type: 'string' },
    agree_numbers: { type: 'array', items: { type: 'string' } },
    disagree_numbers: { type: 'array', items: { type: 'string' } },
    critique: { type: 'string' },
    suggest_replace: { type: 'string' },
  },
  required: ['target', 'agree_numbers', 'disagree_numbers', 'critique'],
};

const DEFENSE_SCHEMA = {
  type: 'object',
  properties: {
    role: { type: 'string' },
    adjustments_made: { type: 'array', items: { type: 'string' } },
    new_pick: { type: 'object', properties: { numbers: { type: 'array', items: { type: 'string' } } } },
    defense: { type: 'string' },
    concessions: { type: 'string' },
  },
  required: ['role', 'adjustments_made', 'new_pick', 'defense', 'concessions'],
};

// 快乐八跳过形态侦探（无连号/重号约束）
const ROLES = [
  { name: '趋势猎手', agentType: 'trend-hunter' },
  { name: '遗漏判官', agentType: 'gap-judge' },
  { name: '结构大师', agentType: 'struct-master' },
  { name: '博弈鬼才', agentType: 'game-theorist' },
];
const N = ROLES.length;
const MAX_ROUNDS = 5;
const CONVERGE_THRESHOLD = 5; // 10码中至少5个被3+人同意

// ══ Phase 1 ══
phase('数据准备');
const dataContext = await agent(
  `读取 data/processed/kl8_draws.csv：
1. 全历史期数，最新一期期号 + 20个开奖号码
2. 近50期01-80每个号码频次
3. 每个号码当前遗漏
4. 近50期奇偶比/大小比(01-40小/41-80大)/和值分布
5. 8个十码段(01-10/11-20/.../71-80)每段活跃度`,
  { label: '数据准备', phase: '数据准备', model: 'haiku' }
);
log('数据就绪');

// ══ Phase 2: 4人并行提名 ══
phase('独立提名');
let picks = await parallel(
  ROLES.map(role => () =>
    agent(
      `## 快乐八选号（选十玩法）\n## 数据\n${dataContext}\n\n作为${role.name}，提名选十10码（01-80升序）。每个号附数据理由。`,
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

  const allReviewsThisRound = [];
  for (let i = 0; i < N; i++) {
    const reviewer = ROLES[i];
    const others = ROLES.map((r, j) => ({ ...r, pick: picks[j] })).filter((_, j) => j !== i);
    const reviewsFromThis = await parallel(
      others.map(target => () =>
        agent(
          `你是${reviewer.name}，提名：${picks[i].numbers.join(' ')}
审核 ${target.name}：${target.pick.numbers.join(' ')}
点评：同意≥2个、反对≥1个、建议替换。引用数据。`,
          { label: `${reviewer.name}→${target.name}`, phase: '对抗验证', agentType: reviewer.agentType, schema: REVIEW_ONE_SCHEMA }
        )
      )
    );
    allReviewsThisRound.push({ reviewer: reviewer.name, reviews: reviewsFromThis.filter(Boolean) });
  }

  const newPicks = [];
  for (let i = 0; i < N; i++) {
    const defender = ROLES[i];
    const reviewsAboutMe = [];
    for (const r of allReviewsThisRound)
      for (const rev of r.reviews)
        if (rev?.target === defender.name) reviewsAboutMe.push({ from: r.reviewer, ...rev });

    const reviewsText = reviewsAboutMe.map(r =>
      `【${r.from}】同意:${r.agree_numbers.join(',')} | 反对:${r.disagree_numbers.join(',')} | ${r.critique}`
    ).join('\n');

    const defense = await agent(
      `你是${defender.name}。当前提名：${picks[i].numbers.join(' ')}
点评：\n${reviewsText}
逐一自证，有道理的接受并调整号码。`,
      { label: `${defender.name}自证`, phase: '对抗验证', agentType: defender.agentType, schema: DEFENSE_SCHEMA }
    );
    if (defense?.new_pick?.numbers) {
      allDebates.push({ round, role: defender.name, defense: defense.defense, concessions: defense.concessions, adjustments: defense.adjustments_made });
      newPicks.push({ numbers: defense.new_pick.numbers, reasoning: picks[i].reasoning });
    } else { newPicks.push(picks[i]); }
  }
  picks = newPicks;

  const allNums = picks.flatMap(p => p.numbers);
  const counts = {}; for (const n of allNums) counts[n] = (counts[n] || 0) + 1;
  const consensus = Object.entries(counts).filter(([, c]) => c >= 3).map(([r]) => r);
  log(`收敛: ${consensus.length}个共识号(≥3票)`);
  if (consensus.length >= CONVERGE_THRESHOLD) { converged = true; log(`✅ 第${round}轮收敛！`); }
}

// ══ Phase 4 ══
phase('首席裁定');
const finalRuling = await agent(
  `你是快乐八选号委员会首席裁判。${round}轮后${converged ? '已收敛' : '未完全收敛'}。
最终方案：${picks.map((p, i) => `${ROLES[i].name}: ${p.numbers.join(' ')}`).join(' | ')}
裁定最终选十10码，标注来源+贡献统计。`,
  { label: '首席裁定', phase: '首席裁定', model: 'opus', effort: 'high' }
);

return { rounds: round, converged, finalPicks: picks.map((p, i) => ({ role: ROLES[i].name, numbers: p.numbers })), debates: allDebates, finalRuling };
