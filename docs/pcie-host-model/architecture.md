# 系统架构

## 1. 全景视图

```
┌────────────────────────────────────────────────────────────┐
│ QEMU (AArch64)                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                  │
│  │ CPU 核    │  │ GICv3/ITS│  │ guest RAM│  ← 共享内存      │
│  │ (TCG)    │  │  (QEMU)  │  │ (mmap)   │    (mmap 同一物理页)│
│  └────┬─────┘  └────┬─────┘  └────┬─────┘                  │
│       │ MMIO        │ 中断线      │ DMA 直读直写            │
└───────┼─────────────┼─────────────┼────────────────────────┘
        │             │             │
        │ TLM-2.0     │  GPIO       │  共享内存
        │ sockets     │ (SC signal) │  (mmap)
┌───────▼─────────────▼─────────────▼────────────────────────┐
│ ★ Host 行为模型 (SystemC TLM-2.0)                           │
│  ┌────────────────────────────────────────────────────┐   │
│  │ RC 总线控制器（地址解码 / 事务路由 / 延迟注入）        │   │
│  ├── 配置引擎（枚举 / BAR / MSI-X / 配置空间代理）        │   │
│  ├── SMMU v3 模型（STRTAB/CMD/EVENT + stage-2 转换+ATS） │   │
│  ├── MSI 路由（MSI 消息 → GIC SPI/LPI 映射）            │   │
│  ├── 内存模型（DMA target socket / 描述符环 / 包缓冲）    │   │
│  └── NIC 行为模块（队列状态机 / 收发包注入 / 中断聚合）    │   │
│  └────────────────────────────────────────────────────┘   │
│       ▲                                      │            │
│       │ TLM-2.0 (cfg/mmio/msg/ats 域)        │ TLM-2.0    │
│       │                                      │ (dma 域)   │
│  ┌─────────────── TLM (承载 TLP) ─────────────────────┐ │
│  │               │  · tlp_initiator: CfgRd/Wr, MRd/MWr  │ │
│  │               │  · tlp_target: Cpl/CplD, DMA, Msg     │ │
│  │   ┌───────────▼───────────┐                          │ │
│  │   │ Synopsys PCIe RC VIP  │                          │ │
│  │   │  · TLP 层接口（格式待 FAE 确认）                  │ │
│  │   │  · DLLP/链路训练/PHY 由 VIP 处理                  │ │
│  │   └──────────┬────────────┘                          │ │
│  │              │ PCIe 物理链路                          │ │
│            ┌────▼─────┐                                    │
│            │ DUT 网卡EP│ ← 被测对象                          │
│            └──────────┘                                    │
└────────────────────────────────────────────────────────────┘
```

## 2. 模块职责

| 模块 | 职责 | 对接口 |
|------|------|--------|
| QEMU（AArch64） | 跑 guest 软件栈；提供 CPU/GICv3/ITS 模型 | MMIO TLM socket、中断 GPIO、共享内存 |
| QEMU-SystemC 桥 | QEMU MMIO 总线 ↔ TLM-2.0 sockets；中断线导出 | TLM-2.0 + sc_signal |
| **RC 总线控制器** | host 模型入口：地址解码、事务路由（CFG/MMIO/DMA/消息）、延迟注入、日志 | 全部内部模块 |
| **配置引擎** | 模拟 CPU 软件发起的配置访问：枚举、BAR 分配、MSI-X 配置；维护配置空间状态镜像 | CPU 侧 TLM、VIP 侧 TLM |
| **SMMU v3 模型** | 模拟 SMMUv3 寄存器接口与地址转换：流表、CMD/EVENT 队列、stage-2 转换、ATC/ATS | CPU 侧 TLM（寄存器）、DMA 路径（转换） |
| **MSI 路由** | MSI/MSI-X 消息 → GIC 中断映射（POC 为 SPI，完整为 ITS/LPI） | VIP 消息域、QEMU 中断 GPIO |
| **内存模型** | host 内存：DMA 写目标、描述符环、包缓冲；与 QEMU guest RAM 共享物理内存 | TLM target socket（DMA 域） |
| **NIC 行为模块** | 驱动侧视角：队列配置解析、收发包注入、中断聚合策略 | 内存模型、MSI 路由 |
| **TLP 引擎** | TLP 构造/解析：header 字段编码、挂起请求表（tag 管理）、completion 匹配、ECRC 处理 | rc_bus_ctrl、VIP TLP 接口 |
| Synopsys RC VIP | PCIe 链路层以下：DLLP、链路训练、PHY；TLP 层与 host 模型通过 TLM 直连 | TLM（承载 TLP）、PCIe 物理链路 |

## 3. TLM 域划分（关键架构决策）

host 模型对外暴露 **3 个事务域**，地址空间互不重叠，GP 的 address 在各自域内解析：

| 域 | 用途 | 发起方 → 接收方 | 地址语义 |
|----|------|------------------|----------|
| **cpu 域** | CPU 对 host 模型寄存器（配置引擎/SMMU）的访问 | QEMU → host 模型 | host 物理地址窗口 |
| **pcie 域** | host 模型 → DUT 的请求 TLP（Cfg/Mem/Msg） | host 模型 → VIP（TLM 承载 TLP） | TLP 头字段（地址/BAR/配置偏移） |
| **dma 域** | DUT 上行 TLP（DMA 读写/Cpl/消息） | VIP → host 模型 | TLP 头字段（经 SMMU 转换后的 host 地址） |

> **为什么这样切**：CPU 视角、host 模型视角、EP 视角的地址语义不同。
> 域隔离让 SMMU 转换只发生在 pcie↔dma 边界，CPU 侧永远看到 IPA（guest 物理地址），
> 与真实 SoC 的软件视角一致。

## 4. 关键数据流

### 4.1 配置访问流（枚举）
```
QEMU 软件 (读 ECAM) → cpu域 TLM → 配置引擎
  → 判定目标 (DUT 配置空间) → pcie域 TLM → VIP → CFG TLP → DUT
  ← 响应原路返回（completion 延迟由 RC 总线控制器注入）
```

### 4.2 DMA 写流（EP 写 host 内存）
```
DUT → TLP (MWr) → VIP → dma域 TLM
  → SMMU (IPA→PA 转换，若开启)
  → 内存模型 (写共享内存，QEMU guest 立即可见)
  → 响应返回 EP
```

### 4.3 MSI 中断流
```
DUT → TLP (Msg: MSI-X) → VIP → 消息域
  → MSI 路由 (地址/数据解码 → 中断号)
  → POC: 直接拉 QEMU GIC GPIO (SPI)
  → 完整: ITS 翻译 → LPI → QEMU GICv3
```

### 4.4 收包流（NIC 场景）
```
QEMU 软件 配置 TX/RX 队列 (MMIO 到 DUT) → pcie域
DUT 收到包 → DMA 写 RX 描述符+数据 → dma域 → 内存模型
DUT → MSI 中断 → MSI 路由 → QEMU GIC → guest 中断 handler
guest 软件 读描述符环 (共享内存，无拷贝)
```

## 5. 部署视图

- 单进程仿真：QEMU + host 模型 + VIP 全部在同一仿真进程（QEMU-SystemC 集成模式），共享内存无跨进程拷贝
- 构建：CMake 统一管理 SystemC / TLM / QEMU 桥 / VIP 库
- 运行：`scripts/run.sh <scenario>` 启动仿真 + guest 软件加载 + 日志收集

## 6. 简化假设（POC 边界）

| # | 假设 | 影响 | 何时解除 |
|---|------|------|----------|
| 1 | 无 cache 一致性模型，共享内存直接可见 | DMA 后 guest 直接读到数据 | 性能验证阶段 |
| 2 | SMMU 先做「转换缓存查表」，不做页表遍历 | 转换表由测试软件直接写 BT | P4 由 Linux arm-smmu-v3 驱动真实配置 |
| 3 | MSI 先走 SPI 直连，不做 ITS | 中断路径 POC 简化 | P4/P5 引入 ITS/LPI |
| 4 | 单进程、单链路（无多 RC） | 拓扑简化 | 有需求再扩展 |
| 5 | 枚举先做简化扫描（bus 0 深度优先，固定深度） | 拓扑发现逻辑简化 | P1 完成真实枚举算法 |
| 6 | TLP 引擎 POC 简化：生成器只发 Cfg/Mem 请求 TLP（无 I/O/锁定/原子）；tag 顺序复用 | TLP 生成子集 | 有需求再扩展 |
| 7 | ECRC 生成/校验默认交 VIP（TD 位语义以 FAE 确认为准） | 引擎不实现 ECRC 算法 | P0 确认 |
| 8 | completion 乱序：POC 按 tag 顺序返回（VIP 若乱序，挂起表已支持 tag 匹配） | 时序简化 | P2 验证乱序 |
