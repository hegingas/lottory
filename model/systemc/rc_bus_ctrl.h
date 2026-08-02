// rc_bus_ctrl.h — RC 总线控制器（host 模型入口，host-model-design.md §1）
// 职责：
//   · s_cpu 收 QEMU MMIO 访问（cpu 域）→ 地址解码 → 各窗口处理
//   · SMMU/RC 配置寄存器（骨架：寄存器数组 + 语义桩）
//   · 持有 tlp_engine，暴露其对 VIP 的 socket
//   · 上行分流（DMA/Msg）回调 → 内存模型 / MSI 路由（骨架：日志 + 计数）
#pragma once
#include <systemc.h>
#include <tlm.h>
#include <unordered_map>
#include "memory_map.h"
#include "tlp_engine.h"
#include "mem_model.h"
#include "cfg_engine.h"
#include "smmu_v3_model.h"
#include "nic_behavior.h"

namespace pcie {

class rc_bus_ctrl : public sc_module, public tlm::tlm_fw_transport_if<> {
public:
    // QEMU 侧（cpu 域）
    tlm::tlm_target_socket<> s_cpu;

    // 对 VIP 的 TLP socket（透传 tlp_engine）
    tlm::tlm_initiator_socket<>& s_tlp_tx() { return engine_.s_vip_tx; }
    tlm::tlm_target_socket<>&    s_tlp_rx() { return engine_.s_vip_rx; }

    // 内存模型（DMA 目标，共享内存指针由外部注入）
    mem_model& mem() { return mem_; }

    // 统计（测试断言用）
    unsigned dma_write_cnt_ = 0;
    unsigned dma_read_cnt_  = 0;
    unsigned msg_cnt_       = 0;
    unsigned msi_cnt_       = 0;   // 触发的 MSI 次数
    unsigned msi_ignored_cnt_ = 0; // 未使能 MSI 被忽略次数

    // 中断线输出（P3：MSI→GIC SPI；POC 固定 8 根）
    static constexpr int MAX_IRQ = 8;
    sc_signal<bool> irq_out[MAX_IRQ];

    // MSI-X 映射表操作（vector → GIC SPI；P3 由测试/软件注入）
    void msi_map_add(uint32_t vector, int spi) { msi_map_[vector] = spi; }
    void msi_map_clear() { msi_map_.clear(); }

    SC_HAS_PROCESS(rc_bus_ctrl);
    explicit rc_bus_ctrl(sc_module_name nm, uint64_t mem_size = 1 << 23);  // 8MB 默认

    // ── cpu 域入口 ──
    void b_transport(tlm::tlm_generic_payload& gp, sc_time& delay) override;
    tlm::tlm_sync_enum nb_transport_fw(tlm::tlm_generic_payload& gp,
                                       tlm::tlm_phase& ph, sc_time& t) override {
        b_transport(gp, t);
        return tlm::TLM_COMPLETED;
    }
    bool get_direct_mem_ptr(tlm::tlm_generic_payload&, tlm::tlm_dmi&) override {
        return false;
    }
    unsigned transport_dbg(tlm::tlm_generic_payload&) override { return 0; }

    // ── 测试钩子：直接发起 TLP 请求（绕过 CPU 域）──
    bool direct_request(const req_desc& desc,
                        std::function<void(CplStatus, const std::vector<uint8_t>&)> cb) {
        return engine_.request(desc, std::move(cb));
    }
    int64_t pending_count() const { return engine_.pending_count(); }

    // 配置引擎（P1：枚举/BAR）
    cfg_engine& cfg() { return cfg_; }
    // SMMU（P4：stage-2 转换）
    smmu_v3_model& smmu() { return smmu_; }
    // NIC 行为（P5：描述符/流量/聚合）
    nic_behavior& nic() { return nic_; }
    // 同步配置往返（供 cfg_engine sync_fn）：阻塞至 Cpl 或超时（须在 SC_THREAD 上下文）
    bool sync_config(uint8_t bus, uint8_t dev, uint8_t fn,
                     uint16_t off, uint32_t& val, bool write);

    // 对 VIP 的响应发送（host_model 接线用）
    tlm::tlm_initiator_socket<>& s_resp_tx() { return engine_.s_resp_tx; }

private:
    // 通用同步 TLP 往返（cfg/mmio 共用）
    bool sync_tlp(const req_desc& desc, std::vector<uint8_t>& out, CplStatus& st);

    // MSI 处理（上行 MWr 落入 MSI 窗口；任何线程调用，只做判断+notify）
    void handle_msi(uint64_t addr);
    // 中断线驱动进程（唯一写 irq_out 的进程，满足 sc_signal 单 driver 规则）
    void irq_driver();

    tlp_engine engine_;
    cfg_engine cfg_;
    mem_model  mem_;

    std::unordered_map<uint32_t, int> msi_map_;  // vector → GIC SPI
    int pending_spi_ = -1;                       // 待拉高的 SPI（msi_assert 消费）
    sc_event msi_assert_ev_;                     // 触发拉高
    sc_event irq_deassert_ev_;                   // 延迟拉低触发

    // 同步等待状态（单线程仿真，无需互斥）
    sc_event cpl_done_ev_;
    bool     cpl_pending_ = false;
    bool     cpl_result_ = false;
    CplStatus cpl_status_ = CplStatus::SC;
    std::vector<uint8_t> cpl_data_;

    // 寄存器数组（骨架）
    // rc_regs_: RC_CFG 窗口（offset/4 索引）
    static constexpr size_t RC_REGS = 16;
    uint32_t rc_regs_[RC_REGS] = {0};
    smmu_v3_model smmu_;
    nic_behavior  nic_;

    // 上行分流（on_parse 回调）
    void handle_parse(const parse_result& pr);

    void handle_rc_cfg(uint64_t off, bool is_write, uint32_t val, uint32_t& rval);
    void handle_smmu(uint64_t off, bool is_write, uint32_t val, uint32_t& rval);
};

}  // namespace pcie
