'''The coqide package.'''


def setup_debug_log(filename):
    '''Setup the debug logger.'''
    import logging
    logger = logging.getLogger(__name__)
    filehandler = logging.FileHandler(filename, mode='a')
    logger.addHandler(filehandler)
    logger.setLevel(logging.DEBUG)
