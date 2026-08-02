// cfg_engine.cpp — 配置引擎实现
#include "cfg_engine.h"
#include "memory_map.h"

namespace pcie {

bool cfg_engine::read_dw(uint8_t bus, uint8_t dev, uint8_t fn,
                         uint16_t off, uint32_t& val) {
    if (!sync_) return false;
    return sync_(bus, dev, fn, off, val, false);
}

bool cfg_engine::write_dw(uint8_t bus, uint8_t dev, uint8_t fn,
                          uint16_t off, uint32_t val) {
    if (!sync_) return false;
    return sync_(bus, dev, fn, off, val, true);
}

// ── 枚举：递归 bus 扫描 ──
int cfg_engine::enumerate(int max_depth) {
    devices_.clear();
    scan_bus(0, 0);
    // 摘要日志（测试通过 summary() 读取）
    return static_cast<int>(devices_.size());
}

void cfg_engine::scan_bus(int bus, int depth) {
    if (depth > 4 || bus > 255) return;  // 深度保护（roadmap P1: 深度≤8，这里 4 起步可配）
    for (int dev = 0; dev < 32; dev++) {
        bool fn_present[8] = {false};
        bool multifunc = false;
        for (int fn = 0; fn < 8; fn++) {
            uint32_t vid_did = 0;
            if (!read_dw(static_cast<uint8_t>(bus), static_cast<uint8_t>(dev),
                         static_cast<uint8_t>(fn), 0x00, vid_did)) {
                break;  // 传输失败（UR）→ 视为不存在
            }
            uint16_t vid = vid_did & 0xFFFF;
            if (vid == 0xFFFF) {  // 无设备
                break;
            }
            // 设备存在
            device_info d;
            d.bus = static_cast<uint8_t>(bus);
            d.dev = static_cast<uint8_t>(dev);
            d.fn = static_cast<uint8_t>(fn);
            d.vid = vid;
            d.did = vid_did >> 16;
            d.present = true;

            uint32_t cc = 0;
            if (read_dw(d.bus, d.dev, d.fn, 0x08, cc)) {
                d.class_code = (cc >> 24) & 0xFF;      // base class（Byte3）
            }
            uint32_t ht = 0;
            if (read_dw(d.bus, d.dev, d.fn, 0x0C, ht)) {
                d.header_type = (ht >> 16) & 0xFF;
            }
            // 探测 BAR（header type 0 的 EP 才有 BAR；bridge 也有 BAR0-1）
            for (int i = 0; i < 6; i++) {
                probe_bar(d, i);
            }

            fn_present[fn] = true;
            if (fn == 0) multifunc = (d.header_type & 0x80) != 0;
            devices_.push_back(d);

            // 单功能设备（fn0 非 multifunction）→ 跳过剩余 fn
            if (fn == 0 && !multifunc) break;

            // Type1 桥 → 下探
            if (d.class_code == 0x06) {
                uint32_t sec_bus = 0;
                if (read_dw(d.bus, d.dev, d.fn, 0x18, sec_bus)) {
                    int secondary = (sec_bus >> 8) & 0xFF;
                    if (secondary != 0) {
                        scan_bus(secondary, depth + 1);
                    }
                }
            }
        }
        if (!fn_present[0]) break;  // dev 不存在 → 下一个 dev
    }
}

// ── BAR 探测：写 0xFFFFFFFF 读 size（软件语义；实际分配由 assign_bar 完成）──
// 注意: 已实现 BAR 初始读回 0（软件未配置），不能因 cur==0 跳过探测。
void cfg_engine::probe_bar(device_info& dev, int idx) {
    // BAR 寄存器偏移: 0x10 + idx*4；64-bit BAR 占两项
    uint16_t off = static_cast<uint16_t>(0x10 + idx * 4);
    uint32_t cur = 0;
    if (!read_dw(dev.bus, dev.dev, dev.fn, off, cur)) return;

    // 写全 1 → 读回 size 编码（探测写不存储，设备返回 size）
    if (!write_dw(dev.bus, dev.dev, dev.fn, off, 0xFFFFFFFF)) return;
    uint32_t sz_enc = 0;
    if (!read_dw(dev.bus, dev.dev, dev.fn, off, sz_enc)) {
        write_dw(dev.bus, dev.dev, dev.fn, off, cur);
        return;
    }
    // 还原（写回原值；软件尚未分配）
    write_dw(dev.bus, dev.dev, dev.fn, off, cur);

    if ((sz_enc & 0xFFFFFFF0) == 0) {
        dev.bar_size[idx] = 0;   // 未实现 BAR（读回 0）
        return;
    }

    bool is64 = (sz_enc & 0x4) != 0;  // 类型位: 0x2=IO, 0x4=64-bit mem
    uint32_t sz = static_cast<uint32_t>(~(sz_enc & 0xFFFFFFF0)) + 1;
    if (is64) {
        // 64-bit：读高 32 位项判断完整 size（POC 支持 ≤4GB 的 64-bit BAR）
        uint32_t hi = 0;
        read_dw(dev.bus, dev.dev, dev.fn, off + 4, hi);
        uint64_t full = (static_cast<uint64_t>(hi) << 32) | sz_enc;
        uint64_t full_size = (~full) + 1;
        dev.bar_size[idx] = static_cast<uint32_t>(full_size);
        dev.bar_64bit[idx] = true;
    } else {
        dev.bar_size[idx] = sz;
        dev.bar_64bit[idx] = false;
    }
}

// ── BAR 分配（interfaces.md §3.3：32-bit 低窗口 / 64-bit 高窗口）──
uint64_t cfg_engine::assign_bar(device_info& dev, int idx) {
    uint32_t sz = dev.bar_size[idx];
    if (sz == 0) return 0;

    uint64_t base = 0;
    if (dev.bar_64bit[idx]) {
        base = map::MMIO64_BASE + mmio64_alloc_cursor_;
        mmio64_alloc_cursor_ += sz;
    } else {
        base = map::MMIO_BASE + mmio_alloc_cursor_;
        mmio_alloc_cursor_ += sz;
    }
    dev.bar_alloc[idx] = base;
    // 写回 BAR（模拟软件写 BAR 的行为）
    uint16_t off = static_cast<uint16_t>(0x10 + idx * 4);
    write_dw(dev.bus, dev.dev, dev.fn, off, static_cast<uint32_t>(base & 0xFFFFFFF0));
    dev.bar[idx] = static_cast<uint32_t>(base);
    if (dev.bar_64bit[idx]) {
        write_dw(dev.bus, dev.dev, dev.fn, off + 4,
                 static_cast<uint32_t>(base >> 32));
        dev.bar[idx + 1] = static_cast<uint32_t>(base >> 32);
    }
    return base;
}

// ── 软件写 BAR 记录 ──
void cfg_engine::on_bar_write(device_info& dev, int idx, uint32_t value) {
    if (idx < 0 || idx >= 6) return;
    if (value == 0xFFFFFFFF) return;  // size 探测，不记录
    dev.bar[idx] = value;
    if (dev.bar_64bit[idx] && idx + 1 < 6) {
        // 高 32 位写（第二项）
        uint64_t full = (static_cast<uint64_t>(value) << 32) |
                        (dev.bar[idx] & 0xFFFFFFF0);
        dev.bar_alloc[idx] = full;
    } else {
        dev.bar_alloc[idx] = value & 0xFFFFFFF0;
    }
}

cfg_engine::device_info* cfg_engine::find(uint8_t bus, uint8_t dev, uint8_t fn) {
    for (auto& d : devices_) {
        if (d.bus == bus && d.dev == dev && d.fn == fn) return &d;
    }
    return nullptr;
}

const cfg_engine::device_info* cfg_engine::find(uint8_t bus, uint8_t dev, uint8_t fn) const {
    for (const auto& d : devices_) {
        if (d.bus == bus && d.dev == dev && d.fn == fn) return &d;
    }
    return nullptr;
}

std::string cfg_engine::summary() const {
    std::string s;
    char buf[64];
    for (const auto& d : devices_) {
        std::snprintf(buf, sizeof(buf), "%02x:%02x.%x [%s] vid=%04x did=%04x ",
                      d.bus, d.dev, d.fn,
                      d.class_code == 0x06 ? "bridge" : "ep",
                      d.vid, d.did);
        s += buf;
    }
    return s.empty() ? "(无设备)" : s;
}

}  // namespace pcie
