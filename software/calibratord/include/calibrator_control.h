#pragma once

#include <stdbool.h>
#include <stddef.h>

enum cal_json_line_status {
    CAL_JSON_LINE_INCOMPLETE = 0,
    CAL_JSON_LINE_COMPLETE = 1,
    CAL_JSON_LINE_MISSING_NEWLINE = -1,
    CAL_JSON_LINE_TOO_LONG = -2,
    CAL_JSON_LINE_EXTRA_DATA = -3,
};

struct cal_json_line_reader {
    size_t length;
    bool complete;
};

bool cal_poweroff_allowed(const char *value);
int cal_json_line_append(struct cal_json_line_reader *reader, char *line,
                         size_t capacity, const char *chunk, size_t chunk_length);
int cal_json_line_eof(const struct cal_json_line_reader *reader);
