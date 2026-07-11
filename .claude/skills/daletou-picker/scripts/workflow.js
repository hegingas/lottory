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

const RULING_SCHEMA = {
  type: 'object',
  properties: {
    final_fronts: { type: 'array', items: { type: 'string' }, description: '最终前区5码升序' },
    final_backs: { type: 'array', items: { type: 'string' }, description: '最终后区2码升序' },
    has_consecutive: { type: 'boolean', description: '前区是否包含至少一组连号' },
    consecutive_pair: { type: 'string', description: '前区连号位置' },
    overlap_count: { type: 'number', description: '前区与上期重叠个数(1-2)' },
    overlap_numbers: { type: 'array', items: { type: 'string' } },
    sources: { type: 'array', items: { type: 'object', properties: { number: { type: 'string' }, from: { type: 'string' }, reason: { type: 'string' } } } },
    contributions: { type: 'array', items: { type: 'object', properties: { role: { type: 'string' }, count: { type: 'number' } } } },
  },
  required: ['final_fronts', 'final_backs', 'has_consecutive', 'consecutive_pair', 'overlap_count', 'overlap_numbers', 'sources', 'contributions'],
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

  // Step A: N×(N-1) 条全并发审核
  const reviewMeta = [], reviewTasks = [];
  for (let i = 0; i < N; i++) {
    for (let j = 0; j < N; j++) {
      if (i === j) continue;
      const reviewer = ROLES[i], target = ROLES[j];
      reviewMeta.push({ reviewerIdx: i, targetIdx: j, reviewerName: reviewer.name, targetName: target.name });
      reviewTasks.push(() =>
        agent(
          `你是${reviewer.name}，你的提名：前区 ${picks[i].fronts.join(' ')} | 后区 ${picks[i].backs.join(' ')}

🔥 严厉审核 ${target.name}：前区 ${picks[j].fronts.join(' ')} | 后区 ${picks[j].backs.join(' ')}

别客气！用你的专业视角狠狠怼他的方案：
1. 同意哪些（≥2个）—— 好的要认，数据说话
2. 反对哪些（≥1个）—— 狠狠批！他的方法论哪里出错了？数据哪里不支持？
3. 建议换成什么号 —— 别光说不练

⚠️ 拿数据砸！频率、遗漏、ratio、历史分布。不准说"我觉得""可能"。
🎭 保持你的人设性格！该暴躁暴躁，该嘲讽嘲讽。
📢 中文口语，像真实会议吵架一样。`,
          { label: `${reviewer.name}→${target.name}`, phase: '对抗验证', agentType: reviewer.agentType, schema: REVIEW_ONE_SCHEMA }
        )
      );
    }
  }
  const allReviewResults = await parallel(reviewTasks);
  log(`审核完成：${allReviewResults.filter(Boolean).length}/${reviewTasks.length} 条`);

  // Step B: N 人全并发自辩
  const reviewsAboutEach = ROLES.map(() => []);
  for (let k = 0; k < reviewMeta.length; k++) {
    const rev = allReviewResults[k];
    if (rev) {
      const { targetName, reviewerName } = reviewMeta[k];
      const idx = ROLES.findIndex(r => r.name === targetName);
      reviewsAboutEach[idx].push({ from: reviewerName, ...rev });
    }
  }
  const defenseTasks = ROLES.map((role, i) => {
    const aboutMe = reviewsAboutEach[i];
    const reviewsText = aboutMe.map(r =>
      `【${r.from}】同意:${r.agree_numbers.join(',')} | 反对:${r.disagree_numbers.join(',')} | 理由:${r.critique} | 建议替换:${r.suggest_replace || '无'}`
    ).join('\n');
    return () => agent(
      `你是${role.name}。你的提名：前区 ${picks[i].fronts.join(' ')} | 后区 ${picks[i].backs.join(' ')}

⚔️ 有人对你开火！所有点评：
${reviewsText}

现在反击：
1. 每个被反对的号，用数据狠狠怼回去。对手有道理就认，胡说八道就拍回去
2. 多人同时怼同一个号？认真想想。坚信自己就死保，数据比他们更强就赢了
3. 输出最终号码

🎭 保持人设！中文口语，像真实吵架。`,
      { label: `${role.name}自证`, phase: '对抗验证', agentType: role.agentType, schema: DEFENSE_SCHEMA }
    );
  });
  const allDefenses = await parallel(defenseTasks);

  const newPicks = [];
  for (let i = 0; i < N; i++) {
    const defense = allDefenses[i];
    if (defense?.new_pick?.fronts) {
      allDebates.push({ round, role: ROLES[i].name, defense: defense.defense, concessions: defense.concessions, adjustments: defense.adjustments_made });
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
const latestDrawInfo = dataContext.match(/最新一期[^:]*[：:]\s*[^0-9]*(\d+)[^0-9]*前区[^0-9]*([\d\s]+)[^0-9]*后区[^0-9]*([\d\s]+)/i) || [];
const latestFronts = latestDrawInfo[2] ? latestDrawInfo[2].trim().split(/\s+/) : [];
const latestBacks = latestDrawInfo[3] ? latestDrawInfo[3].trim().split(/\s+/) : [];

const finalRuling = await agent(
  `你是大乐透选号委员会首席裁判。${round}轮后${converged ? '已收敛' : '未完全收敛'}。

## 最新一期（用于约束校验）
上期前区：${latestFronts.join(' ')}
上期后区：${latestBacks.join(' ')}

## 最终方案
${picks.map((p, i) => `${ROLES[i].name}: 前区 ${p.fronts.join(' ')} + 后区 ${p.backs.join(' ')}`).join(' | ')}
辩论：${allDebates.map(d => `[R${d.round}] ${d.role}: ${d.defense?.slice(0, 100)}`).join('\n')}

## 裁定要求
1. 综合辩论裁定最终一注（前5+后2）
2. ⚠️ 硬约束强制校验（至少满足一个，不满足必须重选）：
   - 前区至少一组连号 或 前区与上期(${latestFronts.join(' ')})重叠1-2个
   - 两者都满足更好，但不能两个都不满足
3. 每个号标注来源+贡献统计`,
  { label: '首席裁定', phase: '首席裁定', model: 'opus', effort: 'high', schema: RULING_SCHEMA }
);

return { rounds: round, converged, finalPicks: picks.map((p, i) => ({ role: ROLES[i].name, fronts: p.fronts, backs: p.backs })), debates: allDebates, finalRuling };
