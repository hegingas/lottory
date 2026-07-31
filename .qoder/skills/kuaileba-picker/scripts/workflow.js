// 快乐八四层漏斗 + 对抗验证 · 1901期全量回测验证
// 🔪预筛选(深冻0.97/热≥4/冷>22) → 🏗️结构 → 🔍形态 → 🎯精选 → ⚔️4人审查 → 🗣️漏斗自辩 → 👑终裁
export const meta = {
  name: 'kl8-funnel-pick',
  description: '快乐八四层漏斗+对抗验证+自辩：预筛选→结构→形态→精选→4人审查→漏斗自辩→终裁(区分度24.4%全彩种最强)',
  phases: [{title:'数据准备'},{title:'四层漏斗'},{title:'对抗验证'},{title:'漏斗自辩'},{title:'终裁'}],
};

const text = (v) => { if (!v) return ''; if (typeof v === 'string') return v; if (typeof v.content === 'string') return v.content; return JSON.stringify(v); };

phase('数据准备');
const data = text(await agent(
  `用 Bash 读取 data/processed/kl8_draws.csv(每期20个开奖号)，输出：
1. 最新一期期号+20个开奖号码，近10期明细
2. 频率遗漏(01-80)：近10期/近50期次数，当前遗漏，历史最大遗漏
   标注"深冻"(遗漏>历史最大×0.97)、"热号"(近10期≥4次)、"冷号"(遗漏>22期)
3. 结构(近50期)：20码奇偶比/大小比(01-40小41-80大)分布、和值均值±1σ
4. 8个十码段各段出号数分布
5. 同尾组数分布、跨度、质数个数分布、伴随对Top5`,
  {label:'数据准备',phase:'数据准备',model:'lite'}
));
log('统计就绪');

phase('四层漏斗');
const pick = text(await agent(
  `你是快乐八选号专家。按四层漏斗过滤。01-80选十10码，每期开20个号。大小01-40/41-80，8段01-10/11-20/.../71-80。

📊 回测验证(1901期)：深冻误杀1.9%✅ | 热号(≥4次)命中24.7% vs 冷号(>22期)0.3%→区分度24.4%🏆 | 每段~2.5个/期✅

---
${data}
---

# 🔪 第1层：预筛选

**排除：** 遗漏 > 历史最大×0.97 → 排除（误杀1.9%）

**标签：**
- 🔥热号：近10期≥4次（命中24.7%，冷号的80倍！）
- ❄️冷号：遗漏>22期（命中仅0.3%，最多选2个）

\`\`\`
🔪 预筛选 | 排除(N个)：XX(深冻) | 🔥热号(N个)：XX... | ❄️冷号(N个)：XX...
候选池(N个)：XX...
\`\`\`

---

# 🏗️ 第2层：结构框架

锁定10码框架（基于20码结构推导）：

| 维度 | 锁定 |
|------|------|
| 奇偶比 | 4:6~6:4 |
| 大小比 | 4:6~6:4 |
| 和值 | 380-420(20码均值796的一半) |
| 段覆盖 | ≥5个十码段 |

\`\`\`
🏗️ 结构 | 锁定：奇偶≈X:X 大小≈X:X 和值≈380-420 段≥5
框架淘汰：XX(原因) | 晋级(N个)：XX...
\`\`\`

---

# 🔍 第3层：形态约束

| 形态 | 约束 |
|------|------|
| 同尾 | ≤3组 |
| 质数 | 2-4个(共22个质数) |
| 跨度 | 龙头≤15，凤尾≥65 |
| 段平衡 | 每段候选≤4个 |
| 间隔 | 避免3+号集中在5以内区间 |

\`\`\`
🔍 形态 | 同尾淘汰：XX | 段平衡淘汰：XX | 晋级(N个)：XX...
\`\`\`

---

# 🎯 第4层：精选输出

**定胆(2-3个)→组合(热号3-4个+冷号≤2个)→段覆盖校验→终检**

\`\`\`
🎯 精选

【选十10码】XX XX XX XX XX XX XX XX XX XX（升序）
胆码：XX(理由), XX(理由)

【校验】段覆盖X段✅ 奇偶X:X✅ 大小X:X✅ 和值≈XX 热号X/10 冷号X

⚠️ 快乐八为独立随机游戏，历史统计不构成开奖保证。理性购彩，娱乐为主。
\`\`\``,
  {label:'四层漏斗选号',phase:'四层漏斗'}
));
log('漏斗产出就绪');

// ⚔️ 对抗验证 · 收敛循环（最多3轮 review+rebuttal）
const AGENTS = [
  {id:'trend-hunter', role:'趋势猎手🔥——用四窗口频率曲线(近10/20/30/50期)审查号码趋势方向，标记趋势恶化号并给替换建议'},
  {id:'gap-judge', role:'遗漏判官⚖️——审查遗漏状态，标记深冻(>历史最大×0.97)/过热(近10期≥4次)/超跌回补信号，给替换建议'},
  {id:'struct-master', role:'结构大师🏗️——审查奇偶/大小/和值/段覆盖是否落在历史高频区间，标记偏离'},
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
      `你是选号审查委员会的**${a.role}**。审查以下快乐八漏斗产出${round>1?'（第'+round+'轮，聚焦未解决争议）':''}。
CSV路径: data/processed/kl8_draws.csv（如需具体数据请用Bash自行读取）
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
    `你是快乐八漏斗选号专家。第${round}轮审查意见如下，请逐条自辩：
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
      `检查第${round}轮是否已收敛。看自辩是否标注【CONVERGED】，核心反对是否已被充分回应。只输出：CONVERGED 或 NEED_NEXT_ROUND`,
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
输出最终号码+裁决依据。⚠️ 快乐八为独立随机游戏，理性购彩。`,
  {label:'首席裁定',phase:'终裁'}
));

phase('存档');
await agent(
  `用 Bash 完成：
1. 读 data/processed/kl8_draws.csv 最后一行拿最新期号，算下一期(+1)
2. 从终裁输出提取：选十10码(或复式11码)、胆码、核心逻辑
3. 调用 python scripts/_archive_prediction.py kl8 '{"period_id":"...","compound":"...","s1":"...","s2":"...","s3":"...","dan_ma":"...","notes":"..."}' 归档

终裁输出：
${final}

号码空格分隔，notes保留核心逻辑(≤100字)。只输出归档结果。`,
  {label:'预测存档',phase:'存档',model:'lite'}
);
log('✅ 完成');
return {funnelResult:pick, allReviews, final, phases:['预筛选','结构','形态','精选','对抗验证-收敛循环','终裁','存档']};
