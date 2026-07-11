// 双色球选号委员会 Workflow
// 五人提名 → 全面对抗验证(循环至收敛) → 首席裁定
export const meta = {
  name: 'ssq-committee-pick',
  description: '双色球五人委员会选号：全面对抗验证——每人审核所有对手+收到点评后自证+循环至收敛+首席裁定',
  phases: [
    { title: '数据准备', detail: '读取 ssq_draws.csv 提取上期+近50期数据' },
    { title: '独立提名', detail: '5 个 Agent 并行分析，各自提名一注' },
    { title: '对抗验证', detail: '每人审核所有对手→自证→收敛检查，最多3轮' },
    { title: '首席裁定', detail: '综合全部提名+辩论记录，裁定最终一注' },
  ],
};

// ═══════════════════════════════════════
// Schema 定义
// ═══════════════════════════════════════

const NOMINATION_SCHEMA = {
  type: 'object',
  properties: {
    reds: { type: 'array', items: { type: 'string' }, description: '红球6码升序' },
    blue: { type: 'string', description: '蓝球1码' },
    reasoning: { type: 'string', description: '每个号的数据支撑理由' },
  },
  required: ['reds', 'blue', 'reasoning'],
};

// 一人点评另一人
const REVIEW_ONE_SCHEMA = {
  type: 'object',
  properties: {
    target: { type: 'string', description: '被点评的委员名' },
    agree_numbers: { type: 'array', items: { type: 'string' }, description: '同意的号码（至少2个）' },
    disagree_numbers: { type: 'array', items: { type: 'string' }, description: '反对的号码（至少1个）' },
    critique: { type: 'string', description: '反对理由，引用数据' },
    suggest_replace: { type: 'string', description: '如果要替换，建议换成什么号' },
  },
  required: ['target', 'agree_numbers', 'disagree_numbers', 'critique'],
};

// 一人收到所有对自己的点评后的自证
const DEFENSE_SCHEMA = {
  type: 'object',
  properties: {
    role: { type: 'string', description: '委员名' },
    current_pick: { type: 'object', properties: { reds: { type: 'array', items: { type: 'string' } }, blue: { type: 'string' } } },
    adjustments_made: { type: 'array', items: { type: 'string' }, description: '本轮调整了哪些号（如有）' },
    new_pick: { type: 'object', properties: { reds: { type: 'array', items: { type: 'string' } }, blue: { type: 'string' } }, description: '调整后的号码（如无调整则与current_pick相同）' },
    defense: { type: 'string', description: '对每个被反对的号逐一自证，用数据说话' },
    concessions: { type: 'string', description: '承认哪些反对有理，为什么接受调整' },
  },
  required: ['role', 'current_pick', 'adjustments_made', 'new_pick', 'defense', 'concessions'],
};

// ═══════════════════════════════════════
// 五人角色
// ═══════════════════════════════════════
const ROLES = [
  { name: '趋势猎手', agentType: 'trend-hunter' },
  { name: '遗漏判官', agentType: 'gap-judge' },
  { name: '结构大师', agentType: 'struct-master' },
  { name: '形态侦探', agentType: 'pattern-spy' },
  { name: '博弈鬼才', agentType: 'game-theorist' },
];
const N = ROLES.length;
const MAX_ROUNDS = 1;
const CONVERGE_THRESHOLD = 3; // 至少3个红球被3+人同意才算收敛

// ═══════════════════════════════════════
// Phase 1: 数据准备
// ═══════════════════════════════════════
phase('数据准备');

const dataContext = await agent(
  `读取 data/processed/ssq_draws.csv：
1. 全历史期数，最新一期期号 + 开奖号码（红球+蓝球）
2. 近50期每个红球01-33和蓝球01-16的出现频次
3. 每个号码的当前遗漏期数
4. 近50期奇偶比分布、大小比分布(01-16小/17-33大)、和值均值+范围
5. 近50期连号出现频率

返回结构化摘要。`,
  { label: '数据准备', phase: '数据准备', model: 'haiku' }
);
log(`数据就绪`);

// ═══════════════════════════════════════
// Phase 2: 五人并行独立提名
// ═══════════════════════════════════════
phase('独立提名');

let picks = await parallel(
  ROLES.map(role => () =>
    agent(
      `## 数据背景\n${dataContext}\n\n## 任务\n作为${role.name}，按你的专属方法论独立分析数据，提名一注双色球（红球6码升序+蓝球1码）。每个号必须附带数据理由。`,
      { label: role.name, phase: '独立提名', agentType: role.agentType, schema: NOMINATION_SCHEMA }
    )
  )
);
picks = picks.filter(Boolean);
log(`提名完成：${picks.length}/5 人提交`);

// ═══════════════════════════════════════
// Phase 3: 对抗验证循环
// ═══════════════════════════════════════
phase('对抗验证');

let round = 0;
let converged = false;
const allDebates = []; // 累积所有轮次的辩论记录

while (round < MAX_ROUNDS && !converged) {
  round++;
  log(`━━━ 第 ${round} 轮对抗验证 ━━━`);

  // ── Step A: 全面审核 — N×(N-1) 条全并发 ──
  const reviewMeta = []; // [{reviewerIdx, targetIdx, reviewerName, targetName}]
  const reviewTasks = [];
  for (let i = 0; i < N; i++) {
    for (let j = 0; j < N; j++) {
      if (i === j) continue;
      const reviewer = ROLES[i], target = ROLES[j];
      reviewMeta.push({ reviewerIdx: i, targetIdx: j, reviewerName: reviewer.name, targetName: target.name });
      reviewTasks.push(() =>
        agent(
          `你是${reviewer.name}，你的提名：红球 ${picks[i].reds.join(' ')} | 蓝球 ${picks[i].blue}

🔥 你要**严厉审核** ${target.name} 的方案：红球 ${picks[j].reds.join(' ')} | 蓝球 ${picks[j].blue}

别客气！把你的专业脾气拿出来。用你的专业视角怼他的方案：
1. 同意哪些号（至少2个）—— 也别光怼，好的要认，用数据说话
2. 反对哪些号（至少1个）—— 狠狠批！为什么不该选？数据哪里不支持？他哪里犯了方法论错误？
3. 建议换成什么号 —— 别光说不练，给出更好的替代方案

⚠️ 不要说"我觉得""可能""大概"——拿数据砸！频率、遗漏、ratio、历史分布，硬数据甩脸上。
🎭 别忘了你的性格！保持人设——该暴躁就暴躁，该嘲讽就嘲讽，该冷笑就冷笑。
📢 用中文口语风格，像真实会议里吵架一样。`,
          { label: `${reviewer.name}→${target.name}`, phase: '对抗验证', agentType: reviewer.agentType, schema: REVIEW_ONE_SCHEMA }
        )
      );
    }
  }
  const allReviewResults = await parallel(reviewTasks);
  log(`第${round}轮审核完成：${allReviewResults.filter(Boolean).length}/${reviewTasks.length} 条`);

  // ── Step B: 自证 — N 人全并发自辩 ──
  // 按人汇总点评（从 reviewMeta + allReviewResults 重建）
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
    const reviewsText = aboutMe
      .map(r => `【${r.from}】同意:${r.agree_numbers.join(',')} | 反对:${r.disagree_numbers.join(',')} | 理由:${r.critique} | 建议替换:${r.suggest_replace || '无'}`)
      .join('\n');
    return () => agent(
      `你是${role.name}。你的提名：红球 ${picks[i].reds.join(' ')} | 蓝球 ${picks[i].blue}

⚔️ 有人对你开火了！以下是所有委员对你方案的点评：
${reviewsText}

现在轮到你反击！完成以下任务：

1. **逐一反击**：每个被反对的号，用数据狠狠怼回去。如果对手说得有道理——大方认。"行，这个我认栽"不丢人；但如果他们胡说八道——拿数据把他们拍到墙上！
2. **决定是否调整**：多个委员同时怼同一个号？认真想想是不是真的选错了。如果坚信自己正确——死保！给出比他们更强的数据支撑。如果有人说得对——改！别死要面子。
3. **输出最终号码**：红球6码升序+蓝球1码

🎭 保持你的人设性格！该暴躁暴躁，该沉稳沉稳，该阴阳怪气就阴阳怪气。
📢 中文口语，像真实吵架一样说话。可以说"离谱""搞笑""你认真的？""数据拍脸上"这种口语。`,
      { label: `${role.name}自证`, phase: '对抗验证', agentType: role.agentType, schema: DEFENSE_SCHEMA }
    );
  });
  const allDefenses = await parallel(defenseTasks);

  const newPicks = [];
  for (let i = 0; i < N; i++) {
    const defense = allDefenses[i], myPick = picks[i], aboutMe = reviewsAboutEach[i];
    if (defense) {
      allDebates.push({
        round, role: ROLES[i].name,
        reviews_received: aboutMe.map(r => ({ from: r.from, agree: r.agree_numbers, disagree: r.disagree_numbers })),
        defense: defense.defense, concessions: defense.concessions, adjustments: defense.adjustments_made,
      });
      if (defense.new_pick && defense.new_pick.reds && defense.new_pick.reds.length === 6) {
        newPicks.push({ reds: defense.new_pick.reds, blue: defense.new_pick.blue,
          reasoning: myPick.reasoning + `\n[第${round}轮调整: ${(defense.adjustments_made || []).join('; ')}]` });
      } else { newPicks.push(myPick); }
    } else { newPicks.push(myPick); }
  }

  picks = newPicks;
  log(`第${round}轮自证完成`);

  // ── Step C: 检查收敛 ──
  // 收敛条件：至少 CONVERGE_THRESHOLD 个红球被3+人同时选中
  const allReds = picks.flatMap(p => p.reds);
  const redCounts = {};
  for (const r of allReds) {
    redCounts[r] = (redCounts[r] || 0) + 1;
  }
  const consensusReds = Object.entries(redCounts)
    .filter(([, c]) => c >= 3)
    .map(([r]) => r);

  // 蓝球收敛
  const allBlues = picks.map(p => p.blue);
  const blueCounts = {};
  for (const b of allBlues) {
    blueCounts[b] = (blueCounts[b] || 0) + 1;
  }
  const topBlue = Object.entries(blueCounts).sort((a, b) => b[1] - a[1])[0];

  log(`收敛状态: ${consensusReds.length}个红球共识(≥3票), 蓝球共识 ${topBlue[0]}(${topBlue[1]}票)`);

  if (consensusReds.length >= CONVERGE_THRESHOLD && topBlue[1] >= 3) {
    converged = true;
    log(`✅ 第${round}轮达成收敛！`);
  } else if (round >= MAX_ROUNDS) {
    log(`⚠ 已达最大轮次(${MAX_ROUNDS})，未收敛，启动兜底机制`);
  }
}

// ═══════════════════════════════════════
// Phase 3.5: 未收敛兜底 — B(加权投票) + D(最终陈述)
// ═══════════════════════════════════════
let weightedScores = [];
let finalStatements = [];

if (!converged) {
  phase('未收敛兜底');

  // ── B: 加权投票 ──
  // 权重 = 该委员的号码中有多少个是共识号(≥3票)
  const allReds2 = picks.flatMap(p => p.reds);
  const rc = {}; for (const r of allReds2) rc[r] = (rc[r] || 0) + 1;
  const consensusSet = new Set(Object.entries(rc).filter(([,c]) => c >= 3).map(([r]) => r));

  weightedScores = ROLES.map((role, i) => {
    const score = picks[i].reds.filter(r => consensusSet.has(r)).length;
    const blueVotes = picks.filter(p => p.blue === picks[i].blue).length;
    return { role: role.name, consensusHits: score, blueVotes, weight: score * 0.7 + blueVotes * 0.3 };
  });
  weightedScores.sort((a, b) => b.weight - a.weight);
  log(`权重排名: ${weightedScores.map(w => `${w.role}(${w.weight.toFixed(1)})`).join(' > ')}`);

  // ── D: 最终陈述 ──
  const otherPicks = picks.map((p, i) => `${ROLES[i].name}: 红球 ${p.reds.join(' ')} | 蓝球 ${p.blue}`).join('\n');
  finalStatements = await parallel(
    ROLES.map((role, i) => () =>
      agent(
        `你是${role.name}。经过 ${round} 轮对抗仍未达成一致。现在是最后机会！

## 所有委员最终方案
${otherPicks}

## 你的方案
红球 ${picks[i].reds.join(' ')} | 蓝球 ${picks[i].blue}

## 共识号（≥3票）
${[...consensusSet].join(', ') || '无'}

## 你的权重得分
共识命中: ${weightedScores.find(w=>w.role===role.name)?.consensusHits || 0}个 | 蓝球票数: ${weightedScores.find(w=>w.role===role.name)?.blueVotes || 0}

## 任务
这是你最后一次说服首席的机会！请做最终陈述：
1. 为什么你的方案比其他人的更好？用数据说话，不要谦虚
2. 你的方案中哪些号是共识号（权重加分项），哪些是独到之见（别人没看到的价值）
3. 如果首席要在你的方案和权重最高的方案之间抉择，为什么应该选你的

🔥 全力以赴！这是 final pitch，不许留余力！保持人设！`,
        { label: `${role.name}最终陈述`, phase: '未收敛兜底', agentType: role.agentType }
      )
    )
  );
  log('最终陈述完成');
}

// ═══════════════════════════════════════
// Phase 4: 首席裁定
// ═══════════════════════════════════════
phase('首席裁定');

const nominationsText = picks
  .map((p, i) => `${ROLES[i].name}: 红球 ${p.reds.join(' ')} | 蓝球 ${p.blue}`)
  .join('\n');

const debatesText = allDebates
  .map(d => `[第${d.round}轮] ${d.role}: 被${d.reviews_received.length}人点评 | 自辩: ${d.defense?.slice(0, 150)} | 让步: ${d.concessions?.slice(0, 100)} | 调整: ${d.adjustments?.join(',') || '无'}`)
  .join('\n');

const weightText = converged ? '' : `
## 加权投票排名（共识命中数×0.7 + 蓝球票数×0.3）
${weightedScores.map((w,i) => `${i+1}. ${w.role}: 共识命中${w.consensusHits}个 蓝球${w.blueVotes}票 综合权重${w.weight.toFixed(1)}`).join('\n')}
`;

const statementText = converged ? '' : `
## 委员最终陈述
${finalStatements.filter(Boolean).map((s,i) => `### ${ROLES[i].name}\n${s?.slice(0, 300)}`).join('\n\n')}
`;

const finalRuling = await agent(
  `你是双色球选号委员会的**首席裁判**。经过 ${round} 轮对抗验证后${converged ? '已达成收敛✅' : '未收敛⚠️，以下为兜底数据'}。

## 最终提名方案
${nominationsText}
${weightText}
${statementText}

## 全部辩论记录
${debatesText}

## 裁定要求
1. 统计每个号码的最终票数（共识号高亮）
2. ${converged ? '基于共识裁定' : '⚠️ 未收敛！综合权重排名+最终陈述+辩论记录，强制裁定'}最终一注（红6+蓝1）
3. 硬约束（至少满足一个）：一组连号 或 与上期重叠1-2个号
4. 每个选定号标注来源+权重数据支撑
5. 贡献统计表`,
  { label: '首席裁定', phase: '首席裁定', model: 'opus', effort: 'high' }
);

// ═══════════════════════════════════════
return {
  // 最重要的：首席最终裁定
  ruling: finalRuling,
  // 元信息
  rounds, converged,
  // 详细信息（可选查看）
  finalPicks: picks.map((p, i) => ({ role: ROLES[i].name, reds: p.reds, blue: p.blue })),
  debates: allDebates,
};
