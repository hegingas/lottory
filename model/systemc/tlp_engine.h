// tlp_engine.h — TLP 引擎（sc_module 包装，TLM socket 对 VIP）
// 职责（对齐 host-model-design.md §7）：
//   · 下行：request() 构造 TLP → 挂起表登记 → s_vip_tx 发出（异步，Cpl 回来回调）
//   · 上行：s_vip_rx 收 TLP → 解析分流（Cpl 匹配挂起表 / DMA/Msg 上抛 on_parse）
//   · 超时：周期 process 扫描挂起表，超时报 completion timeout
//
// TLP 在 TLM 上的承载（骨架阶段）：
//   GP.data_ptr 承载 TLP 字节流（header+payload），gp.data_length = 字节数。
//   后续可升级为 tlp_ext 扩展字段（interfaces.md §6.1），接口不变。
#pragma once
#include <systemc.h>
#include <tlm.h>
#include <functional>
#include "pcie_types.h"
#include "tlp_builder.h"
#include "tlp_parser.h"
#include "pending_table.h"

namespace pcie {

class tlp_engine : public sc_module,
                   public tlm::tlm_fw_transport_if<>,   // s_vip_rx 的 target 侧
                   public tlm::tlm_bw_transport_if<> {  // s_vip_tx 的 initiator 侧
public:
    // 对 VIP 侧 socket
    tlm::tlm_initiator_socket<> s_vip_tx;   // 下行 TLP（RC 请求）→ VIP
    tlm::tlm_target_socket<>    s_vip_rx;   // 上行 TLP（EP 请求/消息）← VIP
    tlm::tlm_initiator_socket<> s_resp_tx;  // 下行响应（CplD：RC 对 EP 请求的完成）→ VIP

    // 上行分流结果回调（DMA/Msg/ERR → rc_bus_ctrl 接管）
    std::function<void(const parse_result&)> on_parse;

    SC_HAS_PROCESS(tlp_engine);
    explicit tlp_engine(sc_module_name nm);

    // 发请求：构造 TLP → 登记挂起表 → 发出。
    // 不阻塞等待完成；Cpl 回来时 cb(status, data) 被调用。
    // 返回 false = 挂起表满或构造失败。
    bool request(const req_desc& desc,
                 std::function<void(CplStatus, const std::vector<uint8_t>&)> cb);

    // 周期超时检查（进程自动运行）
    void check_timeouts();

    // ── tlm_fw_transport_if（s_vip_rx 的 target 侧）──
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

    // ── tlm_bw_transport_if（s_vip_tx 的反向回调，骨架不实现）──
    tlm::tlm_sync_enum nb_transport_bw(tlm::tlm_generic_payload& gp,
                                       tlm::tlm_phase& ph, sc_time& t) override {
        SC_REPORT_WARNING("pcie.tlp_engine", "收到 unexpected nb_transport_bw");
        return tlm::TLM_COMPLETED;
    }
    void invalidate_direct_mem_ptr(sc_dt::uint64, sc_dt::uint64) override {}

    // 发送任意 TLP（响应路径：CplD 等；经 s_resp_tx）
    bool send_tlp(const tlp_transaction& tlp);

    void set_timeout_ns(int64_t ns) { timeout_ns_ = ns; }
    int64_t pending_count() const { return pending_.pending_count(); }

private:
    tlp_builder   builder_;
    tlp_parser    parser_;
    pending_table pending_;
    int64_t       timeout_ns_ = 1'000'000;   // 1 ms, 见 delays.cfg cpl_timeout_ns
    sc_event_queue timeout_ev_;              // 触发超时扫描
    int64_t       now_ns() const { return sc_time_stamp().to_default_time_units(); }
};

}  // namespace pcie
