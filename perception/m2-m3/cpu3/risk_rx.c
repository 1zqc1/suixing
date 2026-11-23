#include "risk_rx.h"
#include <string.h>

static uint64_t read_le(const uint8_t *buf, size_t size)
{
    uint64_t result = 0;
    for (size_t i = 0; i < size; ++i)
        result |= (uint64_t)buf[i] << (8 * i);
    return result;
}

static uint16_t crc16(const uint8_t *buf, size_t size)
{
    uint16_t crc = 0xffff;
    for (size_t i = 0; i < size; ++i) {
        crc ^= (uint16_t)buf[i] << 8;
        for (unsigned bit = 0; bit < 8; ++bit)
            crc = (uint16_t)((crc << 1) ^ ((crc & 0x8000) ? 0x1021 : 0));
    }
    return crc;
}

sx_status sx_decode(const uint8_t *buf, size_t len, uint64_t now_ros_ns,
                    bool clock_synced, sx_risk *out)
{
    if (!out)
        return SX_INVALID;
    *out = (sx_risk){0};
    if (!buf || len != 64 || memcmp(buf, "SXR1", 4) || buf[4] != 1 || buf[5] != 1 ||
        read_le(buf + 48, 2) != crc16(buf, 48) ||
        buf[40] > 3 || buf[41] > 3 || buf[42] > 3)
        return SX_INVALID;

    sx_risk frame = {
        .session = (uint32_t)read_le(buf + 8, 4),
        .sequence = (uint32_t)read_le(buf + 12, 4),
        .sample_ns = read_le(buf + 16, 8),
        .generated_ns = read_le(buf + 24, 8),
        .valid_ms = (uint16_t)read_le(buf + 32, 2),
        .left = buf[40], .straight = buf[41], .right = buf[42],
    };
    if (frame.generated_ns == 0 || frame.sample_ns > frame.generated_ns)
        return SX_INVALID;
    if (frame.sample_ns == 0 && (frame.left || frame.straight || frame.right ||
        frame.valid_ms != 0xffff || (buf[6] & 0x0f) != 0))
        return SX_INVALID;
    *out = frame;
    if (!frame.left && !frame.straight && !frame.right)
        return SX_UNKNOWN;
    if (!clock_synced || now_ros_ns < frame.generated_ns || !frame.valid_ms ||
        frame.valid_ms == 0xffff || now_ros_ns - frame.generated_ns >= (uint64_t)frame.valid_ms * 1000000)
        return SX_STALE;
    return SX_FRESH;
}
