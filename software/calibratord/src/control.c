#include "calibrator_control.h"

#include <string.h>

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
            return index + 1 == chunk_length ? CAL_JSON_LINE_COMPLETE : CAL_JSON_LINE_EXTRA_DATA;
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
