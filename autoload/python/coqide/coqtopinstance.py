#!/usr/bin/env python3
'''Coqtop process handle.'''

import logging
from queue import Queue, Empty
from subprocess import Popen, PIPE, TimeoutExpired
from threading import Thread
import xml.etree.ElementTree as ET

from . import xmlprotocol as xp


logger = logging.getLogger(__name__)         # pylint: disable=C0103


_XML_DOCTYPE = '''<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN"
                 "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd" [
                 <!ENTITY nbsp ' '>
                 <!ENTITY quot '"'>
                 ]>'''


class CoqtopQuit(Exception):
    '''The coqtop process quits.'''


class _XMLLogger:        # pylint: disable=R0903
    '''A class that converts the XML document to its string representation.'''

    def __init__(self, xml):
        self._xml = xml

    def __str__(self):
        return ET.tostring(self._xml).decode()


class _CoqtopReader:
    '''The output processor for the coqtop process.'''

    def __init__(self, pipe):
        self._pipe = pipe
        self._closed = False
        self._thread = Thread(target=self._thread_entry)
        self._res_queue = Queue()

    def start(self):
        '''Start the processor thread.'''
        self._thread.start()

    def join(self):
        '''Wait for the thread to quit.'''
        self._thread.join()

    def get_response(self):
        '''Get a response from coqtop process.

        Raise `CoqtopQuit` if the process terminates.
        '''
        res = self._res_queue.get()
        if res is None or self._closed:
            raise CoqtopQuit()
        return res

    def get_responses_nowait(self):
        '''Get all the available responses.

        The method is non-blocking.'''
        responses = []
        try:
            while True:
                response = self._res_queue.get_nowait()
                if response is None or self._closed:
                    break
                responses.append(response)
        except Empty:
            pass
        return responses

    def _thread_entry(self):
        chunks = []
        while True:
            data = self._pipe.read1(1000)
            if not data:
                self._closed = True
                self._res_queue.put(None)
                break

            chunks.append(data)
            doc = [_XML_DOCTYPE, '<root>'] + chunks + ['</root>']
            try:
                root = ET.fromstringlist(doc)
                for element in root:
                    logger.debug('Coqtop response: %s', _XMLLogger(element))
                    self._res_queue.put(element)
                chunks = []
            except ET.ParseError:
                pass


class CoqtopInstance:
    '''Manages the connection with a coqtop process.'''

    def __init__(self):
        self._proc = None
        self._reader = None

    def spawn(self, exec_args):
        '''Create the coqtop process.'''
        if self._proc is not None:
            raise RuntimeError('CoqtopInstance already spawned.')
        self._proc = Popen(exec_args, stdin=PIPE, stdout=PIPE)
        self._reader = _CoqtopReader(self._proc.stdout)
        self._reader.start()

    def call(self, rtype, req):
        '''Send the request `req` of request type `rtype` to the coqtop
        process.
        '''
        if self._proc is None:
            raise RuntimeError('CoqtopInstance not spawned.')
        req_xml = xp.req_to_xml(rtype, req)
        req_bytes = ET.tostring(req_xml)
        logger.debug('Coqtop request: %s', req_bytes)
        self._proc.stdin.write(req_bytes)
        self._proc.stdin.flush()

    def get_response(self, rtype):
        '''Get a reponse from coqtop.

        If the response is a value, return `('value', value_dict)`
        where `value_dict` is decoded from XML according to the
        request type `rtype`.

        If the response is a feedback, return `('feedback',
        fb_dict)` where `fb_dict` is decoded from XML as a
        feedback.'''

        xml = self._reader.get_response()
        if xml.tag == 'feedback':
            return ('feedback', xp.feedback_from_xml(xml))
        elif xml.tag == 'value':
            return ('value', xp.res_from_xml(rtype, xml))
        else:
            raise ValueError('Bad coqtop response: {}'.format(
                ET.tostring(xml)))

    def close(self):
        '''Terminate the coqtop process.'''
        if self._proc is None:
            return

        self._proc.stdin.close()
        try:
            self._proc.wait(timeout=5)
        except TimeoutExpired:
            self._proc.kill()
            self._proc.wait(timeout=5)

        self._reader.join()
        self._proc = None
        self._reader = None

    def get_feedbacks(self):
        '''Read all the available feedbacks.'''
        if self._proc is None:
            raise RuntimeError('CoqtopInstance not spawned.')
        return list(map(xp.feedback_from_xml, self._reader.get_responses_nowait()))
