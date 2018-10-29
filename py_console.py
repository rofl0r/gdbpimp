import code
import sys
import threading

"""
usage:
py_console.Shell(locals=globals()).interact('ishell. hit CTRL-C to exit.')

"""



"""
# https://stackoverflow.com/questions/4031135/why-does-my-python-interactive-console-not-work-properly
# http://www.programcreek.com/python/example/709/readline.parse_and_bind
if 'DEBUG' in os.environ:
    import pdb
    import sys
    oeh = sys.excepthook
    def debug_exceptions(type, value, traceback):
        pdb.post_mortem(traceback)
        oeh(type, value, traceback)
    sys.excepthook = debug_exceptions
"""

class PseudoFile(object):
    '''A psuedo file object, to redirect I/O operations from Python Shell to
       InteractiveShellInput.
    '''

    def __init__(self, sh):
        self.sh = sh

    def write(self, s):
        '''To write to a PsuedoFile object.
        '''
        self.sh.write(s)

    def writelines(self, lines):
        '''To write lines to a PsuedoFile object.
        '''

        for line in lines:
            self.write(line)

    def flush(self):
        '''To flush a PsuedoFile object.
        '''
        pass

    def isatty(self):
        '''To determine if PsuedoFile object is a tty or not.
        '''
        return True


class Shell(code.InteractiveConsole):
    "Wrapper around Python that can filter input/output to the shell"

    def __init__(self, locals=None, histfile=None, writefunc=None):
        code.InteractiveConsole.__init__(self, locals)
        self.thread = None
        self._exit = False
	if writefunc and callable(writefunc):
		self.write = writefunc
        try:
            import readline
        except ImportError:
            pass
        else:
            try:
                import rlcompleter
                readline.set_completer(rlcompleter.Completer(locals).complete)
            except ImportError:
                pass
            readline.parse_and_bind("tab: complete")

    def runcode(self, _code):
        """Execute a code object.

        When an exception occurs, self.showtraceback() is called to
        display a traceback. All exceptions are caught except
        SystemExit, which is reraised.

        A note about KeyboardInterrupt: this exception may occur
        elsewhere in this code, and may not always be caught. The
        caller should be prepared to deal with it.

        """
        org_stdout = sys.stdout
        sys.stdout = PseudoFile(self)
        try:
            exec(_code, self.locals)
        except SystemExit:
            self._exit = True
        except:
            self.showtraceback()

        sys.stdout = org_stdout

    def exit(self):
        '''To exit PythonConsole.
        '''
        self._exit = True

    def interact(self, banner=None):
        """Closely emulate the interactive Python console.

        The optional banner argument specify the banner to print
        before the first interaction; by default it prints a banner
        similar to the one printed by the real Python interpreter,
        followed by the current class name in parentheses (so as not
        to confuse this with the real interpreter -- since it's so
        close!).

        """
        try:
            sys.ps1
        except AttributeError:
            sys.ps1 = ">>> "
        try:
            sys.ps2
        except AttributeError:
            sys.ps2 = "... "
        cprt = 'Type "help", "copyright", "credits" or "license"'\
            ' for more information.'
        if banner is None:
            self.write("Python %s on %s\n%s\n(%s)\n" %
                       (sys.version, sys.platform, cprt,
                        self.__class__.__name__))
        else:
            self.write("%s\n" % str(banner))
        more = 0
        while not self._exit:
            try:
                if more:
                    prompt = sys.ps2
                else:
                    prompt = sys.ps1
                try:
                    line = self.raw_input(prompt)
                    if line is None:
                        continue
                    # Can be None if sys.stdin was redefined
                    encoding = getattr(sys.stdin, "encoding", None)
                    if encoding and isinstance(line, bytes):
                        line = line.decode(encoding)
                except EOFError:
                    self.write("\n")
                    break
                else:
                    more = self.push(line)

            except KeyboardInterrupt:
                self.write("\nKeyboardInterrupt\n")
                self.resetbuffer()
                more = 0
                break


class InteractiveThread(threading.Thread):
    '''Another thread in which main loop of Shell will run.
    '''
    def __init__(self, sh):
        super(InteractiveThread, self).__init__()
        self._sh = sh
        self._sh.thread = self

    def run(self):
        '''To start main loop of _sh in this thread.
        '''
        self._sh.interact()


