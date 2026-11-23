#include "risk_rx.h"
#include <assert.h>
#include <stdio.h>

static void read_fixture(const char *name, uint8_t *buf)
{
    char path[128];
    assert(snprintf(path, sizeof path, "fixtures/%s/risk.bin", name) > 0);
    FILE *file = fopen(path, "rb");
    assert(file && fread(buf, 1, 64, file) == 64 && fgetc(file) == EOF);
    fclose(file);
}

int main(void)
{
    uint8_t buf[64];
    sx_risk risk;
    read_fixture("normal", buf);
    assert(sx_decode(buf, 64, 1139999999, true, &risk) == SX_FRESH);
    assert(risk.valid_ms == 120 && risk.straight == 1 && risk.sequence == 1);
    assert(sx_decode(buf, 64, 1140000000, true, &risk) == SX_STALE);
    assert(sx_decode(buf, 64, 1020000000, false, &risk) == SX_STALE);
    assert(sx_decode(buf, 32, 1020000000, true, &risk) == SX_INVALID);
    buf[63] = 0xff;
    assert(sx_decode(buf, 64, 1020000000, true, &risk) == SX_FRESH);
    assert(risk.session == 0x01234567 && risk.sequence == 1);
    buf[20] ^= 1;
    assert(sx_decode(buf, 64, 1020000000, true, &risk) == SX_INVALID);
    read_fixture("exact_expiry", buf);
    assert(sx_decode(buf, 64, 1140000000, true, &risk) == SX_UNKNOWN);
    assert(!risk.sample_ns && risk.valid_ms == 0xffff && !risk.straight);
    read_fixture("both_missing", buf);
    assert(sx_decode(buf, 64, 1200000000, true, &risk) == SX_UNKNOWN);
    assert(!risk.sample_ns && risk.valid_ms == 0xffff && !risk.straight);
    puts("PASS C decoder: normal, exact receiver deadline, unsynced clock, legacy length, CRC, ignored tail, expired sensors, both missing");
}
