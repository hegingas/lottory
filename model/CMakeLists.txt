# pcie-host-model 构建配置
# 用法（MSYS2 环境）:
#   cmake -B build -DCMAKE_BUILD_TYPE=Release
#   cmake --build build
#   ctest --test-dir build
cmake_minimum_required(VERSION 3.20)
project(pcie_host_model CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POLICY_VERSION_MINIMUM 3.5)

# SystemC 安装前缀（本机: C:/systemc-2.3.4）
set(SYSTEMC_HOME "C:/systemc-2.3.4" CACHE PATH "SystemC installation prefix")

# ── 纯逻辑层（无 SystemC 依赖）──
add_library(pcie_core STATIC
  src/pcie_types.cpp
  src/tlp_ext.cpp
  src/tlp_builder.cpp
  src/tlp_parser.cpp
  src/pending_table.cpp
  src/memory_map.cpp
  src/cfg_engine.cpp
  src/smmu_v3_model.cpp
)
target_include_directories(pcie_core PUBLIC include)

# ── SystemC 层 ──
add_library(pcie_sc STATIC
  systemc/tlp_engine.cpp
  systemc/rc_bus_ctrl.cpp
)
target_include_directories(pcie_sc PUBLIC include systemc ${SYSTEMC_HOME}/include)
# pthread: SystemC 库在 MSYS2 下编译，依赖 winpthread（MinGW-Builds 亦提供）
target_link_libraries(pcie_sc PUBLIC pcie_core
  ${SYSTEMC_HOME}/lib/libsystemc.a pthread)

# ── 测试 ──
enable_testing()

add_executable(test_core tests/test_tlp.cpp)
target_link_libraries(test_core pcie_core)
add_test(NAME core COMMAND test_core)
set_tests_properties(core PROPERTIES WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR})

add_executable(test_sc tests/test_sc_integration.cpp)
target_link_libraries(test_sc pcie_sc)
add_test(NAME sc_integration COMMAND test_sc)
set_tests_properties(sc_integration PROPERTIES WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR})
