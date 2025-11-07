# p2p_time_sync

Peer-to-peer 时间同步库与示例工具。

这个仓库演示了如何在对等网络中，在不依赖集中式时间服务器的情况下通过交换时间戳来估计并收敛时钟偏移。示例实现使用 asyncio + UDP，并包含简单的报文签名。

## 特性

- 轻量级 P2P 时间同步协议
- 时间戳交换与偏移估计
- 示例 peer 节点实现
- 可选的消息签名/校验
- 可配置的采样、平滑和延迟过滤参数

## 要求

- Python 3.8+
- 可选：PyNaCl
  - 安装：pip install pynacl

注意：代码使用 asyncio、dataclasses、typing、secrets、statistics 等标准库模块；若不安装 PyNaCl，签名相关功能会自动被跳过（退化到无签名模式）。

## 安装

推荐使用虚拟环境：

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
# 如果需要签名/验证功能：
pip install pynacl

## 快速开始

1. 克隆仓库：

   git clone https://github.com/TYEclipse/p2p_time_sync.git
   cd p2p_time_sync

2. 运行示例 peer（在不同终端中启动两个或多个 peer）：

   # 启动 peer A
   python3 p2p_time_sync.py --port 8000 --peer 127.0.0.1:8001

   # 启动 peer B
   python3 p2p_time_sync.py --port 8001 --peer 127.0.0.1:8000

默认情况下，节点会周期性地对其已知 peers 发起探测，收集偏移样本并使用 EMA（指数移动平均）来平滑本地的逻辑时钟偏移。

如果需要指定监听地址，例如仅监听本机接口：

python3 p2p_time_sync.py --host 127.0.0.1 --port 8000 --peer 127.0.0.1:8001

## 协议概览

交换的报文为 JSON：

- REQ:
  {
    "type": "REQ",
    "nonce": "<随机字符串>",
    "from": "<peer_id>",
    "ts": <t0_client_wall>   # 发送时的本地 wall clock 时间
  }

- RESP:
  {
    "type": "RESP",
    "nonce": "<相同的随机字符串>",
    "from": "<peer_id>",
    "t1": <t1_srv_wall>,    # 服务器接收请求时的 wall 时间
    "t2": <t2_srv_wall>,    # 服务器发送响应时的 wall 时间
    "sig": "<hex signature>",    # 可选（如果启用 PyNaCl）
    "vk": "<hex verify key>"     # 可选（发送方的公钥，用于验证 sig）
  }

时间估计算法（与 NTP 类似）：
- 本地发送时间 t0（wall）
- 远端接收时间 t1（远端 wall）
- 远端发送时间 t2（远端 wall）
- 本地接收时间 t3（wall）

使用这些值估计时钟偏移 theta 和往返延迟 delta：
- theta = ((t1 - t0) + (t2 - t3)) / 2
- delta = (t3 - t0) - (t2 - t1)

实现中会对同一 peer 做多次采样、选取延迟较小的样本、对 offset 集合做修剪（trim）并用中位数或修剪后的中位数做聚合，然后用 EMA 平滑更新本地逻辑偏移（PeerNode.offset）。

消息签名（可选）：
- 如果安装并可用 PyNaCl，节点会生成一个临时签名密钥（SigningKey）及对应 VerifyKey，并在 RESP 中附带 vk 与 sig。接收方会校验签名以防止伪造响应。
- 若不希望在每次运行都生成新的密钥，代码可以扩展以从外部保存/加载签名密钥（当前实现为运行时生成并缓存对等方的公钥）。

## 配置选项（在 p2p_time_sync.py 中可调整或扩展）

- host: 本地监听地址（默认 0.0.0.0）
- port: 本地监听端口（必需）
- --peer: 指定对等节点，格式 host:port，可重复，示例：--peer 127.0.0.1:8001
- samples_per_peer: 每个 peer 的探测次数（默认为 3）
- per_round_peer_count: 每轮要探测的 peer 数量上限（默认为 20）
- request_timeout: 单次请求超时时间（秒，默认为 5.0）
- round_interval: 每轮探测之间的间隔（秒，默认为 60.0）
- ema_alpha: EMA 平滑系数（默认为 0.3）
- trim_ratio: 修剪比例用于计算稳健中位数（默认为 0.15）
- min_samples_for_update: 更新偏移所需的最小样本数（默认为 5）

## 运行日志与调试

- 代码使用标准库 logging；默认在简单运行环境下设置了 basicConfig（INFO 级别）。要查看更多调试信息，请在运行前配置环境变量或在脚本顶部调整 logging 配置，例如：

python -c "import logging; logging.basicConfig(level=logging.DEBUG)" && python3 p2p_time_sync.py --port 8000 ...

也可以在代码中直接修改 logging.basicConfig 的级别或格式。

## 贡献

欢迎贡献：修复 bug、完善协议、添加持久化密钥支持、增加发现/引导机制、或者添加更完善的测试与 CI。请先打开 issue 讨论大的设计变更，或直接提交 PR 并在 PR 描述中说明修改内容。

## 联系

维护者: TYEclipse
