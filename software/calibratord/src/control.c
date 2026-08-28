#define _POSIX_C_SOURCE 200809L

#include "calibrator_control.h"

#include <ctype.h>
#include <limits.h>
#include <stdint.h>
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

enum request_field {
    FIELD_AUTH = 1u << 0,
    FIELD_COMMAND = 1u << 1,
    FIELD_THRESHOLD = 1u << 2,
    FIELD_CHANNEL = 1u << 3,
    FIELD_INTEGER_DELAY = 1u << 4,
    FIELD_FRACTIONAL_DELAY = 1u << 5,
    FIELD_GAIN_REAL = 1u << 6,
    FIELD_GAIN_IMAG = 1u << 7,
    FIELD_FLAGS = 1u << 8,
};

static void skip_space(const char **cursor)
{
    while (isspace((unsigned char)**cursor))
        ++*cursor;
}

static int parse_string(const char **cursor, char *output, size_t capacity)
{
    size_t length = 0;
    if (**cursor != '"')
        return -1;
    ++*cursor;
    while (**cursor != '\0' && **cursor != '"') {
        unsigned char character = (unsigned char)**cursor;
        if (character < 0x20u || character == '\\' || length + 1u >= capacity)
            return -1;
        output[length++] = (char)character;
        ++*cursor;
    }
    if (**cursor != '"')
        return -1;
    ++*cursor;
    output[length] = '\0';
    return 0;
}

static int parse_integer(const char **cursor, bool signed_value,
                         int64_t minimum, uint64_t maximum, int64_t *result)
{
    const char *position = *cursor;
    bool negative = false;
    uint64_t magnitude = 0;
    uint64_t limit;
    if (*position == '-') {
        if (!signed_value)
            return -1;
        negative = true;
        ++position;
    }
    if (!isdigit((unsigned char)*position))
        return -1;
    if (*position == '0' && isdigit((unsigned char)position[1]))
        return -1;
    limit = negative ? (uint64_t)(-(minimum + 1)) + 1u : maximum;
    do {
        unsigned digit = (unsigned)(*position - '0');
        if (magnitude > (limit - digit) / 10u)
            return -1;
        magnitude = magnitude * 10u + digit;
        ++position;
    } while (isdigit((unsigned char)*position));
    if (negative) {
        if (magnitude == (uint64_t)INT64_MAX + 1u)
            *result = INT64_MIN;
        else
            *result = -(int64_t)magnitude;
    } else {
        *result = (int64_t)magnitude;
    }
    if (*result < minimum || (!negative && magnitude > maximum))
        return -1;
    *cursor = position;
    return 0;
}

static enum cal_control_command command_from_name(const char *name)
{
    static const struct {
        const char *name;
        enum cal_control_command command;
    } commands[] = {
        {"get_status", CAL_CONTROL_COMMAND_GET_STATUS},
        {"start", CAL_CONTROL_COMMAND_START},
        {"stop", CAL_CONTROL_COMMAND_STOP},
        {"set_threshold", CAL_CONTROL_COMMAND_SET_THRESHOLD},
        {"set_calibration", CAL_CONTROL_COMMAND_SET_CALIBRATION},
        {"commit_calibration", CAL_CONTROL_COMMAND_COMMIT_CALIBRATION},
        {"run_mts", CAL_CONTROL_COMMAND_RUN_MTS},
        {"clear_errors", CAL_CONTROL_COMMAND_CLEAR_ERRORS},
        {"shutdown", CAL_CONTROL_COMMAND_SHUTDOWN},
    };
    size_t index;
    for (index = 0; index < sizeof(commands) / sizeof(commands[0]); ++index) {
        if (strcmp(name, commands[index].name) == 0)
            return commands[index].command;
    }
    return CAL_CONTROL_COMMAND_INVALID;
}

static int parse_request_field(const char **cursor, const char *key,
                               struct cal_control_request *request, uint32_t *present)
{
    uint32_t field;
    int64_t value;
    char text[CAL_CONTROL_TOKEN_HEX_LENGTH + 1u];
    bool string_value = false;
    bool signed_value = false;
    int64_t minimum = 0;
    uint64_t maximum = UINT32_MAX;

    if (strcmp(key, "auth") == 0) {
        field = FIELD_AUTH;
        string_value = true;
    } else if (strcmp(key, "command") == 0) {
        field = FIELD_COMMAND;
        string_value = true;
    } else if (strcmp(key, "threshold") == 0) {
        field = FIELD_THRESHOLD;
    } else if (strcmp(key, "channel") == 0) {
        field = FIELD_CHANNEL;
        maximum = 7;
    } else if (strcmp(key, "integer_delay") == 0) {
        field = FIELD_INTEGER_DELAY;
        maximum = 2047;
    } else if (strcmp(key, "fractional_delay_q20") == 0) {
        field = FIELD_FRACTIONAL_DELAY;
        maximum = 1048575;
    } else if (strcmp(key, "gain_real") == 0) {
        field = FIELD_GAIN_REAL;
        signed_value = true;
        minimum = -8388608;
        maximum = 8388607;
    } else if (strcmp(key, "gain_imag") == 0) {
        field = FIELD_GAIN_IMAG;
        signed_value = true;
        minimum = -8388608;
        maximum = 8388607;
    } else if (strcmp(key, "flags") == 0) {
        field = FIELD_FLAGS;
        maximum = 1;
    } else {
        return -1;
    }
    if ((*present & field) != 0)
        return -1;
    *present |= field;
    if (string_value) {
        if (parse_string(cursor, text, sizeof(text)))
            return -1;
        if (field == FIELD_AUTH) {
            if (strlen(text) != CAL_CONTROL_TOKEN_HEX_LENGTH)
                return -1;
            memcpy(request->auth, text, sizeof(request->auth));
        } else {
            request->command = command_from_name(text);
            if (request->command == CAL_CONTROL_COMMAND_INVALID)
                return -1;
        }
        return 0;
    }
    if (parse_integer(cursor, signed_value, minimum, maximum, &value))
        return -1;
    switch (field) {
    case FIELD_THRESHOLD: request->threshold = (uint32_t)value; break;
    case FIELD_CHANNEL: request->channel = (uint32_t)value; break;
    case FIELD_INTEGER_DELAY: request->integer_delay = (uint32_t)value; break;
    case FIELD_FRACTIONAL_DELAY: request->fractional_delay_q20 = (uint32_t)value; break;
    case FIELD_GAIN_REAL: request->gain_real = (int32_t)value; break;
    case FIELD_GAIN_IMAG: request->gain_imag = (int32_t)value; break;
    case FIELD_FLAGS: request->flags = (uint32_t)value; break;
    default: return -1;
    }
    return 0;
}

int cal_parse_control_request(const char *line, struct cal_control_request *request)
{
    const uint32_t basic = FIELD_AUTH | FIELD_COMMAND;
    const uint32_t calibration = basic | FIELD_CHANNEL | FIELD_INTEGER_DELAY |
        FIELD_FRACTIONAL_DELAY | FIELD_GAIN_REAL | FIELD_GAIN_IMAG | FIELD_FLAGS;
    const char *cursor = line;
    uint32_t present = 0;
    uint32_t required;
    if (line == NULL || request == NULL)
        return -1;
    memset(request, 0, sizeof(*request));
    skip_space(&cursor);
    if (*cursor++ != '{')
        return -1;
    skip_space(&cursor);
    if (*cursor == '}')
        return -1;
    for (;;) {
        char key[32];
        if (parse_string(&cursor, key, sizeof(key)))
            return -1;
        skip_space(&cursor);
        if (*cursor++ != ':')
            return -1;
        skip_space(&cursor);
        if (parse_request_field(&cursor, key, request, &present))
            return -1;
        skip_space(&cursor);
        if (*cursor == '}') {
            ++cursor;
            break;
        }
        if (*cursor++ != ',')
            return -1;
        skip_space(&cursor);
    }
    skip_space(&cursor);
    if (*cursor != '\0')
        return -1;
    if (request->command == CAL_CONTROL_COMMAND_SET_THRESHOLD)
        required = basic | FIELD_THRESHOLD;
    else if (request->command == CAL_CONTROL_COMMAND_SET_CALIBRATION)
        required = calibration;
    else
        required = basic;
    return present == required ? 0 : -1;
}

bool cal_control_token_valid(const char *expected, const char *presented)
{
    volatile unsigned difference = 0;
    size_t index;
    if (expected == NULL || presented == NULL ||
        strlen(expected) != CAL_CONTROL_TOKEN_HEX_LENGTH ||
        strlen(presented) != CAL_CONTROL_TOKEN_HEX_LENGTH)
        return false;
    for (index = 0; index < CAL_CONTROL_TOKEN_HEX_LENGTH; ++index) {
        unsigned char left = (unsigned char)expected[index];
        unsigned char right = (unsigned char)presented[index];
        difference |= (unsigned)(left ^ right);
        difference |= (unsigned)(!isxdigit(left));
        difference |= (unsigned)(!isxdigit(right));
    }
    return difference == 0;
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
