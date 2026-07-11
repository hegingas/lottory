// 大乐透选号委员会 Workflow
// 五人提名 → 全面对抗验证(循环至收敛) → 首席裁定
export const meta = {
  name: 'dlt-committee-pick',
  description: '大乐透五人委员会选号：全面对抗验证——每人审核所有对手→自证→循环至收敛→首席裁定',
  phases: [
    { title: '数据准备', detail: '读取 dlt_draws.csv 提取数据' },
    { title: '独立提名', detail: '5 Agent 并行分析，各提名前5+后2' },
    { title: '对抗验证', detail: '每人审核所有对手→自证→收敛检查，最多5轮' },
    { title: '首席裁定', detail: '综合裁定最终一注' },
  ],
};

const NOMINATION_SCHEMA = {
  type: 'object',
  properties: {
    fronts: { type: 'array', items: { type: 'string' }, description: '前区5码升序' },
    backs: { type: 'array', items: { type: 'string' }, description: '后区2码升序' },
    reasoning: { type: 'string' },
  },
  required: ['fronts', 'backs', 'reasoning'],
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
    new_pick: { type: 'object', properties: { fronts: { type: 'array', items: { type: 'string' } }, backs: { type: 'array', items: { type: 'string' } } } },
    defense: { type: 'string' },
    concessions: { type: 'string' },
  },
  required: ['role', 'adjustments_made', 'new_pick', 'defense', 'concessions'],
};

const ROLES = [
  { name: '趋势猎手', agentType: 'trend-hunter' },
  { name: '遗漏判官', agentType: 'gap-judge' },
  { name: '结构大师', agentType: 'struct-master' },
  { name: '形态侦探', agentType: 'pattern-spy' },
  { name: '博弈鬼才', agentType: 'game-theorist' },
];
const N = ROLES.length;
const MAX_ROUNDS = 5;
const CONVERGE_THRESHOLD = 3;

// ══ Phase 1: 数据准备 ══
phase('数据准备');
const dataContext = await agent(
  `读取 data/processed/dlt_draws.csv：
1. 全历史期数，最新一期期号 + 开奖号码（前区5码+后区2码）
2. 近50期前区01-35和后区01-12每个号码的频次
3. 每个号码当前遗漏期数
4. 近50期前区奇偶比/大小比(01-17小/18-35大)/和值分布，后区奇偶/大小(01-06小/07-12大)
5. 近50期连号频率`,
  { label: '数据准备', phase: '数据准备', model: 'haiku' }
);
log('数据就绪');

// ══ Phase 2: 5人并行独立提名 ══
phase('独立提名');
let picks = await parallel(
  ROLES.map(role => () =>
    agent(
      `## 大乐透选号\n## 数据背景\n${dataContext}\n\n作为${role.name}，按你的方法论分析数据，提名一注大乐透：前区5码（01-35升序）+后区2码（01-12升序）。每个号附带数据理由。`,
      { label: role.name, phase: '独立提名', agentType: role.agentType, schema: NOMINATION_SCHEMA }
    )
  )
);
picks = picks.filter(Boolean);
log(`提名完成：${picks.length}/5 人`);

// ══ Phase 3: 对抗验证循环 ══
phase('对抗验证');
let round = 0, converged = false;
const allDebates = [];

while (round < MAX_ROUNDS && !converged) {
  round++;
  log(`━━━ 第 ${round} 轮 ━━━`);

  // Step A: 每人审核所有其他4人
  const allReviewsThisRound = [];
  for (let i = 0; i < N; i++) {
    const reviewer = ROLES[i];
    const myPick = picks[i];
    const others = ROLES.map((r, j) => ({ ...r, pick: picks[j] })).filter((_, j) => j !== i);

    const reviewsFromThis = await parallel(
      others.map(target => () =>
        agent(
          `你是${reviewer.name}，你的提名：前区 ${myPick.fronts.join(' ')} | 后区 ${myPick.backs.join(' ')}
审核 ${target.name}：前区 ${target.pick.fronts.join(' ')} | 后区 ${target.pick.backs.join(' ')}
从你的专业视角点评：同意哪些（≥2个）、反对哪些（≥1个）、建议替换什么。必须引用数据。`,
          { label: `${reviewer.name}→${target.name}`, phase: '对抗验证', agentType: reviewer.agentType, schema: REVIEW_ONE_SCHEMA }
        )
      )
    );
    allReviewsThisRound.push({ reviewer: reviewer.name, reviews: reviewsFromThis.filter(Boolean) });
  }
  log(`审核完成：${allReviewsThisRound.reduce((s, r) => s + r.reviews.length, 0)} 条点评`);

  // Step B: 自证
  const newPicks = [];
  for (let i = 0; i < N; i++) {
    const defender = ROLES[i];
    const reviewsAboutMe = [];
    for (const r of allReviewsThisRound)
      for (const rev of r.reviews)
        if (rev && rev.target === defender.name)
          reviewsAboutMe.push({ from: r.reviewer, ...rev });

    const reviewsText = reviewsAboutMe.map(r =>
      `【${r.from}】同意:${r.agree_numbers.join(',')} | 反对:${r.disagree_numbers.join(',')} | 理由:${r.critique} | 建议替换:${r.suggest_replace || '无'}`
    ).join('\n');

    const defense = await agent(
      `你是${defender.name}。当前提名：前区 ${picks[i].fronts.join(' ')} | 后区 ${picks[i].backs.join(' ')}
所有点评：\n${reviewsText}
逐一自证每个被反对的号，接受有道理的反对并调整号码。`,
      { label: `${defender.name}自证`, phase: '对抗验证', agentType: defender.agentType, schema: DEFENSE_SCHEMA }
    );

    if (defense?.new_pick?.fronts) {
      allDebates.push({ round, role: defender.name, defense: defense.defense, concessions: defense.concessions, adjustments: defense.adjustments_made });
      newPicks.push({ fronts: defense.new_pick.fronts, backs: defense.new_pick.backs, reasoning: picks[i].reasoning });
    } else {
      newPicks.push(picks[i]);
    }
  }
  picks = newPicks;

  // Step C: 收敛检查
  const allFronts = picks.flatMap(p => p.fronts);
  const frontCounts = {}; for (const f of allFronts) frontCounts[f] = (frontCounts[f] || 0) + 1;
  const consensusFronts = Object.entries(frontCounts).filter(([, c]) => c >= 3).map(([r]) => r);
  const allBacks = picks.flatMap(p => p.backs);
  const backCounts = {}; for (const b of allBacks) backCounts[b] = (backCounts[b] || 0) + 1;
  const topBack = Object.entries(backCounts).sort((a, b) => b[1] - a[1])[0];

  log(`收敛: ${consensusFronts.length}前区共识(≥3票), 后区 ${topBack[0]}(${topBack[1]}票)`);
  if (consensusFronts.length >= CONVERGE_THRESHOLD && topBack[1] >= 3) { converged = true; log(`✅ 第${round}轮收敛！`); }
}

// ══ Phase 4: 首席裁定 ══
phase('首席裁定');
const finalRuling = await agent(
  `你是大乐透选号委员会首席裁判。经过 ${round} 轮对抗${converged ? '已收敛' : '未完全收敛'}。
最终方案：${picks.map((p, i) => `${ROLES[i].name}: 前区 ${p.fronts.join(' ')} + 后区 ${p.backs.join(' ')}`).join(' | ')}
辩论：${allDebates.map(d => `[R${d.round}] ${d.role}: ${d.defense?.slice(0, 100)}`).join('\n')}
裁定最终一注（前5+后2），硬约束：至少一组前区连号 + 与上期重叠1-2号。标注来源+贡献统计。`,
  { label: '首席裁定', phase: '首席裁定', model: 'opus', effort: 'high' }
);

return { rounds: round, converged, finalPicks: picks.map((p, i) => ({ role: ROLES[i].name, fronts: p.fronts, backs: p.backs })), debates: allDebates, finalRuling };
