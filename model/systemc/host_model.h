// host_model.h — Host 行为模型顶层（architecture.md §2）
// 实例化 rc_bus_ctrl（含 tlp_engine/mem_model），暴露对 QEMU 和 VIP 的接口。
// P0 骨架：cfg_engine/smmu/msi_router/nic_behavior 后续阶段接入 rc_bus_ctrl。
#pragma once
#include <systemc.h>
#include <tlm.h>
#include "rc_bus_ctrl.h"

namespace pcie {

class host_model : public sc_module {
public:
    // ── 对外接口 ──
    tlm::tlm_target_socket<>& s_cpu() { return bus_.s_cpu; }           // ← QEMU
    tlm::tlm_initiator_socket<>& s_tlp_tx() { return bus_.s_tlp_tx(); } // → VIP (下行请求)
    tlm::tlm_target_socket<>&    s_tlp_rx() { return bus_.s_tlp_rx(); } // ← VIP (上行)
    tlm::tlm_initiator_socket<>& s_resp_tx() { return bus_.s_resp_tx(); } // → VIP (下行响应)

    // 访问内部（测试/后续阶段用）
    rc_bus_ctrl& bus() { return bus_; }
    mem_model&   mem()  { return bus_.mem(); }

    // 中断线输出（P3：MSI→GIC SPI；测试/后续接 QEMU GIC）
    sc_signal<bool>& irq(int spi) { return bus_.irq_out[spi]; }
    static constexpr int MAX_IRQ = rc_bus_ctrl::MAX_IRQ;

    SC_HAS_PROCESS(host_model);
    explicit host_model(sc_module_name nm, uint64_t mem_size = 1 << 23)  // 8MB 默认
        : sc_module(nm), bus_("rc_bus_ctrl", mem_size) {}

private:
    rc_bus_ctrl bus_;
};

}  // namespace pcie
