'''Coq XML Protocols.

The protocols includes:

- the definitions of Coq data structures that have no counterpart in Python;
- the translation functions mapping between Coq and Python types;
- the definitions of Coq calls/values and feedbacks.

Basic data types and their XML representations:

unit:

<unit/>

bool:

<bool val="true"/>
<bool val="false"/>

string:

<string>hello</string>

int:

<int>256</int>

Stateid.t:

<state_id val="1"/>

(int list):

<list>
  <int>3</int>
  <int>4</int>
  <int>5</int>
</list>

(int option):

<option val="some">
  <int>3</int>
</option>
<option val="none"/>

(bool * int):

<pair>
  <bool val="false"/>
  <int>3</int>
</pair>

((bool, int) CSig.union):

<union val="in_l">
  <bool val="false"/>
</union>

All other types are records represented by a node named like the OCaml
type which contains a flattened n-tuple.

All other types are records represented by a node named like the OCaml
type which contains a flattened n-tuple.
'''

import xml.etree.ElementTree as ET

from .types import Unit, StateID, Some, UnionL, UnionR, Goals, Goal, \
    Location, Message

## ==================
## Basic types
##

#   Coq data types  Python data types
#        unit        Unit
#        bool        bool
#        string      str
#        int         int
#        StateID     StateID
#        list        list
#        option
#          | some    Some
#          | none    None
#        pair        2-element tuple (a, b)
#        union       UnionL or UnionR
#        goals       Goals
#        goal        Goal
#        loc         Location


def _xml(tag, **keys):
    '''Make a XML element.

    There are two special keys:
    - child: a list of children elements;
    - text: the text of the element

    Other keys are passed to `ET.Element` as attributes.
    '''
    if 'child' in keys:
        children = keys['child']
        del keys['child']
    else:
        children = []

    if 'text' in keys:
        text = keys['text']
        del keys['text']
    else:
        text = None

    xml = ET.Element(tag, **keys)
    for child in children:
        xml.append(child)
    if text:
        xml.text = text
    return xml


_CONVERTERS_TO_XML = [
    [Unit, lambda _: _xml('unit')],
    [bool, lambda v: _xml('bool', val=str(v).lower())],
    [str, lambda v: _xml('string', text=v)],
    [int, lambda v: _xml('int', text=str(v))],
    [StateID, lambda v: _xml('state_id', val=str(v.val))],
    [list, lambda v: _xml('list', child=[_data_to_xml(i) for i in v])],
    [lambda v: v is None, lambda v: _xml('option', val='none')],
    [Some, lambda v: _xml('option', val='some', child=[_data_to_xml(v.val)])],
    [lambda v: isinstance(v, tuple) and len(v) == 2,
     lambda v: _xml('pair', child=[_data_to_xml(i) for i in v])],
    [UnionL, lambda v: _xml('union', val='in_l', child=[_data_to_xml(v.val)])],
    [UnionR, lambda v: _xml('union', val='in_r', child=[_data_to_xml(v.val)])],
]
'''The list of converters that serialize Python objects to XML elements.

Each element in the list is a pair [match, convert]. `match` can be a unary
function or a type. If it is a type `T`, it is regarded as `lambda v:
isinstance(v, T)`.

For a Python object `v`, if `match(v) == True`, `v` is converted to
`convert(v)`.  The converters are tried in the order that they appear in the
list.
'''


def _data_to_xml(data):
    '''Serialize a Python object into a XML element by the rules defined in
    `_CONVERTERS_TO_XML`.'''
    for match, convert in _CONVERTERS_TO_XML:
        if isinstance(match, type):
            if isinstance(data, match):
                return convert(data)
        else:
            if match(data):
                return convert(data)
    raise TypeError('Cannot serialize [{}] to XML'.format(data))


_CONVERTERS_FROM_XML = [
    ['unit', lambda _: Unit()],
    [lambda v: v.tag == 'bool' and v.attrib['val'] == 'true', lambda _: True],
    [lambda v: v.tag == 'bool' and v.attrib['val'] == 'false', lambda _: False],
    ['string', lambda v: v.text or ''],
    ['int', lambda v: int(v.text)],
    ['state_id', lambda v: StateID(int(v.attrib['val']))],
    ['list', lambda v: [_data_from_xml(i) for i in v]],
    [lambda v: v.tag == 'option' and v.attrib['val'] == 'some',
     lambda v: Some(_data_from_xml(v[0]))],
    [lambda v: v.tag == 'option' and v.attrib['val'] == 'none', lambda _: None],
    ['pair', lambda v: tuple(_data_from_xml(i) for i in v)],
    [lambda v: v.tag == 'union' and v.attrib['val'] == 'in_l',
     lambda v: UnionL(_data_from_xml(v[0]))],
    [lambda v: v.tag == 'union' and v.attrib['val'] == 'in_r',
     lambda v: UnionR(_data_from_xml(v[0]))],
    # Discard all the decorations of richpp.
    ['richpp', lambda v: ''.join(v.itertext())],
    ['goals', lambda v: Goals(*map(_data_from_xml, v))],
    ['goal', lambda v: Goal(*map(_data_from_xml, v))],
    ['loc', lambda v: Location(int(v.attrib['start']), int(v.attrib['stop']))],
]
'''The list of converters that deserialize Python objects from XML elements.

Each element in the list is a pair [match, convert]. `match` can be a unary
function or a str. If it is a str `s`, it is regarded as `lambda v: v.tag ==
s`.

For a XML element `v`, if `match(v) == True`, `v` is converted to `convert(v)`.
The converters are tried in the order that they appear in the list.
'''


def _data_from_xml(xml):
    '''Deserialize the XML Element object by the rules defined in
    `_CONVERTERS_FROM_XML`.'''
    for match, convert in _CONVERTERS_FROM_XML:
        if isinstance(match, str):
            if xml.tag == match:
                return convert(xml)
        else:
            if match(xml):
                return convert(xml)
    raise TypeError('Cannot deserialize [{}] from XML'.format(ET.tostring(xml)))


## ============================
## Requests and Responses
##

def _error_value_from_xml(xml):
    '''Convert an error value from xml.'''
    assert xml.tag == 'value'
    assert xml.attrib['val'] == 'fail'
    if 'loc_s' in xml.attrib:
        start = int(xml.attrib['loc_s'])
        end = int(xml.attrib['loc_e'])
        loc = Location(start, end)
    else:
        loc = None
    state_id = _data_from_xml(xml[0])
    message = _data_from_xml(xml[1])
    return {'loc': loc, 'state_id': state_id, 'message': message}


def _add_req_to_xml(req):
    content = ((req['command'], req['edit_id']),
               (req['state_id'], req['verbose']))
    xml = ET.Element('call', val='Add')
    xml.append(_data_to_xml(content))
    return xml


def _add_res_from_xml(xml):
    assert xml.tag == 'value'
    if xml.attrib['val'] == 'fail':
        return None, _error_value_from_xml(xml)
    content = _data_from_xml(xml[0])
    res = {'state_id': content[0],
           'message': content[1][1]}
    if isinstance(content[1][0], UnionL):
        res['closed_proof'] = None
    else:
        res['closed_proof'] = {'next_state_id': content[1][0].val}
    return res, None


def _init_req_to_xml(_):
    xml = ET.Element('call', val='Init')
    xml.append(_data_to_xml(None))
    return xml


def _init_res_from_xml(xml):
    assert xml.tag == 'value'
    if xml.attrib['val'] == 'fail':
        return None, _error_value_from_xml(xml)
    content = _data_from_xml(xml[0])
    return {'init_state_id': content}, None


def _edit_at_req_to_xml(req):
    xml = ET.Element('call', val='Edit_at')
    xml.append(_data_to_xml(req['state_id']))
    return xml


def _edit_at_res_from_xml(xml):
    assert xml.tag == 'value'
    if xml.attrib['val'] == 'fail':
        return None, _error_value_from_xml(xml)
    res = {}
    content = _data_from_xml(xml[0])
    if isinstance(content, UnionL):
        res['focused_proof'] = None
    else:
        res['focused_proof'] = {
            'proof_state_id': content.val[0],
            'qed_state_id': content.val[1][0],
            'old_focused': content.val[1][1]
        }
    return res, None


def _goal_req_to_xml(_):
    xml = ET.Element('call', val='Goal')
    xml.append(_data_to_xml(Unit()))
    return xml


def _goal_res_from_xml(xml):
    assert xml.tag == 'value'
    if xml.attrib['val'] == 'fail':
        return None, _error_value_from_xml(xml)
    content = _data_from_xml(xml[0])
    if isinstance(content, Some):
        goals = content.val
    else:
        goals = Goals([], [], [], [])
    return {'goals': goals}, None


_REQ_CONVERTERS = {
    'init': _init_req_to_xml,
    'add': _add_req_to_xml,
    'edit_at': _edit_at_req_to_xml,
    'goal': _goal_req_to_xml,
}
'''The dictionary of functions to convert a request to XML. The key is the type
of the request, and the value is the converter function.
'''

def req_to_xml(rtype, req):
    '''Convert the request `req` of request type `rtype` to XML.'''
    return _REQ_CONVERTERS[rtype](req)


_RES_CONVERTERS = {
    'init': _init_res_from_xml,
    'add': _add_res_from_xml,
    'edit_at': _edit_at_res_from_xml,
    'goal': _goal_res_from_xml,
}
'''The dictionary of functions to convert XML to a response. The key is the type
of the request, and the value is the converter function.'''


def res_from_xml(rtype, xml):
    '''Convert the response `xml` of request type `rtype` to `(res, error)`.'''
    return _RES_CONVERTERS[rtype](xml)


## ================
## Feedbacks
##

def _fb_error_msg_from_xml(xml):
    loc = _data_from_xml(xml[0])
    msg = _data_from_xml(xml[1])
    return {'loc': loc, 'message': Message('error', msg)}


def _fb_file_dependency_from_xml(xml):
    source = _data_from_xml(xml[0])
    dependency = _data_from_xml(xml[1])
    return {'dependency': dependency, 'source': source}


def _fb_file_loaded_from_xml(xml):
    module = _data_from_xml(xml[0])
    vo_file_name = _data_from_xml(xml[1])
    return {'module': module, 'vo_file_name': vo_file_name}


def _fb_message_from_xml(xml):
    level = xml[0][0].attrib['val']
    if len(xml[0]) == 2:
        loc = None
        text = _data_from_xml(xml[0][1])
    else:
        locopt = _data_from_xml(xml[0][1])
        text = _data_from_xml(xml[0][2])

        if locopt is not None:
            loc = locopt.val
        else:
            loc = None
    return {'loc': loc, 'message': Message(level, text)}


def _fb_processing_in_from_xml(xml):
    worker = _data_from_xml(xml[0])
    return {'worker': worker}


def _unhandled_fb_from_xml(xml):
    return {'raw': ET.tostring(xml)}


_FEEDBACK_CONVERTERS = {
    'addedaxiom': lambda _: {},
    'errormsg': _fb_error_msg_from_xml,
    'filedependency': _fb_file_dependency_from_xml,
    'fileloaded': _fb_file_loaded_from_xml,
    'incomplete': lambda _: {},
    'inprogress': lambda _: {},
    'message': _fb_message_from_xml,
    'processed': lambda _: {},
    'processingin': _fb_processing_in_from_xml,
}


def feedback_from_xml(xml):
    '''Convert the feedback `xml` to a dict.'''
    assert xml.tag == 'feedback'
    if xml.attrib['object'] != 'state':
        raise TypeError('Unsupported feedback')
    state_id = _data_from_xml(xml[0])
    content_type = xml[1].attrib['val']
    feedback = {'type': content_type, 'state_id': state_id}
    if content_type in _FEEDBACK_CONVERTERS:
        feedback['content'] = _FEEDBACK_CONVERTERS[content_type](xml[1])
    else:
        feedback['content'] = _unhandled_fb_from_xml(xml[1])
    return feedback
