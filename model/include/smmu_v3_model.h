// smmu_v3_model.h — SMMUv3 行为模型（host-model-design.md §3）
// 纯逻辑层。POC 范围（架构简化假设 #2）：
//   · 转换表 = 模型内 TLB 缓存（软件经 TEST_TLB 窗口直写，不做页表遍历）
//   · 寄存器子集：CR0/STRTAB_BASE/GBPA/EVENTQ + 测试窗口
//   · 旁路模式：SMMU_EN=0 → 恒等映射
// P4 后期（Linux arm-smmu-v3 对齐）再扩展 STE/页表遍历。
#pragma once
#include <cstdint>
#include <vector>
#include <string>

namespace pcie {

class smmu_v3_model {
public:
    // ── 寄存器偏移（SMMUv3 规范简化子集）──
    static constexpr uint64_t REG_IDR0        = 0x000;  // 只读：支持能力
    static constexpr uint64_t REG_CR0         = 0x020;  // bit0=SMMU_EN
    static constexpr uint64_t REG_STRTAB_BASE = 0x040;  // 流表基址（POC 仅记录）
    static constexpr uint64_t REG_GBPA        = 0x100;  // 默认流（POC 仅记录）
    static constexpr uint64_t REG_EVENTQ_PROD = 0x300;  // 事件队列（简化：故障记录）
    static constexpr uint64_t REG_EVENTQ_CONS = 0x304;
    static constexpr uint64_t REG_FAULT_REC   = 0x308;  // 最近故障记录（guest 可读）

    // ── POC 测试窗口（模型专属，非 SMMUv3 规范）──
    static constexpr uint64_t REG_TEST_TLB_SID    = 0x800;  // stream_id
    static constexpr uint64_t REG_TEST_TLB_IPA    = 0x804;  // IPA（低 32）
    static constexpr uint64_t REG_TEST_TLB_PA     = 0x80C;  // PA（低 32）
    static constexpr uint64_t REG_TEST_TLB_SIZE   = 0x814;  // size（低 32）
    static constexpr uint64_t REG_TEST_TLB_COMMIT = 0x81C;  // 写 1 提交表项
    static constexpr uint64_t REG_TEST_TLB_CLEAR  = 0x904;  // 写 1 清空
    static constexpr uint64_t REG_TEST_FAULT_CNT  = 0x900;  // 只读

    // 寄存器访问（cpu 域；返回 false = 偏移非法）
    bool reg_write(uint64_t off, uint32_t val);
    bool reg_read(uint64_t off, uint32_t& val);

    // 转换：DMA 地址（IPA）→ PA。返回 false = 转换故障（未命中）
    // sid: stream id（POC 单设备 = 0）
    bool translate(uint32_t sid, uint64_t ipa, uint64_t& pa);

    bool enabled() const { return (cr0_ & 0x1) != 0; }
    unsigned fault_cnt() const { return fault_cnt_; }
    unsigned tlb_size() const { return static_cast<unsigned>(tlb_.size()); }

private:
    struct tlb_entry {
        uint32_t sid = 0;
        uint64_t ipa = 0, pa = 0, size = 0;
    };

    uint32_t cr0_ = 0;
    uint32_t strtab_base_ = 0;
    uint32_t gbpa_ = 0;
    uint32_t eventq_prod_ = 0, eventq_cons_ = 0;
    uint32_t fault_rec_ = 0;   // 最近故障 sid/ipa 压缩记录
    uint64_t fault_ip_ = 0;    // 最近故障 IPA
    unsigned fault_cnt_ = 0;

    std::vector<tlb_entry> tlb_;

    // 测试窗口暂存
    uint32_t t_sid_ = 0;
    uint64_t t_ipa_ = 0, t_pa_ = 0, t_size_ = 0;

    void record_fault(uint32_t sid, uint64_t ipa);
};

}  // namespace pcie
