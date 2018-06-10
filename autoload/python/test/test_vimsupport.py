'''Test module `coqide.vimsupport`.'''

from unittest import TestCase
from unittest.mock import MagicMock, Mock, call

from coqide.vimsupport import VimSupport
from coqide.types import Mark, Sentence


# pylint: disable=R0201
class TestVimSupport(TestCase):
    '''Test class `VimSupport`.'''

    def test_get_buffer(self):
        '''Test method `get_buffer`.'''
        api = Mock()
        vim = VimSupport(api)
        self.assertEqual(vim.get_buffer(), api.current.buffer)

    def test_get_sentence_after(self):
        '''Test method `get_sentence_after`.'''
        api = Mock()
        api.current.buffer = [
            'Proof. simpl.',
            '  reflexivity.',
            'Qed.']
        vim = VimSupport(api)
        sentence = vim.get_sentence_after(Mark(1, 1))
        self.assertEqual(sentence,
                         Sentence('Proof.', Mark(1, 1), Mark(1, 7)))
        sentence = vim.get_sentence_after(Mark(1, 7))
        self.assertEqual(sentence,
                         Sentence(' simpl.', Mark(1, 7), Mark(1, 14)))
        sentence = vim.get_sentence_after(Mark(1, 14))
        self.assertEqual(sentence,
                         Sentence('\n  reflexivity.', Mark(1, 14), Mark(2, 15)))
        sentence = vim.get_sentence_after(Mark(2, 15))
        self.assertEqual(sentence,
                         Sentence('\nQed.', Mark(2, 15), Mark(3, 5)))

    def test_get_cursor(self):
        '''Test method `get_cursor`.'''
        api = Mock()
        api.eval.side_effect = \
            lambda x: [None, 3, 6, None] if x == 'getpos(".")' else None
        vim = VimSupport(api)
        self.assertEqual(vim.get_cursor(), Mark(3, 6))

    def test_add_match(self):
        '''Test method `add_match`.'''
        def _eval(cmd):
            if cmd == 'matchaddpos("CoqStcSent", [[1, 5, 3], 2, [3, 1, 2]])':
                return 1
            return None
        api = Mock()
        api.eval.side_effect = _eval
        api.current.buffer = [
            'aaaa333',
            '32414',
            '33aaa']
        vim = VimSupport(api)
        self.assertEqual(vim.add_match(Mark(1, 5), Mark(3, 3), 'CoqStcSent'),
                         [1])

    def test_del_match(self):
        '''Test method `del_match`.'''
        api = Mock()
        vim = VimSupport(api)
        vim.del_match([1, 2])
        self.assertListEqual(api.eval.call_args_list, [
            call('matchdelete(1)'),
            call('matchdelete(2)'),
        ])

    def test_in_winid(self):
        '''Test method `in_winid`.'''
        def _eval(cmd):
            if cmd == 'winsaveview()':
                return {'a': 1}
            elif cmd == 'winnr()':
                return '3'
            elif cmd == 'win_id2win(184)':
                return '1'
            elif cmd == 'winrestview({\'a\': 1})':
                return None
            raise AssertionError('bad cmd: {}'.format(cmd))

        api = Mock()
        api.eval.side_effect = _eval
        vim = VimSupport(api)
        done = False
        with vim.in_winid('184'):
            done = True
        self.assertTrue(done)
        self.assertListEqual(api.command.call_args_list, [
            call('1wincmd w'),
            call('3wincmd w'),
        ])

    def test_set_bufname_lines(self):
        '''Test method `set_bufname_lines`.'''
        buf1 = MagicMock()
        buf1.name = 'buf1'
        buf2 = MagicMock()
        buf2.name = 'buf2'
        api = Mock()
        api.buffers = [buf1, buf2]
        vim = VimSupport(api)
        vim.set_bufname_lines('buf2', ['a', 'b'])
        buf2.__setitem__.assert_called_once_with(
            slice(None, None, None), ['a', 'b'])
        buf1.__setitem__.assert_not_called()
