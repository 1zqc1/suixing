/*
 * rpmsg_echo_test.c - 飞腾派 OpenAMP RPMsg 收发自测
 *
 * 用途：在 Linux 侧创建端点，绑定到从核已创建的 rpmsg 通道，
 *       发送一条消息并等待回环，验证数据真的能双向流动。
 *
 * 编译：gcc -O2 -o rpmsg_echo_test rpmsg_echo_test.c
 * 运行：sudo ./rpmsg_echo_test [service_name]
 */

#define _GNU_SOURCE
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

#include <linux/rpmsg.h>

#ifndef RPMSG_ADDR_ANY
#define RPMSG_ADDR_ANY 0xFFFFFFFF
#endif

static int max_rpmsg_id(void)
{
    DIR *d = opendir("/dev");
    struct dirent *e;
    int m = -1;

    if (!d)
        return -1;

    while ((e = readdir(d)) != NULL) {
        int n;
        if (sscanf(e->d_name, "rpmsg%d", &n) == 1 && n > m)
            m = n;
    }
    closedir(d);
    return m;
}

static int create_ept(int cfd, const char *svc, unsigned int src, unsigned int dst)
{
    struct rpmsg_endpoint_info ept;

    memset(&ept, 0, sizeof(ept));
    strncpy(ept.name, svc, sizeof(ept.name) - 1);
    ept.src = src;
    ept.dst = dst;

    return ioctl(cfd, RPMSG_CREATE_EPT_IOCTL, &ept);
}

int main(int argc, char **argv)
{
    const char *svc = (argc > 1) ? argv[1] : "rpmsg-openamp-demo-channel";
    int cfd, fd, before, after, id, rc, n;
    char path[64];
    char buf[256];
    unsigned char out[64];
    const char *payload = "ping-from-linux";
    unsigned int plen;
    struct pollfd pfd;

    printf("service = %s\n", svc);

    cfd = open("/dev/rpmsg_ctrl0", O_RDWR);
    if (cfd < 0) {
        perror("open /dev/rpmsg_ctrl0");
        return 1;
    }

    before = max_rpmsg_id();
    printf("rpmsg devices before: max id = %d\n", before);

    rc = create_ept(cfd, svc, RPMSG_ADDR_ANY, 0x0);
    if (rc < 0) {
        printf("create ept (src=ANY, dst=0x0) failed: %s\n", strerror(errno));
        rc = create_ept(cfd, svc, 0x400, 0x0);
        if (rc < 0) {
            printf("create ept (src=0x400, dst=0x0) failed: %s\n", strerror(errno));
            close(cfd);
            return 2;
        }
    }
    printf("endpoint created\n");

    sleep(1);
    after = max_rpmsg_id();
    printf("rpmsg devices after: max id = %d\n", after);

    id = (after >= 0) ? after : before;
    snprintf(path, sizeof(path), "/dev/rpmsg%d", id);

    for (n = 0; n < 10; n++) {
        fd = open(path, O_RDWR);
        if (fd >= 0)
            break;
        snprintf(path, sizeof(path), "/dev/rpmsg%d", id - n);
        usleep(200000);
    }
    if (fd < 0) {
        printf("cannot open any /dev/rpmsgN: %s\n", strerror(errno));
        close(cfd);
        return 3;
    }
    printf("using %s\n", path);

    /*
     * 从核固件（rpmsg-echo_os.c）的协议：
     *   struct { uint32_t command; uint16_t length; char data[]; }
     * 只有 command = 0x0003 (DEVICE_CORE_CHECK) 才会回环。
     */
    plen = (unsigned int)strlen(payload) + 1;
    if (plen > sizeof(out) - 6)
        plen = sizeof(out) - 6;

    memset(out, 0, sizeof(out));
    *(unsigned int *)out = 0x0003U;          /* DEVICE_CORE_CHECK */
    *(unsigned short *)(out + 4) = (unsigned short)plen;
    memcpy(out + 6, payload, plen);

    n = write(fd, out, plen + 6);
    printf("write -> %d bytes (cmd=0x3, len=%u, payload=\"%s\")\n",
           n, plen, payload);

    pfd.fd = fd;
    pfd.events = POLLIN;
    pfd.revents = 0;

    rc = poll(&pfd, 1, 3000);
    if (rc > 0 && (pfd.revents & POLLIN)) {
        memset(buf, 0, sizeof(buf));
        n = read(fd, buf, sizeof(buf) - 1);
        if (n >= 6) {
            unsigned int cmd = *(unsigned int *)buf;
            unsigned short len = *(unsigned short *)(buf + 4);
            printf("RECV %d bytes: cmd=0x%x len=%u payload=\"%.*s\"\n",
                   n, cmd, len, (int)len, buf + 6);
            printf("RESULT: ECHO_OK\n");
        } else {
            printf("RECV %d bytes (short)\nRESULT: BAD_FRAME\n", n);
        }
    } else if (rc == 0) {
        printf("RESULT: NO_ECHO_TIMEOUT\n");
    } else {
        printf("RESULT: POLL_ERROR %s\n", strerror(errno));
    }

    close(fd);
    close(cfd);
    return 0;
}
