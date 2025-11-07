# p2p_time_sync

Peer-to-peer (P2P) time synchronization library and example tools.

This repository provides a small project for synchronizing clocks across peers in a network without relying on a centralized time server. It demonstrates simple protocols for exchanging timestamps, estimating clock offsets, and applying adjustments to achieve better time alignment between nodes.

## Features

- Lightweight P2P time synchronization protocol
- Timestamp exchange and offset estimation
- Example client and server (or peer) implementations
- Configurable network and timing parameters

## Requirements

- Go 1.20+ (or the language/runtime used in this repo)
- Git

> Note: If this repository uses a different language, update this section accordingly.

## Getting started

1. Clone the repository:

   git clone https://github.com/TYEclipse/p2p_time_sync.git
   cd p2p_time_sync

2. Build (for Go projects):

   go build ./...

3. Run an example peer (adjust commands for the actual project structure):

   # start peer A
   ./peer -port 8000 -peers 127.0.0.1:8001

   # start peer B
   ./peer -port 8001 -peers 127.0.0.1:8000

4. Observe logs to see offset estimation and adjustments.

## Protocol overview

This project implements a simple timestamp exchange protocol:

1. Peer A sends a "request" message with its local timestamp t1.
2. Peer B receives the request at t2 (local) and replies with t2 and its reply-send time t3.
3. Peer A receives the reply at t4 and computes round-trip time (RTT) and clock offset estimates.

Using these values, peers estimate their clock offsets and optionally apply smooth adjustments to converge.

## Configuration

Configuration options (examples):

- listen port
- list of peer addresses
- polling/heartbeat interval
- smoothing factor for adjustments

Check the configuration file or flags in the code for exact options.

## Testing

If there are tests in the repository, run them with:

   go test ./...

## Contributing

Contributions are welcome. Please open an issue to discuss major changes or file a pull request with a clear description of your changes.

## License

If this project has a license, add it here (e.g., MIT, Apache-2.0). If not, add a LICENSE file to clarify.

## Contact

Maintainer: TYEclipse
