// smmu_v3_model.cpp — SMMUv3 行为模型实现
#include "smmu_v3_model.h"

namespace pcie {

bool smmu_v3_model::reg_write(uint64_t off, uint32_t val) {
    switch (off) {
        case REG_CR0:         cr0_ = val; return true;
        case REG_STRTAB_BASE: strtab_base_ = val; return true;
        case REG_GBPA:        gbpa_ = val; return true;
        case REG_EVENTQ_PROD: eventq_prod_ = val; return true;
        case REG_EVENTQ_CONS: eventq_cons_ = val; return true;
        // 测试窗口
        case REG_TEST_TLB_SID:  t_sid_ = val; return true;
        case REG_TEST_TLB_IPA:  t_ipa_ = (t_ipa_ & 0xFFFFFFFF00000000ULL) | val; return true;
        case REG_TEST_TLB_PA:   t_pa_ = (t_pa_ & 0xFFFFFFFF00000000ULL) | val; return true;
        case REG_TEST_TLB_SIZE: t_size_ = (t_size_ & 0xFFFFFFFF00000000ULL) | val; return true;
        case REG_TEST_TLB_COMMIT:
            if (val == 1 && t_size_ != 0) {
                tlb_.push_back({t_sid_, t_ipa_, t_pa_, t_size_});
                t_sid_ = t_ipa_ = t_pa_ = t_size_ = 0;
            }
            return true;
        case REG_TEST_TLB_CLEAR:
            if (val == 1) tlb_.clear();
            return true;
        default:
            return false;
    }
}

bool smmu_v3_model::reg_read(uint64_t off, uint32_t& val) {
    switch (off) {
        case REG_IDR0:        val = 0x0000'0101;  // 支持 S2 / 简化能力位
            return true;
        case REG_CR0:         val = cr0_; return true;
        case REG_STRTAB_BASE: val = strtab_base_; return true;
        case REG_GBPA:        val = gbpa_; return true;
        case REG_EVENTQ_PROD: val = eventq_prod_; return true;
        case REG_EVENTQ_CONS: val = eventq_cons_; return true;
        case REG_FAULT_REC:   val = fault_rec_; return true;
        case REG_TEST_FAULT_CNT: val = fault_cnt_; return true;
        default:
            return false;
    }
}

// ── 转换：未使能 → 恒等；使能 → TLB 查表 ──
bool smmu_v3_model::translate(uint32_t sid, uint64_t ipa, uint64_t& pa) {
    if (!enabled()) {
        pa = ipa;  // 旁路（SMMU_EN=0）
        return true;
    }
    for (const auto& e : tlb_) {
        if (e.sid == sid && ipa >= e.ipa && ipa < e.ipa + e.size) {
            pa = e.pa + (ipa - e.ipa);
            return true;
        }
    }
    record_fault(sid, ipa);
    return false;  // 转换故障
}

void smmu_v3_model::record_fault(uint32_t sid, uint64_t ipa) {
    fault_cnt_++;
    fault_ip_ = ipa;
    fault_rec_ = sid | 0x8000'0000;  // 压缩记录：高位置故障标记
    eventq_prod_++;                  // 简化：每故障一个事件
}

}  // namespace pcie
