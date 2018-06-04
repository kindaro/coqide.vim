'''The functions for Vim operations.'''

from contextlib import contextmanager

import vim


def get_buffer():
    '''Return the current buffer.'''
    return vim.current.buffer


def get_sentence_after(start):
    '''Return the sentence object containing the text after the start mark.'''


def get_cursor():
    '''Return the position of the cursor in Mark.'''


def add_match(start, stop, hlgroup):
    '''Add a match to the current window and return the match id.'''


def del_match(match_id):
    '''Remove the match of the given id.'''


@contextmanager
def in_window(bufnr):
    '''Switch to the window in the given buffer number.'''
