"""
Miscellaneous utilities and helper functions for mfcauto.py
"""
import sys
import logging
from urllib.parse import quote, unquote

def create_logger(name, *, stdout=True, file=False):
    """Helper to create loggers from the logging
    module with some common predefines"""
    name = name.upper()
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    #formatter = logging.Formatter('[%(asctime)s  %(name)s  %(levelname)s] %(message)s')
    if name == "MFCAUTO":
        formatter = logging.Formatter('[%(asctime)s] %(message)s')
    else:
        formatter = logging.Formatter('[%(asctime)s, %(name)s] %(message)s')

    if stdout:
        stdout_handler = logging.StreamHandler(stream=sys.stdout)
        stdout_handler.setFormatter(formatter)
        logger.addHandler(stdout_handler)

    if file:
        file_handler = logging.FileHandler(name + ".log")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger

log = create_logger('mfcauto')

def unquote_str(text):
    """Takes a string that may or may not be encoded via JavaScript's
    encodeURIComponent and decodes it if necessary"""
    if isinstance(text, str):
        unquoted_text = unquote(text)
        if text == unquoted_text:
            return text
        else:
            quoted_text = quote(unquoted_text, safe="~()*!.\'")
            if quoted_text == text:
                return unquoted_text
    return text

def unquote_any(anything):
    """Unquotes strings, lists, or dicts recursively"""
    if isinstance(anything, str):
        anything = unquote_str(anything)
    elif isinstance(anything, list):
        for i, value in enumerate(anything):
            anything[i] = unquote_any(value)
    elif isinstance(anything, dict):
        for key, value in anything.items():
            anything[key] = unquote_any(value)
    return anything

__all__ = ["create_logger", "log", "unquote_any"]
