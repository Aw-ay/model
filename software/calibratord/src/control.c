#define _POSIX_C_SOURCE 200809L

#include "calibrator_control.h"

#include <limits.h>
#include <string.h>

#ifndef _WIN32
#include <errno.h>
#include <poll.h>
#include <sys/socket.h>
#include <time.h>
#endif

bool cal_poweroff_allowed(const char *value)
{
    return value != NULL && strcmp(value, "1") == 0;
}

int cal_json_line_append(struct cal_json_line_reader *reader, char *line,
                         size_t capacity, const char *chunk, size_t chunk_length)
{
    size_t index;
    if (reader == NULL || line == NULL || chunk == NULL || capacity == 0)
        return CAL_JSON_LINE_TOO_LONG;
    if (reader->complete)
        return CAL_JSON_LINE_EXTRA_DATA;
    for (index = 0; index < chunk_length; ++index) {
        if (chunk[index] == '\n') {
            line[reader->length] = '\0';
            reader->complete = true;
            return CAL_JSON_LINE_COMPLETE;
        }
        if (reader->length + 1 >= capacity)
            return CAL_JSON_LINE_TOO_LONG;
        line[reader->length++] = chunk[index];
    }
    return CAL_JSON_LINE_INCOMPLETE;
}

int cal_json_line_eof(const struct cal_json_line_reader *reader)
{
    return reader != NULL && reader->complete ? CAL_JSON_LINE_COMPLETE : CAL_JSON_LINE_MISSING_NEWLINE;
}

#ifndef _WIN32
static int remaining_timeout_ms(const struct timespec *deadline)
{
    struct timespec now;
    time_t seconds;
    long nanoseconds;
    long long milliseconds;
    if (clock_gettime(CLOCK_MONOTONIC, &now))
        return -1;
    seconds = deadline->tv_sec - now.tv_sec;
    nanoseconds = deadline->tv_nsec - now.tv_nsec;
    if (nanoseconds < 0) {
        --seconds;
        nanoseconds += 1000000000L;
    }
    if (seconds < 0 || (seconds == 0 && nanoseconds <= 0))
        return 0;
    if (seconds > INT_MAX / 1000)
        return INT_MAX;
    milliseconds = (long long)seconds * 1000 + (nanoseconds + 999999L) / 1000000L;
    return milliseconds > INT_MAX ? INT_MAX : (int)milliseconds;
}
#endif

int cal_read_json_request(int fd, char *line, size_t capacity, int timeout_ms)
{
#ifdef _WIN32
    (void)fd;
    (void)line;
    (void)capacity;
    (void)timeout_ms;
    return CAL_JSON_LINE_READ_ERROR;
#else
    struct cal_json_line_reader reader = {0};
    char chunk[512];
    struct timespec deadline;
    if (fd < 0 || line == NULL || capacity == 0 || timeout_ms <= 0)
        return CAL_JSON_LINE_READ_ERROR;
    if (clock_gettime(CLOCK_MONOTONIC, &deadline))
        return CAL_JSON_LINE_READ_ERROR;
    deadline.tv_sec += timeout_ms / 1000;
    deadline.tv_nsec += (long)(timeout_ms % 1000) * 1000000L;
    if (deadline.tv_nsec >= 1000000000L) {
        ++deadline.tv_sec;
        deadline.tv_nsec -= 1000000000L;
    }
    for (;;) {
        struct pollfd ready = { .fd = fd, .events = POLLIN };
        int remaining_ms = remaining_timeout_ms(&deadline);
        int poll_status;
        ssize_t count;
        int status;
        if (remaining_ms < 0)
            return CAL_JSON_LINE_READ_ERROR;
        if (remaining_ms == 0)
            return CAL_JSON_LINE_TIMEOUT;
        poll_status = poll(&ready, 1, remaining_ms);
        if (poll_status < 0 && errno == EINTR)
            continue;
        if (poll_status < 0)
            return CAL_JSON_LINE_READ_ERROR;
        if (poll_status == 0)
            return CAL_JSON_LINE_TIMEOUT;
        count = recv(fd, chunk, sizeof(chunk), 0);
        if (count < 0 && errno == EINTR)
            continue;
        if (count < 0)
            return CAL_JSON_LINE_READ_ERROR;
        if (count == 0)
            return cal_json_line_eof(&reader);
        status = cal_json_line_append(&reader, line, capacity, chunk, (size_t)count);
        if (status != CAL_JSON_LINE_INCOMPLETE)
            return status;
    }
#endif
}
