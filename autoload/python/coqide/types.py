'''Common data types.'''

from collections import namedtuple
from functools import total_ordering
from itertools import chain

Unit = namedtuple('Unit', '')
StateID = namedtuple('StateID', 'val')
Some = namedtuple('Some', 'val')
UnionL = namedtuple('Union', ' val')
UnionR = namedtuple('Union', ' val')
Location = namedtuple('Location', 'start stop')
Message = namedtuple('Message', 'level text')
Sentence = namedtuple('Sentence', 'text start stop')
Goal = namedtuple('Goal', 'id hyps goal')


@total_ordering
class Mark(namedtuple('Mark', 'line col')):
    '''The position in a document represented with 1-indexed line/column.'''

    def __lt__(self, other):
        return self.line < other.line or \
            (self.line == other.line and self.col < other.col)


class Goals(namedtuple('Goals', 'fg bg shelved abandoned')):
    '''The goals of the current state.'''

    def tolines(self):
        '''Return a list of strings as the text representation.'''
        content = []
        nr_fg = len(self.fg)
        if nr_fg == 0:
            total = 0
            for goal_pair in self.bg:
                total += len(goal_pair[0]) + len(goal_pair[1])

            if total > 0:
                content.append('This subproof is complete, but there are '
                               'some unfocused goals:')
                content.append('')
                index = 1
                for goal_pair in self.bg:
                    for goal in chain(goal_pair[0], goal_pair[1]):
                        content.append('_______________________ ({}/{})'
                                       .format(index, total))
                        content.extend(goal.goal.split('\n'))
            else:
                content.append('No more subgoals.')
        else:
            if nr_fg == 1:
                content.append('1 subgoal')
            else:
                content.append('{} subgoals'.format(nr_fg))

            for hyp in self.fg[0].hyps:
                content.extend(hyp.split('\n'))
            for index, goal in enumerate(self.fg):
                content.append('_______________________ ({}/{})'
                               .format(index + 1, nr_fg))
                content.extend(goal.goal.split('\n'))
        return content
