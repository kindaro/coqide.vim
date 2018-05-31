'''The unit test of module `coqide.coqtopinstance`.'''

import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from coqide import xmlprotocol as xp
from coqide.coqtopinstance import CoqtopInstance


# pylint:disable=C0111,R0201
class TestCoqtopInstance(unittest.TestCase):
    @patch('coqide.coqtopinstance.Popen')
    @patch('coqide.coqtopinstance._CoqtopReader')
    def test_spawn(self, reader_mock, popen_mock):
        inst = CoqtopInstance()
        inst.spawn(['coqtop', '-ideslave'])

        popen_mock.assert_called_once()
        self.assertEqual(popen_mock.call_args[0][0], ['coqtop', '-ideslave'])
        reader_mock.return_value.start.assert_called_once()

    @patch('coqide.coqtopinstance.Popen')
    @patch('coqide.coqtopinstance._CoqtopReader')
    def test_call(self, reader_mock, popen_mock):
        inst = CoqtopInstance()
        inst.spawn(['coqtop', '-ideslave'])

        xml_str = '<value val="good"><state_id val="42" /></value>'
        xml = ET.fromstring(xml_str)
        reader_mock.return_value.get_response.side_effect = [xml]

        inst.call('init', {})
        tag, res = inst.get_response('init')

        write_mock = popen_mock.return_value.stdin.write
        write_mock.assert_called_once_with(
            b'<call val="Init"><option val="none" /></call>')
        self.assertEqual(tag, 'value')
        self.assertEqual(res, ({'init_state_id': xp.StateID(42)}, None))
