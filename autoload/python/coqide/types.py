'''Common data types.'''

from collections import namedtuple

Unit = namedtuple('Unit', '')
StateID = namedtuple('StateID', 'val')
Some = namedtuple('Some', 'val')
UnionL = namedtuple('Union', ' val')
UnionR = namedtuple('Union', ' val')
Goals = namedtuple('Goals', 'fg bg shelved abandoned')
Goal = namedtuple('Goal', 'id hyps goal')
Location = namedtuple('Location', 'start stop')
Message = namedtuple('Message', 'level text')
Mark = namedtuple('Mark', 'line col')
Sentence = namedtuple('Sentence', 'text start stop')
