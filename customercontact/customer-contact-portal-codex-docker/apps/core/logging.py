"""Allowlist log fields so request paths, inputs and exception values stay private."""
import json
import logging


class SafeFormatter(logging.Formatter):
    def format(self, record):
        fields = {"level": record.levelname, "logger": record.name}
        if isinstance(getattr(record, "status_code", None), int):
            fields["status"] = record.status_code
        if record.exc_info:
            fields["exception"] = record.exc_info[0].__name__
        return json.dumps(fields)
