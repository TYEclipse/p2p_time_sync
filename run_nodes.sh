#!/usr/bin/env bash
set -euo pipefail

# 一键启动脚本：在本目录下启动 N 个 p2p_time_sync.py 节点
# 每个节点间隔 1 秒启动，日志级别为 DEBUG
# 启动方式：使用内嵌 python 命令先设置 logging.basicConfig，再用 runpy 执行模块，这样能在同一进程中把日志级别设置为 DEBUG。

# 配置
NODE_COUNT=${NODE_COUNT:-40}
START_PORT=${START_PORT:-8000}
HOST=${HOST:-127.0.0.1}
BASEDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOGDIR="$BASEDIR/logs"

mkdir -p "$LOGDIR"

echo "Starting $NODE_COUNT nodes starting at port $START_PORT on $HOST"

for ((i=0;i<NODE_COUNT;i++)); do
  port=$((START_PORT + i))
  next_index=$(((i + 1) % NODE_COUNT))
  next_port=$((START_PORT + next_index))

  log_file="$LOGDIR/node_${port}.log"
  pid_file="$LOGDIR/node_${port}.pid"

  # 使用 python3 -c 来先设置 logging 再运行 p2p_time_sync.py 并传递参数（通过修改 sys.argv）
  # 注意：这里通过 bash -c 包裹并且用 runpy.run_path 在同一 python 进程内执行模块，从而让 logging.basicConfig 生效。
  # 构建 sys.argv 字符串：包含 --port 以及除自身外的所有 --peer entries，
  # 这样每个节点都会知道集群中其它所有节点，能实现全互联同步。
  sys_argv="['p2p_time_sync.py','--port','${port}'"
  for ((j=0;j<NODE_COUNT;j++)); do
    if [ "$j" -eq "$i" ]; then
      continue
    fi
    pport=$((START_PORT + j))
    sys_argv+=", '--peer','${HOST}:${pport}'"
  done
  sys_argv+="]"

  cmd="python3 -c \"import logging,runpy,sys; logging.basicConfig(level=logging.DEBUG); sys.argv=${sys_argv}; runpy.run_path('p2p_time_sync.py', run_name='__main__')\""

  # 用 nohup + bash -c 启动到后台并记录 pid
  nohup bash -c "$cmd" > "$log_file" 2>&1 &
  echo $! > "$pid_file"

  echo "Launched node port=$port peer=${HOST}:${next_port} pid=$(cat $pid_file) -> $log_file"

  sleep 1
done

echo "All $NODE_COUNT nodes started. Logs in $LOGDIR"
