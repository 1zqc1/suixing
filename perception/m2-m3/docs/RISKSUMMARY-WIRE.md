# RiskSummary 定长线格式 v1

本文定义跨越 Linux → CPU3 的唯一风险数据结构。ROS 话题 `/suixing/risk_frame` 与 RPMsg 使用**完全相同**的字节串，禁止把 ROS 序列化结果直接送进 RPMsg。

实现与测试：`ros_ws/src/suixing_risk/suixing_risk/protocol.py`、`tests/test_protocol.py`。

## 1. 通用规则

- 长度固定 **64 字节**，小端序，无对齐填充。
- 第 0–3 字节为魔数 `SXR1`（`53 58 52 31`）。
- CRC 为 **CRC-16/CCITT-FALSE**（多项式 `0x1021`，初值 `0xFFFF`，不反转），覆盖字节 0–47，结果写在 48–49。
- 收到帧先校验：长度 → 魔数 → 版本 → 消息类型 → CRC → 枚举值。任一失败整帧丢弃，不降级使用。
- 空值统一用 `0xFFFF`，不要用 0 代替"未知"。
- 发送端将保留字段填 0，接收端忽略其内容。偏移 46–47 的保留字节仍受 CRC 校验。偏移 50–63 的尾部不参与 CRC，v1 不赋予尾部任何含义。

## 2. 字节布局

| 偏移 | 长度 | 字段 | 类型 | 说明 |
|---|---|---|---|---|
| 0 | 4 | `magic` | char[4] | `"SXR1"` |
| 4 | 1 | `version` | uint8 | 当前 1 |
| 5 | 1 | `msg_type` | uint8 | 1 = 风险摘要 |
| 6 | 1 | `quality` | uint8 | 证据质量位，见 3.1 |
| 7 | 1 | `reason` | uint8 | 主要原因，见 3.2 |
| 8 | 4 | `session_id` | uint32 | 每会话一个，JSON 到线格式的映射见下文 |
| 12 | 4 | `seq` | uint32 | 单调递增，回绕按模 2³² |
| 16 | 8 | `sample_ns` | uint64 | 最老参与传感器采样时间，ROS 纳秒。双源均不可用时写 0 |
| 24 | 8 | `generated_ns` | uint64 | 摘要生成时间 |
| 32 | 2 | `valid_ms` | uint16 | 生成时剩余有效期，`0xFFFF` 未知 |
| 34 | 2 | `source_age_ms` | uint16 | 采样年龄，`0xFFFF` 未知 |
| 36 | 2 | `ttc_min_ms` | uint16 | TTC 区间下界，`0xFFFF` 无 |
| 38 | 2 | `ttc_max_ms` | uint16 | TTC 区间上界，`0xFFFF` 无 |
| 40 | 1 | `risk_left` | uint8 | 0 未知 / 1 通行 / 2 注意 / 3 危险 |
| 41 | 1 | `risk_straight` | uint8 | 同上 |
| 42 | 1 | `risk_right` | uint8 | 同上 |
| 43 | 1 | `flags` | uint8 | 见 3.3 |
| 44 | 2 | `speed_limit_centi` | uint16 | 建议限速 ×100，`0xFFFF` 未知；`0` 表示停车 |
| 46 | 2 | `reserved0` | uint16 | 必须为 0 |
| 48 | 2 | `crc16` | uint16 | 覆盖 0–47 |
| 50 | 14 | `reserved1` | uint8[14] | 必须为 0 |

JSON 节点会话号是 32 个十六进制字符。二进制会话号为前 8 个字符按十六进制解析后的 uint32，以小端写入偏移 8–11。例如 `0123456789abcdef0123456789abcdef` 对应 `67 45 23 01`。联调日志保留完整 JSON 会话号，并使用映射后的值与二进制回执核对。32 位值存在碰撞可能。通用编码器也接受 uint32，以及可用首 8 字符解析为十六进制数的字符串。其他字符串先去掉两端空白，再对 UTF-8 字节计算 CRC32。

## 3. 枚举

### 3.1 quality 位

| 位 | 值 | 含义 |
|---|---|---|
| 0 | 0x01 | 本次有可用 D6 扫描 |
| 1 | 0x02 | 本次有可用双目证据 |
| 2 | 0x04 | 两路时间戳在 40 ms 内对齐 |
| 3 | 0x08 | 使用了语义增强 |
| 4 | 0x10 | 接收时间已知（可算传输年龄） |

### 3.2 reason

| 值 | 含义 | 处理建议 |
|---|---|---|
| 0 | 无异常 | 正常使用 |
| 1 | 无观测 | 保持停车 |
| 2 | 观测过期 | 保持停车 |
| 3 | 未对齐 | 保持停车，记录同步问题 |
| 4 | 覆盖不足 | 该方向不可信 |
| 5 | 存在危险方向 | 停车或按 `speed_limit` 处理 |
| 6 | 语义升级导致 | 复核语义置信度 |

### 3.3 flags 位

| 位 | 值 | 含义 |
|---|---|---|
| 0 | 0x01 | 存在未覆盖区域（`unknown_region`） |
| 1 | 0x02 | TTC 区间有效 |
| 2 | 0x04 | 限速值有效 |
| 3 | 0x08 | 语义已参与风险 |

## 4. C 结构体

```c
#include <stdint.h>

struct sx_risk_frame {          /* 64 字节，小端，紧凑 */
    char     magic[4];          /* "SXR1" */
    uint8_t  version;           /* 1 */
    uint8_t  msg_type;          /* 1 = risk */
    uint8_t  quality;
    uint8_t  reason;
    uint32_t session_id;
    uint32_t seq;
    uint64_t sample_ns;
    uint64_t generated_ns;
    uint16_t valid_ms;
    uint16_t source_age_ms;
    uint16_t ttc_min_ms;
    uint16_t ttc_max_ms;
    uint8_t  risk_left;
    uint8_t  risk_straight;
    uint8_t  risk_right;
    uint8_t  flags;
    uint16_t speed_limit_centi;
    uint16_t reserved0;
    uint16_t crc16;
    uint8_t  reserved1[14];
} __attribute__((packed));

_Static_assert(sizeof(struct sx_risk_frame) == 64, "risk frame must stay 64 bytes");
```

CRC 校验函数约定：`crc16_ccitt_false(frame, 48)` 与帧内 `crc16` 比较。

## 5. 示例帧

输入：session `0123456789abcdef`、seq 7、sample 1 000 000 000 ns、generated 1 000 010 000 ns、左通行/直注意/右危险、TTC 1.25–1.75 s、有效期 80 ms、采样年龄 12 ms、限速 0.3 m/s、语义参与、双路对齐。

```
53 58 52 31 01 01 1f 05 67 45 23 01 07 00 00 00
00 ca 9a 3b 00 00 00 00 10 f1 9a 3b 00 00 00 00
50 00 0c 00 e2 04 d6 06 01 02 03 06 1e 00 00 00
f3 6d 00 00 00 00 00 00 00 00 00 00 00 00 00 00
```

解读：`quality=0x1f`（五位全开），`reason=0x05`（存在危险方向），`flags=0x06`（TTC 与限速有效）。

## 6. 失效与拒绝

| 情况 | 发送端 | 接收端 |
|---|---|---|
| 无任何观测 | 发 `reason=1`、三向未知、限速 0 | 停车 |
| 观测过期 | `valid_ms` 递减，两路均不可用后发 `reason=1` | 超过 `valid_ms` 仍未更新则停车 |
| 时间戳早于上次 | 清空缓存、换 `session_id` | 按新会话处理 |
| CRC 错误 | — | 丢弃，不更新状态 |
| 版本不认识 | — | 丢弃并上报 |

## 7. 变更规则

新增字段只能占用 `reserved1`，并同时升 `version`。接收端必须按 `version` 分支处理，禁止按长度猜测。

## 双源断流与期限

双源均不可用时，JSON 的 `sample_ns` 与 `valid_for_ms` 为 null。二进制字段分别为 0 与 0xFFFF，三方向为 UNKNOWN，速度建议为 0，`generated_ns` 仍是本次生成时刻。持续断流期间，只要 ROS 时钟正常推进，节点仍发送该帧。接收方看到 UNKNOWN、无效帧或本地接收看门狗超时均撤销本路证据。下一个有效帧不能绕过使用者发起运动及其他车端许可条件。

保留原版本号和 64 字节布局。32 字节自测报文须保留独立分支或独立端点，不能用截断后的风险帧充当旧报文。
