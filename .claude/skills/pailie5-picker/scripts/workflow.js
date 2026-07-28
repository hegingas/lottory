// 排列5三层漏斗 + 对抗验证 · 7558期全量回测验证
// 🏗️按位结构 → 🔍跨位形态 → 🎯精选 → ⚔️4人审查 → 🗣️漏斗自辩 → 👑终裁
export const meta = {
  name: 'pl5-funnel-pick',
  description: '排列5三层漏斗+对抗验证+自辩：按位结构→跨位形态→精选→4人审查→漏斗自辩→终裁(深冻>0.99安全)',
  phases: [{title:'数据准备'},{title:'三层漏斗'},{title:'对抗验证'},{title:'漏斗自辩'},{title:'终裁'}],
};

phase('数据准备');
const data = await agent(
  `用 Bash 读取 data/processed/pl5_draws.csv，按位独立统计(d1只算d1,d2只算d2...)：
1. 最新一期期号+5位数字，上上期，近10期明细
2. 每位0-9在近10期/近50期出现次数，当前遗漏，历史最大遗漏
   标注"深冻"(遗漏>历史最大×0.99)
3. 每位奇偶比/大小比(0-4小5-9大)分布
4. 跨位形态(近50期)：重复数字频率、顺子模式频率、跨度分布、012路分布`,
  {label:'数据准备',phase:'数据准备',model:'haiku'}
);
log('统计就绪');

phase('三层漏斗');
const pick = await agent(
  `你是排列5选号专家。按三层漏斗过滤。**d1只跟d1历史比，d2只跟d2比...每位独立！**

每位0-9独立，允许跨位重复。大小0-4小/5-9大。

📊 回测(7558期)：深冻>0.99误杀0%✅ | 按位独立分析

---
${data}
---

# 🏗️ 第1层：按位结构

**排除：** 每位遗漏 > 该位历史最大×0.99 → 排除

**每位锁定：** 奇偶倾向、大小倾向（基于该位近50期分布）

**全局：** 全5位不火5奇/全偶/全大/全小

\`\`\`
🏗️ 按位结构
d1：排除X(深冻) → 奇/偶=X 大小=X → 候选X X X X X
d2-d5：(同样格式)
全局约束：奇偶≠0:5/5:0 大小≠0:5/5:0
\`\`\`

---

# 🔍 第2层：跨位形态

| 检查项 | 约束 |
|------|------|
| 重复模式 | 近10期重复频率→判定本期可能/无位置重复 |
| 顺子/对称 | 避免≥3位连续递增或对称模式 |
| 跨度 | 全5位max-min宜3-8 |
| 012路 | 不能某路完全缺失 |
| 历史去重 | 不与近10期完全重复 |

\`\`\`
🔍 跨位形态 | 重复预期：[可能/不太可能]
跨位淘汰：dX=X(顺子风险) | d1核心：X X X | d2核心：X X X | ... | d5核心：X X X
\`\`\`

---

# 🎯 第3层：精选输出

**每位定数字→跨位协调→博弈微调→校验**

\`\`\`
🎯 精选

【5位数字】d1=X d2=X d3=X d4=X d5=X  即 X X X X X

【每位理由】d1=X(趋势+遗漏+结构) d2=X...

【校验】奇偶X:X✅ 大小X:X✅ 跨度X✅

⚠️ 排列5为独立随机游戏，历史统计不构成开奖保证。理性购彩。
\`\`\``,
  {label:'三层漏斗选号',phase:'三层漏斗'}
);
log('漏斗产出就绪');

// ⚔️ 对抗验证 · 收敛循环（最多3轮 review+rebuttal）
const AGENTS = ['trend-hunter','gap-judge','struct-master','game-theorist'];
const MAX_ROUNDS = 3;
let allReviews = [];
let currentPick = pick;
let converged = false;

for (let round = 1; round <= MAX_ROUNDS && !converged; round++) {
  phase(`对抗验证-R${round}`);
  const roundReviews = await parallel(
    AGENTS.map(a => () => agent(
      `你是选号审查委员会的**${a}**。审查以下排列5漏斗产出${round>1?'（第'+round+'轮，聚焦未解决争议）':''}。
CSV路径: data/processed/pl5_draws.csv（如需具体数据请自行读取）
${round>1?'⚠️ 聚焦上一轮未解决的核心争议。':''}
漏斗当前产出：${currentPick}
${round>1?'\n历史辩论摘要：\n'+allReviews.slice(-3).map(r=>`[R${r.round}${r.type}] ${r.content.slice(0,2000)}`).join('\n'):''}
请从你的专业视角审查，指出问题并给改进建议。${round>1?'只关注未充分回应的核心争议。':''}`,
      {agentType: a, label: `${a}审查-R${round}`, phase: `对抗验证-R${round}`}
    ))
  );
  const validR = roundReviews.filter(Boolean);
  validR.forEach(r => allReviews.push({round, type:'审查', content: r}));
  log(`R${round}: ${validR.length}/${AGENTS.length} 审查完成`);

  phase(`漏斗自辩-R${round}`);
  const rebuttalR = await agent(
    `你是排列5漏斗选号专家。第${round}轮审查意见如下，请逐条自辩：
当前产出：${currentPick}
审查意见（R${round}）：${validR.map((r,i)=>`【${AGENTS[i]}】\n${r}`).join('\n\n')}
${round>1?'\n历史辩论：\n'+allReviews.filter(r=>r.round<round).map(r=>r.content.slice(0,3000)).join('\n...\n'):''}
规则：有道理→认栽调整, 不合理→用数据反驳, 调整→输出修正版, 争议全部解决→开头写【CONVERGED】`,
    {label:`漏斗自辩-R${round}`, phase:`漏斗自辩-R${round}`}
  );
  allReviews.push({round, type:'自辩', content: rebuttalR});
  currentPick = rebuttalR;
  log(`R${round}: 漏斗已自辩`);

  if (round < MAX_ROUNDS) {
    const check = await agent(
      `检查第${round}轮是否已收敛。只输出：CONVERGED 或 NEED_NEXT_ROUND`,
      {label:`收敛检查-R${round}`, phase:'收敛检查', model:'haiku'}
    );
    if (check.toUpperCase().includes('CONVERGED') && !check.toUpperCase().includes('NEED_NEXT_ROUND')) {
      converged = true; log(`✅ R${round} 已收敛`);
    } else { log(`🔄 R${round} 未收敛，进入R${round+1}`); }
  }
}

phase('终裁');
const final = await agent(
  `你是首席裁判。综合${allReviews.filter(r=>r.type==='审查').length}轮辩论，输出最终推荐号码。
─── 漏斗原始产出 ─── ${pick}
─── 全部辩论 ─── ${allReviews.map(r=>`[${r.type}-R${r.round}] ${r.content.slice(0,4000)}`).join('\n---\n')}
裁决规则：1.漏斗最后认栽→采纳修正版 2.有理反驳未被再追击→驳回审查 3.结构硬伤→必须修正 4.维持原格式
输出最终号码+裁决依据。⚠️ 排列5为独立随机游戏，理性购彩。`,
  {label:'首席裁定',phase:'终裁',model:'sonnet'}
);

phase('存档');
await agent(
  `用 Bash 完成：
1. 读 data/processed/pl5_draws.csv 最后一行拿最新期号，算下一期(+1)
2. 从终裁输出提取：5位数字(即主推号)、核心逻辑
3. 调用 python scripts/_archive_prediction.py pl5 '{"period_id":"...","s1":"X X X X X","s2":"X X X X X","s3":"X X X X X","notes":"..."}' 归档

终裁输出：
${final}

号码空格分隔，notes保留核心逻辑(≤100字)。只输出归档结果。`,
  {label:'预测存档',phase:'存档',model:'haiku'}
);
log('✅ 完成');
return {funnelResult:pick, allReviews, final, phases:['按位结构','跨位形态','精选','对抗验证-收敛循环','终裁','存档']};
