// nic_behavior.h — NIC 行为模块（host-model-design.md §6，纯逻辑层）
// 职责：host 软件侧的网卡交互辅助——描述符环布局、RX 流量生成、中断聚合判断。
// POC 边界：
//   · DUT 动作（DMA 写包/发 MSI）由外部（mock VIP/测试胶水）扮演
//   · 流量模型：固定模式 payload + seq 编号（端到端校验用）
//   · 聚合：按包数阈值（超时聚合 POC 不做，需时钟）
#pragma once
#include <cstdint>
#include <vector>
#include "mem_model.h"

namespace pcie {

class nic_behavior {
public:
    // RX/TX 描述符（16B/项，模拟 ixgbe 风格简化）
    struct desc {
        uint64_t buf_addr = 0;   // 包缓冲地址（host 内存）
        uint32_t len = 0;        // 包长
        uint32_t seq = 0;        // 序列号（校验）
        uint32_t qid = 0;        // 队列号
    };

    // 描述符环布局（host 内存）
    void set_ring(uint64_t base, uint32_t depth, int queues) {
        ring_base_ = base; ring_depth_ = depth; queues_ = queues;
        pending_.resize(queues > 0 ? queues : 1, 0);  // 防越界（每队列聚合计数）
    }
    uint64_t ring_base() const { return ring_base_; }
    uint32_t ring_depth() const { return ring_depth_; }
    int queues() const { return queues_; }

    // 队列环的起始地址（每队列独立环）
    uint64_t queue_ring_base(int qid) const {
        return ring_base_ + static_cast<uint64_t>(qid) * ring_depth_ * 16;
    }

    // RX：构造包（模式 payload + seq）并写入描述符环（内存模型）
    // 返回描述符在环中的索引；失败返回 -1
    int rx_desc_write(mem_model& mem, int qid, uint32_t idx,
                      uint64_t buf_addr, uint32_t pkt_len, uint32_t seq) {
        if (qid < 0 || qid >= queues_ || idx >= ring_depth_) return -1;
        desc d;
        d.buf_addr = buf_addr;
        d.len = pkt_len;
        d.seq = seq;
        d.qid = static_cast<uint32_t>(qid);
        uint64_t off = queue_ring_base(qid) + static_cast<uint64_t>(idx) * 16;
        uint8_t raw[16];
        raw[0] = static_cast<uint8_t>(d.buf_addr);
        raw[1] = static_cast<uint8_t>(d.buf_addr >> 8);
        raw[2] = static_cast<uint8_t>(d.buf_addr >> 16);
        raw[3] = static_cast<uint8_t>(d.buf_addr >> 24);
        raw[4] = static_cast<uint8_t>(d.buf_addr >> 32);
        raw[5] = static_cast<uint8_t>(d.buf_addr >> 40);
        raw[6] = static_cast<uint8_t>(d.buf_addr >> 48);
        raw[7] = static_cast<uint8_t>(d.buf_addr >> 56);
        raw[8] = static_cast<uint8_t>(d.len);
        raw[9] = static_cast<uint8_t>(d.len >> 8);
        raw[10] = static_cast<uint8_t>(d.len >> 16);
        raw[11] = static_cast<uint8_t>(d.len >> 24);
        raw[12] = static_cast<uint8_t>(d.seq);
        raw[13] = static_cast<uint8_t>(d.seq >> 8);
        raw[14] = static_cast<uint8_t>(d.seq >> 16);
        raw[15] = static_cast<uint8_t>(d.seq >> 24);
        return mem.write(off, raw, 16) ? static_cast<int>(idx) : -1;
    }

    // 读描述符（guest 回收/校验用）
    bool rx_desc_read(mem_model& mem, int qid, uint32_t idx, desc& out) const {
        if (qid < 0 || qid >= queues_ || idx >= ring_depth_) return false;
        uint8_t raw[16];
        uint64_t off = queue_ring_base(qid) + static_cast<uint64_t>(idx) * 16;
        if (!mem.read(off, raw, 16)) return false;
        out.buf_addr = 0;
        for (int i = 0; i < 8; i++) out.buf_addr |= static_cast<uint64_t>(raw[i]) << (8 * i);
        out.len = static_cast<uint32_t>(raw[8]) |
                  (static_cast<uint32_t>(raw[9]) << 8) |
                  (static_cast<uint32_t>(raw[10]) << 16) |
                  (static_cast<uint32_t>(raw[11]) << 24);
        out.seq = static_cast<uint32_t>(raw[12]) |
                  (static_cast<uint32_t>(raw[13]) << 8) |
                  (static_cast<uint32_t>(raw[14]) << 16) |
                  (static_cast<uint32_t>(raw[15]) << 24);
        out.qid = static_cast<uint32_t>(qid);
        return true;
    }

    // 包载荷模式（校验用）：seq 填充
    static std::vector<uint8_t> make_payload(uint32_t seq, uint32_t len) {
        std::vector<uint8_t> p(len);
        for (uint32_t i = 0; i < len; i++) {
            p[i] = static_cast<uint8_t>((seq * 31 + i) & 0xFF);
        }
        return p;
    }
    static bool payload_valid(const std::vector<uint8_t>& p, uint32_t seq) {
        for (uint32_t i = 0; i < p.size(); i++) {
            if (p[i] != static_cast<uint8_t>((seq * 31 + i) & 0xFF)) return false;
        }
        return true;
    }

    // 中断聚合：qid 待计数达 coalesce_n → true 并清零（POC 按包数）
    bool rx_coalesce(int qid, int coalesce_n) {
        if (qid < 0 || qid >= queues_) return false;
        if (++pending_[qid] >= coalesce_n) {
            pending_[qid] = 0;
            return true;
        }
        return false;
    }
    void reset() { for (auto& p : pending_) p = 0; }

private:
    uint64_t ring_base_ = 0;
    uint32_t ring_depth_ = 64;
    int queues_ = 1;
    std::vector<int> pending_ = {0};  // 每队列待中断计数
};

}  // namespace pcie
