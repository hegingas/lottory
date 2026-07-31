// 双色球四层漏斗 + 对抗验证 · 3379期全量回测验证
// 🔪预筛选(深冻0.99/热≥4/冷>18) → 🏗️结构 → 🔍形态 → 🎯精选 → ⚔️审查(最多3轮收敛) → 👑终裁
export const meta = {
  name: 'ssq-funnel-pick',
  description: '双色球四层漏斗+收敛对抗：预筛选→结构→形态→精选→5人审查(最多3轮收敛循环)→终裁',
  phases: [{title:'数据准备'},{title:'四层漏斗'},{title:'对抗验证-收敛循环'},{title:'终裁'}],
};

const text = (v) => { if (!v) return ''; if (typeof v === 'string') return v; if (typeof v.content === 'string') return v.content; return JSON.stringify(v); };

phase('数据准备');
const data = text(await agent(
  `用 Bash 读取 data/processed/ssq_draws.csv，输出：
1. 最新一期期号+开奖号码（红6+蓝1），上上期，近10期明细
2. 频率遗漏：红01-33+蓝01-16 近10期/近50期次数，当前遗漏，历史最大遗漏
   标注"深冻"(遗漏>历史最大×0.99)、"热号"(近10期≥4次)、"冷号"(遗漏>18期)
3. 结构(近50期)：奇偶比/大小比(01-16小17-33大)分布、和值均值±1σ、012路比、质数个数分布
4. 形态(近50期)：连号组数分布、重号个数分布、同尾组数、跨度范围、三区间分布
5. 伴随对Top5、蓝球跟随规律(重复/邻号/跳号比例)`,
  {label:'数据准备',phase:'数据准备',model:'lite'}
));
log('统计就绪');

phase('四层漏斗');
const pick = text(await agent(
  `你是双色球选号专家。按四层漏斗过滤。红球01-33选6，蓝球01-16选1，大小分界01-16/17-33。

📊 回测验证(3381期)：深冻0.99误杀0.3%✅ | 热号≥4次命中18.3% vs 冷号>18期1.3%→区分度17%✅ | 连号61%✅(分布:0连39% 1连38% 2连18% 3连5%) | 重号1-2个74%✅(分布:0个19% 1个48% 2个26%) | 和值μ=99 σ=21,1σ覆盖66%✅

---
${data}
---

# 🔪 第1层：预筛选（回测参数）

**排除：** 当前遗漏 > 历史最大遗漏×0.99 → 排除（误杀率0.2%）

**标签（不排名）：**
- 🔥热号：近10期≥4次（命中率18.3%，是冷号的14倍）
- ❄️冷号：遗漏>18期（命中率仅1.3%）

**蓝球：** 近2期出过的标记"降温"，上期蓝球直接排除（重复率仅6%）

\`\`\`
🔪 预筛选 | 排除红球(N个)：XX(深冻·漏X/最大Y) | 排除蓝球：XX(上期重复)
🔥热号(N个)：XX... | ❄️冷号(N个)：XX... | 蓝球降温：XX
候选红球(N个)：XX... | 候选蓝球(N个)：XX...
\`\`\`

---

# 🏗️ 第2层：结构框架

锁定本期硬约束（近50期分布）：

| 维度 | 锁定 |
|------|------|
| 奇偶比 | 3:3(37%)或4:2(24%)——Top2覆盖61% |
| 大小比 | 3:3(35%)或2:4(25%)——Top2覆盖60% |
| 和值 | 78-119(μ=99 σ=21) |
| 012路 | 每路≥1，单路≤3 |
| 质数 | 1-3个(占80%) |

框架反推淘汰不合规的号。

\`\`\`
🏗️ 结构 | 锁定：奇偶=X:X或X:X 大小=X:X或X:X 和值=78-119
框架淘汰：XX(原因) | 晋级红球(N个)：XX... | 晋级蓝球(N个)：XX...
\`\`\`

---

# 🔍 第3层：形态约束

| 形态 | 判定 |
|------|------|
| 连号 | 60%概率有，近5期节奏判定本期有/无 |
| 重号 | 75%概率1-2个，近10期分布锁定 |
| 同尾 | ≤2组 |
| 区间 | 三区间≥2区有号 |
| 跨度 | 近50期均值±5 |
| AC值 | 6-10 |

\`\`\`
🔍 形态 | 连号预期：[有/无] | 重号预期：[0/1/2]个
形态淘汰：XX(原因) | 晋级红球(N个)：XX... | 晋级蓝球(N个)：XX...
\`\`\`

---

# 🎯 第4层：精选输出

**定胆(1-2个)→组合(热号2-3个+冷号≤1个)→博弈微调→终检**

硬约束：连号∨重号1-2 | 不重历史 | AC值6-10 | 蓝球≠上期

\`\`\`
🎯 精选

【复式】红球(10-12码)：XX XX...（升序） 蓝球(2-3码)：XX XX...
胆码：XX(理由)

【或3注单式】
①红 XX XX XX XX XX XX + 蓝 XX  ②红 XX XX XX XX XX XX + 蓝 XX  ③红 XX XX XX XX XX XX + 蓝 XX

【校验】连号✅/❌ 重号✅X个 AC值=X 奇偶X:X 大小X:X 和值≈XX 热号X/6 冷号X
【理由】1-2句话

⚠️ 双色球为独立随机游戏，历史统计不构成开奖保证。理性购彩，娱乐为主。
\`\`\``,
  {label:'四层漏斗选号',phase:'四层漏斗'}
));
log('漏斗产出就绪');

// ⚔️ 对抗验证 · 收敛循环（最多3轮 review+rebuttal）
const AGENTS = [
  {id:'trend-hunter', role:'趋势猎手🔥——用四窗口频率曲线(近10/20/30/50期)审查号码趋势方向，标记趋势恶化号并给替换建议'},
  {id:'gap-judge', role:'遗漏判官⚖️——审查遗漏状态，标记深冻(>历史最大×0.99)/过热(近10期≥4次)/超跌回补信号，给替换建议'},
  {id:'struct-master', role:'结构大师🏗️——审查奇偶/大小/和值/012路/质数是否落在历史高频区间，标记>1σ偏离'},
  {id:'pattern-spy', role:'形态侦探🔍——审查连号/重号/区间均衡/跨度/同尾/AC值'},
  {id:'game-theorist', role:'博弈鬼才🎲——检查号码是否过热/太大众化，给反共识替换建议'},
];
const MAX_ROUNDS = 3;
let allReviews = [];
let currentPick = pick;
let converged = false;

for (let round = 1; round <= MAX_ROUNDS && !converged; round++) {
  // ── 审查 ──
  phase(`对抗验证-R${round}`);
  const roundReviews = await parallel(
    AGENTS.map(a => () =>
      agent(
        `你是选号审查委员会的**${a.role}**。审查以下双色球漏斗产出${round > 1 ? '（第' + round + '轮，聚焦上一轮未解决的争议）' : ''}。

CSV路径: data/processed/ssq_draws.csv（如需具体数据请用Bash自行读取）

${round > 1 ? '⚠️ 上一轮自辩未能完全说服审查员，本轮聚焦尚未解决的核心争议，不再重复已达成共识的问题。' : ''}

漏斗当前产出：
${currentPick}
${round > 1 ? '\n历史辩论：\n' + allReviews.map(r => `[R${r.round} ${r.type}] ${r.content.slice(0, 2000)}`).join('\n\n') : ''}

请从你的专业视角审查，指出问题并给改进建议。${round > 1 ? '只关注上一轮自辩未充分回应的核心争议。' : ''}`,
        {label: `${a.id}审查-R${round}`, phase: `对抗验证-R${round}`}
      )
    )
  );
  const validR = roundReviews.filter(Boolean).map(r => text(r));
  validR.forEach((r, i) => allReviews.push({round, type:'审查', agent: AGENTS[i] ? AGENTS[i].id : `reviewer-${i}`, content: r}));
  log(`R${round}: ${validR.length}/${AGENTS.length} 审查完成`);

  // ── 自辩 ──
  phase(`漏斗自辩-R${round}`);
  const rebuttalR = text(await agent(
    `你是双色球漏斗选号专家。第${round}轮审查意见如下，请逐条自辩${round > 1 ? '（聚焦未解决的争议）' : ''}：

你的当前产出：
${currentPick}

审查意见（第${round}轮）：
${validR.map((r, i) => `【${AGENTS[i] ? AGENTS[i].id : 'reviewer'}】\n${r}`).join('\n\n')}
${round > 1 ? '\n历史辩论摘要：\n' + allReviews.filter(r => r.type==='审查' && r.round < round).map(r => r.content.slice(0, 3000)).join('\n...\n') : ''}

规则：
- 有道理的批评 → 大方认栽，给出调整
- 不合理的批评 → 用回测数据反驳
- 调整号码 → 输出修正版（格式同漏斗层）
- 维持原判 → 说明理由
- 如果所有争议已解决→开头写【CONVERGED】

输出：逐条回应 + 修正后号码${round < MAX_ROUNDS ? ' + 如果已无实质性分歧请标注【CONVERGED】' : ''}`,
    {label:`漏斗自辩-R${round}`, phase:`漏斗自辩-R${round}`}
  ));
  allReviews.push({round, type:'自辩', agent:'funnel', content: rebuttalR});
  currentPick = rebuttalR || currentPick;
  log(`R${round}: 漏斗已自辩`);

  // ── 收敛检查 ──
  if (round < MAX_ROUNDS) {
    const check = text(await agent(
      `检查第${round}轮辩论是否已收敛。看自辩是否标注了【CONVERGED】，以及审查意见的核心反对（结构硬伤/遗漏超限/趋势严重恶化）是否已被充分回应或调整。

辩论记录：
${allReviews.slice(-3).map(r => `[${r.type}-R${r.round}] ${r.content.slice(0, 3000)}`).join('\n\n---\n')}

只输出一个词：CONVERGED 或 NEED_NEXT_ROUND`,
      {label:`收敛检查-R${round}`, phase:`收敛检查`, model:'lite'}
    ));
    if (check.toUpperCase().includes('CONVERGED') && !check.toUpperCase().includes('NEED_NEXT_ROUND')) {
      converged = true;
      log(`✅ R${round} 已收敛，结束辩论`);
    } else {
      log(`🔄 R${round} 未收敛，进入第${round+1}轮`);
    }
  }
}

// 👑 终裁：综合所有轮次辩论
phase('终裁');
const final = text(await agent(
  `你是首席裁判。综合漏斗产出和${allReviews.length}条辩论记录（${allReviews.filter(r=>r.type==='审查').length}轮审查+自辩），输出最终推荐号码。

─── 漏斗原始产出 ───
${pick}

─── 全部辩论记录 ───
${allReviews.map(r => `【${r.type}-R${r.round}】\n${r.content.slice(0, 4000)}`).join('\n\n---\n')}

─── 裁决规则 ──
1. 漏斗在最后一轮自辩中认栽的 → 采纳修正版
2. 漏斗有理有据反驳且审查员未再追击的 → 驳回审查
3. 结构硬伤（012路/奇偶/和值违规）→ 必须修正
4. 维持原漏斗格式输出（复式+单式+校验+理由）

输出最终号码，简述裁决依据。

⚠️ 双色球为独立随机游戏，历史统计不构成开奖保证。理性购彩，娱乐为主。`,
  {label:'首席裁定',phase:'终裁'}
));

phase('存档');
await agent(
  `用 Bash 完成：
1. 读 data/processed/ssq_draws.csv 最后一行拿最新期号，算下一期(+1)
2. 从终裁输出提取：复式红球/蓝球、3注单式红球+蓝球、胆码、核心逻辑
3. 调用 python scripts/_archive_prediction.py ssq '{"period_id":"...","compound_red":"...","compound_blue":"...","s1_red":"...","s1_blue":"...","s2_red":"...","s2_blue":"...","s3_red":"...","s3_blue":"...","dan_ma":"...","notes":"..."}' 归档

终裁输出：
${final}

号码空格分隔，notes保留核心逻辑(≤100字)。只输出归档结果。`,
  {label:'预测存档',phase:'存档',model:'lite'}
);
log('✅ 完成');
return {funnelResult:pick, allReviews, final, phases:['预筛选','结构','形态','精选','对抗验证-收敛循环','终裁','存档']};
