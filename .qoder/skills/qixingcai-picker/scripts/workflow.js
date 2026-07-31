// 七星彩四层漏斗 + 对抗验证 · 769期全量回测验证
// 🔪预筛选(深冻0.97) → 🏗️按位结构 → 🔍跨位形态 → 🎯精选 → ⚔️4人审查 → 🗣️漏斗自辩 → 👑终裁
export const meta = {
  name: 'qxc-funnel-pick',
  description: '七星彩四层漏斗+对抗验证+自辩：预筛选→按位结构→跨位形态→精选→4人审查→漏斗自辩→终裁',
  phases: [{title:'数据准备'},{title:'四层漏斗'},{title:'对抗验证'},{title:'漏斗自辩'},{title:'终裁'}],
};

const text = (v) => { if (!v) return ''; if (typeof v === 'string') return v; if (typeof v.content === 'string') return v.content; return JSON.stringify(v); };

phase('数据准备');
const data = text(await agent(
  `用 Bash 读取 data/processed/qxc_draws.csv，按位独立统计：
1. 最新一期期号+前区d1-d6+后区special，上上期，近10期明细
2. 前区每位0-9+后区0-14在近10期/近50期出现次数，当前遗漏，历史最大遗漏
   标注"深冻"(遗漏>历史最大×0.97)
3. 前区每位奇偶比/大小比(0-4小5-9大)；后区special奇偶/大小(0-7小8-14大)/012路
4. 跨位形态(近50期)：前区重复频率、顺子/对称频率、跨度分布、奇偶/大小分布`,
  {label:'数据准备',phase:'数据准备',model:'lite'}
));
log('统计就绪');

phase('四层漏斗');
const pick = text(await agent(
  `你是七星彩选号专家。按四层漏斗过滤。**每位独立：d1只跟d1比，special只跟special比。**

前区d1-d6每位0-9(允许重复)，后区special 0-14。大小：前区0-4小/5-9大，后区0-7小/8-14大。

📊 回测(769期)：深冻>0.97误杀0.1%✅

---
${data}
---

# 🔪 第1层：预筛选

**排除：** 每位遗漏 > 该位历史最大×0.97 → 排除（误杀0.1%）

\`\`\`
🔪 预筛选
d1：排除X(深冻) → 候选X X X X X X X | d2：排除X → 候选...
d3-d6：(同样) | special：排除X → 候选X X X X X X X X X X
\`\`\`

---

# 🏗️ 第2层：按位结构

**每位锁定：** 奇偶倾向、大小倾向

**全局：** 前区6位不能全奇/全偶/全大/全小；后区012路合理

\`\`\`
🏗️ 按位结构
d1锁定：奇/偶=X 大小=X → 晋级X X X X X
d2-d6：(同样) | special锁定：奇/偶=X 大小=X 012路=X → 晋级X X X X X
全局：前区奇偶≠0:6/6:0 大小≠0:6/6:0
\`\`\`

---

# 🔍 第3层：跨位形态

| 检查 | 约束 |
|------|------|
| 重复模式 | 近10期重复频率判定 |
| 顺子/对称 | 避免≥3位连续递增 |
| 跨度 | 前区max-min宜4-9 |
| 012路 | 不能某路缺失 |
| 后区关联 | special与d6跟随规律 |

\`\`\`
🔍 跨位形态 | 重复预期：[可能/不太可能]
跨位淘汰：dX=X(顺子风险) | d1核心：X X X X | ... | d6核心：X X X X | special核心：X X X X X
\`\`\`

---

# 🎯 第4层：精选输出

**每位定数字→跨位协调→博弈微调→校验**

\`\`\`
🎯 精选

【前6+后1】d1=X d2=X d3=X d4=X d5=X d6=X + X
即 X X X X X X + X

【每位理由】d1=X(趋势+遗漏+结构) d2=X...

【校验】前区奇偶X:X✅ 大小X:X✅ 跨度X✅ 后区012路✅

⚠️ 七星彩为独立随机游戏，历史统计不构成开奖保证。理性购彩。
\`\`\``,
  {label:'四层漏斗选号',phase:'四层漏斗'}
));
log('漏斗产出就绪');

// ⚔️ 对抗验证 · 收敛循环（最多3轮 review+rebuttal）
const AGENTS = [
  {id:'trend-hunter', role:'趋势猎手🔥——用四窗口频率曲线(近10/20/30/50期)审查号码趋势方向，标记趋势恶化号并给替换建议'},
  {id:'gap-judge', role:'遗漏判官⚖️——审查遗漏状态，标记深冻(>历史最大×0.97)/过热/超跌回补信号，给替换建议'},
  {id:'struct-master', role:'结构大师🏗️——审查按位奇偶/大小/全局012路/跨度是否落在历史高频区间'},
  {id:'game-theorist', role:'博弈鬼才🎲——检查号码是否过热/太大众化，给反共识替换建议'},
];
const MAX_ROUNDS = 3;
let allReviews = [];
let currentPick = pick;
let converged = false;

for (let round = 1; round <= MAX_ROUNDS && !converged; round++) {
  phase(`对抗验证-R${round}`);
  const roundReviews = (await parallel(
    AGENTS.map(a => () => agent(
      `你是选号审查委员会的**${a.role}**。审查以下七星彩漏斗产出${round>1?'（第'+round+'轮，聚焦未解决争议）':''}。
CSV路径: data/processed/qxc_draws.csv（如需具体数据请用Bash自行读取）
${round>1?'⚠️ 聚焦上一轮未解决的核心争议。':''}
漏斗当前产出：${currentPick}
${round>1?'\n历史辩论摘要：\n'+allReviews.slice(-3).map(r=>`[R${r.round}${r.type}] ${r.content.slice(0,2000)}`).join('\n'):''}
请从你的专业视角审查，指出问题并给改进建议。${round>1?'只关注未充分回应的核心争议。':''}`,
      {label: `${a.id}审查-R${round}`, phase: `对抗验证-R${round}`}
    ))
  )).filter(Boolean).map(r => text(r));
  const validR = roundReviews;
  validR.forEach((r, i) => allReviews.push({round, type:'审查', agent: AGENTS[i] ? AGENTS[i].id : `reviewer-${i}`, content: r}));
  log(`R${round}: ${validR.length}/${AGENTS.length} 审查完成`);

  phase(`漏斗自辩-R${round}`);
  const rebuttalR = text(await agent(
    `你是七星彩漏斗选号专家。第${round}轮审查意见如下，请逐条自辩：
当前产出：${currentPick}
审查意见（R${round}）：${validR.map((r,i)=>`【${AGENTS[i]?AGENTS[i].id:'reviewer'}】\n${r}`).join('\n\n')}
${round>1?'\n历史辩论：\n'+allReviews.filter(r=>r.round<round).map(r=>r.content.slice(0,3000)).join('\n...\n'):''}
规则：有道理→认栽调整, 不合理→用数据反驳, 调整→输出修正版, 争议全部解决→开头写【CONVERGED】`,
    {label:`漏斗自辩-R${round}`, phase:`漏斗自辩-R${round}`}
  ));
  allReviews.push({round, type:'自辩', agent:'funnel', content: rebuttalR});
  currentPick = rebuttalR || currentPick;
  log(`R${round}: 漏斗已自辩`);

  if (round < MAX_ROUNDS) {
    const check = text(await agent(
      `检查第${round}轮是否已收敛。只输出：CONVERGED 或 NEED_NEXT_ROUND`,
      {label:`收敛检查-R${round}`, phase:'收敛检查', model:'lite'}
    ));
    if (check.toUpperCase().includes('CONVERGED') && !check.toUpperCase().includes('NEED_NEXT_ROUND')) {
      converged = true; log(`✅ R${round} 已收敛`);
    } else { log(`🔄 R${round} 未收敛，进入R${round+1}`); }
  }
}

phase('终裁');
const final = text(await agent(
  `你是首席裁判。综合${allReviews.filter(r=>r.type==='审查').length}轮辩论，输出最终推荐号码。
─── 漏斗原始产出 ─── ${pick}
─── 全部辩论 ─── ${allReviews.map(r=>`[${r.type}-R${r.round}] ${r.content.slice(0,4000)}`).join('\n---\n')}
裁决规则：1.漏斗最后认栽→采纳修正版 2.有理反驳未被再追击→驳回审查 3.结构硬伤→必须修正 4.维持原格式
输出最终号码+裁决依据。⚠️ 七星彩为独立随机游戏，理性购彩。`,
  {label:'首席裁定',phase:'终裁'}
));

phase('存档');
await agent(
  `用 Bash 完成：
1. 读 data/processed/qxc_draws.csv 最后一行拿最新期号，算下一期(+1)
2. 从终裁输出提取：前区6位+后区1位、核心逻辑
3. 调用 python scripts/_archive_prediction.py qxc '{"period_id":"...","compound_front":"...","compound_back":"...","s1_front":"...","s1_back":"...","s2_front":"...","s2_back":"...","s3_front":"...","s3_back":"...","notes":"..."}' 归档

终裁输出：
${final}

号码空格分隔，notes保留核心逻辑(≤100字)。只输出归档结果。`,
  {label:'预测存档',phase:'存档',model:'lite'}
);
log('✅ 完成');
return {funnelResult:pick, allReviews, final, phases:['预筛选','按位结构','跨位形态','精选','对抗验证-收敛循环','终裁','存档']};
