// mem_model.h — host 内存模型（interfaces.md §5 / 设计文档 §5）
// 纯逻辑层：共享内存读写。SystemC 集成时包一层 target socket。
// 对齐规则：PCIe 语义 8B 对齐；非对齐读写由调用方拆分（POC 直接拒绝并报错）。
#pragma once
#include <cstdint>
#include <cstring>
#include <vector>
#include <stdexcept>

namespace pcie {

class mem_model {
public:
    // 构造：外部共享内存（QEMU guest RAM mmap 区域）直接映射
    // 若 base==nullptr：内部自建（单元测试用）
    explicit mem_model(uint64_t size, uint8_t* external_base = nullptr)
        : size_(size), owned_(external_base == nullptr) {
        if (owned_) {
            buf_.resize(size, 0);
            base_ = buf_.data();
        } else {
            base_ = external_base;
        }
    }
    ~mem_model() = default;
    mem_model(const mem_model&) = delete;
    mem_model& operator=(const mem_model&) = delete;

    bool read(uint64_t offset, uint8_t* dst, size_t n) const {
        if (!in_range(offset, n)) return false;
        std::memcpy(dst, base_ + offset, n);
        return true;
    }
    bool write(uint64_t offset, const uint8_t* src, size_t n) {
        if (!in_range(offset, n)) return false;
        std::memcpy(base_ + offset, src, n);
        return true;
    }

    // 直接指针访问（DMA 免拷贝路径，SystemC 集成时用）
    uint8_t* ptr(uint64_t offset = 0) { return base_ + offset; }
    const uint8_t* ptr(uint64_t offset = 0) const { return base_ + offset; }

    uint64_t size() const { return size_; }

private:
    bool in_range(uint64_t offset, size_t n) const {
        return offset + n <= size_;
    }

    uint64_t size_;
    std::vector<uint8_t> buf_;   // owned_ 时持有
    uint8_t* base_ = nullptr;
    bool owned_ = false;
};

}  // namespace pcie
