import asyncio
import json
import time
import secrets
import statistics
from dataclasses import dataclass, field
from typing import Dict, Tuple, List, Optional
import logging
import random

# 添加模块级 logger（修复因未定义 logger 导致的运行错误，并统一日志来源）
logger = logging.getLogger(__name__)

try:
    from nacl.signing import SigningKey, VerifyKey
    from nacl.encoding import HexEncoder
    HAVE_NACL = True
except Exception:
    HAVE_NACL = False

# ---- Utilities ----

def now_wall() -> float:
    return time.time()

def now_mono() -> float:
    return time.monotonic()

def median_trim(values: List[float], trim_ratio: float = 0.15) -> Optional[float]:
    if not values:
        return None
    n = len(values)
    k = int(n * trim_ratio)
    values_sorted = sorted(values)
    trimmed = values_sorted[k:n - k] if n - 2 * k >= 1 else values_sorted
    return statistics.median(trimmed)

# ---- Wire format helpers ----

def pack(obj: dict) -> bytes:
    return json.dumps(obj, separators=(",", ":")).encode("utf-8")

def unpack(data: bytes) -> dict:
    return json.loads(data.decode("utf-8"))

# ---- Messages ----
# REQ: { "type":"REQ", "nonce": str, "from": peer_id, "ts": t0_client_wall }
# RESP: { "type":"RESP", "nonce": str, "from": peer_id, "t1": t1_srv_wall, "t2": t2_srv_wall, "sig": hex }

# ---- Core Node ----

@dataclass
class PeerNode:
    host: str
    port: int
    peers: List[Tuple[str, int]]  # list of (host, port)
    samples_per_peer: int = 3
    per_round_peer_count: int = 20
    request_timeout: float = 5.0
    round_interval: float = 60.0
    ema_alpha: float = 0.3
    trim_ratio: float = 0.15
    min_samples_for_update: int = 5

    # logical offset applied to local wall clock to get "network time"
    offset: float = 0.0

    # pending requests: nonce -> (t0_wall, t0_mono, future)
    pending: Dict[str, Tuple[float, float, asyncio.Future]] = field(default_factory=dict)

    # crypto
    sk: Optional[SigningKey] = None
    vk: Optional[VerifyKey] = None
    peer_keys: Dict[str, VerifyKey] = field(default_factory=dict)  # peer_id -> verify key

    # id
    peer_id: str = field(default_factory=lambda: secrets.token_hex(16))

    def __post_init__(self):
        if HAVE_NACL and self.sk is None:
            self.sk = SigningKey.generate()
            self.vk = self.sk.verify_key
        # ensure logger has at least basic config in simple runs
        if not logging.getLogger().handlers:
            logging.basicConfig(level=logging.INFO)

    def network_now(self) -> float:
        # logical network time view
        return now_wall() + self.offset

    # ---- UDP protocol ----
    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        try:
            msg = unpack(data)
        except Exception as e:
            # 记录解析失败的调试信息，便于排查网络消息格式问题
            logger.debug("Failed to unpack datagram from %s: %s", addr, e)
            return
        mtype = msg.get("type")
        if mtype == "REQ":
            asyncio.create_task(self.handle_req(msg, addr))
        elif mtype == "RESP":
            self.handle_resp(msg, addr)

    async def handle_req(self, msg: dict, addr):
        # record receive timestamp (server's wall time)
        t1 = now_wall()
        # minimal processing; immediately reply
        t2 = now_wall()
        nonce = msg.get("nonce")
        from_peer = msg.get("from")
        resp = {
            "type": "RESP",
            "nonce": nonce,
            "from": self.peer_id,
            "t1": t1,
            "t2": t2,
        }
        if HAVE_NACL and self.sk:
            payload = json.dumps({k: resp[k] for k in ("nonce", "from", "t1", "t2")}, separators=(",", ":")).encode()
            sig = self.sk.sign(payload).signature.hex()
            resp["sig"] = sig
            resp["vk"] = self.vk.encode(encoder=HexEncoder).decode()
        self.transport.sendto(pack(resp), addr)

    def handle_resp(self, msg: dict, addr):
        nonce = msg.get("nonce")
        fut = self.pending.get(nonce, (None, None, None))[2]
        if fut is None or fut.done():
            logger.debug("Received RESP for unknown/finished nonce %s from %s", nonce, addr)
            return
        # signature check
        if HAVE_NACL:
            vk_hex = msg.get("vk")
            sig_hex = msg.get("sig")
            try:
                if not vk_hex or not sig_hex:
                    raise ValueError("missing signature")
                # If we already have a cached key for this peer, prefer it.
                peer_from = msg.get("from")
                cached_vk = self.peer_keys.get(peer_from)
                if cached_vk is not None:
                    vk = cached_vk
                else:
                    # construct VerifyKey from provided vk_hex (validate)
                    vk = VerifyKey(vk_hex, encoder=HexEncoder)
                payload = json.dumps({k: msg[k] for k in ("nonce", "from", "t1", "t2")}, separators=(",", ":")).encode()
                vk.verify(payload, bytes.fromhex(sig_hex))
                # cache key if not cached
                if peer_from and peer_from not in self.peer_keys:
                    self.peer_keys[peer_from] = vk
            except Exception as e:
                logger.warning("Signature verification failed for nonce %s from %s: %s", nonce, addr, e)
                fut.set_exception(ValueError("bad signature"))
                return
        fut.set_result(msg)

    async def query_peer_once(self, peer: Tuple[str, int]) -> Optional[Tuple[float, float]]:
        """
        Return (theta, delta) for one best-of-m probes, or None
        """
        best = None  # (theta, delta)
        for _ in range(self.samples_per_peer):
            nonce = secrets.token_hex(16)
            t0_wall = now_wall()
            t0_mono = now_mono()
            req = {"type": "REQ", "nonce": nonce, "from": self.peer_id, "ts": t0_wall}
            loop = asyncio.get_running_loop()
            fut = loop.create_future()
            self.pending[nonce] = (t0_wall, t0_mono, fut)
            self.transport.sendto(pack(req), peer)
            try:
                msg = await asyncio.wait_for(fut, timeout=self.request_timeout)
            except asyncio.TimeoutError:
                logger.debug("Timeout waiting for nonce %s from %s", nonce, peer)
                continue
            except asyncio.CancelledError:
                logger.debug("Cancelled waiting for nonce %s", nonce)
                continue
            except Exception as e:
                # fut may carry verification exceptions etc.
                logger.debug("Exception while waiting for nonce %s: %s", nonce, e)
                continue
            finally:
                # clean pending entry (single place)
                self.pending.pop(nonce, None)

            t3_wall = now_wall()
            t3_mono = now_mono()

            # sanity: detect local clock jumps using monotonic comparator
            rtt_wall = t3_wall - t0_wall
            rtt_mono = t3_mono - t0_mono
            if abs(rtt_wall - rtt_mono) > 0.5:  # suspicious local wallclock leap within probe
                logger.debug("Monotonic/wall mismatch rtt_wall=%.3f rtt_mono=%.3f", rtt_wall, rtt_mono)
                continue

            t1 = msg.get("t1")
            t2 = msg.get("t2")
            # NTP 4-timestamp formulas
            theta = ((t1 - t0_wall) + (t2 - t3_wall)) / 2.0
            delta = (t3_wall - t0_wall) - (t2 - t1)

            # pick the minimal delta sample as representative for this peer
            if delta < 0:
                logger.debug("Negative delta sample ignored: %.6f", delta)
                continue  # negative delay indicates bad sample
            if best is None or delta < best[1]:
                best = (theta, delta)
        return best

    async def one_round(self):
        # pick peers
        if not self.peers:
            return
        if len(self.peers) <= self.per_round_peer_count:
            sample_peers = self.peers
        else:
            sr = random.SystemRandom()
            # sample without replacement to avoid duplicate probes to the same peer
            idxs = sr.sample(range(len(self.peers)), self.per_round_peer_count)
            sample_peers = [self.peers[i] for i in idxs]

        tasks = [self.query_peer_once(p) for p in sample_peers]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        offsets: List[float] = []
        delays: List[float] = []

        for res in results:
            if isinstance(res, tuple):
                theta, delta = res
                # filter by delay percentile later; first collect all
                offsets.append(theta)
                delays.append(delta)

        if len(offsets) < self.min_samples_for_update:
            logger.debug("Not enough samples (%d) to update offset", len(offsets))
            return

        # delay-based filtering: drop the worst delays (e.g., top 30%)
        if delays:
            # robust percentile fallback: if too few samples for quantiles, use sorted index
            try:
                if len(delays) >= 10:
                    cutoff = statistics.quantiles(delays, n=10)[6]  # ~70th percentile
                else:
                    sorted_delays = sorted(delays)
                    idx = min(int(len(sorted_delays) * 0.7), len(sorted_delays) - 1)
                    cutoff = sorted_delays[idx]
            except Exception as e:
                logger.debug("Percentile computation error: %s - fallback to max delay", e)
                cutoff = max(delays)
            good = [(o, d) for o, d in zip(offsets, delays) if d <= cutoff]
            if len(good) >= self.min_samples_for_update:
                offsets = [o for o, _ in good]
            else:
                logger.debug("Filtering would reduce samples below threshold (%d -> %d), skipping filter",
                             len(offsets), len(good))

        # robust aggregate
        theta_star = median_trim(offsets, trim_ratio=self.trim_ratio)
        if theta_star is None:
            logger.debug("median_trim returned None")
            return

        # EMA smoothing
        self.offset = (1 - self.ema_alpha) * self.offset + self.ema_alpha * theta_star

    async def run(self):
        loop = asyncio.get_running_loop()
        transport, protocol = await loop.create_datagram_endpoint(
            lambda: _ProtoAdapter(self),
            local_addr=(self.host, self.port),
        )
        self.transport = transport
        try:
            while True:
                await self.one_round()
                await asyncio.sleep(self.round_interval)
        finally:
            transport.close()

class _ProtoAdapter(asyncio.DatagramProtocol):
    def __init__(self, node: PeerNode):
        self.node = node

    def connection_made(self, transport):
        self.node.connection_made(transport)

    def datagram_received(self, data, addr):
        self.node.datagram_received(data, addr)

# ---- Example bootstrap ----
# Usage: create N nodes with known peer lists and run run() per node.
# In real deployment, use discovery/gossip to maintain peer sets and exchange verify keys out-of-band.

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--peer", action="append", help="host:port", default=[])
    args = parser.parse_args()

    peers = []
    for p in args.peer:
        h, s = p.split(":")
        peers.append((h, int(s)))

    node = PeerNode(host=args.host, port=args.port, peers=peers)
    asyncio.run(node.run())
