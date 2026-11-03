# 历史 A 评分解析核对

`vlm/utils.py:detect_frontier_probabilities` 要求带标签和理由的 JSON；提示同时说单字典列表并展示字典。实现先去除 Markdown 代码围栏，再 `json.loads`，接受字典或首项为字典的非空列表。它本身不检查标签集合、概率范围或值的形状；agent 要求非空字典，缺失标签取 0.5，值索引异常走异常重试。每个评分事件最多尝试 10 次。正式对照若需保留 A 的可比性，应保持这些行为，不应悄悄收紧校验。

历史日志示例：`run.log` 第 866 行附近，4ok3usBNeis episode 1 的回复是带 A/B 标题的自然语言而非 JSON；同一步重试后返回字典。第 2185 行附近 episode 2 的回复只有 `r`，同样解析失败后重试得到字典。这些是解析失败，不是 HTTP 错误。原始日志保留完整文本。

现有统计的 parse_failures 是解析函数返回 False 的次数，exceptions 分开计算；agent_retry_calls 依据同一步逻辑调用数减一估计，不能直接等同于重评事件数。
