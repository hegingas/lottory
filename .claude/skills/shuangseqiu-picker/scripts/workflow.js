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
const MAX_ROUNDS = 5;
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

  // ── Step A: 全面审核 — 每人审核所有其他4人 ──
  const allReviewsThisRound = [];

  for (let i = 0; i < N; i++) {
    const reviewer = ROLES[i];
    const myPick = picks[i];
    const others = ROLES.map((r, j) => ({ ...r, pick: picks[j] })).filter((_, j) => j !== i);

    const reviewsFromThis = await parallel(
      others.map(target => () =>
        agent(
          `你是${reviewer.name}，你的提名：红球 ${myPick.reds.join(' ')} | 蓝球 ${myPick.blue}

🔥 你要**严厉审核** ${target.name} 的方案：红球 ${target.pick.reds.join(' ')} | 蓝球 ${target.pick.blue}

别客气！把你的专业脾气拿出来。用你的专业视角怼他的方案：
1. 同意哪些号（至少2个）—— 也别光怼，好的要认，用数据说话
2. 反对哪些号（至少1个）—— 狠狠批！为什么不该选？数据哪里不支持？他哪里犯了方法论错误？
3. 建议换成什么号 —— 别光说不练，给出更好的替代方案

⚠️ 不要说"我觉得""可能""大概"——拿数据砸！频率、遗漏、ratio、历史分布，硬数据甩脸上。
🎭 别忘了你的性格！保持人设——该暴躁就暴躁，该嘲讽就嘲讽，该冷笑就冷笑。
📢 用中文口语风格，像真实会议里吵架一样。`,
          { label: `${reviewer.name}→${target.name}`, phase: '对抗验证', agentType: reviewer.agentType, schema: REVIEW_ONE_SCHEMA }
        )
      )
    );

    allReviewsThisRound.push({
      reviewer: reviewer.name,
      reviews: reviewsFromThis.filter(Boolean),
    });
  }

  log(`第${round}轮审核完成：${allReviewsThisRound.reduce((s, r) => s + r.reviews.length, 0)} 条点评`);

  // ── Step B: 自证 — 每人收到所有对自己的点评后自辩/调整 ──
  const newPicks = [];

  for (let i = 0; i < N; i++) {
    const defender = ROLES[i];
    const myPick = picks[i];

    // 收集所有对我的点评
    const reviewsAboutMe = [];
    for (const r of allReviewsThisRound) {
      for (const rev of r.reviews) {
        if (rev && rev.target === defender.name) {
          reviewsAboutMe.push({ from: r.reviewer, ...rev });
        }
      }
    }

    const reviewsText = reviewsAboutMe
      .map(r => `【${r.from}】同意:${r.agree_numbers.join(',')} | 反对:${r.disagree_numbers.join(',')} | 理由:${r.critique} | 建议替换:${r.suggest_replace || '无'}`)
      .join('\n');

    const defense = await agent(
      `你是${defender.name}。你的提名：红球 ${myPick.reds.join(' ')} | 蓝球 ${myPick.blue}

⚔️ 有人对你开火了！以下是所有委员对你方案的点评：
${reviewsText}

现在轮到你反击！完成以下任务：

1. **逐一反击**：每个被反对的号，用数据狠狠怼回去。如果对手说得有道理——大方认。"行，这个我认栽"不丢人；但如果他们胡说八道——拿数据把他们拍到墙上！
2. **决定是否调整**：多个委员同时怼同一个号？认真想想是不是真的选错了。如果坚信自己正确——死保！给出比他们更强的数据支撑。如果有人说得对——改！别死要面子。
3. **输出最终号码**：红球6码升序+蓝球1码

🎭 保持你的人设性格！该暴躁暴躁，该沉稳沉稳，该阴阳怪气就阴阳怪气。
📢 中文口语，像真实吵架一样说话。可以说"离谱""搞笑""你认真的？""数据拍脸上"这种口语。`,
      { label: `${defender.name}自证`, phase: '对抗验证', agentType: defender.agentType, schema: DEFENSE_SCHEMA }
    );

    if (defense) {
      allDebates.push({
        round,
        role: defender.name,
        reviews_received: reviewsAboutMe.map(r => ({ from: r.from, agree: r.agree_numbers, disagree: r.disagree_numbers })),
        defense: defense.defense,
        concessions: defense.concessions,
        adjustments: defense.adjustments_made,
      });

      // 使用调整后的号码（如有）
      if (defense.new_pick && defense.new_pick.reds && defense.new_pick.reds.length === 6) {
        newPicks.push({
          reds: defense.new_pick.reds,
          blue: defense.new_pick.blue,
          reasoning: myPick.reasoning + `\n[第${round}轮调整: ${(defense.adjustments_made || []).join('; ')}]`,
        });
      } else {
        newPicks.push(myPick);
      }
    } else {
      newPicks.push(myPick);
    }
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
    log(`⚠ 已达最大轮次(${MAX_ROUNDS})，强制进入裁定`);
  }
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

const finalRuling = await agent(
  `你是双色球选号委员会的**首席裁判**。经过 ${round} 轮对抗验证后${converged ? '已达成收敛' : '未完全收敛'}，现在由你做最终裁定。

## 最终提名方案
${nominationsText}

## 全部辩论记录
${debatesText}

## 裁定要求
1. 统计每个号码的最终票数（共识号高亮）
2. 综合全部辩论，裁定最终一注（红6+蓝1）
3. 硬约束：至少一组连号 + 与上期重叠1-2个号
4. 每个选定号标注来源（哪位委员的观点被采纳）
5. 贡献统计表
6. 如未收敛，说明你为何在分歧中选择某方观点`,
  { label: '首席裁定', phase: '首席裁定', model: 'opus', effort: 'high' }
);

// ═══════════════════════════════════════
return {
  rounds: round,
  converged,
  finalPicks: picks.map((p, i) => ({ role: ROLES[i].name, reds: p.reds, blue: p.blue })),
  debates: allDebates,
  finalRuling,
};
