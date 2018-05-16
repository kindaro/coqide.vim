'''The CoqIDE module.'''


def setup_debug_log(filename):
    '''Setup the logger for the package.'''
    import logging
    logger = logging.getLogger(__name__)
    filehandler = logging.FileHandler(filename, mode='a')
    logger.addHandler(filehandler)
    logger.setLevel(logging.DEBUG)


def activate():
    '''Activate CoqIDE and return the VimUI instance.'''
    from .vimui import VimUI
    return VimUI()
