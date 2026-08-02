// test_sc_integration.cpp — SystemC 层集成测试（P0 里程碑）
// 覆盖：
//   1. cpu 域：QEMU 写 RC_CFG 寄存器 → 读回
//   2. TLP 下行：direct_request(CfgRd0) → mock VIP 收到 TLP（字段校验）→ Cpl 返回 → 回调
//   3. TLP 上行：mock VIP 发 DMA MWr → rc_bus_ctrl 分流 → 内存模型写入
//   4. 挂起表超时：无响应 → completion timeout 上报
#include <systemc.h>
#include <tlm.h>
#include <cassert>
#include <cstdio>
#include "host_model.h"
#include "tlp_ext.h"

using namespace pcie;
using namespace sc_core;

// ── Mock VIP：TLP 发起（上行发送；定义在 tgt 前以满足 send_cpl 调用）──
struct mock_vip_init : sc_module,
                       tlm::tlm_bw_transport_if<>,
                       tlm::tlm_fw_transport_if<> {
    tlm::tlm_initiator_socket<> sock{"sock"};
    tlm::tlm_target_socket<>    resp_sock{"resp_sock"};  // 收 RC 的 CplD 响应
    // 收到的响应记录
    std::vector<tlp_transaction> rx_resps;

    SC_CTOR(mock_vip_init) {
        sock.bind(*this);
        resp_sock.bind(*this);
    }

    // resp_sock 的 fw 侧（收 CplD）
    void b_transport(tlm::tlm_generic_payload& gp, sc_time& delay) override {
        tlp_transaction tlp;
        if (tlp_transaction::from_bytes(gp.get_data_ptr(),
                                        gp.get_data_length(), tlp)) {
            rx_resps.push_back(tlp);
        }
        gp.set_response_status(tlm::TLM_OK_RESPONSE);
        delay += sc_time(1, SC_NS);
    }
    tlm::tlm_sync_enum nb_transport_fw(tlm::tlm_generic_payload&, tlm::tlm_phase&, sc_time&) override { return tlm::TLM_COMPLETED; }
    bool get_direct_mem_ptr(tlm::tlm_generic_payload&, tlm::tlm_dmi&) override { return false; }
    unsigned transport_dbg(tlm::tlm_generic_payload&) override { return 0; }

    // 上行发一个 Cpl（模拟 EP 完成）
    void send_cpl(uint16_t tag, CplStatus st,
                  const std::vector<uint8_t>& data = {}) {
        auto h = tlp_header::completion(make_req_id(0, 0, 0), tag,
                                        make_req_id(0, 0, 0), st,
                                        static_cast<uint16_t>(data.size()),
                                        !data.empty());
        if (data.empty()) h.length = 0;
        tlp_transaction tlp(h, data);
        auto bytes = tlp.to_bytes();
        tlm::tlm_generic_payload gp;
        gp.set_command(tlm::TLM_WRITE_COMMAND);
        gp.set_address(0);
        gp.set_data_ptr(bytes.data());
        gp.set_data_length(static_cast<unsigned int>(bytes.size()));
        gp.set_streaming_width(static_cast<unsigned int>(bytes.size()));
        sc_time delay = sc_time(1, SC_NS);
        sock->b_transport(gp, delay);
    }

    // 上行发一个 DMA MRd（模拟 EP 读 host 内存）
    void send_dma_read(uint64_t addr, uint16_t dw_len, uint16_t tag = 0x50) {
        auto h = tlp_header::mmio_read(make_req_id(2, 0, 0), tag, addr);
        h.length = dw_len;
        tlp_transaction tlp(h);
        auto bytes = tlp.to_bytes();
        tlm::tlm_generic_payload gp;
        gp.set_command(tlm::TLM_WRITE_COMMAND);
        gp.set_address(0);
        gp.set_data_ptr(bytes.data());
        gp.set_data_length(static_cast<unsigned int>(bytes.size()));
        gp.set_streaming_width(static_cast<unsigned int>(bytes.size()));
        sc_time delay = sc_time(1, SC_NS);
        sock->b_transport(gp, delay);
    }

    // 上行发一个 MSI（模拟 EP 发 MSI 中断：写 MSI 地址）
    void send_msi(uint32_t vector) {
        std::vector<uint8_t> data = {0x00, 0x00, 0x00, 0x00};
        uint64_t addr = map::MSI_ADDR_BASE + static_cast<uint64_t>(vector) * 4;
        send_dma_write(addr, data);
    }

    // 上行发一个 DMA MWr（模拟 EP 写 host 内存）
    void send_dma_write(uint64_t addr, const std::vector<uint8_t>& data) {
        auto h = tlp_header::mmio_write(make_req_id(2, 0, 0), 0x77, addr,
                                        static_cast<uint16_t>(data.size() / 4));
        tlp_transaction tlp(h, data);
        auto bytes = tlp.to_bytes();
        tlm::tlm_generic_payload gp;
        gp.set_command(tlm::TLM_WRITE_COMMAND);
        gp.set_address(0);
        gp.set_data_ptr(bytes.data());
        gp.set_data_length(static_cast<unsigned int>(bytes.size()));
        gp.set_streaming_width(static_cast<unsigned int>(bytes.size()));
        sc_time delay = sc_time(1, SC_NS);
        sock->b_transport(gp, delay);
    }

    tlm::tlm_sync_enum nb_transport_bw(tlm::tlm_generic_payload&, tlm::tlm_phase&, sc_time&) override { return tlm::TLM_COMPLETED; }
    void invalidate_direct_mem_ptr(sc_dt::uint64, sc_dt::uint64) override {}
};

// ── Mock VIP：TLP 目标（下行接收，含模拟 DUT 配置空间）──
struct mock_vip_tgt : sc_module, tlm::tlm_fw_transport_if<> {
    tlm::tlm_target_socket<> sock{"sock"};
    // 记录收到的下行 TLP
    std::vector<tlp_transaction> rx_tlps;
    CplStatus respond_status = CplStatus::SC;

    // 模拟 DUT 配置空间（256B）
    uint8_t cfg_space[256] = {0};
    unsigned cfg_read_cnt = 0, cfg_write_cnt = 0;

    // BAR 实现表（模拟真实 DUT 的探测语义）
    bool bar_impl[6] = {true, false, false, false, false, false};
    uint32_t bar_size[6] = {0x1000, 0, 0, 0, 0, 0};

    SC_CTOR(mock_vip_tgt) {
        sock.bind(*this);
        init_cfg_space();
    }

    // 模拟 EP：VID/DID/BAR0(4KB 32-bit)/Class=网络控制器
    void init_cfg_space() {
        uint16_t vid = 0x1AF4, did = 0x0001;
        cfg_space[0x00] = vid & 0xFF; cfg_space[0x01] = vid >> 8;
        cfg_space[0x02] = did & 0xFF; cfg_space[0x03] = did >> 8;
        cfg_space[0x08] = 0x00;  // class: base=0x02 网络控制器
        cfg_space[0x09] = 0x00;
        cfg_space[0x0A] = 0x00;
        cfg_space[0x0B] = 0x02;
        cfg_space[0x0C] = 0x00;  // header type 0（单功能）
        cfg_space[0x0D] = 0x00;
        cfg_space[0x0E] = 0x00;
        cfg_space[0x0F] = 0x00;
    }

    // BAR 读（探测语义：写全 1 后读回 size 编码；未实现读回 0）
    uint32_t bar_read(uint16_t off) {
        int idx = (off - 0x10) / 4;
        if (idx < 0 || idx > 5) return 0;
        if (!bar_impl[idx]) return 0;  // 未实现
        uint32_t cur = 0;
        std::memcpy(&cur, cfg_space + off, 4);
        if (cur == 0xFFFFFFFF) {  // 探测状态
            uint32_t sz_enc = static_cast<uint32_t>(~(bar_size[idx] - 1)) & 0xFFFFFFF0;
            return sz_enc | 0;  // 32-bit 非预取 mem
        }
        return cur;
    }

    // 上行发送通道（由 sc_main 注入；用于发 Cpl 响应）
    mock_vip_init* init_ = nullptr;
    void set_init(mock_vip_init* p) { init_ = p; }

    // DUT MMIO 空间（BAR0，4KB 模拟寄存器）
    uint8_t mmio_space[4096] = {0};
    uint64_t bar0_base_ = 0;
    void set_bar_base(uint64_t b) { bar0_base_ = b; }

    // P5: TX 处理——host 内存读取器（测试胶水注入）+ TX 环基址
    std::function<bool(uint64_t, void*, uint32_t)> mem_reader;
    uint64_t tx_ring_base_ = 0;
    unsigned tx_ok = 0, tx_bad = 0;
    void set_tx_ring(uint64_t base, std::function<bool(uint64_t, void*, uint32_t)> r) {
        tx_ring_base_ = base;
        mem_reader = std::move(r);
    }

    void b_transport(tlm::tlm_generic_payload& gp, sc_time& delay) override {
        tlp_transaction tlp;
        bool ok = tlp_transaction::from_bytes(gp.get_data_ptr(),
                                              gp.get_data_length(), tlp);
        if (!ok) { gp.set_response_status(tlm::TLM_COMMAND_ERROR_RESPONSE); return; }
        rx_tlps.push_back(tlp);

        // Cfg 请求 → 模拟 DUT 配置空间响应（经上行通道发 Cpl）
        if (tlp.header.is_cfg() && init_) {
            uint16_t off = tlp.header.reg_off;
            uint16_t tag = static_cast<uint16_t>(tlp.header.tag);
            // 仅 bus0:dev0:fn0 有配置空间；其他位置返回全 1（视为不存在）
            if (tlp.header.target_bus != 0 || tlp.header.target_dev != 0 ||
                tlp.header.target_fn != 0) {
                std::vector<uint8_t> ff(4, 0xFF);
                init_->send_cpl(tag, CplStatus::SC, ff);
            } else if (off + 4 > 256) {
                init_->send_cpl(tag, CplStatus::UR, {});  // 配置空间外 → UR
            } else if (off >= 0x10 && off <= 0x27) {
                // BAR 区域（探测语义：全 1 写入即探测状态，bar_read 返回 size 编码）
                if (tlp.header.is_write()) {
                    std::memcpy(cfg_space + off, tlp.payload.data(), 4);
                    cfg_write_cnt++;
                    init_->send_cpl(tag, CplStatus::SC, {});
                } else {
                    cfg_read_cnt++;
                    uint32_t bar = bar_read(off);
                    std::vector<uint8_t> data = {
                        static_cast<uint8_t>(bar), static_cast<uint8_t>(bar >> 8),
                        static_cast<uint8_t>(bar >> 16), static_cast<uint8_t>(bar >> 24)};
                    init_->send_cpl(tag, CplStatus::SC, data);
                }
            } else if (tlp.header.is_write()) {
                std::memcpy(cfg_space + off, tlp.payload.data(), 4);
                cfg_write_cnt++;
                init_->send_cpl(tag, CplStatus::SC, {});
            } else {
                cfg_read_cnt++;
                std::vector<uint8_t> data(cfg_space + off, cfg_space + off + 4);
                init_->send_cpl(tag, CplStatus::SC, data);
            }
            gp.set_response_status(tlm::TLM_OK_RESPONSE);
            delay += sc_time(5, SC_NS);
            return;
        }

        // MMIO 请求（P2/P5）：模拟 DUT BAR0 寄存器空间
        if (tlp.header.is_mem() && init_) {
            uint16_t tag = static_cast<uint16_t>(tlp.header.tag);
            uint64_t off = tlp.header.address - bar0_base_;
            if (bar0_base_ == 0 || off >= sizeof(mmio_space)) {
                init_->send_cpl(tag, CplStatus::UR, {});
            } else if (off == 0x00 && tlp.header.is_write() && mem_reader) {
                // P5: TX doorbell——DUT 读描述符环 + 校验载荷
                uint32_t door = 0;
                std::memcpy(&door, tlp.payload.data(), 4);
                uint64_t daddr = tx_ring_base_ + static_cast<uint64_t>(door) * 16;
                uint8_t raw[16] = {0};
                if (!mem_reader(daddr, raw, 16)) {
                    tx_bad++;
                } else {
                    uint64_t buf_addr = 0;
                    for (int b = 0; b < 8; b++) buf_addr |= static_cast<uint64_t>(raw[b]) << (8 * b);
                    uint32_t len = static_cast<uint32_t>(raw[8]) |
                                   (static_cast<uint32_t>(raw[9]) << 8) |
                                   (static_cast<uint32_t>(raw[10]) << 16) |
                                   (static_cast<uint32_t>(raw[11]) << 24);
                    uint32_t seq = static_cast<uint32_t>(raw[12]) |
                                   (static_cast<uint32_t>(raw[13]) << 8) |
                                   (static_cast<uint32_t>(raw[14]) << 16) |
                                   (static_cast<uint32_t>(raw[15]) << 24);
                    std::vector<uint8_t> pkt(len);
                    if (mem_reader(buf_addr, pkt.data(), len) &&
                        nic_behavior::payload_valid(pkt, seq)) {
                        tx_ok++;
                    } else {
                        tx_bad++;
                    }
                }
                std::memcpy(mmio_space + off, tlp.payload.data(), 4);
                init_->send_cpl(tag, CplStatus::SC, {});
            } else if (tlp.header.is_write()) {
                std::memcpy(mmio_space + off, tlp.payload.data(),
                            tlp.payload.size());
                init_->send_cpl(tag, CplStatus::SC, {});
            } else {
                // 读请求无 payload：长度在 header.length（DW）——不能读 payload.size()！
                size_t n = tlp.header.payload_bytes();
                if (off + n > sizeof(mmio_space)) {
                    init_->send_cpl(tag, CplStatus::UR, {});
                    gp.set_response_status(tlm::TLM_OK_RESPONSE);
                    delay += sc_time(5, SC_NS);
                    return;
                }
                std::vector<uint8_t> data(n);
                std::memcpy(data.data(), mmio_space + off, n);
                init_->send_cpl(tag, CplStatus::SC, data);
            }
            gp.set_response_status(tlm::TLM_OK_RESPONSE);
            delay += sc_time(5, SC_NS);
            return;
        }

        // 其他：仅记录，回 SC
        gp.set_response_status(tlm::TLM_OK_RESPONSE);
        delay += sc_time(5, SC_NS);
    }
    tlm::tlm_sync_enum nb_transport_fw(tlm::tlm_generic_payload&, tlm::tlm_phase&, sc_time&) override { return tlm::TLM_COMPLETED; }
    bool get_direct_mem_ptr(tlm::tlm_generic_payload&, tlm::tlm_dmi&) override { return false; }
    unsigned transport_dbg(tlm::tlm_generic_payload&) override { return 0; }
};

// ── 测试驱动器 ──
struct test_driver : sc_module, tlm::tlm_bw_transport_if<> {
    host_model& host;
    mock_vip_tgt& vip_tgt;
    mock_vip_init& vip_init;
    tlm::tlm_initiator_socket<> cpu_sock{"cpu_sock"};  // 对 host.s_cpu() 的 initiator
    sc_in<bool> irq_in[4];  // 中断线（P3：绑 host.irq(0..3)）
    unsigned irq_cnt[4] = {0, 0, 0, 0};
    int failures = 0;

    SC_HAS_PROCESS(test_driver);  // 自定义构造函数需显式声明

    test_driver(sc_module_name nm, host_model& h, mock_vip_tgt& t, mock_vip_init& i)
        : sc_module(nm), host(h), vip_tgt(t), vip_init(i) {
        cpu_sock.bind(*this);
        SC_THREAD(run_all);
    }

    // tlm_bw_transport_if（cpu_sock 的 bw 侧）
    tlm::tlm_sync_enum nb_transport_bw(tlm::tlm_generic_payload&, tlm::tlm_phase&, sc_time&) override { return tlm::TLM_COMPLETED; }
    void invalidate_direct_mem_ptr(sc_dt::uint64, sc_dt::uint64) override {}

    void run_all() {
        test_cpu_regs();
        test_cfg_rd_roundtrip();
        test_dma_write();
        test_timeout();
        test_enumeration();   // P1
        test_bar_assign();    // P1
        test_cfg_ur();        // P1
        test_mmio_roundtrip(); // P2
        test_mmio_edge();      // P2
        test_dma_read();       // P2
        test_msi_single();     // P3
        test_msi_burst();      // P3
        test_msi_ignored();    // P3
        test_smmu_bypass();    // P4
        test_smmu_translate(); // P4
        test_smmu_fault();     // P4
        test_nic_tx();         // P5
        test_nic_rx();         // P5
        test_nic_multiqueue(); // P5
        test_nic_coalesce();   // P5
        std::printf("==== SC 集成测试: %s ====\n",
                    failures ? "有失败" : "全部通过");
        if (failures) sc_stop();
    }

    void check(bool cond, const char* what) {
        if (cond) { std::printf("  PASS %s\n", what); }
        else { std::printf("  FAIL %s\n", what); failures++; }
    }

    // 1) cpu 域寄存器读写
    void test_cpu_regs() {
        uint32_t val = 0xDEADBEEF;
        tlm::tlm_generic_payload gp;
        gp.set_command(tlm::TLM_WRITE_COMMAND);
        gp.set_address(map::RC_CFG_BASE + 0x10);
        gp.set_data_ptr(reinterpret_cast<unsigned char*>(&val));
        gp.set_data_length(4);
        gp.set_streaming_width(4);
        sc_time d = SC_ZERO_TIME;
        cpu_sock->b_transport(gp, d);
        check(gp.get_response_status() == tlm::TLM_OK_RESPONSE, "cpu 写 RC_CFG 寄存器");

        uint32_t rd = 0;
        gp.set_command(tlm::TLM_READ_COMMAND);
        gp.set_address(map::RC_CFG_BASE + 0x10);
        gp.set_data_ptr(reinterpret_cast<unsigned char*>(&rd));
        cpu_sock->b_transport(gp, d);
        check(gp.get_response_status() == tlm::TLM_OK_RESPONSE && rd == 0xDEADBEEF,
              "cpu 读回一致");
    }

    // 2) CfgRd0 TLP 下行 → mock VIP → Cpl 返回 → 回调
    void test_cfg_rd_roundtrip() {
        bool cb_called = false;
        CplStatus cb_st = CplStatus::UR;
        std::vector<uint8_t> cpl_data;

        req_desc desc;
        desc.txn_class = TxnClass::CFG_READ;
        desc.bus = 0; desc.dev = 0; desc.fn = 0;
        desc.reg_off = 0x00;  // Vendor ID
        desc.requester_id = make_req_id(0, 0, 0);

        bool ok = host.bus().direct_request(
            desc, [&](CplStatus s, const std::vector<uint8_t>& d) {
                cb_called = true; cb_st = s; cpl_data = d;
            });
        check(ok, "direct_request 发出");

        // mock VIP 应收到 CfgRd0
        check(vip_tgt.rx_tlps.size() == 1, "VIP 收到 1 个 TLP");
        if (vip_tgt.rx_tlps.size() == 1) {
            const auto& h = vip_tgt.rx_tlps[0].header;
            check(h.is_cfg() && !h.is_write(), "TLP 是 CfgRd0");
            check(h.reg_off == 0x00, "reg_off=0 (Vendor ID)");
            check(h.tag == 0, "tag=0（首个分配）");
        }

        // 模拟 EP 完成：Cpl SC + 4B 数据（off0 = VID+DID = 0x00011AF4）
        // 注: mock 已自动响应此请求；手动 send_cpl 的 tag 0 已释放（未命中 WARN 属预期）
        std::vector<uint8_t> data = {0xF4, 0x1A, 0x01, 0x00};
        vip_init.send_cpl(0, CplStatus::SC, data);

        check(cb_called, "完成回调触发");
        check(cb_st == CplStatus::SC, "回调状态 SC");
        check(cpl_data == data, "回调数据正确（VID+DID 回填）");
    }

    // 3) 上行 DMA MWr → 内存模型
    void test_dma_write() {
        std::vector<uint8_t> payload(8, 0xAB);
        vip_init.send_dma_write(0x80000ULL, payload);  // 1MB 内存模型内

        check(host.bus().dma_write_cnt_ == 1, "DMA_WRITE 分流计数");
        // 校验内存模型内容
        uint8_t buf[8] = {0};
        bool r = host.mem().read(0x80000ULL, buf, 8);
        bool same = r && std::memcmp(buf, payload.data(), 8) == 0;
        check(same, "DMA 数据写入内存模型");
    }

    // 5) P1 枚举：配置引擎递归扫描（走 ECAM→TLP→mock DUT 全链路）
    void test_enumeration() {
        int n = host.bus().cfg().enumerate(2);
        check(n == 1, "枚举到 1 个设备");
        auto* dev = host.bus().cfg().find(0, 0, 0);
        check(dev != nullptr, "设备表有 bus0:dev0:fn0");
        if (dev) {
            check(dev->vid == 0x1AF4, "VID 正确 (0x1AF4)");
            check(dev->did == 0x0001, "DID 正确");
            check(dev->class_code == 0x02, "Class=网络控制器");
            check(dev->bar_size[0] == 0x1000, "BAR0 size 探测 4KB");
            check(dev->bar_size[1] == 0, "BAR1 未实现（size=0）");
        }
        // mock 侧计数（枚举共 N 次配置读）
        check(vip_tgt.cfg_read_cnt > 0, "mock DUT 收到配置读");
    }

    // 6) P1 BAR 分配：分配 → 写回 DUT → DUT 侧验证
    void test_bar_assign() {
        auto* dev = host.bus().cfg().find(0, 0, 0);
        if (!dev) { check(false, "设备存在（前置）"); return; }
        uint64_t base = host.bus().cfg().assign_bar(*dev, 0);
        check(base == map::MMIO_BASE, "BAR0 分配在 MMIO 窗口起始");
        vip_tgt.set_bar_base(base);  // mock DUT 知道自己的 BAR0 地址
        // DUT 侧验证：mock 配置空间 BAR0 == 分配值
        uint32_t dut_bar = 0;
        std::memcpy(&dut_bar, vip_tgt.cfg_space + 0x10, 4);
        check((dut_bar & 0xFFFFFFF0) == (static_cast<uint32_t>(base) & 0xFFFFFFF0),
              "DUT 侧 BAR0 写回正确");
        check(dev->bar_alloc[0] == base, "设备表 BAR 记录正确");
    }

    // 7) P1 错误路径：配置空间外访问 → UR → 读回全 1
    void test_cfg_ur() {
        // 经 cpu 域 ECAM 地址读 off 0x100（mock 返回 UR）
        tlm::tlm_generic_payload gp;
        uint32_t rd = 0;
        gp.set_command(tlm::TLM_READ_COMMAND);
        gp.set_address(map::ECAM_BASE + map::ECAM_OFFSET(0, 0, 0, 0x100));
        gp.set_data_ptr(reinterpret_cast<unsigned char*>(&rd));
        gp.set_data_length(4);
        gp.set_streaming_width(4);
        sc_time d = SC_ZERO_TIME;
        cpu_sock->b_transport(gp, d);
        check(gp.get_response_status() == tlm::TLM_OK_RESPONSE, "UR 后 cpu 域仍 OK");
        check(rd == 0xFFFFFFFF, "UR 读回全 1（PCIe 语义）");
    }

    // 8) P2 MMIO 往返：guest 写 DUT BAR0 寄存器 → 读回一致
    void test_mmio_roundtrip() {
        auto* dev = host.bus().cfg().find(0, 0, 0);
        if (!dev || dev->bar_alloc[0] == 0) { check(false, "BAR0 已分配（前置）"); return; }
        uint64_t bar0 = dev->bar_alloc[0];

        // guest 写 BAR0+0x100
        uint32_t w = 0xCAFEBABE;
        tlm::tlm_generic_payload gp;
        gp.set_command(tlm::TLM_WRITE_COMMAND);
        gp.set_address(bar0 + 0x100);
        gp.set_data_ptr(reinterpret_cast<unsigned char*>(&w));
        gp.set_data_length(4);
        gp.set_streaming_width(4);
        sc_time d = SC_ZERO_TIME;
        cpu_sock->b_transport(gp, d);
        check(gp.get_response_status() == tlm::TLM_OK_RESPONSE, "MMIO 写 OK");

        // guest 读回
        uint32_t rd = 0;
        gp.set_command(tlm::TLM_READ_COMMAND);
        gp.set_address(bar0 + 0x100);
        gp.set_data_ptr(reinterpret_cast<unsigned char*>(&rd));
        cpu_sock->b_transport(gp, d);
        check(gp.get_response_status() == tlm::TLM_OK_RESPONSE && rd == 0xCAFEBABE,
              "MMIO 读回一致");

        // DUT 侧验证
        uint32_t dut = 0;
        std::memcpy(&dut, vip_tgt.mmio_space + 0x100, 4);
        check(dut == 0xCAFEBABE, "DUT 侧 MMIO 寄存器正确");
    }

    // 9) P2 边界：非 4B 对齐 / 超 256B / 未分配 BAR 地址 → 拒绝
    void test_mmio_edge() {
        auto* dev = host.bus().cfg().find(0, 0, 0);
        if (!dev || dev->bar_alloc[0] == 0) { check(false, "BAR0 已分配（前置）"); return; }
        uint64_t bar0 = dev->bar_alloc[0];
        sc_time d = SC_ZERO_TIME;

        // 非 4B 对齐读（len=2）
        uint32_t rd = 0;
        tlm::tlm_generic_payload gp;
        gp.set_command(tlm::TLM_READ_COMMAND);
        gp.set_address(bar0 + 0x102);
        gp.set_data_ptr(reinterpret_cast<unsigned char*>(&rd));
        gp.set_data_length(2);
        gp.set_streaming_width(2);
        cpu_sock->b_transport(gp, d);
        check(gp.get_response_status() == tlm::TLM_COMMAND_ERROR_RESPONSE,
              "非 4B 对齐拒绝");

        // 超长（512B）
        std::vector<uint8_t> buf(512);
        gp.set_command(tlm::TLM_READ_COMMAND);
        gp.set_address(bar0);
        gp.set_data_ptr(buf.data());
        gp.set_data_length(512);
        gp.set_streaming_width(512);
        cpu_sock->b_transport(gp, d);
        check(gp.get_response_status() == tlm::TLM_COMMAND_ERROR_RESPONSE,
              "超 256B 拒绝");

        // 未分配 BAR 地址（BAR 外）
        gp.set_command(tlm::TLM_READ_COMMAND);
        gp.set_address(bar0 + 0x1000 + 0x100);  // 越过 BAR0 4KB
        gp.set_data_ptr(reinterpret_cast<unsigned char*>(&rd));
        gp.set_data_length(4);
        gp.set_streaming_width(4);
        cpu_sock->b_transport(gp, d);
        check(gp.get_response_status() == tlm::TLM_COMMAND_ERROR_RESPONSE,
              "BAR 外地址拒绝");
    }

    // 10) P2 DMA 读：EP 读 host 内存 → CplD 数据回填
    void test_dma_read() {
        // 先写 host 内存
        std::vector<uint8_t> payload(8, 0x5A);
        host.mem().write(0x80000, payload.data(), 8);
        // EP 发起 DMA 读
        vip_init.send_dma_read(0x80000, 2);  // 2 DW = 8B

        check(host.bus().dma_read_cnt_ == 1, "DMA_READ 分流计数");
        // mock（EP 侧）收到 CplD 响应
        check(vip_init.rx_resps.size() == 1, "EP 收到 CplD 响应");
        if (vip_init.rx_resps.size() == 1) {
            const auto& cpl = vip_init.rx_resps[0];
            check(cpl.header.is_cpl() && cpl.header.has_data(), "响应是 CplD");
            check(cpl.header.status == CplStatus::SC, "CplD SC");
            check(cpl.header.tag == 0x50, "CplD tag 匹配请求");
            check(cpl.payload == payload, "CplD 数据 == host 内存内容");
        }
    }

    // 11) P3 MSI 单发：EP 写 MSI 地址 → 中断线 → guest 计数
    void test_msi_single() {
        host.bus().msi_map_clear();
        host.bus().msi_map_add(0, 0);  // vector 0 → SPI 0
        vip_init.send_msi(0);
        wait(irq_in[0].posedge_event());
        irq_cnt[0]++;
        wait(sc_time(200, SC_NS));  // 等脉冲结束（100ns + 余量）
        check(irq_cnt[0] == 1, "MSI 单发 → 中断线 1 次");
        check(host.bus().msi_cnt_ == 1, "MSI 计数 1");
    }

    // 12) P3 连续 100 次 MSI 无丢失
    void test_msi_burst() {
        for (int i = 0; i < 100; i++) {
            vip_init.send_msi(0);
            wait(irq_in[0].posedge_event());
            irq_cnt[0]++;
            // 等脉冲结束（100ns 脉冲 + 余量），否则下一次 write(true) 无 posedge
            wait(sc_time(200, SC_NS));
        }
        check(irq_cnt[0] == 101, "连续 100 次无丢失（累计 101）");
        check(host.bus().msi_cnt_ == 101, "MSI 计数 101");
    }

    // 13) P3 未使能 MSI → WARN + 不触发中断
    void test_msi_ignored() {
        unsigned before = host.bus().msi_ignored_cnt_;
        vip_init.send_msi(5);  // vector 5 无映射
        wait(sc_time(1000, SC_NS));
        check(host.bus().msi_ignored_cnt_ == before + 1, "未使能 MSI 被忽略（WARN）");
        check(host.bus().msi_cnt_ == 101, "有效 MSI 计数不变");
        check(irq_cnt[0] == 101, "中断线未触发");
    }

    // 14) P4 SMMU 旁路：未使能 → 恒等映射
    void test_smmu_bypass() {
        // 确保 SMMU 关闭
        uint32_t cr0 = 0;
        tlm::tlm_generic_payload gp;
        gp.set_command(tlm::TLM_WRITE_COMMAND);
        gp.set_address(map::SMMU_BASE + smmu_v3_model::REG_CR0);
        gp.set_data_ptr(reinterpret_cast<unsigned char*>(&cr0));
        gp.set_data_length(4);
        gp.set_streaming_width(4);
        sc_time d = SC_ZERO_TIME;
        cpu_sock->b_transport(gp, d);
        check(gp.get_response_status() == tlm::TLM_OK_RESPONSE, "SMMU_CR0 写（关闭）");

        // DMA 写直接落到 IPA
        std::vector<uint8_t> payload(4, 0x11);
        vip_init.send_dma_write(0x10000, payload);
        uint8_t buf[4] = {0};
        host.mem().read(0x10000, buf, 4);
        check(std::memcmp(buf, payload.data(), 4) == 0, "旁路：DMA 落到 IPA");
        check(host.bus().smmu().fault_cnt() == 0, "旁路：无故障");
    }

    // 15) P4 SMMU 转换：使能 + 直写 TLB → DMA 转换落点
    void test_smmu_translate() {
        auto& smmu = host.bus().smmu();
        // 使能 SMMU
        uint32_t cr0 = 0x1;
        tlm::tlm_generic_payload gp;
        gp.set_command(tlm::TLM_WRITE_COMMAND);
        gp.set_address(map::SMMU_BASE + smmu_v3_model::REG_CR0);
        gp.set_data_ptr(reinterpret_cast<unsigned char*>(&cr0));
        gp.set_data_length(4);
        gp.set_streaming_width(4);
        sc_time d = SC_ZERO_TIME;
        cpu_sock->b_transport(gp, d);
        check(gp.get_response_status() == tlm::TLM_OK_RESPONSE, "SMMU_CR0 写（使能）");

        // 直写转换表：sid 0, IPA 0x10000 → PA 0x20000, size 4KB
        struct { uint64_t off; uint32_t val; } wr[] = {
            {smmu_v3_model::REG_TEST_TLB_SID, 0},
            {smmu_v3_model::REG_TEST_TLB_IPA, 0x10000},
            {smmu_v3_model::REG_TEST_TLB_PA, 0x20000},
            {smmu_v3_model::REG_TEST_TLB_SIZE, 0x1000},
            {smmu_v3_model::REG_TEST_TLB_COMMIT, 1},
        };
        for (auto& w : wr) {
            gp.set_command(tlm::TLM_WRITE_COMMAND);
            gp.set_address(map::SMMU_BASE + w.off);
            gp.set_data_ptr(reinterpret_cast<unsigned char*>(&w.val));
            gp.set_data_length(4);
            cpu_sock->b_transport(gp, d);
            check(gp.get_response_status() == tlm::TLM_OK_RESPONSE, "SMMU TLB 写入");
        }
        check(smmu.tlb_size() == 1, "TLB 1 条表项");

        // DMA 写 IPA 0x10000 → 应落到 PA 0x20000
        std::vector<uint8_t> payload(4, 0x22);
        vip_init.send_dma_write(0x10000, payload);
        uint8_t at_pa[4] = {0}, at_ipa[4] = {0};
        host.mem().read(0x20000, at_pa, 4);
        host.mem().read(0x10000, at_ipa, 4);
        check(std::memcmp(at_pa, payload.data(), 4) == 0, "DMA 转换落点 = PA 0x20000");
        // 注: IPA 0x10000 有旁路测试残留 0x11——断言「未被本次 0x22 写入」即可
        check(at_ipa[0] != 0x22, "IPA 0x10000 未被写（转换生效）");
    }

    // 16) P4 SMMU 故障：无转换条目 → 不写入 + 故障计数
    void test_smmu_fault() {
        auto& smmu = host.bus().smmu();
        unsigned before = smmu.fault_cnt();
        // 预置哨兵值（mem 初始全 0，用 0xFF 区分）
        uint8_t sentinel[4] = {0xFF, 0xFF, 0xFF, 0xFF};
        host.mem().write(0x50000, sentinel, 4);
        std::vector<uint8_t> payload(4, 0x33);
        vip_init.send_dma_write(0x50000, payload);  // 无 TLB 条目
        check(smmu.fault_cnt() == before + 1, "转换故障计数 +1");
        uint8_t buf[4] = {0};
        host.mem().read(0x50000, buf, 4);
        check(buf[0] == 0xFF, "故障：内存未被写入（哨兵保持）");

        // 故障记录可读（EVENTQ 语义）
        uint32_t fr = 0;
        tlm::tlm_generic_payload gp;
        gp.set_command(tlm::TLM_READ_COMMAND);
        gp.set_address(map::SMMU_BASE + smmu_v3_model::REG_FAULT_REC);
        gp.set_data_ptr(reinterpret_cast<unsigned char*>(&fr));
        gp.set_data_length(4);
        sc_time d = SC_ZERO_TIME;
        cpu_sock->b_transport(gp, d);
        check((fr & 0x8000'0000) != 0, "故障记录可读（故障标记）");

        // 恢复：关 SMMU（不影响后续测试）
        uint32_t cr0 = 0;
        gp.set_command(tlm::TLM_WRITE_COMMAND);
        gp.set_address(map::SMMU_BASE + smmu_v3_model::REG_CR0);
        gp.set_data_ptr(reinterpret_cast<unsigned char*>(&cr0));
        cpu_sock->b_transport(gp, d);
    }

    // 17) P5 TX：guest 构造描述符+包 → doorbell → DUT 解析校验
    void test_nic_tx() {
        auto& nic = host.bus().nic();
        nic.set_ring(0x200000, 64, 4);
        // mock DUT 的 TX 环与内存读取器
        vip_tgt.set_tx_ring(0x200000,
            [this](uint64_t a, void* p, uint32_t n) {
                return host.mem().read(a, static_cast<uint8_t*>(p), n);
            });

        // guest 构造 TX 描述符（qid0 idx0）+ 包数据
        std::vector<uint8_t> pkt = nic_behavior::make_payload(99, 64);
        host.mem().write(0x400000, pkt.data(), 64);
        nic_behavior::desc txd;
        txd.buf_addr = 0x400000; txd.len = 64; txd.seq = 99;
        uint8_t raw[16];
        for (int b = 0; b < 8; b++) raw[b] = static_cast<uint8_t>(txd.buf_addr >> (8 * b));
        raw[8] = 64; raw[9] = 0; raw[10] = 0; raw[11] = 0;
        raw[12] = 99; raw[13] = 0; raw[14] = 0; raw[15] = 0;
        host.mem().write(0x200000, raw, 16);

        // doorbell 写 DUT 寄存器 0x00 = idx 0
        uint32_t door = 0;
        tlm::tlm_generic_payload gp;
        gp.set_command(tlm::TLM_WRITE_COMMAND);
        gp.set_address(host.bus().cfg().find(0, 0, 0)->bar_alloc[0] + 0x00);
        gp.set_data_ptr(reinterpret_cast<unsigned char*>(&door));
        gp.set_data_length(4);
        gp.set_streaming_width(4);
        sc_time d = SC_ZERO_TIME;
        cpu_sock->b_transport(gp, d);
        check(gp.get_response_status() == tlm::TLM_OK_RESPONSE, "TX doorbell OK");
        std::printf("  [dbg] tx_ok=%u tx_bad=%u\n", vip_tgt.tx_ok, vip_tgt.tx_bad);
        check(vip_tgt.tx_ok == 1 && vip_tgt.tx_bad == 0,
              "DUT 校验 TX 包载荷一致");
    }

    // 18) P5 RX：注入 16 包（聚合 8）→ DMA 写 + MSI → guest 回收无丢包
    void test_nic_rx() {
        auto& nic = host.bus().nic();
        const int NPKT = 16, COAL = 8, PLEN = 128;
        unsigned irq_before = irq_cnt[0];

        for (int i = 0; i < NPKT; i++) {
            uint64_t buf = 0x300000 + static_cast<uint64_t>(i) * 256;
            std::vector<uint8_t> pkt = nic_behavior::make_payload(
                static_cast<uint32_t>(i), PLEN);
            // 描述符入环（guest 视角可见）
            nic.rx_desc_write(host.mem(), 0, static_cast<uint32_t>(i), buf, PLEN,
                              static_cast<uint32_t>(i));
            // DUT DMA 写包数据 + 聚合中断
            vip_init.send_dma_write(buf, pkt);
            if (nic.rx_coalesce(0, COAL)) {
                vip_init.send_msi(0);
                wait(irq_in[0].posedge_event());
                irq_cnt[0]++;
                wait(sc_time(200, SC_NS));
            }
        }
        check(irq_cnt[0] == irq_before + (NPKT / COAL),
              "聚合中断次数 = 16/8 = 2");

        // guest 回收：读描述符 → 包缓冲 → 校验 seq 完整（无丢包）
        int ok_cnt = 0;
        for (int i = 0; i < NPKT; i++) {
            nic_behavior::desc d;
            if (nic.rx_desc_read(host.mem(), 0, static_cast<uint32_t>(i), d)) {
                std::vector<uint8_t> buf(d.len);
                host.mem().read(d.buf_addr, buf.data(), d.len);
                if (nic_behavior::payload_valid(buf, d.seq)) ok_cnt++;
            }
        }
        std::printf("  [dbg] rx ok_cnt=%d/%d\n", ok_cnt, NPKT);
        check(ok_cnt == NPKT, "RX 回收 16 包全部校验通过（无丢包）");
    }

    // 19) P5 多队列：4 队列独立收包/中断
    void test_nic_multiqueue() {
        auto& nic = host.bus().nic();
        // 每队列 4 包，聚合 4 → 每队列 1 次 MSI（vector=qid → SPI=qid）
        for (int q = 0; q < 4; q++) {
            host.bus().msi_map_add(static_cast<uint32_t>(q), q);
        }
        unsigned irq_before[4] = {irq_cnt[0], irq_cnt[1], irq_cnt[2], irq_cnt[3]};

        for (int q = 0; q < 4; q++) {
            for (int i = 0; i < 4; i++) {
                uint64_t buf = 0x500000 + static_cast<uint64_t>(q) * 0x10000 +
                               static_cast<uint64_t>(i) * 256;
                std::vector<uint8_t> pkt = nic_behavior::make_payload(
                    static_cast<uint32_t>(q * 100 + i), 64);
                nic.rx_desc_write(host.mem(), q, static_cast<uint32_t>(i), buf, 64,
                                  static_cast<uint32_t>(q * 100 + i));
                vip_init.send_dma_write(buf, pkt);
                if (nic.rx_coalesce(q, 4)) {
                    vip_init.send_msi(static_cast<uint32_t>(q));
                    wait(irq_in[q].posedge_event());
                    irq_cnt[q]++;
                    wait(sc_time(200, SC_NS));
                }
            }
        }
        bool all_ok = true;
        for (int q = 0; q < 4; q++) {
            if (irq_cnt[q] != irq_before[q] + 1) all_ok = false;
            std::printf("  [dbg] q=%d irq_cnt=%u (before=%u)\n", q, irq_cnt[q], irq_before[q]);
        }
        check(all_ok, "4 队列各触发 1 次独立 MSI");
        check(host.bus().msi_cnt_ >= 4, "MSI 总计数 ≥ 4");
    }

    // 20) P5 聚合配置可调：coalesce_n=16 → 16 包 1 次中断
    void test_nic_coalesce() {
        auto& nic = host.bus().nic();
        const int NPKT = 16, COAL = 16, PLEN = 64;
        unsigned irq_before = irq_cnt[0];

        for (int i = 0; i < NPKT; i++) {
            uint64_t buf = 0x600000 + static_cast<uint64_t>(i) * 256;
            std::vector<uint8_t> pkt = nic_behavior::make_payload(
                static_cast<uint32_t>(i), PLEN);
            nic.rx_desc_write(host.mem(), 0, static_cast<uint32_t>(i), buf, PLEN,
                              static_cast<uint32_t>(i));
            vip_init.send_dma_write(buf, pkt);
            if (nic.rx_coalesce(0, COAL)) {
                vip_init.send_msi(0);
                wait(irq_in[0].posedge_event());
                irq_cnt[0]++;
                wait(sc_time(200, SC_NS));
            }
        }
        check(irq_cnt[0] == irq_before + 1, "聚合 16 → 仅 1 次中断");
    }

    // 4) 无响应 → completion timeout
    void test_timeout() {
        req_desc desc;
        desc.txn_class = TxnClass::MMIO_READ;
        desc.address = 0x5000'0000ULL;
        desc.requester_id = make_req_id(0, 0, 0);
        bool ok = host.bus().direct_request(desc, [](CplStatus, const std::vector<uint8_t>&) {});
        check(ok, "MMIO 读发出（不响应）");
        // 等 2.5ms（超时 1ms + 周期检查 1ms）让 check_timeouts 触发两次
        wait(sc_time(2'500'000, SC_NS));
        check(host.bus().dma_read_cnt_ == 0, "无 DMA 分流（未响应）");
        // 超时后挂起表应被清理（pending=0）
        check(host.bus().pending_count() == 0, "超时后挂起表清空");
    }
};

int sc_main(int, char**) {
    sc_set_default_time_unit(1, SC_NS);
    host_model host("host", 1 << 23);  // 8MB（P5 描述符环/包缓冲需要）
    mock_vip_tgt vip_tgt("vip_tgt");
    mock_vip_init vip_init("vip_init");

    // 接线：host ↔ mock VIP
    host.s_tlp_tx().bind(vip_tgt.sock);
    vip_init.sock.bind(host.s_tlp_rx());
    host.s_resp_tx().bind(vip_init.resp_sock);  // RC 响应（CplD）→ EP
    vip_tgt.set_init(&vip_init);  // mock DUT 上行响应通道

    test_driver driver("driver", host, vip_tgt, vip_init);
    driver.cpu_sock.bind(host.s_cpu());  // 驱动 → host cpu 域
    for (int i = 0; i < 4; i++) {
        driver.irq_in[i].bind(host.irq(i));  // 中断线（P3）
    }

    sc_start();
    return 0;
}
