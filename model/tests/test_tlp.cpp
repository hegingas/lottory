// test_tlp.cpp — 纯逻辑层冒烟测试（无 SystemC 依赖）
// 覆盖: TLP 构造/序列化/解析往返、挂起表、地址解码、内存模型、配置加载。
#include <cstdio>
#include <string>
#include <vector>
#include "pcie_types.h"
#include "tlp_ext.h"
#include "tlp_builder.h"
#include "tlp_parser.h"
#include "pending_table.h"
#include "memory_map.h"
#include "mem_model.h"
#include "config_loader.h"

using namespace pcie;

static int g_fail = 0;
static int g_pass = 0;

#define CHECK(cond, msg)                                          \
    do {                                                          \
        if (cond) { g_pass++; }                                   \
        else { g_fail++; std::printf("FAIL %s:%d — %s\n",         \
               __FILE__, __LINE__, msg); }                        \
    } while (0)

// ── 1. TLP 构造 → 字节流 → 解析 往返 ──
static void test_tlp_roundtrip() {
    // CfgRd0
    {
        auto h = tlp_header::cfg_read(make_req_id(0, 0, 0), 0x12,
                                      0, 0, 0, 0x50);
        tlp_transaction t(h);
        auto bytes = t.to_bytes();
        CHECK(bytes.size() == 12, "CfgRd0 序列化 12B");

        tlp_transaction back;
        CHECK(tlp_transaction::from_bytes(bytes.data(), bytes.size(), back),
              "CfgRd0 解析成功");
        CHECK(back.header.type == Type::CfgRd0, "CfgRd0 类型");
        CHECK(back.header.tag == 0x12, "CfgRd0 tag");
        CHECK(back.header.reg_off == 0x50, "CfgRd0 reg_off");
        CHECK(back.header.target_bus == 0 && back.header.target_dev == 0 &&
              back.header.target_fn == 0, "CfgRd0 目标");
    }
    // MMIO 写 3DW（地址 0x50001000，4B 数据）
    {
        std::vector<uint8_t> data = {0xAA, 0xBB, 0xCC, 0xDD};
        auto h = tlp_header::mmio_write(make_req_id(0, 0, 0), 0x33,
                                        0x5000'1000ULL, 1);
        tlp_transaction t(h, data);
        CHECK(t.to_bytes().size() == 16, "3DW MWr = 12 + 4 payload");

        tlp_transaction back;
        CHECK(tlp_transaction::from_bytes(t.to_bytes().data(),
                                          t.to_bytes().size(), back),
              "MWr 解析成功");
        CHECK(back.header.type == Type::MWr, "MWr 类型");
        CHECK(back.header.address == 0x5000'1000ULL, "MWr 地址");
        CHECK(back.payload == data, "MWr 数据");
    }
    // MMIO 写 4DW（64-bit 地址）
    {
        std::vector<uint8_t> data(8, 0x11);
        auto h = tlp_header::mmio_write(make_req_id(1, 2, 3), 0x44,
                                        0x80'0001'0000ULL, 2, true);
        tlp_transaction t(h, data);
        CHECK(t.to_bytes().size() == 24, "4DW MWr = 16 + 8 payload");

        tlp_transaction back;
        CHECK(tlp_transaction::from_bytes(t.to_bytes().data(),
                                          t.to_bytes().size(), back),
              "4DW MWr 解析");
        CHECK(back.header.address == 0x80'0001'0000ULL, "4DW 地址");
        CHECK(back.header.fmt == Fmt::T4DW_WITH_DATA, "4DW fmt");
    }
    // Cpl SC（带数据）
    {
        auto h = tlp_header::completion(make_req_id(2, 0, 0), 0x12,
                                        make_req_id(0, 0, 0), CplStatus::SC,
                                        4, true);
        tlp_transaction t(h, std::vector<uint8_t>(4, 0x5A));
        tlp_transaction back;
        CHECK(tlp_transaction::from_bytes(t.to_bytes().data(),
                                          t.to_bytes().size(), back),
              "CplD 解析");
        CHECK(back.header.type == Type::CplD, "CplD 类型");
        CHECK(back.header.status == CplStatus::SC, "CplD status SC");
        CHECK(back.header.cpl_requester_id == make_req_id(0, 0, 0),
              "CplD requester_id");
        CHECK(back.header.byte_count == 4, "CplD byte_count");
    }
    // Cpl UR
    {
        auto h = tlp_header::completion(make_req_id(2, 0, 0), 0x55,
                                        make_req_id(0, 0, 0), CplStatus::UR,
                                        0, false);
        tlp_transaction t(h);
        tlp_transaction back;
        CHECK(tlp_transaction::from_bytes(t.to_bytes().data(),
                                          t.to_bytes().size(), back),
              "Cpl UR 解析");
        CHECK(back.header.type == Type::Cpl, "Cpl 类型（无数据）");
        CHECK(back.header.status == CplStatus::UR, "Cpl status UR");
    }
    // Msg（INTx Assert）
    {
        auto h = tlp_header::message(make_req_id(3, 0, 0),
                                     MSG_INTX_ASSERT);
        tlp_transaction t(h);
        tlp_transaction back;
        CHECK(tlp_transaction::from_bytes(t.to_bytes().data(),
                                          t.to_bytes().size(), back),
              "Msg 解析");
        CHECK(back.header.is_msg(), "Msg 类型");
        CHECK(back.header.msg_code == MSG_INTX_ASSERT, "Msg code");
    }
}

// ── 2. 构造器 ──
static void test_builder() {
    tlp_builder b;
    // CFG_READ
    req_desc r;
    r.txn_class = TxnClass::CFG_READ;
    r.bus = 0; r.dev = 0; r.fn = 0;
    r.reg_off = 0x00;  // Vendor ID
    r.requester_id = make_req_id(0, 0, 0);
    r.tag = 1;
    auto res = b.build(r);
    CHECK(res.ok && res.tlp.header.type == Type::CfgRd0, "builder CfgRd0");
    CHECK(res.tlp.header.reg_off == 0, "builder reg_off=0");

    // MMIO_WRITE 非对齐 → 报错
    r.txn_class = TxnClass::MMIO_WRITE;
    r.address = 0x5000'0000ULL;
    r.data = {1, 2, 3};  // 3B 非法
    auto bad = b.build(r);
    CHECK(!bad.ok, "builder 拒绝非 DW 对齐");

    // MMIO_READ
    r.txn_class = TxnClass::MMIO_READ;
    r.address = 0x5000'1000ULL;
    r.data.clear();
    auto rd = b.build(r);
    CHECK(rd.ok && rd.tlp.header.type == Type::MRd, "builder MRd");

    // CFG_WRITE 数据不足
    r.txn_class = TxnClass::CFG_WRITE;
    r.data = {1, 2};  // 2B 非法
    r.bus = 0; r.dev = 0; r.fn = 0; r.reg_off = 0x10;
    auto bw = b.build(r);
    CHECK(!bw.ok, "builder 拒绝 CfgWr 数据不足");

    // 不支持的事务类
    r.txn_class = TxnClass::CPL;
    auto unsup = b.build(r);
    CHECK(!unsup.ok, "builder 拒绝 CPL 类");
}

// ── 3. 解析器分流 ──
static void test_parser() {
    tlp_parser p;
    // 上行 MWr → DMA_WRITE
    {
        auto h = tlp_header::mmio_write(make_req_id(1, 0, 0), 0x10,
                                        0x1000'0000ULL, 1);
        h.requester_id = make_req_id(1, 0, 0);  // EP 的 req_id
        tlp_transaction t(h, std::vector<uint8_t>(4, 0));
        auto r = p.parse(t);
        CHECK(r.ok && r.txn_class == TxnClass::DMA_WRITE, "解析 DMA_WRITE");
        CHECK(r.dma_addr == 0x1000'0000ULL, "DMA 地址");
    }
    // 上行 MRd → DMA_READ
    {
        auto h = tlp_header::mmio_read(make_req_id(1, 0, 0), 0x11,
                                       0x1000'0004ULL);
        auto r = p.parse(tlp_transaction(h));
        CHECK(r.ok && r.txn_class == TxnClass::DMA_READ, "解析 DMA_READ");
    }
    // 上行 Cpl → CPL + tag
    {
        auto h = tlp_header::completion(make_req_id(0, 0, 0), 0x20,
                                        make_req_id(1, 0, 0), CplStatus::SC,
                                        4, true);
        auto r = p.parse(tlp_transaction(h, std::vector<uint8_t>(4, 0)));
        CHECK(r.ok && r.txn_class == TxnClass::CPL, "解析 CPL");
        CHECK(r.cpl_tag == 0x20, "Cpl tag");
    }
    // 上行 Msg → MSG_INTX
    {
        auto h = tlp_header::message(make_req_id(1, 0, 0), MSG_INTX_ASSERT);
        auto r = p.parse(tlp_transaction(h));
        CHECK(r.ok && r.txn_class == TxnClass::MSG_INTX, "解析 MSG_INTX");
    }
}

// ── 4. 挂起请求表 ──
static void test_pending_table() {
    pending_table pt;
    bool cb_called = false;
    CplStatus cb_status = CplStatus::UR;

    auto h = tlp_header::cfg_read(make_req_id(0, 0, 0), 0, 0, 0, 0, 0);
    CHECK(pt.issue(h, TxnClass::CFG_READ, {},
                   [&](CplStatus s, const std::vector<uint8_t>&) {
                       cb_called = true;
                       cb_status = s;
                   }, 0),
          "issue 成功");
    CHECK(pt.pending_count() == 1, "挂起 1 项");

    // 错误 tag 未命中
    CHECK(!pt.complete(99, CplStatus::SC, {}), "未命中 tag 报错");
    // 正确完成
    std::vector<uint8_t> cpl_data(4, 0xAB);
    CHECK(pt.complete(0, CplStatus::SC, cpl_data), "complete 命中");
    CHECK(cb_called && cb_status == CplStatus::SC, "回调触发且状态正确");
    CHECK(pt.pending_count() == 0, "挂起清零");

    // 超时
    pt.issue(h, TxnClass::CFG_READ, {}, nullptr, 1000);
    auto expired = pt.check_timeout(2000, 100);  // now=2000, 超时=100 → 900 过期
    CHECK(expired.size() == 1, "超时检测");
    CHECK(expired[0] == 1, "超时 tag");
    CHECK(pt.remove(1), "remove 超时项");
    CHECK(pt.pending_count() == 0, "清理后挂起 0");
}

// ── 5. 地址解码 ──
static void test_memory_map() {
    using namespace map;
    // ECAM bus0/dev0/fn0/off0
    {
        auto r = decode_host_addr(ECAM_BASE + ECAM_OFFSET(0, 0, 0, 0));
        CHECK(r.kind == decode_result::Kind::ECAM, "ECAM 窗口");
        CHECK(r.bus == 0 && r.dev == 0 && r.fn == 0, "ECAM 拆分");
    }
    // ECAM bus1/dev5/fn3/off0x50
    {
        auto r = decode_host_addr(ECAM_BASE + ECAM_OFFSET(1, 5, 3, 0x50));
        CHECK(r.kind == decode_result::Kind::ECAM && r.bus == 1 &&
              r.dev == 5 && r.fn == 3 && r.reg_off == 0x50,
              "ECAM 完整拆分");
    }
    // MMIO
    {
        auto r = decode_host_addr(MMIO_BASE + 0x1000);
        CHECK(r.kind == decode_result::Kind::MMIO && r.offset == 0x1000,
              "MMIO 窗口");
    }
    // SMMU / RC 寄存器
    {
        auto r1 = decode_host_addr(SMMU_BASE + 0x10);
        CHECK(r1.kind == decode_result::Kind::SMMU_REG, "SMMU 窗口");
        auto r2 = decode_host_addr(RC_CFG_BASE + 0x8);
        CHECK(r2.kind == decode_result::Kind::RC_CFG_REG, "RC 配置窗口");
    }
    // DDR
    {
        auto r = decode_host_addr(0x1000'0000ULL);
        CHECK(r.kind == decode_result::Kind::DDR && r.ddr_off == 0x1000'0000ULL,
              "DDR 窗口");
    }
    // 未知
    {
        auto r = decode_host_addr(0xFFFF'0000ULL);
        CHECK(r.kind == decode_result::Kind::UNKNOWN, "未知地址");
    }
}

// ── 6. 内存模型 ──
static void test_mem_model() {
    mem_model mem(4096);
    uint8_t data[8] = {0, 1, 2, 3, 4, 5, 6, 7};
    CHECK(mem.write(0x100, data, 8), "mem 写");
    uint8_t out[8] = {0};
    CHECK(mem.read(0x100, out, 8), "mem 读");
    CHECK(out[5] == 5, "mem 数据正确");
    CHECK(!mem.write(4090, data, 8), "mem 越界拒绝");
}

// ── 7. 配置加载 ──
static void test_config() {
    config_loader cfg;
    CHECK(!cfg.load("nonexistent.cfg"), "缺文件加载失败");
    CHECK(cfg.load("config/delays.cfg"), "配置加载成功");  // cwd = model/
    uint64_t v = 0;
    CHECK(cfg.get_u64("pcie_cfg_delay_ns", v) && v == 100,
          "delays.pcie_cfg_delay_ns");
}

int main() {
    std::printf("[1] roundtrip...\n");  fflush(stdout);
    test_tlp_roundtrip();
    std::printf("[2] builder...\n");    fflush(stdout);
    test_builder();
    std::printf("[3] parser...\n");     fflush(stdout);
    test_parser();
    std::printf("[4] pending...\n");    fflush(stdout);
    test_pending_table();
    std::printf("[5] memmap...\n");     fflush(stdout);
    test_memory_map();
    std::printf("[6] mem...\n");        fflush(stdout);
    test_mem_model();
    std::printf("[7] config...\n");     fflush(stdout);
    test_config();

    std::printf("\n==== 冒烟测试: %d 通过, %d 失败 ====\n", g_pass, g_fail);
    std::printf("[done]\n");            fflush(stdout);
    return g_fail ? 1 : 0;
}
