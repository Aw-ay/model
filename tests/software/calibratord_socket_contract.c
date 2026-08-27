#include "calibrator_control.h"

#include <string.h>
#include <sys/socket.h>
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
           partial_request_times_out() || exact_length_boundary();
}
