// cfg_engine.h — 配置引擎（host-model-design.md §2）
// 纯逻辑层：设备表维护、递归枚举（bus 扫描 + Type1 桥下探）、BAR 分配状态。
// 配置访问的传输语义通过 sync_fn 注入（rc_bus_ctrl 提供「同步 TLP 往返」）。
#pragma once
#include <cstdint>
#include <functional>
#include <vector>
#include <string>
#include "pcie_types.h"

namespace pcie {

class cfg_engine {
public:
    struct device_info {
        uint8_t bus = 0, dev = 0, fn = 0;
        bool present = false;
        uint16_t vid = 0, did = 0;
        uint8_t class_code = 0;      // 0x06 = bridge
        uint8_t header_type = 0;     // bit7 = multifunction
        uint32_t bar[6] = {0};       // 软件写回的 BAR 值
        uint32_t bar_size[6] = {0};  // 探测到的 size（power of 2）
        uint64_t bar_alloc[6] = {0}; // 分配的总线地址（含 64-bit 高半）
        bool bar_64bit[6] = {false};
    };

    // 同步配置访问函数（由 rc_bus_ctrl 注入）：
    //   读: write=false, val 输出配置空间数据
    //   写: write=true, val 为写入值
    //   返回 false = 传输失败（UR/超时）
    using sync_fn = std::function<bool(uint8_t bus, uint8_t dev, uint8_t fn,
                                       uint16_t off, uint32_t& val, bool write)>;

    void set_sync_fn(sync_fn fn) { sync_ = std::move(fn); }

    // 递归枚举：从 bus 0 开始扫描，Type1 桥下探（深度限制防环）
    // 返回发现的设备数
    int enumerate(int max_depth = 4);

    const std::vector<device_info>& devices() const { return devices_; }
    device_info* find(uint8_t bus, uint8_t dev, uint8_t fn);
    const device_info* find(uint8_t bus, uint8_t dev, uint8_t fn) const;

    // BAR 分配：按 size 从低窗口分配（interfaces.md §3.3）
    // 返回分配的总线地址；0 = 分配失败（超窗口）
    uint64_t assign_bar(device_info& dev, int idx);

    // 记录软件写 BAR（ECAM 写路径调用；同时探测 size 语义）
    void on_bar_write(device_info& dev, int idx, uint32_t value);

    std::string summary() const;  // 设备表摘要（日志/测试断言）

private:
    void scan_bus(int bus, int depth);
    bool read_dw(uint8_t bus, uint8_t dev, uint8_t fn, uint16_t off, uint32_t& val);
    bool write_dw(uint8_t bus, uint8_t dev, uint8_t fn, uint16_t off, uint32_t val);
    void probe_bar(device_info& dev, int idx);

    sync_fn sync_;
    std::vector<device_info> devices_;
    int max_devices_ = 256;   // bus/dev/fn 上限保护
    uint64_t mmio_alloc_cursor_ = 0;  // 32-bit 窗口分配游标（interfaces.md §3.1 MMIO_BASE 起）
    uint64_t mmio64_alloc_cursor_ = 0; // 64-bit 窗口
};

}  // namespace pcie
