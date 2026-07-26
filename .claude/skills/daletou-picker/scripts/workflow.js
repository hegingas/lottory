// 大乐透三层漏斗 + 对抗验证 · 2798期全量回测验证
// 🏗️结构 → 🔍形态 → 🎯精选 → ⚔️5人审查 → 🗣️漏斗自辩 → 👑终裁  (深冻/热冷均无效，跳过预筛选)
export const meta = {
  name: 'dlt-funnel-pick',
  description: '大乐透三层漏斗+对抗验证+自辩：结构→形态→精选→5人审查→漏斗自辩→终裁(深冻误杀13.8%已跳过)',
  phases: [{title:'数据准备'},{title:'三层漏斗'},{title:'对抗验证'},{title:'漏斗自辩'},{title:'终裁'}],
};

phase('数据准备');
const data = await agent(
  `用 Bash 读取 data/processed/dlt_draws.csv，输出：
1. 最新一期期号+开奖号码(前5+后2)，上上期，近10期明细
2. 频率遗漏：前区01-35+后区01-12 近10期/近50期次数，当前遗漏，历史最大遗漏
3. 结构(近50期)：前区奇偶比/大小比(01-17小18-35大)分布、和值均值±1σ、012路比、质数个数(2,3,5,7,11,13,17,19,23,29,31)分布；后区奇偶/大小(01-06小07-12大)分布
4. 形态(近50期)：前区连号组数分布、重号个数分布、同尾组数、跨度、三区间(01-12/13-24/25-35)分布；后区与上期重叠个数
5. 前区伴随对Top5、后区组合模式`,
  {label:'数据准备',phase:'数据准备',model:'haiku'}
);
log('统计就绪');

phase('三层漏斗');
const pick = await agent(
  `你是大乐透选号专家。按三层漏斗过滤。前区01-35选5，后区01-12选2，大小分界前区01-17/18-35，后区01-06/07-12。

📊 回测验证(2800期)：深冻误杀13.8%❌跳过 | 热/冷区分度1.2%❌跳过 | 奇偶Top2:3:2(35%)+2:3(33%)=68%✅ | 大小Top2:3:2(35%)+2:3(34%)=68%✅ | 和值μ=87 σ=22,1σ[65-109]覆盖69%✅ | 连号50%⚠️(分布:0连50% 1连38% 2连10% 3连3%) | 重号1-2个52%✅(分布:0个46% 1个36% 2个16%)

---
${data}
---

# 🏗️ 第1层：结构框架

锁定本期硬约束：

| 维度 | 锁定 |
|------|------|
| 前区奇偶比 | 3:2(35%)或2:3(33%)——Top2覆盖68% |
| 前区大小比 | 3:2(35%)或2:3(34%)——Top2覆盖68% |
| 前区和值 | 65-109(μ=87 σ=22) |
| 前区012路 | 每路≥1，单路≤3 |
| 前区质数 | 1-3个 |
| 后区 | 奇偶+大小参考近50期最高频模式 |

\`\`\`
🏗️ 结构 | 锁定：奇偶=X:X或X:X 大小=X:X或X:X 和值=65-108
框架淘汰：XX(原因) | 晋级前区(N个)：XX... | 晋级后区(N个)：XX...
\`\`\`

---

# 🔍 第2层：形态约束

| 形态 | 判定 |
|------|------|
| 连号 | 50%概率，近5期节奏判定 |
| 重号 | 52%概率1-2个 |
| 同尾 | ≤2组 |
| 区间 | 三区间≥2区 |
| 跨度 | 近50期均值±5 |
| 后区 | 与上期重叠≤1个(硬约束) |

\`\`\`
🔍 形态 | 连号预期：[有/无] | 重号预期：[0/1/2]个
形态淘汰：XX(原因) | 晋级前区(N个)：XX... | 晋级后区(N个)：XX...
\`\`\`

---

# 🎯 第3层：精选输出

**定胆→组合→博弈微调→终检**

硬约束：前区连号∨重号1-2 | 后区与上期重叠≤1 | 不重历史

\`\`\`
🎯 精选

【复式】前区(10-12码)：XX XX...（升序） 后区(3-4码)：XX XX...（升序）
胆码：XX(理由)

【或3注单式】
①前 XX XX XX XX XX + 后 XX XX  ②前 XX XX XX XX XX + 后 XX XX  ③前 XX XX XX XX XX + 后 XX XX

【校验】连号✅/❌ 重号✅X个 后区重叠≤1✅ 奇偶X:X 大小X:X 和值≈XX
【理由】1-2句话

⚠️ 大乐透为独立随机游戏，历史统计不构成开奖保证。理性购彩，娱乐为主。
\`\`\``,
  {label:'三层漏斗选号',phase:'三层漏斗'}
);
log('漏斗产出就绪');

// ⚔️ 对抗验证 · 收敛循环（最多3轮 review+rebuttal）
const AGENTS = ['trend-hunter','gap-judge','struct-master','pattern-spy','game-theorist'];
const MAX_ROUNDS = 3;
let allReviews = [];
let currentPick = pick;
let converged = false;

for (let round = 1; round <= MAX_ROUNDS && !converged; round++) {
  phase(`对抗验证-R${round}`);
  const roundReviews = await parallel(
    AGENTS.map(a => () => agent(
      `你是选号审查委员会的**${a}**。审查以下大乐透漏斗产出${round>1?'（第'+round+'轮，聚焦未解决争议）':''}。
CSV路径: data/processed/dlt_draws.csv（如需具体数据请自行读取）
${round>1?'⚠️ 聚焦上一轮未解决的核心争议。':''}
漏斗当前产出：${currentPick}
${round>1?'\n历史辩论摘要：\n'+allReviews.slice(-3).map(r=>`[R${r.round}${r.type}] ${r.content.slice(0,400)}`).join('\n'):''}
请从你的专业视角审查，指出问题并给改进建议。${round>1?'只关注未充分回应的核心争议。':''}`,
      {agentType: a, label: `${a}审查-R${round}`, phase: `对抗验证-R${round}`}
    ))
  );
  const validR = roundReviews.filter(Boolean);
  validR.forEach(r => allReviews.push({round, type:'审查', content: r}));
  log(`R${round}: ${validR.length}/${AGENTS.length} 审查完成`);

  phase(`漏斗自辩-R${round}`);
  const rebuttalR = await agent(
    `你是大乐透漏斗选号专家。第${round}轮审查意见如下，请逐条自辩：
当前产出：${currentPick}
审查意见（R${round}）：${validR.map((r,i)=>`【${AGENTS[i]}】\n${r}`).join('\n\n')}
${round>1?'\n历史辩论：\n'+allReviews.filter(r=>r.round<round).map(r=>r.content.slice(0,300)).join('\n...\n'):''}
规则：有道理→认栽调整, 不合理→用数据反驳, 调整→输出修正版, 争议全部解决→开头写【CONVERGED】`,
    {label:`漏斗自辩-R${round}`, phase:`漏斗自辩-R${round}`}
  );
  allReviews.push({round, type:'自辩', content: rebuttalR});
  currentPick = rebuttalR;
  log(`R${round}: 漏斗已自辩`);

  if (round < MAX_ROUNDS) {
    const check = await agent(
      `检查第${round}轮是否已收敛。看自辩是否标注【CONVERGED】，核心反对是否已被充分回应。
辩论记录：${allReviews.slice(-3).map(r=>`[${r.type}-R${r.round}] ${r.content.slice(0,500)}`).join('\n---\n')}
只输出：CONVERGED 或 NEED_NEXT_ROUND`,
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
─── 全部辩论 ─── ${allReviews.map(r=>`[${r.type}-R${r.round}] ${r.content.slice(0,600)}`).join('\n---\n')}
裁决规则：1.漏斗最后认栽→采纳修正版 2.有理反驳未被再追击→驳回审查 3.结构硬伤→必须修正 4.维持原格式
输出最终号码+裁决依据。⚠️ 大乐透为独立随机游戏，理性购彩。`,
  {label:'首席裁定',phase:'终裁',model:'sonnet'}
);

log('✅ 完成');
return {funnelResult:pick, allReviews, final, phases:['结构','形态','精选','对抗验证-收敛循环','终裁']};
