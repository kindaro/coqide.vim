'''The unit test of `coqtop.xmlprotocol` module.'''


import xml.etree.ElementTree as ET
import unittest

import coqide.xmlprotocol as xp


# pylint: disable=C0111
class TestRequestsToXml(unittest.TestCase):
    def test_init_req(self):
        xml = xp.req_to_xml('init', {})
        out = ET.tostring(xml)
        self.assertEqual(out, b'<call val="Init"><option val="none" /></call>')

    def test_add_req(self):
        xml = xp.req_to_xml('add', {
            'command': 'reflexivity.',
            'edit_id': 3,
            'state_id': xp.StateID(4),
            'verbose': True})
        out = ET.tostring(xml)
        self.assertEqual(out, b'<call val="Add">'
                         b'<pair><pair><string>reflexivity.</string>'
                         b'<int>3</int></pair><pair><state_id val="4" />'
                         b'<bool val="true" /></pair></pair></call>')

    def test_edit_at_req(self):
        xml = xp.req_to_xml('edit_at', {'state_id': xp.StateID(12)})
        out = ET.tostring(xml)
        self.assertEqual(out, b'<call val="Edit_at">'
                         b'<state_id val="12" /></call>')


    def test_goal_req(self):
        xml = xp.req_to_xml('goal', {})
        out = ET.tostring(xml)
        self.assertEqual(out, b'<call val="Goal"><unit /></call>')


class TestValuesFromXml(unittest.TestCase):
    def test_init_res(self):
        text = '<value val="good"><state_id val="42" /></value>'
        xml = ET.fromstring(text)
        res, _ = xp.res_from_xml('init', xml)
        self.assertEqual(res, {'init_state_id': xp.StateID(42)})

    def test_add_res_simple(self):
        text = ('<value val="good"><pair><state_id val="23" />'
                '<pair><union val="in_l"><unit /></union>'
                '<string>Message</string>'
                '</pair></pair></value>')
        xml = ET.fromstring(text)
        res, _ = xp.res_from_xml('add', xml)
        self.assertEqual(res, {'state_id': xp.StateID(23),
                               'closed_proof': None,
                               'message': 'Message'})

    def test_add_res_qed(self):
        text = ('<value val="good"><pair><state_id val="23" />'
                '<pair><union val="in_r"><state_id val="33" /></union>'
                '<string>Message</string>'
                '</pair></pair></value>')
        xml = ET.fromstring(text)
        res, _ = xp.res_from_xml('add', xml)
        self.assertEqual(res, {
            'state_id': xp.StateID(23),
            'closed_proof': {
                'next_state_id': xp.StateID(33)
            },
            'message': 'Message'
        })

    def test_edit_at_res_simple(self):
        text = ('<value val="good"><union val="in_l"><unit /></union></value>')
        xml = ET.fromstring(text)
        res, _ = xp.res_from_xml('edit_at', xml)
        self.assertEqual(res, {'focused_proof': None})

    def test_edit_at_res_focused(self):
        text = ('<value val="good"><union val="in_r">'
                '<pair><state_id val="42" />'
                '<pair><state_id val="50" /><state_id val="60" /></pair>'
                '</pair></union></value>')
        xml = ET.fromstring(text)
        res, _ = xp.res_from_xml('edit_at', xml)
        self.assertEqual(res, {'focused_proof': {
            'proof_state_id': xp.StateID(42),
            'qed_state_id': xp.StateID(50),
            'old_focused': xp.StateID(60),
        }})

    def test_goal_res_none(self):
        text = ('<value val="good"><option val="none" /></value>')
        xml = ET.fromstring(text)
        res, _ = xp.res_from_xml('goal', xml)
        self.assertEqual(res, {'goals': None})

    def test_goal_res_some(self):
        text = ('<value val="good"><option val="some">'
                '<goals><list><goal><string>A</string>'
                '<list><string>hyp1</string><string>hyp2</string></list>'
                '<string>goal1</string>'
                '</goal></list>'
                '<list><pair><list></list><list></list></pair></list>'
                '<list></list>'
                '<list></list>'
                '</goals>'
                '</option></value>')
        xml = ET.fromstring(text)
        res, _ = xp.res_from_xml('goal', xml)
        self.assertEqual(res, {
            'goals': xp.Some(
                xp.Goals(fg=[xp.Goal(id='A',
                                     hyps=['hyp1', 'hyp2'],
                                     goal='goal1')],
                         bg=[([], [])], shelved=[], abandoned=[]))})


class TestFeedbacksFromXml(unittest.TestCase):
    def test_fb_addedaxiom(self):
        text = '''
<feedback object="state" route="0">
  <state_id val="42"/>
  <feedback_content val="addedaxiom" />
</feedback>
'''
        xml = ET.fromstring(text)
        res = xp.feedback_from_xml(xml)
        self.assertEqual(res, {'type': 'addedaxiom',
                               'state_id': xp.StateID(42),
                               'content': {}})

    def test_fb_errormsg(self):
        text = '''
<feedback object="state" route="0">
  <state_id val="42"/>
  <feedback_content val="errormsg">
    <loc start="3" stop="5"/>
    <string>Error</string>
  </feedback_content>
</feedback>
'''
        xml = ET.fromstring(text)
        res = xp.feedback_from_xml(xml)
        self.assertEqual(res, {'type': 'errormsg',
                               'state_id': xp.StateID(42),
                               'content': {
                                   'loc': xp.Location(3, 5),
                                   'message': xp.Message('error', 'Error')
                               }})

    def test_fb_filedep_wo_source(self):
        text = '''
<feedback object="state" route="0">
  <state_id val="42"/>
  <feedback_content val="filedependency">
    <option val="none"/>
    <string>a.v</string>
  </feedback_content>
</feedback>
'''
        xml = ET.fromstring(text)
        res = xp.feedback_from_xml(xml)
        self.assertEqual(res, {'type': 'filedependency',
                               'state_id': xp.StateID(42),
                               'content': {
                                   'dependency': 'a.v',
                                   'source': None,
                               }})

    def test_fb_filedep_w_source(self):
        text = '''
<feedback object="state" route="0">
  <state_id val="42"/>
  <feedback_content val="filedependency">
    <option val="some"><string>s.v</string></option>
    <string>a.v</string>
  </feedback_content>
</feedback>
'''
        xml = ET.fromstring(text)
        res = xp.feedback_from_xml(xml)
        self.assertEqual(res, {'type': 'filedependency',
                               'state_id': xp.StateID(42),
                               'content': {
                                   'dependency': 'a.v',
                                   'source': xp.Some('s.v'),
                               }})

    def test_fb_fileloaded(self):
        text = '''
<feedback object="state" route="0">
  <state_id val="42"/>
  <feedback_content val="fileloaded">
    <string>Module</string>
    <string>Module.v</string>
  </feedback_content>
</feedback>
'''
        xml = ET.fromstring(text)
        res = xp.feedback_from_xml(xml)
        self.assertEqual(res, {'type': 'fileloaded',
                               'state_id': xp.StateID(42),
                               'content': {
                                   'module': 'Module',
                                   'vo_file_name': 'Module.v',
                               }})

    def test_fb_incomplete(self):
        text = '''
<feedback object="state" route="0">
  <state_id val="42"/>
  <feedback_content val="incomplete" />
</feedback>
'''
        xml = ET.fromstring(text)
        res = xp.feedback_from_xml(xml)
        self.assertEqual(res, {'type': 'incomplete',
                               'state_id': xp.StateID(42),
                               'content': {}})

    def test_fb_inprogress(self):
        text = '''
<feedback object="state" route="0">
  <state_id val="42"/>
  <feedback_content val="inprogress">
    <int>1</int>
  </feedback_content>
</feedback>
'''
        xml = ET.fromstring(text)
        res = xp.feedback_from_xml(xml)
        self.assertEqual(res, {'type': 'inprogress',
                               'state_id': xp.StateID(42),
                               'content': {}})

    def test_fb_message(self):
        text = '''
<feedback object="state" route="0">
  <state_id val="42"/>
  <feedback_content val="message">
    <message>
      <message_level val="info"/>
      <option val="some"><loc start="3" stop="5"/></option>
      <richpp>Message</richpp>
    </message>
  </feedback_content>
</feedback>
'''
        xml = ET.fromstring(text)
        res = xp.feedback_from_xml(xml)
        self.assertEqual(res, {'type': 'message',
                               'state_id': xp.StateID(42),
                               'content': {
                                   'loc': xp.Some(xp.Location(3, 5)),
                                   'message': xp.Message('info', 'Message')
                               }})

    def test_fb_message_noloc(self):
        text = '''
<feedback object="state" route="0">
  <state_id val="42"/>
  <feedback_content val="message">
    <message>
      <message_level val="info"/>
      <richpp>Message</richpp>
    </message>
  </feedback_content>
</feedback>
'''
        xml = ET.fromstring(text)
        res = xp.feedback_from_xml(xml)
        self.assertEqual(res, {'type': 'message',
                               'state_id': xp.StateID(42),
                               'content': {
                                   'loc': None,
                                   'message': xp.Message('info', 'Message'),
                               }})

    def test_fb_processed(self):
        text = '''
<feedback object="state" route="0">
  <state_id val="42"/>
  <feedback_content val="processed"/>
</feedback>
'''
        xml = ET.fromstring(text)
        res = xp.feedback_from_xml(xml)
        self.assertEqual(res, {'type': 'processed',
                               'state_id': xp.StateID(42),
                               'content': {}})

    def test_fb_processingin(self):
        text = '''
<feedback object="state" route="0">
  <state_id val="42"/>
  <feedback_content val="processingin">
    <string>master</string>
  </feedback_content>
</feedback>
'''
        xml = ET.fromstring(text)
        res = xp.feedback_from_xml(xml)
        self.assertEqual(res, {'type': 'processingin',
                               'state_id': xp.StateID(42),
                               'content': {'worker': 'master'}})
