# Baseline A：固定 120 条验证任务

服务器目录：`/home/chenhongyuan/projects/openfrontier/experiments/baseline_a_120`。

固定 seed=20261102，从已验证的 1000 条验证任务中选 120 条，六个类别各 20 条，并覆盖全部 36 个场景。`selection_120.json` 保存原始任务索引、原始 episode ID、子集内运行 ID、来源哈希和采样种子，供 B/C/D 复用。

`data/` 为派生入口：只选择任务，不改变起点、朝向、目标与元数据；几何场景通过软链接复用 `/home/chenhongyuan/datasets/HM3D`。原始 1000 条任务和已完成的环境检查保持不变。

## 启动与状态

```bash
cd /home/chenhongyuan/projects/openfrontier
/home/chenhongyuan/.conda/envs/habitat-headless/bin/python -u \
  experiments/baseline_a_120/start_experiment.py
```

启动器会准备固定子集，将 benchmark 中强制覆盖 GPU 0 的一行改为尊重环境变量，并保留 `backups/benchmark.py.before_gpu_env`。然后通过 `nohup`、独立进程会话及文件重定向启动：

- GPU 1：现有 sam3 环境的 SAM3，端口 12184。
- GPU 2：现有 openfrontier-vlm 环境的 InternVL3.5-4B，端口 12185。
- GPU 3：现有 habitat-headless 环境的导航 benchmark。

GPU 0 的其他用户进程保持原样。模型、服务代码和解码参数沿用已跑通配置，不安装环境、不下载模型。

启动器输出 `EXPERIMENT_STARTED` 后可以断开 SSH；模型服务与 benchmark 的输入来自 `/dev/null`，输出写日志，已与 SSH 会话分离。

重新登录后查看状态：

```bash
cd /home/chenhongyuan/projects/openfrontier
/home/chenhongyuan/.conda/envs/habitat-headless/bin/python \
  experiments/baseline_a_120/status.py
```

进程 PID、GPU、服务日志路径与本次结果目录记在 `state.json`。结果位于 `output/baseline_a_120_时间/`：服务日志在 `services/`，实验启动日志在 `launch.log`，导航日志在 `run.log`。

不要在当前 benchmark 仍运行时再次手动执行 `launch.sh`。重复运行启动器会检查当前 benchmark；已在运行时直接报告现有进程。

## 指标与复现

固定 SAM3 + InternVL3.5-4B、500 步上限、当前 1 米成功距离；VLM 保留 `max_new_tokens=200, do_sample=True`。配置来自已成功的单任务 Baseline A。子集关闭 shuffle/cycle，并完整遍历子集文件（`--eval_episodes -1`）。这个参数表示读取全部所选任务，并非运行 1000 条。

`run_with_metrics.py` 为原有 benchmark 增加统计包装，保存 SR/SPL、类别指标、终止原因、VLM 评分/验证请求、JSON/异常重试、HTTP 请求与耗时。SR/SPL 的分母与覆盖检查同步改为实际所选 120 条。每条任务保存 `episode_telemetry.json`；完成时有 `summary.json` 和 `BASELINE_A_COMPLETE`。

VLM 逻辑调用耗时包含通信与内部等待；HTTP 耗时与其重叠，不能相加。HTTP 请求数包含传输重试，不等同于服务器实际 forward 次数。任务计时从 agent 构造到最终视频编码前，另存导航循环时间、编码时间和每次启动的运行时间。

原 benchmark 的保存与异常处理保持原样。不额外保存 PNG，保留原有状态、日志和视频。未完成时 `SR_on_completed` 是已完成子集的临时指标，只有完整覆盖 120 条后才能报告本轮最终 SR/SPL。

源码 commit、现有兼容补丁、配置快照、任务清单和统计脚本副本保存在结果目录的 `provenance/` 等文件中。本轮采样解码的服务随机状态未固定，不宣称逐次运行轨迹完全一致。
