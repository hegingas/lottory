// rc_bus_ctrl.cpp — RC 总线控制器实现
#include "rc_bus_ctrl.h"

namespace pcie {

namespace {
// 十六进制日志辅助（SystemC 2.3.4 无 sc_dt::uint64_to_string）
// 不带 0x 前缀（调用处自带），避免 0x0x 双前缀
std::string hex_str(uint64_t v) {
    char buf[24];
    std::snprintf(buf, sizeof(buf), "%llx", static_cast<unsigned long long>(v));
    return buf;
}
}

rc_bus_ctrl::rc_bus_ctrl(sc_module_name nm, uint64_t mem_size)
    : sc_module(nm), s_cpu("s_cpu"), engine_("tlp_engine"),
      mem_(mem_size) {
    s_cpu.bind(*this);
    engine_.on_parse = [this](const parse_result& pr) { handle_parse(pr); };
    // 配置引擎的同步往返注入
    cfg_.set_sync_fn([this](uint8_t bus, uint8_t dev, uint8_t fn,
                            uint16_t off, uint32_t& val, bool write) {
        return sync_config(bus, dev, fn, off, val, write);
    });
    // 中断线驱动进程（唯一写 irq_out 的进程，满足 sc_signal 单 driver）
    SC_METHOD(irq_driver);
    sensitive << msi_assert_ev_ << irq_deassert_ev_;
    dont_initialize();
}

// ── MSI 处理（P3）：上行 MWr 落入 MSI 窗口 → 查映射 → 通知拉高 ──
// 注意：不能在此直接 write(irq_out)——调用线程非进程，且 sc_signal 单 driver
void rc_bus_ctrl::handle_msi(uint64_t addr) {
    uint32_t vector = static_cast<uint32_t>((addr - map::MSI_ADDR_BASE) / 4);
    auto it = msi_map_.find(vector);
    if (it == msi_map_.end()) {
        msi_ignored_cnt_++;
        SC_REPORT_WARNING("pcie.rc_bus_ctrl",
                          ("未使能 MSI 被忽略: vector=" + std::to_string(vector)).c_str());
        return;
    }
    int spi = it->second;
    if (spi < 0 || spi >= MAX_IRQ) {
        SC_REPORT_WARNING("pcie.rc_bus_ctrl", "SPI 越界");
        return;
    }
    msi_cnt_++;
    pending_spi_ = spi;
    msi_assert_ev_.notify(SC_ZERO_TIME);
    SC_REPORT_INFO("pcie.rc_bus_ctrl",
                   ("MSI vector=" + std::to_string(vector) +
                    " → SPI " + std::to_string(spi)).c_str());
}

// 唯一写 irq_out 的进程：assert 事件 → 拉高 + 安排 100ns 脉冲结束；
// deassert 事件 → 全部拉低
void rc_bus_ctrl::irq_driver() {
    if (msi_assert_ev_.triggered()) {
        if (pending_spi_ >= 0 && pending_spi_ < MAX_IRQ) {
            irq_out[pending_spi_].write(true);
            irq_deassert_ev_.notify(100, SC_NS);
            pending_spi_ = -1;
        }
    } else if (irq_deassert_ev_.triggered()) {
        for (int i = 0; i < MAX_IRQ; i++) {
            irq_out[i].write(false);
        }
    }
}

// ── cpu 域：QEMU 对 host 模型寄存器的访问 ──
void rc_bus_ctrl::b_transport(tlm::tlm_generic_payload& gp, sc_time& delay) {
    const bool is_write = gp.is_write();
    uint64_t addr = gp.get_address();
    unsigned len = gp.get_data_length();
    uint32_t val = 0;
    if (is_write && len == 4) {
        std::memcpy(&val, gp.get_data_ptr(), 4);
    }

    auto dec = map::decode_host_addr(addr);
    switch (dec.kind) {
        case map::decode_result::Kind::SMMU_REG: {
            uint32_t rval = 0;
            handle_smmu(dec.offset, is_write, val, rval);
            if (!is_write && len == 4) std::memcpy(gp.get_data_ptr(), &rval, 4);
            break;
        }
        case map::decode_result::Kind::RC_CFG_REG: {
            uint32_t rval = 0;
            handle_rc_cfg(dec.offset, is_write, val, rval);
            if (!is_write && len == 4) std::memcpy(gp.get_data_ptr(), &rval, 4);
            break;
        }
        case map::decode_result::Kind::MMIO:
        case map::decode_result::Kind::MMIO64: {
            // P2: guest 访问 DUT BAR 空间 → 走 TLP（MRd/MWr）到 DUT
            if (len % 4 != 0) {
                SC_REPORT_WARNING("pcie.rc_bus_ctrl", "MMIO 访问必须 4B 对齐（POC 决策）");
                gp.set_response_status(tlm::TLM_COMMAND_ERROR_RESPONSE);
                return;
            }
            if (len > 256) {
                SC_REPORT_WARNING("pcie.rc_bus_ctrl",
                                  ("MMIO 长度 " + std::to_string(len) +
                                   "B 超 256B 上限（POC 决策：拒绝，不做拆分）").c_str());
                gp.set_response_status(tlm::TLM_COMMAND_ERROR_RESPONSE);
                return;
            }
            // BAR 反查：地址须落在已分配 BAR 内
            bool bar_hit = false;
            for (const auto& d : cfg_.devices()) {
                for (int i = 0; i < 6; i++) {
                    if (d.bar_alloc[i] && addr >= d.bar_alloc[i] &&
                        addr + len <= d.bar_alloc[i] + d.bar_size[i]) {
                        bar_hit = true;
                        break;
                    }
                }
            }
            if (!bar_hit) {
                SC_REPORT_WARNING("pcie.rc_bus_ctrl",
                                  ("MMIO 地址未落在已分配 BAR: 0x" + hex_str(addr)).c_str());
                gp.set_response_status(tlm::TLM_COMMAND_ERROR_RESPONSE);
                return;
            }

            req_desc desc;
            desc.txn_class = is_write ? TxnClass::MMIO_WRITE : TxnClass::MMIO_READ;
            desc.address = addr;
            desc.requester_id = make_req_id(0, 0, 0);
            if (is_write) {
                desc.data.assign(gp.get_data_ptr(), gp.get_data_ptr() + len);
            }

            std::vector<uint8_t> out;
            CplStatus st = CplStatus::UR;
            if (!sync_tlp(desc, out, st)) {
                gp.set_response_status(tlm::TLM_COMMAND_ERROR_RESPONSE);
                SC_REPORT_WARNING("pcie.rc_bus_ctrl",
                                  ("MMIO " + std::string(is_write ? "写" : "读") +
                                   " 失败: 0x" + hex_str(addr)).c_str());
                return;
            }
            if (!is_write && len == out.size()) {
                std::memcpy(gp.get_data_ptr(), out.data(), len);
            }
            break;
        }
        case map::decode_result::Kind::ECAM: {
            // 配置空间访问（P1）：经 TLP 到 DUT（真实 RC 语义，不拦截）
            if (len != 4) {
                SC_REPORT_WARNING("pcie.rc_bus_ctrl", "ECAM 访问长度必须 4B");
                gp.set_response_status(tlm::TLM_COMMAND_ERROR_RESPONSE);
                return;
            }
            uint32_t rval = val;
            bool ok = sync_config(dec.bus, dec.dev, dec.fn, dec.reg_off,
                                  rval, is_write);
            if (!ok) {
                // UR：读回全 1（PCIe 语义），写静默丢弃
                if (is_write) {
                    gp.set_response_status(tlm::TLM_OK_RESPONSE);
                } else {
                    std::memset(gp.get_data_ptr(), 0xFF, len);
                    gp.set_response_status(tlm::TLM_OK_RESPONSE);
                }
                SC_REPORT_WARNING("pcie.rc_bus_ctrl",
                                  ("配置访问失败(UR): " +
                                   format_req_id(make_req_id(dec.bus, dec.dev, dec.fn)) +
                                   " off=" + hex_str(dec.reg_off)).c_str());
                return;
            }
            if (!is_write) std::memcpy(gp.get_data_ptr(), &rval, 4);
            break;
        }
        default:
            // MMIO/DDR 落在 CPU 域 = 未经 TLP 的直访（P2 实现 MMIO 路径）
            SC_REPORT_WARNING("pcie.rc_bus_ctrl",
                              ("cpu 域地址未映射: 0x" + hex_str(addr)).c_str());
            gp.set_response_status(tlm::TLM_COMMAND_ERROR_RESPONSE);
            return;
    }

    gp.set_response_status(tlm::TLM_OK_RESPONSE);
    delay += SC_ZERO_TIME;
}

// ── RC 配置窗口寄存器（骨架：枚举触发桩）──
void rc_bus_ctrl::handle_rc_cfg(uint64_t off, bool is_write, uint32_t val,
                                uint32_t& rval) {
    unsigned idx = static_cast<unsigned>(off / 4);
    if (idx >= RC_REGS) {
        rval = 0;
        return;
    }
    if (is_write) {
        rc_regs_[idx] = val;
        if (off == 0x00 && (val & 1)) {  // CFG_ENUM_START
            // 骨架：触发枚举流程（P1 实现：扫描 + BAR 分配）
            // P0 只记录，由测试直接调用 direct_request 验证 TLP 路径
            SC_REPORT_INFO("pcie.rc_bus_ctrl", "枚举触发（骨架：无实际操作）");
        }
    } else {
        rval = rc_regs_[idx];
    }
}

// ── SMMU 窗口寄存器（P4：smmu_v3_model 接管）──
void rc_bus_ctrl::handle_smmu(uint64_t off, bool is_write, uint32_t val,
                              uint32_t& rval) {
    if (is_write) {
        if (!smmu_.reg_write(off, val)) {
            SC_REPORT_WARNING("pcie.rc_bus_ctrl",
                              ("SMMU 寄存器写越界 off=0x" + hex_str(off)).c_str());
        }
    } else {
        if (!smmu_.reg_read(off, rval)) {
            SC_REPORT_WARNING("pcie.rc_bus_ctrl",
                              ("SMMU 寄存器读越界 off=0x" + hex_str(off)).c_str());
        }
    }
}

// ── 通用同步 TLP 往返（cfg/mmio 共用；须在 SC_THREAD 上下文）──
bool rc_bus_ctrl::sync_tlp(const req_desc& desc, std::vector<uint8_t>& out,
                           CplStatus& st) {
    if (!sc_get_current_process_handle().valid()) {
        SC_REPORT_WARNING("pcie.rc_bus_ctrl", "sync_tlp 需在 SC_THREAD 上下文");
        return false;
    }

    cpl_pending_ = true;
    cpl_data_.clear();

    bool ok = engine_.request(desc, [this](CplStatus s,
                                           const std::vector<uint8_t>& d) {
        cpl_status_ = s;
        cpl_data_ = d;
        cpl_pending_ = false;
        cpl_done_ev_.notify(SC_ZERO_TIME);
    });
    if (!ok) {
        cpl_pending_ = false;
        return false;
    }

    while (cpl_pending_) wait(cpl_done_ev_);

    st = cpl_status_;
    out = cpl_data_;
    return st == CplStatus::SC;
}

// ── 同步配置往返（cfg_engine sync_fn）──
bool rc_bus_ctrl::sync_config(uint8_t bus, uint8_t dev, uint8_t fn,
                              uint16_t off, uint32_t& val, bool write) {
    req_desc desc;
    desc.txn_class = write ? TxnClass::CFG_WRITE : TxnClass::CFG_READ;
    desc.bus = bus; desc.dev = dev; desc.fn = fn;
    desc.reg_off = off;
    desc.requester_id = make_req_id(0, 0, 0);  // RC 自身
    if (write) {
        desc.data.resize(4);
        std::memcpy(desc.data.data(), &val, 4);
    }

    std::vector<uint8_t> out;
    CplStatus st = CplStatus::UR;
    if (!sync_tlp(desc, out, st)) return false;
    if (!write && out.size() >= 4) {
        std::memcpy(&val, out.data(), 4);
    }
    return true;
}

// ── 上行分流：DMA → 内存模型；Msg → 计数（P1+ 接 MSI 路由）──
void rc_bus_ctrl::handle_parse(const parse_result& pr) {
    switch (pr.txn_class) {
        case TxnClass::DMA_WRITE: {
            dma_write_cnt_++;
            // P3: MSI 地址窗口 → 中断路径（不写内存）
            if (pr.dma_addr >= map::MSI_ADDR_BASE &&
                pr.dma_addr < map::MSI_ADDR_BASE + map::MSI_ADDR_SIZE) {
                handle_msi(pr.dma_addr);
                break;
            }
            // P4: SMMU stage-2 转换（sid: POC 单设备 = 0）
            uint64_t pa = 0;
            if (!smmu_.translate(0, pr.dma_addr, pa)) {
                SC_REPORT_WARNING("pcie.rc_bus_ctrl",
                                  ("DMA_WRITE 转换故障: IPA=0x" + hex_str(pr.dma_addr) +
                                   "（未写入内存）").c_str());
                break;
            }
            mem_.write(pa, pr.tlp.payload.data(), pr.dma_len_bytes);
            SC_REPORT_INFO("pcie.rc_bus_ctrl",
                           ("DMA_WRITE IPA=0x" + hex_str(pr.dma_addr) +
                            " → PA=0x" + hex_str(pa) +
                            " len=" + std::to_string(pr.dma_len_bytes)).c_str());
            break;
        }
        case TxnClass::DMA_READ: {
            // P2: EP 读 host 内存 → 读内存模型 → 构造 CplD 发回
            dma_read_cnt_++;
            // P4: SMMU stage-2 转换
            uint64_t pa = 0;
            if (!smmu_.translate(0, pr.dma_addr, pa)) {
                SC_REPORT_WARNING("pcie.rc_bus_ctrl",
                                  ("DMA_READ 转换故障: IPA=0x" + hex_str(pr.dma_addr)).c_str());
                auto h = tlp_header::completion(make_req_id(0, 0, 0),
                                                static_cast<uint16_t>(pr.tlp.header.tag),
                                                pr.tlp.header.requester_id,
                                                CplStatus::UR, 0, false);
                engine_.send_tlp(tlp_transaction(h));
                break;
            }
            if (pa + pr.dma_len_bytes > mem_.size()) {
                SC_REPORT_WARNING("pcie.rc_bus_ctrl", "DMA_READ 越界");
                // UR 完成
                auto h = tlp_header::completion(make_req_id(0, 0, 0),
                                                static_cast<uint16_t>(pr.tlp.header.tag),
                                                pr.tlp.header.requester_id,
                                                CplStatus::UR, 0, false);
                engine_.send_tlp(tlp_transaction(h));
                break;
            }
            std::vector<uint8_t> data(pr.dma_len_bytes);
            mem_.read(pa, data.data(), data.size());
            auto h = tlp_header::completion(
                make_req_id(0, 0, 0), static_cast<uint16_t>(pr.tlp.header.tag),
                pr.tlp.header.requester_id, CplStatus::SC,
                static_cast<uint16_t>(data.size()),
                true, static_cast<uint16_t>(data.size() / 4));
            engine_.send_tlp(tlp_transaction(h, data));
            SC_REPORT_INFO("pcie.rc_bus_ctrl",
                           ("DMA_READ IPA=0x" + hex_str(pr.dma_addr) +
                            " → PA=0x" + hex_str(pa) +
                            " len=" + std::to_string(pr.dma_len_bytes) +
                            " → CplD 已发回").c_str());
            break;
        }
        case TxnClass::MSG_INTX:
        case TxnClass::MSG_ERR: {
            msg_cnt_++;
            SC_REPORT_INFO("pcie.rc_bus_ctrl",
                           ("Msg code=0x" + hex_str(pr.msg_code)).c_str());
            break;
        }
        default:
            SC_REPORT_INFO("pcie.rc_bus_ctrl", "上行事务未处理");
            break;
    }
}

}  // namespace pcie
