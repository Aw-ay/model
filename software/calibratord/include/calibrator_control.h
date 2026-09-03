#pragma once

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define CAL_CONTROL_TOKEN_HEX_LENGTH 64u

enum cal_control_command {
    CAL_CONTROL_COMMAND_INVALID = 0,
    CAL_CONTROL_COMMAND_GET_STATUS,
    CAL_CONTROL_COMMAND_START,
    CAL_CONTROL_COMMAND_STOP,
    CAL_CONTROL_COMMAND_SET_THRESHOLD,
    CAL_CONTROL_COMMAND_SET_CALIBRATION,
    CAL_CONTROL_COMMAND_COMMIT_CALIBRATION,
    CAL_CONTROL_COMMAND_RUN_MTS,
    CAL_CONTROL_COMMAND_CLEAR_ERRORS,
    CAL_CONTROL_COMMAND_SHUTDOWN,
};

struct cal_control_request {
    enum cal_control_command command;
    char auth[CAL_CONTROL_TOKEN_HEX_LENGTH + 1u];
    uint32_t threshold;
    uint32_t channel;
    uint32_t integer_delay;
    uint32_t fractional_delay_q20;
    int32_t gain_real;
    int32_t gain_imag;
    uint32_t flags;
};

enum cal_json_line_status {
    CAL_JSON_LINE_INCOMPLETE = 0,
    CAL_JSON_LINE_COMPLETE = 1,
    CAL_JSON_LINE_MISSING_NEWLINE = -1,
    CAL_JSON_LINE_TOO_LONG = -2,
    CAL_JSON_LINE_EXTRA_DATA = -3,
    CAL_JSON_LINE_READ_ERROR = -4,
    CAL_JSON_LINE_TIMEOUT = -5,
    CAL_JSON_LINE_INVALID_BYTE = -6,
};

struct cal_json_line_reader {
    size_t length;
    bool complete;
};

bool cal_poweroff_allowed(const char *value);
bool cal_control_token_valid(const char *expected, const char *presented);
int cal_parse_control_request(const char *line, struct cal_control_request *request);
int cal_json_line_append(struct cal_json_line_reader *reader, char *line,
                         size_t capacity, const char *chunk, size_t chunk_length);
int cal_json_line_eof(const struct cal_json_line_reader *reader);
int cal_read_json_request(int fd, char *line, size_t capacity, int timeout_ms);
