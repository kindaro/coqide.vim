'''Coqtop handle.

In this module defined CoqtopHandle, a tool to communicate with a coqtop subprocess
and manage the running state of the subprocess.
'''
# pylint: disable=R0903

import logging
import threading
import queue
import subprocess
import xml.etree.ElementTree as ET

from . import xmlprotocol as xp


XML_DOCTYPE = '''<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN"
                 "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd" [
                     <!ENTITY nbsp ' '>
                     <!ENTITY quot '"'>
                 ]>'''


logger = logging.getLogger(__name__)         # pylint: disable=C0103


class XMLInputThread:
    '''A thread that receives data from a stream and parses them into XML.'''

    def __init__(self, stream, cb_data, cb_end):
        '''Create a thread that parses the data from `stream` into XML elements.

        `stream` is a buffered binary IO stream.
        `cb_data` is called each time a XML element is parsed.
        `cb_end` is called when the stream is closed.
        '''
        def thread_main():
            '''Repeat reading until EOF.'''
            fragments = []
            while True:
                chunk = stream.read1(1000)
                if not chunk:
                    cb_end()
                    break
                logger.debug('XMLInputThread receives: %s', chunk)
                fragments.append(chunk.decode())
                wrapped_doc = [XML_DOCTYPE, '<root>'] + fragments + ['</root>']
                try:
                    root = ET.fromstringlist(wrapped_doc)
                    for element in root:
                        cb_data(element)
                    fragments = []
                except ET.ParseError:
                    pass
            logger.debug('XMLInputThread quits normally.')

        thread = threading.Thread(target=thread_main)
        thread.start()
        logger.debug('XMLInputThread starts.')

        self._thread = thread

    def join(self):
        '''Wait for the thread to quit.'''
        self._thread.join()


class XMLOutputThread:
    '''A thread that caches XML data in a queue and sends them to a stream in the
    background.
    '''

    def __init__(self, stream, encoding):
        '''Create a thread that serializes and sends XML elements to `stream`.'''
        self._closing = False
        out_queue = queue.Queue(1000)

        def thread_main():
            '''Repeat send the XML data until closed.'''
            while True:
                xml = out_queue.get()
                if xml is None or self._closing:
                    break
                data = ET.tostring(xml, encoding)
                logger.debug('XMLOutputThread sends: %s', data)

                try:
                    stream.write(data)
                    stream.flush()
                except BrokenPipeError:
                    logger.debug('XMLOutputThread quits by broken pipe.')
                    break
            logger.debug('XMLOutputThread quits normally.')

        thread = threading.Thread(target=thread_main)
        thread.start()
        logger.debug('XMLOutputThread starts.')

        self._queue = out_queue
        self._thread = thread

    def send(self, xml):
        '''Put a XML element to the cache queue.'''
        assert xml is not None
        self._queue.put(xml)

    def shutdown_join(self):
        '''Shutdown the internal thread and join it.

        Unsent data will be discarded.'''
        self._closing = True
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass
        self._thread.join()


def coqtop_process_create():
    '''Create a Popen object of the coqtop program.'''
    command = ['coqtop',
               '-ideslave',
               '-main-channel',
               'stdfds',
               '-async-proofs',
               'on']

    proc = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE)

    return proc


class CoqtopHandle:
    '''The handle to the coqtop subprocess.'''

    def __init__(self, encoding, cb_feedback):
        '''Create a coqtop handle.

        `encoding` is the charset encoding of the channels with the coqtop
        process. `cb_feedback` is a callback that will be called with a
        Feedback object each time a feedback is received from the coqtop
        process. `cb_feedback` is executed in a background thread, so do not
        communicate with Vim in it.
        '''
        process = coqtop_process_create()
        input_thread = XMLInputThread(process.stdout, self._on_receive, self._on_lost)
        output_thread = XMLOutputThread(process.stdin, encoding)

        self._process = process
        self._input_thread = input_thread
        self._output_thread = output_thread
        self._cb_feedback = cb_feedback
        self._cb_res_queue = queue.Queue(1000)

    def terminate(self):
        '''Terminate the coqtop process.'''
        self._output_thread.shutdown_join()
        process = self._process
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate(timeout=5)
        self._input_thread.join()

    def is_running(self):
        '''Return true if the process is running.'''
        return self._process.poll() is None

    def call_async(self, req, cb_res, cb_lost):
        '''Send XML Element `req` to the coqtop server and return immediately.

        `cb_res` is called with the XML element received from coqtop in a
        background thread. Do not communicate with Vim in this callback.

        `cb_lost` is called when the connection with the subprocess is lost.
        '''
        if self._process.poll():
            raise RuntimeError('Coqtop has terminated.')

        logger.debug('CoqtopHandle sends call: %s', req)
        self._cb_res_queue.put((cb_res, cb_lost))
        self._output_thread.send(req.to_xml())

    def _on_receive(self, xml):
        '''On receiving a XML element from the coqtop process.'''
        if xml.tag == 'feedback':
            feedback = xp.Feedback.from_xml(xml)
            logger.debug('CoqtopHandle receives feedback: %s', feedback)
            self._cb_feedback(feedback)
        elif xml.tag == 'value':
            logger.debug('CoqtopHandle receives value.')
            try:
                cb_res, _ = self._cb_res_queue.get_nowait()
                cb_res(xml)
            except queue.Empty:
                raise RuntimeError('Unexpected value received from coqtop.')
        else:
            raise RuntimeError('Unexpected XML received from coqtop: ' + ET.tostring(xml))

    def _on_lost(self):
        '''On the connection being closed.'''
        try:
            while True:
                _, cb_lost = self._cb_res_queue.get_nowait()
                logger.debug('CoqtopHandle cleans up a non-answered response handler.')
                cb_lost()
        except queue.Empty:
            pass
