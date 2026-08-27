#define _POSIX_C_SOURCE 200809L

#include "calibrator_control.h"

#include <signal.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

static int open_pair(int sockets[2])
{
    return socketpair(AF_UNIX, SOCK_STREAM, 0, sockets);
}

static int fragmented_request(void)
{
    int sockets[2];
    char line[64] = {0};
    if (open_pair(sockets) || write(sockets[0], "{\"command\":", 11) != 11 ||
        write(sockets[0], "\"stop\"}\n", 8) != 8)
        return 1;
    if (cal_read_json_request(sockets[1], line, sizeof(line), 100) != CAL_JSON_LINE_COMPLETE ||
        strcmp(line, "{\"command\":\"stop\"}"))
        return 1;
    close(sockets[0]);
    close(sockets[1]);
    return 0;
}

static int first_line_wins_independent_of_segmentation(void)
{
    int sockets[2];
    char line[64] = {0};
    if (open_pair(sockets) || write(sockets[0], "first\nsecond\n", 13) != 13)
        return 1;
    if (cal_read_json_request(sockets[1], line, sizeof(line), 100) != CAL_JSON_LINE_COMPLETE ||
        strcmp(line, "first"))
        return 1;
    close(sockets[0]);
    close(sockets[1]);
    return 0;
}

static int partial_request_times_out(void)
{
    int sockets[2];
    char line[64] = {0};
    if (open_pair(sockets) || write(sockets[0], "partial", 7) != 7)
        return 1;
    if (cal_read_json_request(sockets[1], line, sizeof(line), 25) != CAL_JSON_LINE_TIMEOUT)
        return 1;
    close(sockets[0]);
    close(sockets[1]);
    return 0;
}

static int trickle_request_respects_total_deadline(void)
{
    int sockets[2];
    char line[64] = {0};
    struct timespec start;
    struct timespec finish;
    pid_t writer;
    long elapsed_ms;
    if (open_pair(sockets) || clock_gettime(CLOCK_MONOTONIC, &start))
        return 1;
    writer = fork();
    if (writer < 0)
        return 1;
    if (writer == 0) {
        struct timespec pause = { .tv_sec = 0, .tv_nsec = 40000000L };
        int index;
        close(sockets[1]);
        signal(SIGPIPE, SIG_IGN);
        for (index = 0; index < 6; ++index) {
            if (write(sockets[0], "x", 1) != 1)
                _exit(0);
            nanosleep(&pause, NULL);
        }
        _exit(0);
    }
    close(sockets[0]);
    if (cal_read_json_request(sockets[1], line, sizeof(line), 100) != CAL_JSON_LINE_TIMEOUT)
        return 1;
    if (clock_gettime(CLOCK_MONOTONIC, &finish))
        return 1;
    elapsed_ms = (finish.tv_sec - start.tv_sec) * 1000L +
                 (finish.tv_nsec - start.tv_nsec) / 1000000L;
    close(sockets[1]);
    waitpid(writer, NULL, 0);
    return elapsed_ms > 180L;
}

static int exact_length_boundary(void)
{
    int sockets[2];
    char line[4096] = {0};
    char request[4097];
    memset(request, 'x', 4095);
    request[4095] = '\n';
    if (open_pair(sockets) || write(sockets[0], request, 4096) != 4096)
        return 1;
    if (cal_read_json_request(sockets[1], line, sizeof(line), 100) != CAL_JSON_LINE_COMPLETE ||
        strlen(line) != 4095)
        return 1;
    close(sockets[0]);
    close(sockets[1]);

    memset(request, 'x', sizeof(request));
    if (open_pair(sockets) || write(sockets[0], request, 4096) != 4096)
        return 1;
    if (cal_read_json_request(sockets[1], line, sizeof(line), 100) != CAL_JSON_LINE_TOO_LONG)
        return 1;
    close(sockets[0]);
    close(sockets[1]);
    return 0;
}

int main(void)
{
    return fragmented_request() || first_line_wins_independent_of_segmentation() ||
           partial_request_times_out() || trickle_request_respects_total_deadline() ||
           exact_length_boundary();
}
