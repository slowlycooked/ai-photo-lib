import re
import logging

class SensitiveDataFilter(logging.Filter):
    SENSITIVE_PATTERNS = [
        re.compile(r"(Authorization|Api[-_]?Key|token|secret|DATABASE_URL)['\"]?[:= ]+([^'\"\s]+)", re.I),
        re.compile(r"(Bearer|Token) [A-Za-z0-9\-\._~\+\/]+=*", re.I),
        re.compile(r"postgres://[^:]+:([^@]+)@", re.I),
    ]
    MASK = "***"
    def filter(self, record):
        msg = record.getMessage()
        for pat in self.SENSITIVE_PATTERNS:
            msg = pat.sub(r"\\1: {}".format(self.MASK), msg)
        record.msg = msg
        return True
