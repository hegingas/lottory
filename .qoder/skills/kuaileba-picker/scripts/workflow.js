// 快乐八两段式漏斗 + 对抗验证 · 2013期全量实证(2026-08-02 对抗验证复核)
// 实证：热冷/遗漏维度无预测区分度(命中24.9~25.3%≈随机25.0%)，仅结构轴有效
// 🏗️结构合规 → 🎲共识分散 → ⚔️2人审查 → 🗣️漏斗自辩 → 👑终裁
export const meta = {
  name: 'kl8-funnel-pick',
  description: '快乐八两段式漏斗+对抗验证：结构合规→共识分散→2人审查→自辩→终裁(2013期实证：热冷/遗漏无区分度，仅结构轴有效)',
  phases: [{title:'数据准备'},{title:'两段式漏斗'},{title:'对抗验证'},{title:'漏斗自辩'},{title:'终裁'}],
};

phase('数据准备');
const data = await agent(
  `用 Bash 读取 data/processed/kl8_draws.csv(每期20个开奖号，2013期全量)，输出：
1. 最新一期期号+20个开奖号码，近10期明细
2. 结构统计(近50期)：20码奇偶比分布(均值/σ/Top2高频模式)、大小比(01-40小41-80大)、和值均值±1σ、012路均值±σ、质数个数Top2模式
3. 频率(近10期/近50期)：01-80每个号出现次数
4. 当前遗漏(01-80)，上期开出号清单(漏0)
5. 8个十码段近50期出号数均值`,
  {label:'数据准备',phase:'数据准备',model:'haiku'}
);
log('统计就绪');

phase('两段式漏斗');
const pick = await agent(
  `你是快乐八选号专家。按两段式漏斗生成10码组合。01-80选十10码，每期开20个号。大小01-40/41-80，8段01-10/11-20/.../71-80。

📊 实证结论(2013期全量回测，已复核)：热冷/遗漏维度无预测区分度(热号命中24.87~24.91%、冷号28~29%、遗漏各级24.90~25.25%，均≈随机基准25.0%)，号码选择无统计优势；唯一有统计意义的是结构轴(奇偶/大小/和值/012路/质数需落在历史高频区间)。因此选号=结构合规+共识分散的惯例选择。

---
${data}
---

# 🏗️ 第1层：结构合规（唯一统计轴）

锁定10码结构（基于近50期20码结构推导）：
- 奇偶比、大小比：落在近50期 Top2 高频模式
- 和值：均值±1σ 内
- 012路：各路计数在均值±0.6σ 内
- 质数：2-4个（Top2 模式内）

\`\`\`
🏗️ 结构 | 锁定：奇偶≈X:X 大小≈X:X 和值≈XXX 012路≈X:X:X 质数≈X个
候选池(N个)：XX...
\`\`\`

---

# 🎲 第2层：共识分散（唯一有效策略轴）

从结构合规候选池中选10码，配额约束（**只做配额，不做排除**）：
- 热号(近10期≥4次) ≤3个 —— 防追热摊薄期望（实证：追热无收益）
- 透明人(近10期≤1次) ≥1个 —— 反共识分散
- 漏0(上期开出) ≤4个 —— 防全押上期重号
- 段覆盖 ≥5段 —— 多样性
- 同尾 ≤3组

\`\`\`
🎲 分散 | 热号X/10(≤3) 透明人X/10(≥1) 漏0X/10(≤4) 段覆盖X段(≥5) 同尾X组(≤3)
\`\`\`

---

# 🎯 输出

【选十10码】XX XX XX XX XX XX XX XX XX XX（升序）
胆码：XX(理由), XX(理由)

【校验】奇偶X:X✅(Top2) 大小X:X✅ 和值≈XX✅ 012路✅ 质数X✅ 热号X/10✅ 透明人X✅ 漏0X/10✅ 段覆盖X段✅ 同尾X组✅

⚠️ 快乐八为独立随机游戏，历史统计不构成开奖保证。理性购彩，娱乐为主。`,
  {label:'两段式漏斗',phase:'两段式漏斗'}
);
log('漏斗产出就绪');

// ⚔️ 对抗验证 · 收敛循环（最多2轮 review+rebuttal）
const AGENTS = ['struct-master','game-theorist'];
const MAX_ROUNDS = 2;
let allReviews = [];
let currentPick = pick;
let converged = false;

for (let round = 1; round <= MAX_ROUNDS && !converged; round++) {
  phase(`对抗验证-R${round}`);
  const roundReviews = await parallel(
    AGENTS.map(a => () => agent(
      `你是选号审查委员会的**${a}**。审查以下快乐八漏斗产出${round>1?'（第'+round+'轮，聚焦未解决争议）':''}。
CSV路径: data/processed/kl8_draws.csv（如需具体数据请自行读取）
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
    `你是快乐八漏斗选号专家。第${round}轮审查意见如下，请逐条自辩：
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
      `检查第${round}轮是否已收敛。看自辩是否标注【CONVERGED】，核心反对是否已被充分回应。只输出：CONVERGED 或 NEED_NEXT_ROUND`,
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
输出最终号码+裁决依据。明示：本注为结构合规与共识分散的惯例选择，热冷/遗漏维度经2013期全量回测确认无预测区分度。
⚠️ 快乐八为独立随机游戏，历史统计不构成开奖保证，理性购彩。`,
  {label:'首席裁定',phase:'终裁',model:'sonnet'}
);

phase('存档');
await agent(
  `用 Bash 完成：
1. 读 data/processed/kl8_draws.csv 最后一行拿最新期号，算下一期(+1)
2. 从终裁输出提取：选十10码(或复式11码)、胆码、核心逻辑
3. 调用 python scripts/_archive_prediction.py kl8 '{"period_id":"...","compound":"...","s1":"...","s2":"...","s3":"...","dan_ma":"...","notes":"..."}' 归档

终裁输出：
${final}

号码空格分隔，notes保留核心逻辑(≤100字)。只输出归档结果。`,
  {label:'预测存档',phase:'存档',model:'haiku'}
);
log('✅ 完成');
return {funnelResult:pick, allReviews, final, phases:['两段式漏斗','对抗验证-收敛循环','终裁','存档']};
