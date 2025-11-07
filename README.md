# p2p_time_sync

轻量级的 Peer-to-Peer 时间同步库与示例工具（Python + asyncio + UDP）。

一个演示如何在对等网络中通过交换时间戳估计时钟偏移并收敛的项目；可选支持消息签名（PyNaCl）。

---

简介

- 目标：在不依赖集中式时间服务器的情况下，通过点对点时间戳交换实现时钟偏移估计与收敛。
- 实现要点：asyncio + UDP、采样与延迟过滤、稳健聚合（修剪中位数）、EMA 平滑、可选消息签名。

## 特性

- 轻量 P2P 时间同步协议
- 多次采样、延迟过滤与修剪聚合
- EMA（指数移动平均）平滑逻辑时钟偏移
- 可选的消息签名/校验（使用 PyNaCl）
- 可配置采样参数与超时行为

## 快速开始

1. 克隆仓库并进入目录：

  ```bash
  git clone https://github.com/TYEclipse/p2p_time_sync.git
  cd p2p_time_sync
  ```

2. 推荐使用虚拟环境：

  ```bash
  python3 -m venv .venv
  source .venv/bin/activate
  pip install --upgrade pip
  # 可选：启用消息签名功能
  pip install pynacl
  ```

3. 运行示例 peer（在不同终端启动两个或多个实例）：

- 启动 peer A

    ```bash
    python3 p2p_time_sync.py --port 8000 --peer 127.0.0.1:8001
    ```

- 启动 peer B

    ```bash
    python3 p2p_time_sync.py --port 8001 --peer 127.0.0.1:8000
    ```

- 如果只想监听本地接口：

    ```bash
    python3 p2p_time_sync.py --host 127.0.0.1 --port 8000 --peer 127.0.0.1:8001
    ```

## 协议概览（JSON 报文）

REQ（请求）:

```json
{
  "type": "REQ",
  "nonce": "<随机字符串>",
  "from": "<peer_id>",
  "ts": 1620000000.123  // 发送时的本地 wall clock 时间
}
```

RESP（响应）:

```json
{
  "type": "RESP",
  "nonce": "<相同的随机字符串>",
  "from": "<peer_id>",
  "t1": 1620000000.200,  // 服务器接收请求时的 wall 时间
  "t2": 1620000000.205,  // 服务器发送响应时的 wall 时间
  "sig": "<hex signature>", // 可选（启用 PyNaCl 时）
  "vk": "<hex verify key>"  // 可选（发送方的公钥）
}
```

时间估计算法（与 NTP 类似）

- 本地发送时间 t0（wall）
- 远端接收时间 t1（远端 wall）
- 远端发送时间 t2（远端 wall）
- 本地接收时间 t3（wall）

使用四个时间戳估计：

- theta（时钟偏移） = ((t1 - t0) + (t2 - t3)) / 2
- delta（往返延迟） = (t3 - t0) - (t2 - t1)

实现细节（简要）

- 对每个 peer 做多次采样，选择延迟较小的样本作为代表。
- 对 offset 集合做修剪（trim）并取中位数或修剪后的中位数作为聚合值。
- 使用 EMA 平滑更新本地逻辑偏移：offset = (1-α)*offset + α*theta_star。
- 使用 monotonic 时间检测本地 wall clock 跳变以排除异常样本。

消息签名（可选）

- 若安装 PyNaCl，节点会生成 SigningKey/VerifyKey，在 RESP 中附带 vk 与 sig，接收方校验签名防止伪造。  
- 当前实现为运行时生成临时签名密钥；可扩展为持久化密钥以便长期识别。

## 配置选项（可在 p2p_time_sync.py 中调整）

- host: 本地监听地址（默认 0.0.0.0）
- port: 本地监听端口（必需）
- --peer: 指定对等节点（host:port，可重复）
- samples_per_peer: 每个 peer 的探测次数（默认 3）
- per_round_peer_count: 每轮探测的 peer 上限（默认 20）
- request_timeout: 单次请求超时时间（秒，默认 5.0）
- round_interval: 每轮探测间隔（秒，默认 60.0）
- ema_alpha: EMA 平滑系数（默认 0.3）
- trim_ratio: 修剪比例用于计算稳健中位数（默认 0.15）
- min_samples_for_update: 更新偏移所需的最小样本数（默认 5）

## 日志与调试

- 使用 Python 标准 logging，默认 basicConfig 为 INFO。  
- 若需更详细调试，启动前设置：

```bash
python -c "import logging; logging.basicConfig(level=logging.DEBUG)" && python3 p2p_time_sync.py --port 8000
```

- 代码在关键路径保留了调试日志（如解析失败、签名校验失败、超时等），便于排查。

## 示例用例（本地模拟）

- 在同一台机器上用不同端口运行多个 peer，可观察 offset 收敛。  
- 若有网络延迟波动，算法通过延迟过滤与修剪保持稳健性。

## 贡献

- 欢迎 PR：修复 bug、持久化签名密钥、改进发现/引导机制、增加测试与 CI。  
- 请先打开 issue 讨论较大设计变更，或在 PR 描述中说明修改内容。

## 联系方式

- 维护者: TYEclipse
- 仓库: <https://github.com/TYEclipse/p2p_time_sync>

## 免责声明

- 本项目为教育/演示用途；在对安全或准确性要求极高的生产环境中请慎用，并结合更成熟的时钟同步方案（如 NTP/PTP/专用硬件）。
