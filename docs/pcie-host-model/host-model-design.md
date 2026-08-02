# Host 行为模型内部详细设计

模块清单：RC 总线控制器、配置引擎、SMMU v3 模型、MSI 路由、内存模型、NIC 行为模块。

## 1. RC 总线控制器（rc_bus_ctrl）

**职责**：host 模型入口仲裁、域路由、延迟注入、事务日志。所有 TLM 事务必经此模块。

**接口**：
- 收：`cpu_target`（cpu 域）
- 发：`pcie_initiator`（pcie 域）
- 内部：到配置引擎 / SMMU / 内存模型的 TLM 点对点 socket
- 收：`pcie_target`（dma 域 + 消息）

**行为**：
```
cpu 域事务:
  addr 落在 SMMU 窗口 → 转 SMMU
  addr 落在 RC 配置窗口 → 配置引擎本地寄存器
  其他 → 日志 WARN + UR

pcie 域事务（发向 DUT）:
  按 txn_class 注入延迟 → pcie_initiator
  响应带 completion 语义返回

pcie_target 上行事务:
  DMA_READ/WRITE → SMMU → 内存模型
  MSG_* → MSI 路由
  MSG_ERR → 错误日志（AER 预留）
```

**延迟配置**：`config/delays.json`（见 interfaces.md 2.3）。

**状态**：无内部状态（纯路由+日志），可重入。

## 2. 配置引擎（cfg_engine）

**职责**：模拟 CPU 软件视角的 PCIe 配置管理逻辑，维护 DUT 配置空间状态镜像与 BAR 分配表。

**寄存器接口**（cpu 域，`0x0901_0000` 起）：

| 偏移 | 名称 | 读/写 | 语义 |
|------|------|:---:|------|
| 0x00 | `CFG_ENUM_START` | W | 写 1 触发枚举（同步执行） |
| 0x08 | `CFG_ENUM_STATUS` | R | 枚举完成/错误码 |
| 0x10 | `CFG_BAR_ALLOC` | W | 写 (bar_idx, size, flags) 触发分配 |
| 0x18 | `CFG_MSIX_ENABLE` | W | 写 MSI-X 表项（addr/data/vector） |
| 0x20 | `CFG_REQ_ID` | R/W | 本 RC 的 req_id（默认 0:0:0） |
| 0x28 | `CFG_LOG_LEVEL` | R/W | 日志级别 |

**枚举算法**（P0 简化 → P1 完整）：
```
P0：扫描 bus0/dev0-31/fn0-7，读 vendor/device ID，
    发现响应设备 → 记录到设备表 → 配 BAR → 完成。
    只扫 bus0（深度=1）。
P1：递归：发现 Type1 桥 → 下探 bus，深度优先，
    限制深度 ≤ 8，防环路（配 max_depth 寄存器）。
```

**BAR 分配**：按 interfaces.md 3.3 策略；分配结果写回设备表 + 发送
pcie 域 CFG_WRITE 到 DUT 的 BAR 寄存器（模拟软件写 BAR 的行为）。

**MSI-X 配置**：解析软件写入的 MSI-X 表（在 DUT 配置空间/BAR 内），
维护 `vector → GIC SPI` 映射表，供 MSI 路由模块查询。

**状态**：设备表（`{bus,dev,fn,vid,did,bar[6],msix_table,msi_enabled}`）、
BAR 分配表（当前版本静态，供 rc_bus_ctrl 反查）。

## 3. SMMU v3 模型（smmu_v3_model）

**职责**：模拟 SMMUv3 的行为语义：寄存器接口、流表、CMD/EVENT 队列、stage-2 地址转换、ATC。

**寄存器组**（`0x0900_0000` 起，对齐 SMMUv3 偏移）：

| 寄存器 | 语义（POC 实现子集） |
|--------|----------------------|
| `SMMU_CR0/CR1` | 使能位（SMMU_EN）、stage-2 使能 |
| `SMMU_STRTAB_BASE` | 流表基址/格式（线性表，POC 不做 2 级表） |
| `SMMU_STRTAB_STE` 缓存 | POC 内部维护 STE 哈希表，软件写 STRTAB 时按需懒加载 |
| `SMMU_CMDQ` | CMD 队列：TLBI/CFGI 命令由模型消费（POC 只消费 CFGI，TLBI 记日志） |
| `SMMU_EVENTQ` | 事件队列：转换故障写入（guest 软件可读到） |
| `SMMU_GBPA` | 默认流转换（未命中流表时行为） |

**转换流程**（dma 域）：
```
DMA 事务 → 查 STE（stream_id）:
  未命中流表 → 用 GBPA（默认）→ 恒等转换（POC 默认）
  STE.S1/S2 配置:
    S2 开启 → 查 stage-2 转换表（POC：模型内小表 + 哈希缓存）
    S2 关闭 → IPA == PA
  CFGI 命令 → 清缓存项
  转换故障 → 写入 EVENTQ + 响应带错误语义（POC：置 txn 失败位）
```

**ATC/ATS**（P4，能力依赖 VIP 确认）：
- 接收 pcie 域 ATS 事务（Translation Request）→ 查缓存 → 返回 Translation Completion
- `MSG_ERR` 中的 invalidation 请求 → 清 ATC 项

**简化边界**（见 architecture.md §6 第 2 条）：POC 转换表由测试软件直接写
模型寄存器（`SMMU_TEST_TLB` 窗口），不实现全页表遍历；P4 由 Linux
`arm-smmu-v3` 驱动真实配置时，实现最小页表遍历路径。

## 4. MSI 路由（msi_router）

**职责**：MSI/MSI-X 消息 → GIC 中断映射。

**消息解码**：
```
pcie_target 收到 MSG_MSI / MSG_MSIX（GP 带 data/address 扩展）:
  address 查 MSI-X 表（配置引擎维护）:
    命中 → 读出 vector → 查 vector→SPI 映射 → 拉高 cpu_irq_out[spi] → 延迟 100ns → 拉低
    未命中 → 日志 WARN（未使能的 MSI，模拟软件 bug）
```

**POC 中断线分配**：`cpu_irq_out` 固定 64 根（SPI 32~95 段，与 QEMU virt GIC 对齐），
vector 数超限 → 配置错误（断言）。

**完整路径（P4/P5）**：MSI → ITS 翻译（模型内实现 ITS 寄存器子集 + LPI 表）→
QEMU GIC ITS 直连。此路径与 POC SPI 路径并存，由配置开关切换。

**INTx 预留**：`MSG_INTX` → 4 根传统中断线（a/b/c/d），POC 不实现，预留接口。

## 5. 内存模型（mem_model）

**职责**：host 内存语义：DMA 目标、描述符环、包缓冲。与 QEMU guest RAM 共享。

**实现**：
```
构造参数：共享内存基址/大小（来自 QEMU-SystemC 桥）
mmap 同一物理文件 → 直接指针访问（零拷贝）
tlm_target_socket: b_transport 读/写共享内存
  读写大小: 对齐到 8B（PCIe 语义）；非对齐 → 拆分或报错（可配置）
```

**数据结构**（由 NIC 行为模块管理，模型提供存储）：
- 描述符环：环形缓冲（base/len/head/tail 元数据表），由 guest 软件初始化
- 包缓冲：固定槽位池（slot 数、大小可配置）
- 收包流程：DUT DMA 写描述符+数据 → 模型更新 tail → 通知 NIC 行为模块 → 触发 MSI

**一致性**：POC 无 cache 模型，DMA 写入立即对 guest 可见（架构简化假设 #1）。
若后续 DUT 行为需要 barrier 语义，在 rc_bus_ctrl 加 flush 事件（预留点）。

## 6. NIC 行为模块（nic_behavior）

**职责**：模拟 host 软件侧的网卡驱动行为，使 DUT（网卡 EP）有真实的软件交互对象。

**不实现**：DUT 内部收发包逻辑（那是 DUT 自己的事）；只模拟 host 侧行为。

**功能清单**：

| 功能 | 说明 |
|------|------|
| 队列配置解析 | 从 guest 软件写入 DUT 的队列配置寄存器（MMIO 路径）解析队列参数（描述符环基址/深度/队列数） |
| 发包注入（TX 方向） | 测试脚本/流量模型生成包 → host 模型写 DUT 的 TX 描述符（MMIO/DMA 写）→ 通知 DUT 有包 |
| 收包接收（RX 方向） | 监听 DMA 上行（dma 域）→ 更新 RX 描述符环状态 → 触发 MSI 聚合中断 |
| 中断聚合 | 每收 N 包（默认 8）或超时（默认 100μs）触发一次 MSI；参数可配置 |
| 多队列 | 支持 Q 个队列（默认 4），每个队列独立描述符环+独立 MSI vector |
| 流量模型 | 包大小分布（固定/随机）、速率（包/秒）、方向（TX/RX/双工）；`config/traffic.json` |

**状态机**（RX 队列，简版）：
```
IDLE → (DMA 上行写描述符) → RX_DATA → (描述符环满?) → 触发 MSI → IDLE
                                        └─ 不满 → 等待下一包（聚合计数器 +1）
```

**与内存模型交互**：描述符环读写走 mem_model 的共享内存（guest 软件直接操作），
NIC 行为模块只维护元数据（head/tail 指针视图），与 guest 软件协同。

## 7. TLP 引擎（tlp_engine）

**职责**：host 模型与 VIP 之间的 TLP 事务层核心——构造下行 TLP、解析上行 TLP、
维护挂起请求表（split-transaction 语义）。

**TLP 构造器（下行）**：
```
输入: 事务请求 {类型, 地址/配置偏移, 数据, 长度, 目标ID}
流程: 分配 tag → 填 header 字段 (fmt/type/tc/attr/length/req_id/tag/addr/BE)
      → 挂起表登记 {tag, 类型, 回调} → 发 TLP (TLM WRITE + tlp_ext) → VIP
字段规则:
  length = payload_bytes / 4 (DW), 0 表示 128B
  be_first/be_last: 非对齐访问时计算, 对齐时 0xFF
  req_id: 来自配置引擎 (默认 0:0:0)
  ECRC: 默认不生成 (TD=0, 待 FAE 确认项 #6)
```

**TLP 解析器（上行）**：
```
类型分流:
  Cpl/CplD → 按 tag 查挂起表:
      命中 → 回填数据/status → 完成请求 (唤醒等待者)
      未命中 → WARN (协议违例)
  MWr/MRd → DMA 域转发 (SMMU → 内存模型)
  Msg     → msg_code 分流: MSI 消息 → msi_router; ERR → 错误日志
```

**挂起请求表**：
| 项 | 说明 |
|----|------|
| 表项 | {tag, 请求类型, 期望 Cpl 类型, 数据指针, 回调/事件, 发出时刻} |
| tag 分配 | 环形复用 128 深度；满表时新请求排队（深度可配置） |
| 超时 | 发出后 1ms 无 Cpl → completion timeout 错误（日志 + 上报测试框架） |
| 乱序 | Cpl 按 tag 匹配天然支持乱序返回（架构简化假设 #8） |

**与 rc_bus_ctrl 的交互**：rc_bus_ctrl 发起请求 → 引擎返回「已发出」（异步），
请求完成由引擎回调通知。`b_transport` 语义在 cpu 域保持（QEMU 视角同步），
pcie 域内部是异步的（真实 RC 的 split-transaction 语义）。

## 8. 模块间依赖图

```
rc_bus_ctrl
  ├─→ cfg_engine    (cpu 域寄存器 + pcie 域转发)
  ├─→ tlp_engine    (pcie 域: TLP 构造/解析 + 挂起表)
  ├─→ smmu_v3_model (dma 域转换)
  ├─→ msi_router    (消息域)
  ├─→ mem_model     (dma 域读写)
  └─→ nic_behavior  (事件通知: 收包/中断时机)
tlp_engine ──→ smmu_v3_model / mem_model / msi_router (上行分流)
cfg_engine ──→ msi_router  (MSI-X 表共享)
nic_behavior ──→ mem_model (描述符环视图) ──→ msi_router (中断触发)
```

**依赖规则**：模块间只通过 TLM socket / 事件通道交互，禁止直接函数耦合
（nic_behavior ↔ cfg_engine 通过 rc_bus_ctrl 的注册表间接交互）。

## 9. 配置参数总表

| 配置文件 | 内容 |
|----------|------|
| `config/delays.json` | 各域延迟（见 interfaces 2.3） |
| `config/bars.json` | 静态 BAR 分配表 |
| `config/smmu.json` | SMMU 使能/默认流行为/缓存大小 |
| `config/traffic.json` | NIC 流量模型参数 |
| `config/platform.json` | 地址窗口布局、队列数、SPI 段 |

## 10. 测试策略（模型自测）

| 层级 | 内容 |
|------|------|
| 单元 | 每模块一个 testbench（TLM 直连，无 VIP）：转换正确性、状态机、边界（超长事务/非对齐） |
| 集成 | 带 VIP 的链路冒烟（P0）：枚举 → BAR → 读写 → 中断 |
| 场景 | 收发包全流程（P5）：guest 软件 + 模型 + DUT 三方闭环 |
| 回归 | `scripts/run_all.sh` 串跑全部场景，结果汇总表（断言通过率） |
