#ifndef SUIXING_RISK_RX_H
#define SUIXING_RISK_RX_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef enum { SX_INVALID, SX_STALE, SX_UNKNOWN, SX_FRESH } sx_status;

typedef struct {
    uint32_t session, sequence;
    uint64_t sample_ns, generated_ns;
    uint16_t valid_ms;
    uint8_t left, straight, right;
} sx_risk;

/* now_ros_ns requires a trusted mapping into the sender's ROS time domain.
 * SX_FRESH describes evidence only. CPU3 owns all motion permissions. */
sx_status sx_decode(const uint8_t *buf, size_t len, uint64_t now_ros_ns,
                    bool clock_synced, sx_risk *out);
#endif
