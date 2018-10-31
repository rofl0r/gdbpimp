from __future__ import unicode_literals
from proc import Proc
import tokenizer, py_console
import time, os, pty

def extract_filename(fn):
	a = fn.split('/')
	return a[-1]

class GDB():
	def __init__(self, command, *args, **kwargs):
		self.proc = Proc("LC_ALL=C gdb --args " + command, shell=True)
		self.debugf = open('debug.log', 'w')
		self.sourcefile = ''
		self.sources = []
		self.breakpoints = {}
		self.lineno = -1
		self.cached_stdout = ''
		self.cached_stderr = ''
		time.sleep(0.0001)
		s, t = self.read()
		# disable getting the output split into single pages and interacting
		self.send('set pagination off')
		self.read()
		master, slave = pty.openpty()
		self.send('set inferior-tty ' + os.ttyname(slave))
		self.read()
		self.pty_master = master
		self.pty_slave = slave
		self.cached_stdout = s
		self.cached_stderr = t
	def add_bp(self, file, line):
		file = self.find_sourcefile(file)
		if not file in self.breakpoints: self.breakpoints[file] = []
		self.breakpoints[file].append(line)
	def _set_exit_code(self, ec):
		self.proc.exitcode = ec
	def _reload_sources(self):
		self.send('info sources')
		s = self.proc.stdout().read(1) #''
		while self.proc.canread(self.proc.stdout()):
			s += self.proc.stdout().read(1)
		lines = s.split('\n')
		self.sources = lines[2].split(', ')
	def set_sourcefile(self, file):
		self.sourcefile = file
	def find_sourcefile(self, file):
		if not extract_filename(self.sourcefile) == file:
			self._reload_sources()
			for s in self.sources:
				if extract_filename(s) == file:
					return s
			return ''
		else: return self.sourcefile

	def _consume_cached(self, which):
		if which == 'stdout':
			res = self.cached_stdout
			self.cached_stdout = ''
		else:
			res = self.cached_stderr
			self.cached_stderr = ''
		return res

	def istdout(self):
		return self.pty_master
	def istdout_canread(self):
		return self.proc.canread(self.pty_master)
	def debug(self, text):
		self.debugf.write(text + '\n')
		self.debugf.flush()
	def read(self):
		if self.get_exitcode() is not None: return '', ''
		s = self._consume_cached('stdout')
		#s += self.proc.stdout().read(1)
		while self.proc.canread(self.proc.stdout()):
			c = self.proc.stdout().read(1)
			if not c: break
			s += c

		#if '[Inferior 1 (process 19071) exited normally]
		# [Inferior 1 (process 19224) exited with code 01]
		lines = s.split('\n')
		for l in lines:
			if l.startswith('The program is not being run.'):
				self._set_exit_code(-3)
			if l.startswith('[Inferior 1 (process '):
				if l.endswith('exited normally]'): self.proc.exitcode = 0
				if ') exited with code ' in l and l.endswith(']'):
					self._set_exit_code(int(l.split(' ')[-1].rstrip(']'), 10))
		if not self.proc.exitcode and lines[-1] != '(gdb) ':
			s += self.proc.read_until(self.proc.stdout(), '(gdb) ')
		lines = s.split('\n')
		for l in lines:
			self.debug('L ' + l)
			if l.startswith('Breakpoint ') or l.startswith('Temporary breakpoint '):
				a = l.split(' ')
				le = a[-1]
				self.debug(repr(a))
				file = None
				if le.find(':') == -1:
					# dont have a file:lineno tuple at the end, it's the confirmation a breakpoint has been set
					if len(a) > 4 and a[-4] == u'file' and a[-2] == u'line':
						file = a[-3][:-1]
						lineno = a[-1][:-1]
					if not l.startswith('Temporary'):
						self.add_bp(file, int(lineno))
					file = None
				else:
					file, lineno = le.split(':')
				if file is not None:
					self.set_sourcefile(self.find_sourcefile(file))
					self.lineno = int(lineno)

		t = self._consume_cached('stderr')
		while self.proc.canread(self.proc.stderr()):
			t += self.proc.stderr().read(1)
		lines = t.split('\n')
		for l in lines:
			if len(l): self.debug('E ' + l)
			if l.startswith('During symbol reading, incomplete CFI data'):
				self._set_exit_code(-1)
			if l.startswith('Cannot find bounds of current function'):
				self._set_exit_code(-2)
		return s, t
	def get_exitcode(self):
		return self.proc.exitcode
	def send(self, command):
		if self.get_exitcode() is not None: return
		self.proc.stdin().write(command + '\n')
		time.sleep(0.0001)
	def set_source_from_ouput(self, s):
		a = s.split('\n')
		for x in a:
			if x.startswith('Located in '):
				self.sourcefile = x[len('Located in '):]
				break
		return self.sourcefile


def concat_argv():
	import sys
	s = ''
	for i in xrange(1, len(sys.argv)):
		if len(s): s += ' '
		s += sys.argv[i]
	return s

def setup_gdb(gdb):
	o = ''
	s, t = gdb.read()
	o += s
	o += t

	gdb.send('l')
	s, t = gdb.read()
	o += s
	o += t

	gdb.send('info source')
	s, t = gdb.read()
	source = gdb.set_source_from_ouput(s)

	gdb.send('tbreak main')
	s, t = gdb.read()
	o += s
	o += t
	gdb.send('r')
	s, t = gdb.read()
	o += s
	o += t
	return o


from prompt_toolkit import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.widgets import TextArea, Label
from prompt_toolkit.layout.containers import HSplit, VSplit, Window, ScrollOffsets, ConditionalContainer
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.application import get_app
from prompt_toolkit.key_binding import KeyBindings, merge_key_bindings
from prompt_toolkit.layout.dimension import LayoutDimension, Dimension
from prompt_toolkit.lexers import PygmentsLexer
from prompt_toolkit.document import Document
from prompt_toolkit.selection import SelectionState
from prompt_toolkit.filters import Condition
from pygments.lexers.c_cpp import CLexer
from pygments.token import Token
from prompt_toolkit.styles import Style, style_from_pygments_cls, merge_styles
from editor_style import CodeviewStyle

class OrderedDict():
	def __init__(self):
		self.values = {}
		self.order = None
		self._changed = None
	def update(self, values):
		if self.order is None or len(self.order) == 0:
			self.order = sorted(values.keys())
			self.values = values
			self._changed = self.order
			return
		i = 0
		while i < len(self.order):
			if not self.order[i] in values:
				self.order.pop(i)
			else: i += 1
		new = []
		changed = []
		for key in values:
			if not key in self.order: new.append(key)
			elif not self.values[key] == values[key]: changed.append(key)
		new = sorted(new)
		self.order.extend(new)
		self.values = values
		changed.extend(new)
		self._changed = changed
	def was_changed(self, key):
		return self._changed is not None and key in self._changed
	def get_value_by_index(self, index):
		if index < len(self):
			return self[self.order[index]]
		return None
	def __len__(self):
		if self.order is None: return 0
		return len(self.order)
	def __iter__(self):
		if self.order is None: return
		for x in xrange(len(self.order)):
			yield self.order[x]
	def __getitem__(self, index):
		if index in self.values:
			return self.values[index]
		return None


def sidebar(name, kvdict):
	# shamelessly stolen and adapted from ptpython/layout.py
	_KEY_WIDTH = 8
	_VAL_WIDTH = 14
	_CTR_WIDTH = _KEY_WIDTH + _VAL_WIDTH
	_CTR_WIDTH_STR = str(_CTR_WIDTH)
	def center_str(s, w):
		l = len(s)
		e = w - l
		t = ''
		i = 0
		while i < e/2:
			t += ' '
			i += 1
		t += s
		i = len(t)
		while i < w:
			t += ' '
			i += 1
		return t

	def pad_or_cut(s, w):
		if len(s) > w: s = s[:w]
		while len(s) < w: s+= ' '
		return s

	def get_text_fragments():
		tokens = []
		def append_title(title):
			foc = ',focused' if get_app().focused_control == name else ''
			tokens.extend([
				('class:sidebar', ' '),
				('class:sidebar.title'+foc, center_str(title, _CTR_WIDTH)),
				('class:sidebar', '\n'),
			])
		def append(index, label, status):
			selected = get_app().controls[name].selected_option_index == index
			odd = 'odd' if index%2 != 0 else ''
			sel = ',selected' if selected else ''
			chg = ',changed' if kvdict().was_changed(label) else ''
			tokens.append(('class:sidebar' + sel, '>' if selected else ' '))
			tokens.append(('class:sidebar.label' + odd + sel, pad_or_cut(label, _KEY_WIDTH)))
			tokens.append(('class:sidebar.status' + odd + sel + chg, pad_or_cut(status, _VAL_WIDTH)))
			if selected:
				tokens.append(('[SetCursorPosition]', ''))
			tokens.append(('class:sidebar', '<' if selected else ' '))
			tokens.append(('class:sidebar', '\n'))


		i = 0
		append_title(name)
		mydict = kvdict() if callable(kvdict) else kvdict
		for key in mydict:
			values = mydict[key]
			append(i, key, '%s' % values[0])
			i += 1
		tokens.pop()  # Remove last newline.
		return tokens

	class Control(FormattedTextControl):
		def move_cursor_down(self):
			get_app().controls[name].selected_option_index += 1
		def move_cursor_up(self):
			get_app().controls[name].selected_option_index -= 1

	ctrl =  Window(
		Control(get_text_fragments),
		style='class:sidebar',
		width=Dimension.exact(_CTR_WIDTH+2),
		height=Dimension(min=3),
		scroll_offsets=ScrollOffsets(top=1, bottom=1))
	ctrl.selected_option_index = 0
	return ctrl

def load_sidebar_bindings(name):
	#sidebar_visible = Condition(lambda: config.show_sidebar)
	sidebar_visible = Condition(lambda: True)
	sidebar_focused = Condition(lambda: get_app().focused_control == name)
	sidebar_handles_keys = sidebar_visible & sidebar_focused
	bindings = KeyBindings()
	handle = bindings.add
	@handle('up', filter=sidebar_handles_keys)
	def _(event):
		event.app.controls[name].selected_option_index = (
		(event.app.controls[name].selected_option_index - 1) % len(vars(event.app)[name]))
	@handle('down', filter=sidebar_handles_keys)
	def _(event):
		event.app.controls[name].selected_option_index = (
		(event.app.controls[name].selected_option_index + 1) % len(vars(event.app)[name]))
	if name == 'locals':
		@handle('enter', filter=sidebar_handles_keys)
		def _(event):
			if event.app.controls['vardetails'].text == '':
				event.app.controls['vardetails'].text = 'X'
				event.app.controls['vardetails'].update()
			else: event.app.controls['vardetails'].text = ''
	return bindings

def setup_app(gdb):

	def codeview_line_prefix(line_number, wrap_count):
		try:
			if False: pass
			elif line_number +1 == get_app().gdb.lineno:
				return [('class:text-area.pfx,selected', '>')]
			elif get_app().gdb.sourcefile in get_app().gdb.breakpoints and line_number+1 in get_app().gdb.breakpoints[get_app().gdb.sourcefile]:
				return [('class:text-area.pfx.bp', 'o')]
		except: pass
		return [('class:text-area.pfx', ' ')]

	controls = {}

	controls['header'] = Label(
		text = u'',
		style = u'class:header_label',
	)
	controls['codeview'] = TextArea(
		text = u'',
		read_only = True,
		scrollbar = True,
		line_numbers = True,
		wrap_lines = True,
		get_line_prefix = codeview_line_prefix,
		lexer=PygmentsLexer(CLexer),
		style = u'class:codeview',
	)
	controls['gdbout'] = TextArea(
		text = u'',
		read_only = True,
		scrollbar = True,
		wrap_lines = False,
		style = u'class:gdbout',
		height = LayoutDimension(4, 16, preferred=8),
	)
	controls['inferiorout'] = TextArea(
		text = u'',
		read_only = True,
		scrollbar = True,
		wrap_lines = False,
		style = u'class:inferiorout',
		height = LayoutDimension(1, 16, preferred=1),
	)
	controls['locals'] = sidebar('locals', lambda : get_app().locals)
	controls['input_label'] = Label(
		text = u'(gdb) ',
		style = u'class:input_label',
		width = LayoutDimension.exact(6),
	)
	controls['input'] = TextArea(
		height=LayoutDimension.exact(1),
		dont_extend_height=True,
		read_only = False,
		style = u'class:input',
	)
	controls['vardetails'] = TextArea(
		height=LayoutDimension(1, 4),
		wrap_lines = True,
		read_only = True,
		style = u'class:vardetails',
	)
	def up_():
		val = get_app().locals.get_value_by_index( \
			get_app().controls['locals'].selected_option_index)
		text = get_app().controls['vardetails'].text
		if val is None and text != '':
			get_app().controls['vardetails'].text = '<out of scope>'
		elif text != '':
			get_app().controls['vardetails'].text = val[1]
	controls['vardetails'].update = up_

	def need_vardetails():
		return get_app().controls['vardetails'].text != ''

	controls['root_container'] = HSplit([
		controls['header'],
		ConditionalContainer(controls['vardetails'], Condition(need_vardetails)),
		VSplit([
			HSplit([
				controls['codeview'],
				controls['inferiorout'],
				controls['gdbout'],
				VSplit([
					controls['input_label'],
					controls['input'],
				]),
			]),
			controls['locals'],
		]),
	])

	kb = KeyBindings()
	@kb.add(u'c-q')
	def exit_(event):
		event.app.exit()
	@kb.add(u'f1')
	def eff_one_(event):
		event.app.input_gdb = not event.app.input_gdb
		event.app.controls['input_label'].text = '(gdb) ' if event.app.input_gdb else '>>> '

	def focus(app, cname):
		app.layout.focus(app.controls[cname])
		app.focused_control = cname

	@kb.add(u'enter')
	def enter_(event):
		if event.app.focused_control != 'input':
			focus(event.app, 'input')
			return
		if event.app.input_gdb:
			cmd = event.app.controls['input'].text
			if not len(cmd): cmd = event.app.last_gdb_cmd
			else: event.app.last_gdb_cmd = cmd
			run_gdb_cmd(event.app, cmd)
			if event.app.controls['input'].text == 'q':
				event.app.exit()
		else:
			try: app.console.runsource(event.app.controls['input'].text)
			except Exception as e:
				import traceback
				add_gdbview_text(event.app, traceback.format_exc())
		event.app.controls['input'].text = u''

	@kb.add(u'tab')
	def enter_(event):
		for i in xrange(len(event.app.focus_list)):
			if event.app.focus_list[i] == event.app.focused_control:
				next_focus = i+1
				if next_focus >= len(event.app.focus_list):
					next_focus = 0
				focus(event.app, event.app.focus_list[next_focus])
				break
	@kb.add(u'c-b')
	def cb_(event):
		if event.app.focused_control == 'codeview':
			c = event.app.controls['codeview']
			line, col = c.document.translate_index_to_position(c.document.cursor_position)
			line += 1
			run_gdb_cmd(event.app, 'b %s:%d'%(event.app.gdb.sourcefile, line))
	@kb.add(u'f5')
	def eff_five_(event):
		run_gdb_cmd(event.app, 'c')
	@kb.add(u'f7')
	def _(event):
		run_gdb_cmd(event.app, 's')
	@kb.add(u'f8')
	def _(event):
		run_gdb_cmd(event.app, 'n')

	styledict = {
		'gdbout':'bg:#000000 #888888',
		'inferiorout':'bg:#330000 #888888',
		'input' : 'bg:#000000 #8888ff underline',
		'input_label' : 'bg:#000000 #8888ff underline',
		'header_label' : 'bg:#9999ff #000000 underline',
		'vardetails' : 'bg:#000000 #8888ff',
		'text-area.pfx' : 'bg:#aaaaaa #ff0000',
		'text-area.pfx.selected' : 'bg:#ff0000 #ffffff',
		'sidebar':                                'bg:#bbbbbb #000000',
		'sidebar.title':                          'bg:#668866 #ffffff',
		'sidebar.title focused':                  'bg:#000000 #ffffff bold',
		'sidebar.label':                          'bg:#bbbbbb #222222',
		'sidebar.status':                         'bg:#dddddd #000011',
		'sidebar.labelodd':                      'bg:#bbbb00 #222222',
		'sidebar.statusodd':                     'bg:#dddd00 #000011',
		'sidebar.label selected':                 'bg:#222222 #eeeeee',
		'sidebar.status selected':                'bg:#444444 #ffffff bold',
		'sidebar.status changed':                'bg:#dddddd #ff0000 bold',
	}

	pyg_style = style_from_pygments_cls(CodeviewStyle)

	style = merge_styles([
		Style.from_dict(styledict),
		pyg_style,
	])

	app = Application(
		layout = Layout(
			controls['root_container'],
			focused_element=controls['input'],
		),
		style=style,
		full_screen=True,
		key_bindings=merge_key_bindings([kb, load_sidebar_bindings('locals')]),
	)
	app.controls = controls
	app.locals = OrderedDict()
	app.gdb = gdb
	app.last_gdb_cmd = ''
	app.input_gdb = True
	app.focus_list = ['input', 'codeview', 'gdbout', 'locals']
	app.focused_control = 'input'

	app_console_writefunc = lambda x: add_gdbview_text(get_app(), x)
	app.console = py_console.Shell(locals=globals(), writefunc=app_console_writefunc)

	return app

def interact():
	import code
	code.InteractiveConsole(locals=globals()).interact()

def prepare_text(text):
	return text.replace('\t', '  ').decode('utf-8')

def isnumeric(s):
	if s == '': return False
	for c in s:
		if not c in '0123456789': return False
	return True

def debug(app, text):
	app.controls['header'].text = prepare_text(text)

def add_gdbview_text(app, text):
	app.controls['gdbout'].text += prepare_text(text)
	scroll_down(app.controls['gdbout'])

def codeview_set_line(ctrl, lineno):
	height = ctrl.window.render_info.last_visible_line() - ctrl.window.render_info.first_visible_line()
	scroll_to(ctrl, lineno + height/2)

_STEP_COMMANDS = ['n','s','c','next','step','continue']
def run_gdb_cmd(app, cmd, hide=False):
	oldsrc = app.gdb.sourcefile
	app.gdb.send(cmd)
	s, t = app.gdb.read()
	if not hide: add_gdbview_text(app, s + t)
	if cmd in _STEP_COMMANDS:
		for line in s.split('\n'):
			a = line.replace('\t', ' ').split(' ')
			if isnumeric(a[0]): app.gdb.lineno = int(a[0])
			elif ':' in a[-1]:
				file, lineno = a[-1].split(':')
				app.gdb.set_sourcefile(app.gdb.find_sourcefile(file))
				debug(app, app.gdb.sourcefile)
				if isnumeric(lineno): app.gdb.lineno = int(lineno)
	if app.gdb.istdout_canread():
		app.controls['inferiorout'].text += prepare_text(os.read(app.gdb.istdout(), 1024*4))
		scroll_down(app.controls['inferiorout'])
	if not app.gdb.sourcefile == oldsrc:
		load_source(app)
	if not cmd.startswith('b ') and app.gdb.lineno != -1:
		codeview_set_line(app.controls['codeview'], app.gdb.lineno)
	if cmd in _STEP_COMMANDS:
		get_locals(app)
		app.controls['vardetails'].update()
	return s,t

def oct_to_hex(s):
	foo = int(s[1:], 8)
	return "\\x" + chr(foo).encode('hex')

def hexify_string_literal(s):
	escaped = 0
	t = '"'
	i = 1
	while i < len(s) -1:
		if not escaped and s[i] == '\\':
			escaped = 1
		elif escaped:
			if isnumeric(s[i]):
				t += oct_to_hex(s[i-1:i+3])
				i += 2
			else: t += "\\" + s[i]
			escaped = 0
		else:
			t += s[i]
		i += 1
	return t + '"'

def get_locals(app):
	app.gdb.send('info locals')
	s = app.gdb.proc.read_until(app.gdb.proc.stdout(), '(gdb) ')
	mylocals = dict()
	for line in s.split('\n'):
		if ' = ' in line:
			k, v = line.split(' = ', 1)
			b = tokenizer.split_tokens(v)
			mv = b[-1]
			if mv[0] == "'" and len(mv) > 3: # turn gdb's gay octal literals into hex
				charval = mv[1:-1]
				if charval[0] == '\\' and isnumeric(charval[1]):
					foo = int(charval[1:], 8)
					mv = "'\\x" + chr(foo).encode('hex') + "'"
			elif mv[0] == '"':
				mv = hexify_string_literal(mv)
			elif isnumeric(mv) and int(mv) > 0xffff:
				mv = hex(int(mv))
			elif 'out of bounds>' in v:
				mv= '<OOB>'
			mylocals[k] = (mv, v)
	app.locals.update(mylocals)

def scroll_down(control):
	set_lineno(control, count_char(control.text, '\n')+1)

def scroll_to(control, n):
	set_lineno(control, n)

def load_source(app):
	app.controls['codeview'].text = prepare_text(open(app.gdb.sourcefile, 'r').read())

def set_lineno(control, lineno):
	control.buffer.cursor_position = \
		control.buffer.document.translate_row_col_to_index(lineno - 1, 0)

def count_char(text, ch):
	cnt = 0
	for x in text:
		if x == ch: cnt += 1
	return cnt

if __name__ == '__main__':
	gdb = GDB(concat_argv())
	gdb_output = setup_gdb(gdb)
	app = setup_app(gdb)
	app.controls['gdbout'].text = prepare_text(gdb_output)
	app.gdb = gdb
	scroll_down(app.controls['gdbout'])
	load_source(app)

	app.run()

	import sys
	sys.exit(gdb.get_exitcode())

