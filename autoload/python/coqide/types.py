'''Common data types.'''

from collections import namedtuple
from functools import total_ordering

Unit = namedtuple('Unit', '')
StateID = namedtuple('StateID', 'val')
Some = namedtuple('Some', 'val')
UnionL = namedtuple('Union', ' val')
UnionR = namedtuple('Union', ' val')
Goals = namedtuple('Goals', 'fg bg shelved abandoned')
Goal = namedtuple('Goal', 'id hyps goal')
Location = namedtuple('Location', 'start stop')
Message = namedtuple('Message', 'level text')
Sentence = namedtuple('Sentence', 'text start stop')


@total_ordering
class Mark(namedtuple('Mark', 'line col')):
    '''The position in a document represented with 1-indexed line/column.'''

    def __lt__(self, other):
        return self.line < other.line or \
            (self.line == other.line and self.col < other.col)
