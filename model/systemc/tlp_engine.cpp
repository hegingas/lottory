// tlp_engine.cpp — TLP 引擎实现
#include "tlp_engine.h"

namespace pcie {

tlp_engine::tlp_engine(sc_module_name nm)
    : sc_module(nm), s_vip_tx("s_vip_tx"), s_vip_rx("s_vip_rx"),
      s_resp_tx("s_resp_tx") {
    s_vip_tx.bind(*this);  // initiator socket 绑 bw 接口（反向回调）
    s_vip_rx.bind(*this);  // target socket 绑 fw 接口（b_transport）
    s_resp_tx.bind(*this);
    SC_METHOD(check_timeouts);
    sensitive << timeout_ev_;
    dont_initialize();
}

// ── 发送任意 TLP（响应路径）──
bool tlp_engine::send_tlp(const tlp_transaction& tlp) {
    auto bytes = tlp.to_bytes();
    tlm::tlm_generic_payload gp;
    gp.set_command(tlm::TLM_WRITE_COMMAND);
    gp.set_address(0);
    gp.set_data_ptr(bytes.data());
    gp.set_data_length(static_cast<unsigned int>(bytes.size()));
    gp.set_streaming_width(static_cast<unsigned int>(bytes.size()));
    sc_time delay = SC_ZERO_TIME;
    s_resp_tx->b_transport(gp, delay);
    return gp.get_response_status() == tlm::TLM_OK_RESPONSE;
}

bool tlp_engine::request(
    const req_desc& desc,
    std::function<void(CplStatus, const std::vector<uint8_t>&)> cb) {
    if (pending_.is_full()) {
        SC_REPORT_WARNING("pcie.tlp_engine", "挂起表已满, 请求被拒");
        return false;
    }

    // 1) 预分配 tag → 填入 TLP 头
    int tag = pending_.alloc_tag();
    if (tag < 0) return false;

    req_desc d = desc;
    d.tag = static_cast<uint16_t>(tag);

    // 2) 构造 TLP
    auto br = builder_.build(d);
    if (!br.ok) {
        pending_.release_tag(tag);
        SC_REPORT_WARNING("pcie.tlp_engine", br.error.c_str());
        return false;
    }

    // 3) 登记挂起表
    if (!pending_.register_at(tag, br.tlp.header, d.txn_class, d.data,
                              std::move(cb), now_ns())) {
        pending_.release_tag(tag);
        return false;
    }

    // 4) 发出 TLP（字节流承载；VIP 接受即返回 OK，Cpl 走上行路径）
    tlm::tlm_generic_payload gp;
    auto bytes = br.tlp.to_bytes();
    gp.set_command(tlm::TLM_WRITE_COMMAND);
    gp.set_address(0);                       // TLP 层无总线地址语义
    gp.set_data_ptr(bytes.data());
    gp.set_data_length(static_cast<unsigned int>(bytes.size()));
    gp.set_streaming_width(static_cast<unsigned int>(bytes.size()));
    sc_time delay = SC_ZERO_TIME;
    s_vip_tx->b_transport(gp, delay);

    if (gp.get_response_status() != tlm::TLM_OK_RESPONSE) {
        SC_REPORT_WARNING("pcie.tlp_engine", "VIP 拒绝下行 TLP");
        pending_.complete(static_cast<uint16_t>(tag), CplStatus::CA, {});
        return false;
    }

    // 5) 安排超时检查
    timeout_ev_.notify(SC_ZERO_TIME);
    return true;
}

void tlp_engine::b_transport(tlm::tlm_generic_payload& gp, sc_time& delay) {
    const unsigned char* buf = gp.get_data_ptr();
    unsigned int n = gp.get_data_length();

    tlp_transaction tlp;
    if (!buf || !tlp_transaction::from_bytes(buf, n, tlp)) {
        SC_REPORT_WARNING("pcie.tlp_engine", "上行 TLP 解析失败");
        gp.set_response_status(tlm::TLM_COMMAND_ERROR_RESPONSE);
        return;
    }

    auto pr = parser_.parse(tlp);
    if (!pr.ok) {
        SC_REPORT_WARNING("pcie.tlp_engine", pr.error.c_str());
        gp.set_response_status(tlm::TLM_COMMAND_ERROR_RESPONSE);
        return;
    }

    if (pr.txn_class == TxnClass::CPL) {
        // 完成 → 匹配挂起表
        bool hit = pending_.complete(pr.cpl_tag, tlp.header.status, tlp.payload);
        if (!hit) {
            SC_REPORT_WARNING("pcie.tlp_engine",
                              ("Cpl tag=" + std::to_string(pr.cpl_tag) +
                               " 未匹配挂起表").c_str());
        }
    } else if (on_parse) {
        on_parse(pr);   // DMA / Msg / 错误 → 上抛
    } else {
        SC_REPORT_WARNING("pcie.tlp_engine", "上行事务无回调处理");
    }

    gp.set_response_status(tlm::TLM_OK_RESPONSE);
    delay += sc_time(1, SC_NS);
}

void tlp_engine::check_timeouts() {
    auto expired = pending_.check_timeout(now_ns(), timeout_ns_);
    for (uint16_t tag : expired) {
        SC_REPORT_WARNING("pcie.tlp_engine",
                          ("completion timeout: tag=" + std::to_string(tag)).c_str());
        pending_.complete(tag, CplStatus::UR, {});
    }
    if (!expired.empty()) {
        SC_REPORT_WARNING("pcie.tlp_engine",
                          ("已上报 " + std::to_string(expired.size()) + " 个超时").c_str());
    }
    // 周期重调度（每 timeout 间隔检查一次；有挂起项时持续检查）
    if (pending_.pending_count() > 0) {
        timeout_ev_.notify(timeout_ns_, SC_NS);
    }
}

}  // namespace pcie
