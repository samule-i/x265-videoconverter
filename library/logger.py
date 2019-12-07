#!/usr/bin/env python3
import os
import sys
import logging

def setup_logging(logDirectory=None, loggingLevel=None):
    """Initialise the logger and stdout"""

    if loggingLevel == "DEBUG":
        loggingLevel = logging.DEBUG
    elif loggingLevel == "CRITICAL":
        loggingLevel = logging.CRITICAL
    else:
        loggingLevel = logging.INFO
    # set root
    rootLogger = logging.getLogger()
    format = '%(asctime)s %(name)s.%(funcName)s +%(lineno)s: %(levelname)-8s [%(process)d] %(message)s'
    dateFormat = '%Y-%m-%d %H:%M:%S'
    formatter = logging.Formatter(format, dateFormat)
    if loggingLevel is not None:
        rootLogger.setLevel(loggingLevel)
    # logger set level
    logger = logging.getLogger(__name__)
    # file
    if logDirectory is None:
        scriptDirectory = os.path.dirname(os.path.abspath(sys.argv[0]))
        logDirectory = os.path.join(scriptDirectory, 'logs')
    if not os.path.exists(logDirectory):
        os.makedirs(logDirectory)
    logFile = os.path.join(logDirectory, '265encoder.log')
    if not len(logger.handlers):
        fileHandler = logging.FileHandler(logFile)
        fileHandler.setFormatter(formatter)
        logger.addHandler(fileHandler)
        # console
        consoleHandler = logging.StreamHandler()
        consoleHandler.setFormatter(formatter)
        logger.addHandler(consoleHandler)
    return logger

