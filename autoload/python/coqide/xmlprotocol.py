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
# pylint: disable=R0201,R0903

from collections import namedtuple
import xml.etree.ElementTree as ET

## ==================
## Basic types
##

#   Coq data types  Python data types
#        unit        None
#        bool        bool
#        string      str
#        int         int
#        StateID     StateID
#        list        list
#        option
#          | some    1-element tuple (a,)
#          | none    empty tuple ()
#        pair        2-element tuple (a, b)
#        union       UnionL or UnionR
#        goals       Goals
#        goal        Goal
#        loc         Location

StateID = namedtuple('StateID', 'value')
UnionL = namedtuple('Union', ' value')
UnionR = namedtuple('Union', ' value')
Goals = namedtuple('Goals', 'foreground background shelved abandoned')
Goal = namedtuple('Goal', 'id hypotheses goal')
Location = namedtuple('Location', 'start stop')


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
    [lambda v: v is None, lambda _: _xml('unit')],
    [bool, lambda v: _xml('bool', val=str(v).lower())],
    [str, lambda v: _xml('string', text=v)],
    [int, lambda v: _xml('int', text=str(v))],
    [StateID, lambda v: _xml('state_id', val=str(v.value))],
    [list, lambda v: _xml('list', child=[_data_to_xml(i) for i in v])],
    [lambda v: isinstance(v, tuple) and not v,
     lambda v: _xml('option', val='none')],
    [lambda v: isinstance(v, tuple) and len(v) == 1,
     lambda v: _xml('option', val='some', child=[_data_to_xml(v[0])])],
    [lambda v: isinstance(v, tuple) and len(v) == 2,
     lambda v: _xml('pair', child=[_data_to_xml(i) for i in v])],
    [UnionL, lambda v: _xml('union', val='in_l', child=[_data_to_xml(v.value)])],
    [UnionR, lambda v: _xml('union', val='in_r', child=[_data_to_xml(v.value)])],
]
'''The list of converters that serialize Python objects to XML elements.

Each element in the list is a pair [match, convert]. `match` can be a unary function
or a type. If it is a type `T`, it is regarded as `lambda v: isinstance(v, T)`.

For a Python object `v`, if `match(v) == True`, `v` is converted to `convert(v)`.
The converters are tried in the order that they appear in the list.

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
    ['unit', lambda _: None],
    [lambda v: v.tag == 'bool' and v.attrib['val'] == 'true', lambda _: True],
    [lambda v: v.tag == 'bool' and v.attrib['val'] == 'false', lambda _: False],
    ['string', lambda v: v.text or ''],
    ['int', lambda v: int(v.text)],
    ['state_id', lambda v: StateID(int(v.attrib['val']))],
    ['list', lambda v: [_data_from_xml(i) for i in v]],
    [lambda v: v.tag == 'option' and v.attrib['val'] == 'some',
     lambda v: (_data_from_xml(v[0]),)],
    [lambda v: v.tag == 'option' and v.attrib['val'] == 'none', lambda _: ()],
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

Each element in the list is a pair [match, convert]. `match` can be a unary function
or a str. If it is a str `s`, it is regarded as `lambda v: v.tag == s`.

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

class ErrorValue(namedtuple('Failure', 'location state_id message')):
    '''The error response for calls from the coqtop process.'''
    __slots__ = ()

    @classmethod
    def from_xml(cls, xml):
        '''Deserialize an ErrorValue from XML.'''
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
        return cls(loc, state_id, message)


class AddReq(namedtuple('AddReq', 'command edit_id state_id verbose')):
    '''The request of Add call.'''
    __slots__ = ()

    def to_xml(self):
        '''Serialize the Add request to XML.'''
        content = ((self.command, self.edit_id), (self.state_id, self.verbose))
        xml = ET.Element('call', val='Add')
        xml.append(_data_to_xml(content))
        return xml


class AddRes(namedtuple('AddRes', 'error new_state_id message next_state_id')):
    '''The response of Add call.'''
    __slots__ = ()

    @classmethod
    def from_xml(cls, xml):
        '''Deserialize the Add response from XML.'''
        assert xml.tag == 'value'
        if xml.attrib['val'] == 'good':
            content = _data_from_xml(xml[0])
            return cls(None, content[0], content[1][1], content[1][0].value)
        return cls(ErrorValue.from_xml(xml), None, None, None)


class InitReq(namedtuple('InitReq', '')):
    '''The request of Init call.'''
    __slots__ = ()

    def to_xml(self):
        '''Serialize the Init request to XML.'''
        xml = ET.Element('call', val='Init')
        xml.append(_data_to_xml(()))
        return xml


class InitRes(namedtuple('InitRes', 'error init_state_id')):
    '''The response of Init call.'''
    __slots__ = ()

    @classmethod
    def from_xml(cls, xml):
        '''Deserialize the Init response from XML.'''
        assert xml.tag == 'value'
        if xml.attrib['val'] == 'good':
            content = _data_from_xml(xml[0])
            return cls(None, content)
        return cls(ErrorValue.from_xml(xml), None)


class EditAtReq(namedtuple('EditAtReq', 'state_id')):
    '''The request of Edit_at call.'''
    __slots__ = ()

    def to_xml(self):
        '''Serialize to XML.'''
        xml = ET.Element('call', val='Edit_at')
        xml.append(_data_to_xml(self.state_id))
        return xml


class EditAtRes(namedtuple('EditAtRes', 'error focused qed old')):
    '''The response of Edit_at call.'''
    __slots__ = ()

    @classmethod
    def from_xml(cls, xml):
        '''Deserialize from XML.'''
        assert xml.tag == 'value'
        if xml.attrib['val'] == 'good':
            content = _data_from_xml(xml[0])
            if isinstance(content, UnionL):
                focused = None
                qed = None
                old = None
            elif isinstance(content, UnionR):
                focused = content.value[0]
                qed = content.value[1][0]
                old = content.value[1][1]
            return cls(None, focused, qed, old)
        return cls(ErrorValue.from_xml(xml), None, None, None)


class GoalReq(namedtuple('GoalReq', '')):
    '''The request of Goal call.'''
    __slots__ = ()

    def to_xml(self):
        '''Serialize to XML.'''
        xml = ET.Element('call', val='Goal')
        xml.append(_data_to_xml(None))
        return xml


class GoalRes(namedtuple('GoalRes', 'error goals')):
    '''The response of Goal call.'''
    __slots__ = ()

    @classmethod
    def from_xml(cls, xml):
        '''Deserialize from XML.'''
        assert xml.tag == 'value'
        if xml.attrib['val'] == 'good':
            content = _data_from_xml(xml[0])
            if content:
                return cls(None, content[0])
            return cls(None, None)
        return cls(ErrorValue.from_xml(xml), None)


## ================
## Feedbacks
##

class AddedAxiom(namedtuple('AddedAxiom', '')):
    '''The AddedAxiom feedback.'''
    __slots__ = ()

    @classmethod
    def from_xml(cls, _):
        '''Deserialize from XML.'''
        return cls()


class ErrorMsg(namedtuple('ErrorMsg', 'location message')):
    '''The ErrorMsg feedback.'''
    __slots__ = ()

    @classmethod
    def from_xml(cls, xml):
        '''Deserialize from XML.'''
        loc = _data_from_xml(xml[0])
        message = _data_from_xml(xml[1])
        return cls(loc, message)


class FileDependency(namedtuple('FileDependency', 'dependency source')):
    '''The FileDependency feedback.'''
    __slots__ = ()

    @classmethod
    def from_xml(cls, xml):
        '''Deserialize from XML.'''
        source_opt = _data_from_xml(xml[0])
        if source_opt:
            source = source_opt[0]
        else:
            source = None
        dependency = _data_from_xml(xml[1])
        return cls(dependency, source)


class FileLoaded(namedtuple('FileLoaded', 'module vo_file_name')):
    '''The FileLoaded feedback.'''
    __slots__ = ()

    @classmethod
    def from_xml(cls, xml):
        '''Deserialize from XML.'''
        module = _data_from_xml(xml[0])
        vo_file_name = _data_from_xml(xml[1])
        return cls(module, vo_file_name)


class Incomplete(namedtuple('Incomplete', '')):
    '''The Incomplete feedback.'''
    __slots__ = ()

    @classmethod
    def from_xml(cls, _):
        '''Deserialize from XML.'''
        return cls()


class InProgress(namedtuple('InProgress', '')):
    '''The InProgress feedback.'''
    __slots__ = ()

    @classmethod
    def from_xml(cls, _):
        '''Deserialize from XML.'''
        return cls()


class Message(namedtuple('Message', 'level location message')):
    '''The Message feedback.'''
    __slots__ = ()

    @classmethod
    def from_xml(cls, xml):
        '''Deserialize from XML.'''
        level = xml[0][0].attrib['val']
        if len(xml[0]) == 2:
            loc = None
            message = _data_from_xml(xml[0][1])
        else:
            optloc = _data_from_xml(xml[0][1])
            if optloc:
                loc = optloc[0]
            else:
                loc = None
            message = _data_from_xml(xml[0][2])
        return cls(level, loc, message)


class Processed(namedtuple('Processed', '')):
    '''The Processed feedback.'''
    __slots__ = ()

    @classmethod
    def from_xml(cls, _):
        '''Deserialize from XML.'''
        return cls()


class ProcessingIn(namedtuple('ProcessingIn', 'worker')):
    '''The ProcessingIn feedback.'''
    __slots__ = ()

    @classmethod
    def from_xml(cls, xml):
        '''Deserialize from XML.'''
        worker = _data_from_xml(xml[0])
        return cls(worker)


class AnyContent(namedtuple('AnyContent', 'text')):
    '''Any feedbacks other than those mentioned above.'''
    __slots__ = ()

    @classmethod
    def from_xml(cls, xml):
        '''Deserialize from XML.'''
        return cls(ET.tostring(xml))


class Feedback(namedtuple('Feedback', 'state_id content')):
    '''A feedback from the coqtop process.'''
    __slots__ = ()

    _content_builders = {
        'addedaxiom': AddedAxiom,
        'errormsg': ErrorMsg,
        'filedependency': FileDependency,
        'fileloaded': FileLoaded,
        'incomplete': Incomplete,
        'inprogress': InProgress,
        'message': Message,
        'processed': Processed,
        'processingin': ProcessingIn,
    }

    @classmethod
    def from_xml(cls, xml):
        '''Deserialize from XML.

        Supported feedbacks are listed in the class constant `_content_builders`.
        Other feedback contents are deserialized into `AnyContent`.
        '''
        assert xml.tag == 'feedback'
        if xml.attrib['object'] != 'state':
            raise TypeError('Unsupported feedback')
        state_id = _data_from_xml(xml[0])
        content_type = xml[1].attrib['val']
        if content_type in cls._content_builders:
            builder = cls._content_builders[content_type]
            content = builder.from_xml(xml[1])
        else:
            content = AnyContent.from_xml(xml[1])
        return cls(state_id, content)
