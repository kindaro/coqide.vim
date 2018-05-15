'''The CoqIDE module.'''

import logging

logger = logging.getLogger(__name__)
fh = logging.FileHandler('coqide.log', mode='w')
logger.addHandler(fh)
logger.setLevel(logging.DEBUG)


def activate():
    '''Activate CoqIDE and return the VimUI instance.'''
    from .vimui import VimUI
    return VimUI()
