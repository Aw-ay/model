"""Behavioral contracts for calibratord's process-local control decisions."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]


class CalibratordControlContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        compiler = shutil.which("gcc")
        if compiler is None:
            raise unittest.SkipTest("gcc is unavailable")
        cls._temporary_directory = tempfile.TemporaryDirectory()
        directory = Path(cls._temporary_directory.name)
        program = directory / "calibratord_control_contract.c"
        cls._executable = directory / "calibratord_control_contract"
        program.write_text(
            "#include <string.h>\n"
            "#include \"calibrator_control.h\"\n"
            "\n"
            "static int poweroff_contract(void) {\n"
            "    return cal_poweroff_allowed(NULL) || cal_poweroff_allowed(\"\") ||\n"
            "           cal_poweroff_allowed(\"0\") || !cal_poweroff_allowed(\"1\") ||\n"
            "           cal_poweroff_allowed(\"01\");\n"
            "}\n"
            "\n"
            "static int fragmented_line_contract(void) {\n"
            "    struct cal_json_line_reader reader = {0};\n"
            "    char line[64] = {0};\n"
            "    if (cal_json_line_append(&reader, line, sizeof(line),\n"
            "                             \"{\\\"command\\\":\", 11) != CAL_JSON_LINE_INCOMPLETE)\n"
            "        return 1;\n"
            "    if (cal_json_line_append(&reader, line, sizeof(line),\n"
            "                             \"\\\"stop\\\"}\\n\", 8) != CAL_JSON_LINE_COMPLETE)\n"
            "        return 1;\n"
            "    return strcmp(line, \"{\\\"command\\\":\\\"stop\\\"}\") != 0;\n"
            "}\n"
            "\n"
            "static int invalid_line_contract(void) {\n"
            "    struct cal_json_line_reader reader = {0};\n"
            "    char line[8] = {0};\n"
            "    if (cal_json_line_append(&reader, line, sizeof(line), \"stop\", 4) != CAL_JSON_LINE_INCOMPLETE ||\n"
            "        cal_json_line_eof(&reader) != CAL_JSON_LINE_MISSING_NEWLINE)\n"
            "        return 1;\n"
            "    reader = (struct cal_json_line_reader){0};\n"
            "    if (cal_json_line_append(&reader, line, sizeof(line), \"a\\0b\", 3) != CAL_JSON_LINE_INVALID_BYTE)\n"
            "        return 1;\n"
            "    reader = (struct cal_json_line_reader){0};\n"
            "    if (cal_json_line_append(&reader, line, sizeof(line), \"12345678\", 8) != CAL_JSON_LINE_TOO_LONG)\n"
            "        return 1;\n"
            "    reader = (struct cal_json_line_reader){0};\n"
            "    if (cal_json_line_append(&reader, line, sizeof(line), \"a\\nb\", 3) != CAL_JSON_LINE_COMPLETE ||\n"
            "        strcmp(line, \"a\"))\n"
            "        return 1;\n"
            "    return cal_json_line_append(&reader, line, sizeof(line), \"b\\n\", 2) != CAL_JSON_LINE_EXTRA_DATA;\n"
            "}\n"
            "\n"
            "static int strict_request_contract(void) {\n"
            "    const char *token = \"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\";\n"
            "    struct cal_control_request request;\n"
            "    if (cal_parse_control_request(\" { \\\"auth\\\" : \\\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\\\", \\\"command\\\" : \\\"start\\\" } \", &request))\n"
            "        return 1;\n"
            "    if (request.command != CAL_CONTROL_COMMAND_START ||\n"
            "        !cal_control_token_valid(token, request.auth))\n"
            "        return 1;\n"
            "    if (!cal_parse_control_request(\"{\\\"auth\\\":\\\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\\\",\\\"command\\\":\\\"start\\\",\\\"command\\\":\\\"stop\\\"}\", &request))\n"
            "        return 1;\n"
            "    if (!cal_parse_control_request(\"{\\\"auth\\\":\\\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\\\",\\\"command\\\":\\\"start\\\"}junk\", &request))\n"
            "        return 1;\n"
            "    if (!cal_parse_control_request(\"{\\\"auth\\\":\\\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\\\",\\\"command\\\":\\\"start\\\",\\\"extra\\\":1}\", &request))\n"
            "        return 1;\n"
            "    if (!cal_parse_control_request(\"{\\\"auth\\\":\\\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\\\",\\\"command\\\":\\\"set_threshold\\\",\\\"threshold\\\":123junk}\", &request))\n"
            "        return 1;\n"
            "    if (!cal_parse_control_request(\"{\\\"auth\\\":\\\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\\\",\\\"command\\\":\\\"set_threshold\\\",\\\"threshold\\\":0x10}\", &request))\n"
            "        return 1;\n"
            "    if (!cal_parse_control_request(\"{\\\"auth\\\":\\\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\\\",\\\"command\\\":\\\"set_threshold\\\",\\\"threshold\\\":+1}\", &request))\n"
            "        return 1;\n"
            "    if (!cal_parse_control_request(\"\\f{\\\"auth\\\":\\\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\\\",\\\"command\\\":\\\"start\\\"}\", &request))\n"
            "        return 1;\n"
            "    return cal_control_token_valid(token, \"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\");\n"
            "}\n"
            "\n"
            "static int calibration_request_contract(void) {\n"
            "    struct cal_control_request request;\n"
            "    const char *line = \"{\\\"auth\\\":\\\"0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\\\",\\\"command\\\":\\\"set_calibration\\\",\\\"channel\\\":7,\\\"integer_delay\\\":2047,\\\"fractional_delay_q20\\\":1048575,\\\"gain_real\\\":-8388608,\\\"gain_imag\\\":8388607,\\\"flags\\\":1}\";\n"
            "    if (cal_parse_control_request(line, &request))\n"
            "        return 1;\n"
            "    return request.command != CAL_CONTROL_COMMAND_SET_CALIBRATION ||\n"
            "           request.channel != 7 || request.integer_delay != 2047 ||\n"
            "           request.fractional_delay_q20 != 1048575 ||\n"
            "           request.gain_real != -8388608 || request.gain_imag != 8388607 ||\n"
            "           request.flags != 1;\n"
            "}\n"
            "\n"
            "int main(int argc, char **argv) {\n"
            "    if (argc != 2) return 2;\n"
            "    if (!strcmp(argv[1], \"poweroff\")) return poweroff_contract();\n"
            "    if (!strcmp(argv[1], \"fragmented\")) return fragmented_line_contract();\n"
            "    if (!strcmp(argv[1], \"invalid\")) return invalid_line_contract();\n"
            "    if (!strcmp(argv[1], \"strict\")) return strict_request_contract();\n"
            "    if (!strcmp(argv[1], \"calibration\")) return calibration_request_contract();\n"
            "    return 2;\n"
            "}\n",
            encoding="utf-8",
        )
        subprocess.run(
            [
                compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                "-I", str(ROOT / "software/calibratord/include"), str(program),
                str(ROOT / "software/calibratord/src/control.c"),
                "-o", str(cls._executable),
            ],
            check=True,
            capture_output=True,
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls._temporary_directory.cleanup()

    def _run_contract(self, name: str) -> None:
        self.assertEqual(subprocess.run([str(self._executable), name], check=False).returncode, 0)

    def test_poweroff_requires_an_exact_opt_in_value(self) -> None:
        self._run_contract("poweroff")

    def test_fragmented_tcp_json_line_is_accumulated_until_newline(self) -> None:
        self._run_contract("fragmented")

    def test_missing_newline_and_overlong_input_are_rejected_but_only_first_line_is_consumed(self) -> None:
        self._run_contract("invalid")

    def test_control_json_is_strict_and_authenticated(self) -> None:
        self._run_contract("strict")

    def test_calibration_schema_accepts_only_bounded_fields(self) -> None:
        self._run_contract("calibration")

    def test_socket_reader_is_timeout_bounded_and_one_request_per_connection(self) -> None:
        source = (ROOT / "software/calibratord/src/control.c").read_text("utf-8")
        daemon = (ROOT / "software/calibratord/src/calibratord.c").read_text("utf-8")
        self.assertIn("clock_gettime(CLOCK_MONOTONIC, &deadline)", source)
        self.assertIn("remaining_timeout_ms(&deadline)", source)
        self.assertIn("poll(&ready, 1, remaining_ms)", source)
        self.assertNotIn("poll(&ready, 1, timeout_ms)", source)
        self.assertIn("CAL_JSON_LINE_TIMEOUT", source)
        self.assertIn("cal_read_json_request(client, line, CAL_MAX_LINE, CAL_REQUEST_TIMEOUT_MS)", daemon)
        self.assertNotIn("read_request_line", daemon)

    def test_daemon_binds_to_configured_address_and_rejects_other_peers(self) -> None:
        daemon = (ROOT / "software/calibratord/src/calibratord.c").read_text("utf-8")
        self.assertNotIn("INADDR_ANY", daemon)
        self.assertIn("CALIBRATOR_CONTROL_BIND", daemon)
        self.assertIn("CALIBRATOR_CONTROL_PEER", daemon)
        self.assertIn("CALIBRATOR_CONTROL_TOKEN_FILE", daemon)
        self.assertIn("peer.sin_addr.s_addr != state.control_peer.s_addr", daemon)


if __name__ == "__main__":
    unittest.main()
