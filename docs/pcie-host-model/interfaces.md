# TLM-2.0 接口定义

本文定义 host 模型对外的全部 TLM-2.0 接口：socket 拓扑、Generic Payload 编码规范、地址映射表、响应与延迟约定。实现与接线严格以此为准。

## 1. Socket 拓扑

```
┌─ Host 行为模型 ─────────────────────────────────────────┐
│                                                        │
│  [cpu_target] ← TLM ← QEMU-SystemC 桥 (MMIO 主端口)     │
│  [cpu_irq_out] → sc_signal<…> → QEMU GIC 中断输入 GPIO   │
│                                                        │
│  [tlp_initiator] → TLM (承载 TLP) → VIP TLP 上行端口     │
│  [tlp_target]  ← TLM (承载 TLP) ← VIP TLP 下行端口       │
│                                                        │
│  [mem_dma_target] ← TLM ← tlp_target 内部转发（DMA 域）  │
│                                                        │
└────────────────────────────────────────────────────────┘
```

> **模型工作层级**：host 模型工作在 **PCIe 事务层（TL）**——它构造/解析
> TLP 包（Header + Data + ECRC），通过 TLM 事务承载 TLP 与 VIP 交互。
> VIP 负责 TLP 之下的数据链路层（DLLP）与物理层（PHY）处理。
> TLM 不承载 AXI 总线语义，只做 TLP 的搬运通道。

| Socket 名 | 类型 | 方向 | 协议域 | 说明 |
|-----------|------|------|--------|------|
| `cpu_target` | simple_target_socket | 收 | cpu 域 | QEMU 对 host 模型寄存器（配置引擎/SMMU）的访问 |
| `tlp_initiator` | simple_initiator_socket | 发 | pcie 域 | host 模型 → VIP：**TLP 下行**（CFG/MMIO/Msg 请求 TLP） |
| `tlp_target` | simple_target_socket | 收 | dma 域 + 消息 | VIP → host 模型：**TLP 上行**（Cpl/CplD、DMA MWr/MRd、Msg） |
| `cpu_irq_out` | sc_signal（vector） | 出 | — | MSI→GIC 中断线（POC 为 SPI 号直连） |

> `tlp_target` 收到 TLP 后，内部 TLP 解析器按头字段分流：
> Cpl/CplD → 对应请求的完成（tag 匹配）；MWr/MRd → DMA 域 → SMMU → 内存模型；
> Msg → MSI 路由 / 错误日志。

**域判定规则**：`pcie_target` 收到的 GP 按 `ext_field.txn_class` 分流——
DMA 类 → SMMU 转换 → 内存模型；消息类 → MSI 路由；错误类 → 错误日志模块。

## 2. Generic Payload 编码规范

### 2.1 标准字段语义

| 字段 | 语义约定 |
|------|----------|
| `command` | `TLM_READ_COMMAND` / `TLM_WRITE_COMMAND`（POC 不用自定义命令） |
| `address` | **域相关地址**，见第 3 节地址映射表 |
| `data_ptr` | 事务数据（读写共用） |
| `length` | 字节数；POC 限制 ≤ 256B（后续按 DUT 需求放宽） |
| `response_status` | `TLM_OK_RESPONSE` / `TLM_INCOMPLETE_RESPONSE`（见 2.3） |
| `streaming_width` | POC 恒为 `length`（非流式） |
| `dmi` | POC 不使用（共享内存已天然免拷贝） |

### 2.2 扩展字段（Extension Payload）

定义自定义扩展 `pcie_gp_ext`，挂载于所有 GP：

| 字段 | 类型 | 域 | 含义 |
|------|------|-----|------|
| `txn_class` | enum | 全部 | 事务类：`CFG_READ/WRITE`、`MMIO_READ/WRITE`、`DMA_READ/WRITE`、`MSG_MSI`、`MSG_MSIX`、`MSG_INTX`、`MSG_ERR`、`ATS_TRANSLATE`、`ATS_INVALIDATE` |
| `phase` | enum | pcie | 调用阶段：`ENUM`（枚举）、`CFG`（配置）、`RUN`（运行）——供延迟注入与日志分级 |
| `req_id` | u32 | pcie/dma | 请求者 ID（bus/device/function 编码） |
| `tag` | u16 | pcie/dma | 事务标签（乱序跟踪预留） |
| `stream_id` | u32 | dma | SMMU stream ID（DUT 侧 StreamID 源） |
| `substream_id` | u32 | dma | PASID（虚拟化预留，POC 可置 0） |
| `translated` | bool | dma | 该地址是否已由 SMMU 转换（防二次转换） |
| `bar_index` | u8 | pcie | 目标 BAR 号（MMIO 时有效） |
| `dtd` | u32 | 全部 | 死锁超时值（ns），0 = 默认 |

### 2.3 响应与延迟约定

| 响应 | 语义 | 使用场景 |
|------|------|----------|
| `TLM_OK_RESPONSE` | 事务成功完成 | 正常路径 |
| `TLM_INCOMPLETE_RESPONSE` | 未完成（模拟 completion timeout） | 延迟注入超时 / 地址解码失败（模拟 UR） |
| `TLM_COMMAND_ERROR_RESPONSE` | 命令非法 | 断言错误，测试失败信号 |

**延迟注入规则**（POC 为固定值，可配置）：
- CPU 域：0 ns（寄存器访问立即响应）
- pcie 域 CFG：100 ns（模拟 RC 到 EP 的往返）
- pcie 域 MMIO：200 ns
- dma 域：300 ns（写后响应）
- 注入点在 RC 总线控制器，单处实现，日志可查

**乱序处理**：POC 全部走 `b_transport`（阻塞、按序）。
`nb_transport` 接口预留但不实现——若 P2 发现 DMA 深度队列需要乱序，
再在 pcie_target 后挂 split-transaction 队列模块（架构已预留该扩展点）。

## 3. 地址映射表（v0.1 草案）

### 3.1 host 物理地址布局（QEMU virt 风格，可配置）

| 窗口 | 地址范围 | 大小 | 用途 |
|------|----------|------|------|
| DDR0 | `0x0000_0000` ~ `0x3FFF_FFFF` | 1 GiB | guest RAM（与 QEMU 共享内存） |
| GIC | `0x0800_0000` ~ `0x080F_FFFF` | 1 MiB | QEMU 自带（本模型不接管） |
| SMMU 寄存器 | `0x0900_0000` ~ `0x0900_FFFF` | 64 KiB | SMMUv3 寄存器（host 模型实现） |
| RC 配置寄存器 | `0x0901_0000` ~ `0x0901_FFFF` | 64 KiB | 配置引擎/总线控制器寄存器（host 模型实现） |
| PCIe 配置空间 | `0x4000_0000` ~ `0x400F_FFFF` | 1 MiB | ECAM 风格：`[bus(8)][dev(5)][func(3)][off(12)]` |
| PCIe MMIO 窗口 | `0x5000_0000` ~ `0x5FFF_FFFF` | 256 MiB | DUT BAR 映射（BAR 分配器从这里切） |
| PCIe 高 MMIO | `0x80_0000_0000` ~ `0x8F_FFFF_FFFF` | 64 GiB | 64 位 BAR 预留（DUT 若用 64-bit BAR） |

### 3.2 地址转换规则

| 转换 | 规则 | 例子 |
|------|------|------|
| ECAM 地址 → CFG TLP | `offset = addr & 0xFFF`；`bus/dev/fn` 由地址字段拆出 | `0x4000_0000` → bus0/dev0/fn0/off0 |
| MMIO 地址 → BAR 空间 | 按 BAR 分配表反查 `bar_index`；不在表内 → UR | `0x5000_1000` → BAR0+0x1000 |
| DMA（guest 视角） | 先 SMMU stage-2（IPA→PA），再直接映射共享内存 | IPA `0x1000_0000` → PA `0x1000_0000`（identity 时） |
| SMMU 关闭时 | IPA == PA（恒等映射），转换模块旁路 | — |

### 3.3 BAR 分配策略（配置引擎）

- POC：固定静态分配表（`config/bars.json`），不实现动态重配
- 分配顺序：64-bit BAR 优先放高 MMIO 窗口，32-bit 放低窗口
- 每 BAR 对齐到其 size（硬件语义：`size & ~(size-1)` 对齐）
- BAR 分配表是配置引擎与 RC 总线控制器的共享状态（单例）

## 4. 各域事务序列模板

### 4.1 CPU → 配置引擎（cpu 域）
```
QEMU 写 RC_CFG_BASE + reg_off  → b_transport(cpu_target)
  → 配置引擎解析寄存器语义（枚举触发/BAR 写/MSI-X 使能）
  → 若涉及 DUT 配置空间：转发 pcie 域事务（见 4.2）
  → 响应：TLM_OK（本地寄存器立即） / TLM_OK（DUT 完成）
```

### 4.2 host 模型 → DUT 配置/MMIO（pcie 域）
```
构造 GP：txn_class=CFG_READ/WRITE 或 MMIO_READ/WRITE
  address = 配置空间偏移 或 总线地址
  → b_transport(pcie_initiator) → VIP → TLP → DUT
  → 响应按 2.3 注入延迟后返回
```

### 4.3 DUT → host 内存（dma 域，经 pcie_target 上行）
```
VIP 收到 EP 的 MWr/MRd → b_transport(pcie_target)
  → txn_class=DMA_READ/WRITE
  → SMMU：stream_id 查流表 → stage-2 转换（若开）→ PA
  → 内存模型写/读共享内存 → TLM_OK
```

### 4.4 MSI 消息（pcie_target 消息分支）
```
VIP 收到 Msg (MSI-X write) → b_transport(pcie_target)
  → txn_class=MSG_MSIX
  → MSI 路由：address/data → (中断号, 高/低数据)
  → 查 MSI-X 表（配置引擎维护）→ 映射 GIC SPI → cpu_irq_out 拉高 → 延迟后拉低
```

## 5. 与 QEMU-SystemC 桥的契约

| 项 | 约定 |
|----|------|
| MMIO 映射 | QEMU 侧把 host 模型寄存器窗口（SMMU/RC 配置）注册为 MMIO 设备，桥转为 cpu_target 事务 |
| 共享内存 | guest RAM 用 `mmap` 同一物理文件；桥把 QEMU RAM 基址传给 host 模型内存模型 |
| 中断 | 桥导出 N 条 GPIO 输入线（= GIC SPI 编号段）；host 模型 `cpu_irq_out` 直连 |
| 时钟 | 无独立时钟域；host 模型纯 event 驱动，延迟用 `sc_time` 相对延迟 |
| 复位 | 桥提供 `rst_n` sc_signal；模型复位时清空 BAR 表/SMMU 表/中断状态 |

## 6. TLP 事务编码规范（TLM 承载 TLP）

host 模型与 VIP 之间，**TLM 事务承载完整 TLP**（Header + Data + ECRC）。
TLP 以扩展字段 `tlp_ext` 挂载于 GP：header 字段全部显式化，data 复用 GP.data_ptr。

### 6.1 TLP 头字段（扩展字段 `tlp_ext`，与 PCIe Base Spec 对齐）

通用字段（所有 TLP）：

| 字段 | 位宽 | 说明 |
|------|:---:|------|
| `fmt` | 2 | 00=3DW无数据 01=4DW无数据 10=3DW带数据 11=4DW带数据 |
| `type` | 5 | 事务类型（见 6.2 编码表） |
| `tc` | 3 | Traffic Class |
| `td` | 1 | 有 ECRC（TD=1 时 payload 后附 4B ECRC） |
| `ep` | 1 | Poisoned 标记 |
| `attr` | 2 | [1]=No Snoop [0]=Relaxed Ordering |
| `at` | 2 | Address Type（1=转换后地址，P4 ATS 用） |
| `length` | 10 | 数据长度（DW 单位；0 表示 128B） |

类型相关字段（按类型有效）：

| 字段 | 适用于 | 说明 |
|------|--------|------|
| `requester_id` | 所有请求 TLP | bus[7:0]:dev[4:0]:fn[2:0] |
| `completer_id` | Cpl/CplD | 完成者 ID |
| `tag` | 请求/Cpl | 事务标签（乱序匹配键） |
| `be_first` / `be_last` | Mem 请求 | First/Last DW Byte Enable |
| `addr64` | Mem 请求（4DW 头） | 64 位地址（低 2 bit 恒 0） |
| `addr32` | Mem 请求（3DW 头） | 32 位地址 |
| `reg_off` | CfgRd/Wr | 配置寄存器偏移（低 12 bit） |
| `target_id` | Cfg 请求 | 目标 bus/dev/fn（枚举下探用） |
| `msg_code` | Msg | 消息编码（0x34=INTx Assert 等） |
| `status` | Cpl | 000=SC 001=UR 010=CRS 100=CA |
| `byte_count` | Cpl | 完成字节数（12 bit + BCM） |

### 6.2 TLP 类型编码表（host 模型生成的集合）

| 事务 | fmt | type[4:0] | host 模型用途 |
|------|:---:|:---:|------|
| CfgRd0 / CfgWr0 | 00 / 10 | `0_0100` | 枚举：读/写 Type0 配置空间 |
| CfgRd1 / CfgWr1 | 00 / 10 | `0_0101` | 枚举：桥下探（P1 完整枚举） |
| MRd | 00 / 01 | `0_0000` | MMIO 读（DUT BAR 空间） |
| MWr | 10 / 11 | `0_0000` | MMIO 写 |
| Msg（INTx） | 01 | `1_0rrr` | 传统中断（POC 预留） |
| — | — | — | — |

host 模型 **不生成**：I/O 事务、锁定事务、原子操作（POC 边界）。

### 6.3 TLM GP ↔ TLP 映射规则

| GP 字段 | 映射 |
|---------|------|
| `command` | 固定 `TLM_WRITE_COMMAND`（TLP 是单向包，方向由方向表达；读写语义在 tlp_ext.type 表达） |
| `address` | 用于日志/索引，真实地址在 `addr64/addr32/reg_off` |
| `data_ptr` / `length` | TLP payload（`length` 字段 = length/4，DW 单位） |
| `response_status` | TLP 完成映射：Cpl SC → `TLM_OK_RESPONSE`；UR → `TLM_INCOMPLETE_RESPONSE`；CRS → 特殊标记（重试语义） |
| `tlp_ext` | 全部头字段 |

### 6.4 上行 TLP 处理（tlp_target 接收路径）

```
VIP 上行 TLP → tlp_target
  → TLP 解析器:
    type=Cpl/CplD → tag 匹配挂起请求表 → 完成请求（唤醒等待的 b_transport）
    type=MWr/MRd → DMA 域: SMMU 转换 → 内存模型 → 上行完成响应
    type=Msg     → msg_code 分流: MSI 消息 → MSI 路由; ERR 消息 → 错误日志(AER 预留)
    type=CfgRd0 响应  → 枚举状态机消费（回填读数据）
```

### 6.5 挂起请求表（split-transaction 语义）

- host 模型发出请求 TLP 时记录 `{tag, 请求类型, 期望响应类型, 回调}`
- 上行 Cpl/CplD 按 tag 匹配；未匹配 → WARN 日志（协议违例）
- tag 分配：8 bit，主机维护递增分配器（POC 环形复用，128 深度）
- POC 时序：`b_transport` 发出后**不阻塞等待**，由 Cpl 回调完成（等价 completion 异步语义）；若 1ms 超时无 Cpl → 报 completion timeout 错误

## 7. 与 Synopsys VIP 的契约（TLP 接口，FAE 确认项）

| # | 待确认 | 影响 |
|---|--------|------|
| 1 | VIP TLP 事务接口的形式：TLM socket / DPI / 队列 API？字段命名（fmt_type 组合 vs 分字段） | 决定桥接封装层（若有）和 tlp_ext 字段映射表 |
| 2 | VIP 是否透传原始 TLP（含 header 全部字段）还是限制字段集合（如 tag 分配、BE 处理） | 决定 host 模型 TLP 生成器的自由度 |
| 3 | VIP 是否支持 ATS Translation 事务透传 | 决定 SMMU 的 ATS 功能是否可验（P4 前置） |
| 4 | VIP 是否支持错误注入（UR/CA/poisoned TLP）与接收侧报告 | 错误路径验证范围 |
| 5 | 链路训练完成 / link 事件的 TLP 接口外通知方式 | host 模型启动时序依赖此信号 |
| 6 | ECRC 生成/校验是否由 VIP 完成（TD 位处理） | host 模型生成器是否需算 ECRC |
| 7 | 上行完成（Cpl）的返回通道：与请求同 socket 还是独立 | 影响挂起请求表接线 |

## 8. 日志与调试契约

- 每个 TLM 事务在 RC 总线控制器打印一行结构化日志（CSV 可导入）：
  `时间, 域, txn_class, 命令, 地址, 长度, 响应, 延迟(ns), req_id`
- 枚举级别：`ERROR / WARN / TXN / DETAIL`
- 断言：事务响应异常（UR/超时）在测试末汇总为 pass/fail 报告
