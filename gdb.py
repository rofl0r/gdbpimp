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
from prompt_toolkit.widgets import TextArea, Label, MenuContainer, MenuItem
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
from prompt_toolkit.history import InMemoryHistory
from pygments.lexers.c_cpp import CLexer
from pygments.token import Token
from prompt_toolkit.styles import Style, style_from_pygments_cls, merge_styles
from editor_style import CodeviewStyle
import six

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

from prompt_toolkit.mouse_events import MouseEventType
def if_mousedown(handler):
	def handle_if_mouse_down(mouse_event):
		if mouse_event.event_type == MouseEventType.MOUSE_DOWN:
			return handler(mouse_event)
		else:
			return NotImplemented
	return handle_if_mouse_down


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
			@if_mousedown
			def focus_from_title(mouse_event):
				get_app().my.set_focus(name)
			foc = ',focused' if get_app().my.focused_control == name else ''
			tokens.extend([
				('class:sidebar', ' ', focus_from_title),
				('class:sidebar.title'+foc, center_str(title, _CTR_WIDTH), focus_from_title),
				('class:sidebar', '\n'),
			])
		def append(index, label, status):
			selected = get_app().my.controls[name].selected_option_index == index

			@if_mousedown
			def select_item(mouse_event):
				get_app().my.set_focus(name)
				get_app().my.controls[name].selected_option_index = index

			@if_mousedown
			def trigger_vardetail(mouse_event):
				get_app().my.set_focus(name)
				get_app().my.controls[name].selected_option_index = index
				vardetails_toggle_on_off()

			odd = 'odd' if index%2 != 0 else ''
			sel = ',selected' if selected else ''
			chg = ',changed' if kvdict().was_changed(label) else ''
			tokens.append(('class:sidebar' + sel, '>' if selected else ' '))
			tokens.append(('class:sidebar.label' + odd + sel, pad_or_cut(label, _KEY_WIDTH), select_item))
			tokens.append(('class:sidebar.status' + odd + sel + chg, pad_or_cut(status, _VAL_WIDTH), trigger_vardetail))
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
			get_app().my.controls[name].selected_option_index += 1
		def move_cursor_up(self):
			get_app().my.controls[name].selected_option_index -= 1
		def focus_on_click(self):
			return True

	ctrl =  Window(
		Control(get_text_fragments),
		style='class:sidebar',
		width=Dimension.exact(_CTR_WIDTH+2),
		height=Dimension(min=3),
		scroll_offsets=ScrollOffsets(top=1, bottom=1))
	ctrl.selected_option_index = 0
	return ctrl

def vardetails_toggle_on_off():
	app = get_app()
	if app.my.controls['vardetails'].text == '':
		app.my.controls['vardetails'].text = 'X'
		app.my.controls['vardetails'].update()
	else: app.my.controls['vardetails'].text = ''

def load_sidebar_bindings(name):
	#sidebar_visible = Condition(lambda: config.show_sidebar)
	sidebar_visible = Condition(lambda: True)
	sidebar_focused = Condition(lambda: get_app().my.focused_control == name)
	sidebar_handles_keys = sidebar_visible & sidebar_focused
	bindings = KeyBindings()
	handle = bindings.add
	@handle('up', filter=sidebar_handles_keys)
	def _(event):
		event.app.my.controls[name].selected_option_index = (
		(event.app.my.controls[name].selected_option_index - 1) % len(vars(event.app.my)[name]))
		# the vars thing is so we can point to app.my.locals OrderedDict
		# but when we repurpose the sidebar, to something else
	@handle('down', filter=sidebar_handles_keys)
	def _(event):
		event.app.my.controls[name].selected_option_index = (
		(event.app.my.controls[name].selected_option_index + 1) % len(vars(event.app.my)[name]))
	if name == 'locals':
		@handle('enter', filter=sidebar_handles_keys)
		def _(event):
			vardetails_toggle_on_off()
	return bindings

def load_inputbar_bindings():
	inputbar_focused = Condition(lambda: get_app().my.focused_control == 'input')
	bindings = KeyBindings()
	handle = bindings.add
	@handle('up', filter=inputbar_focused)
	def _(event):
		event.app.my.controls['input'].content.buffer.auto_up()
	@handle('down', filter=inputbar_focused)
	def _(event):
		event.app.my.controls['input'].content.buffer.auto_down()
	return bindings

def setup_app(gdb):

	def codeview_line_prefix(line_number, wrap_count):
		try:
			if False: pass
			elif line_number +1 == get_app().my.gdb.lineno:
				return [('class:text-area.pfx,selected', '>')]
			elif get_app().my.gdb.sourcefile in get_app().my.gdb.breakpoints and line_number+1 in get_app().my.gdb.breakpoints[get_app().my.gdb.sourcefile]:
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
		focusable = True,
		focus_on_click=True,
	)
	controls['gdbout'] = TextArea(
		text = u'',
		read_only = True,
		scrollbar = True,
		wrap_lines = False,
		style = u'class:gdbout',
		height = LayoutDimension(4, 16, preferred=8),
		focusable = True,
		focus_on_click=True,
	)
	controls['inferiorout'] = TextArea(
		text = u'',
		read_only = True,
		scrollbar = True,
		wrap_lines = False,
		style = u'class:inferiorout',
		height = LayoutDimension(1, 16, preferred=1),
		focusable = True,
		focus_on_click=True,
	)
	controls['locals'] = sidebar('locals', lambda : get_app().my.locals)
	controls['input_label'] = Label(
		text = u'(gdb) ',
		style = u'class:input_label',
		width = LayoutDimension.exact(6),
	)
	controls['input'] = Window(
		content=BufferControl(
			buffer=Buffer(
				read_only = False,
				multiline = False,
				history = InMemoryHistory(),
			),
			focusable = True,
			focus_on_click=True,
		),
		height=LayoutDimension.exact(1),
		dont_extend_height=True,
		style = u'class:input',
	)
	controls['vardetails'] = TextArea(
		height=LayoutDimension(1, 4),
		wrap_lines = True,
		read_only = True,
		style = u'class:vardetails',
	)
	def up_():
		val = get_app().my.locals.get_value_by_index( \
			get_app().my.controls['locals'].selected_option_index)
		text = get_app().my.controls['vardetails'].text
		if val is None and text != '':
			get_app().my.controls['vardetails'].text = '<out of scope>'
		elif text != '':
			get_app().my.controls['vardetails'].text = val[1]
	controls['vardetails'].update = up_

	def need_vardetails():
		return get_app().my.controls['vardetails'].text != ''

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

	def do_exit():
		get_app().exit(result=True)
	def do_cont():
		run_gdb_cmd(get_app(), 'c')
	def do_step_into():
		run_gdb_cmd(get_app(), 's')
	def do_step_over():
		run_gdb_cmd(get_app(), 'n')
	def do_set_bp():
		if get_app().my.focused_control == 'codeview':
			c = get_app().my.controls['codeview']
			line, col = c.document.translate_index_to_position(c.document.cursor_position)
			line += 1
			run_gdb_cmd(get_app(), 'b %s:%d'%(get_app().my.gdb.sourcefile, line))

	def do_toggle_prompt():
		get_app().my.input_gdb = not get_app().my.input_gdb
		get_app().my.controls['input_label'].text = '(gdb) ' if get_app().my.input_gdb else '>>> '
	def do_toggle_mouse():
		# we need to have the ability to turn mouse off to use the X11
		# clipboard (selection needs to be handled by X11, not the app)
		get_app().my.mouse_enabled = not get_app().my.mouse_enabled

	controls['root_container'] = MenuContainer(body=controls['root_container'], menu_items=[
		MenuItem('File', children=[
			MenuItem('-', disabled=True),
			MenuItem('Exit', handler=do_exit),
		]),
		MenuItem('Debug', children=[
			MenuItem('Continue  (F5)', handler=do_cont),
			MenuItem('Step Into (F7)', handler=do_step_into),
			MenuItem('Step Over (F8)', handler=do_step_over),
			MenuItem('Set Breakpoint (CTRL-b)', handler=do_set_bp),
		]),
		MenuItem('Extra', children=[
			MenuItem('Toggle python prompt  (F1)', handler=do_toggle_prompt),
			MenuItem('Toggle mouse support  (F2)', handler=do_toggle_mouse),
		]),
	], floats=[])

	kb = KeyBindings()
	@kb.add(u'escape', 'f')
	def _focus_menu(event):
		get_app().layout.focus(get_app().my.controls['root_container'].window)
	@kb.add(u'c-q')
	def exit_(event):
		do_exit()
	@kb.add(u'f1')
	def eff_one_(event):
		do_toggle_prompt()

	@kb.add(u'enter')
	def enter_(event):
		if event.app.my.focused_control != 'input':
			event.app.my.set_focus('input')
			return
		if event.app.my.input_gdb:
			cmd = event.app.my.controls['input'].content.buffer.text
			if not len(cmd): cmd = event.app.my.last_gdb_cmd
			else: event.app.my.last_gdb_cmd = cmd
			run_gdb_cmd(event.app, cmd)
			if event.app.my.controls['input'].content.buffer.text == 'q':
				event.app.exit()
		else:
			try: app.my.console.runsource(event.app.my.controls['input'].content.buffer.text)
			except Exception as e:
				import traceback
				add_gdbview_text(event.app, traceback.format_exc())
		event.app.my.controls['input'].content.buffer.reset(append_to_history=True)

	@kb.add(u'tab')
	def enter_(event):
		for i in xrange(len(event.app.my.focus_list)):
			if event.app.my.focus_list[i] == event.app.my.focused_control:
				next_focus = i+1
				if next_focus >= len(event.app.my.focus_list):
					next_focus = 0
				event.app.my.set_focus(event.app.my.focus_list[next_focus])
				break
	@kb.add(u'c-b')
	def cb_(event):
		do_set_bp()
	@kb.add(u'f5')
	def eff_five_(event):
		do_cont()
	@kb.add(u'f7')
	def _(event):
		do_step_into()
	@kb.add(u'f8')
	def _(event):
		do_step_over()
	@kb.add(u'f2')
	def _(event):
		do_toggle_mouse()

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
		'sidebar.statusodd changed':              'bg:#dddd00 #ff0000 bold',
	}

	pyg_style = style_from_pygments_cls(CodeviewStyle)

	style = merge_styles([
		Style.from_dict(styledict),
		pyg_style,
	])

	@Condition
	def _is_mouse_active():
		return get_app().my.mouse_enabled
	app = Application(
		layout = Layout(
			controls['root_container'],
			focused_element=controls['input'],
		),
		style=style,
		full_screen=True,
		key_bindings=merge_key_bindings([
			kb,
			load_sidebar_bindings('locals'),
			load_inputbar_bindings(),
		]),
		mouse_support = _is_mouse_active,
	)
	class My(): pass
	app.my = My()
	app.my.mouse_enabled = True
	app.my.controls = controls
	app.my.control_to_name_mapping = {}
	for name in controls:
		app.my.control_to_name_mapping[controls[name]] = name
		if isinstance(controls[name], TextArea) or 'control' in vars(controls[name]):
			app.my.control_to_name_mapping[controls[name].control] = name
		elif 'content' in vars(controls[name]):
			app.my.control_to_name_mapping[controls[name].content] = name

	app.my.locals = OrderedDict()
	app.my.gdb = gdb
	app.my.last_gdb_cmd = ''
	app.my.input_gdb = True
	app.my.focus_list = ['input', 'codeview', 'inferiorout', 'gdbout', 'locals']
	app.my.focused_control = 'input'
	def _set_focus(ctrl_or_name):
		if isinstance(ctrl_or_name, six.text_type):
			ctrl = get_app().my.controls[ctrl_or_name]
			name = ctrl_or_name
		else:
			ctrl = ctrl_or_name
			name = get_app().my.control_to_name_mapping[ctrl]
		get_app().layout.focus(ctrl)
		get_app().my.focused_control = name
	app.my.set_focus = _set_focus
	def _has_focus(ctrl_or_name):
		ctrl = get_app().my.controls[ctrl_or_name] if isinstance(ctrl_or_name, str) else ctrl_or_name
		return get_app().layout.has_focus(ctrl)
	app.my.has_focus = _has_focus
	app_console_writefunc = lambda x: add_gdbview_text(get_app(), x)
	app.my.console = py_console.Shell(locals=globals(), writefunc=app_console_writefunc)
	def my_mouse_handler(self, mouse_event):
		# loosely based on prompt_toolkit/layout/controls.py:716
		#if self.focus_on_click() and mouse_event.event_type == MouseEventType.MOUSE_DOWN:
		if mouse_event.event_type == MouseEventType.MOUSE_DOWN:
			get_app().my.set_focus(self)
			processed_line = self._last_get_processed_line(mouse_event.position.y)
			xpos = processed_line.display_to_source(mouse_event.position.x)
			index = self.buffer.document.translate_row_col_to_index(mouse_event.position.y, xpos)
			self.buffer.cursor_position = index
		else: return NotImplemented
	for x in app.my.focus_list:
		if x == 'locals': continue #don't override custom mouse handler
		if isinstance(app.my.controls[x], TextArea):
			app.my.controls[x].control.mouse_handler = my_mouse_handler.__get__(app.my.controls[x].control)
		else:
			app.my.controls[x].content.mouse_handler = my_mouse_handler.__get__(app.my.controls[x].content)

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
	app.my.controls['header'].text = prepare_text(text)

def add_gdbview_text(app, text):
	pt = prepare_text(text)
	app.my.controls['gdbout'].text += '\n' + pt.replace('\n(gdb) ', '')
	scroll_down(app.my.controls['gdbout'])

def codeview_set_line(ctrl, lineno):
	fl = ctrl.window.render_info.first_visible_line()
	height = ctrl.window.render_info.last_visible_line() - fl
	direction = -1 if lineno < fl else 1
	scroll_to(ctrl, lineno + (height/2)*direction)

_STEP_COMMANDS = ['n','s','c','next','step','continue']
def run_gdb_cmd(app, cmd, hide=False):
	oldsrc = app.my.gdb.sourcefile
	app.my.gdb.send(cmd)
	s, t = app.my.gdb.read()
	if not hide: add_gdbview_text(app, s + t)
	if cmd in _STEP_COMMANDS:
		for line in s.split('\n'):
			a = line.replace('\t', ' ').split(' ')
			if isnumeric(a[0]): app.my.gdb.lineno = int(a[0])
			elif ':' in a[-1]:
				file, lineno = a[-1].split(':')
				app.my.gdb.set_sourcefile(app.my.gdb.find_sourcefile(file))
				debug(app, app.my.gdb.sourcefile)
				if isnumeric(lineno): app.my.gdb.lineno = int(lineno)
	if app.my.gdb.istdout_canread():
		app.my.controls['inferiorout'].text += prepare_text(os.read(app.my.gdb.istdout(), 1024*4))
		scroll_down(app.my.controls['inferiorout'])
	if not app.my.gdb.sourcefile == oldsrc:
		load_source(app)
	if not cmd.startswith('b ') and app.my.gdb.lineno != -1:
		codeview_set_line(app.my.controls['codeview'], app.my.gdb.lineno)
	if cmd in _STEP_COMMANDS:
		get_locals(app)
		app.my.controls['vardetails'].update()
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
	app.my.gdb.send('info locals')
	s = app.my.gdb.proc.read_until(app.my.gdb.proc.stdout(), '(gdb) ')
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
	app.my.locals.update(mylocals)

def scroll_down(control):
	set_lineno(control, count_char(control.text, '\n')+1)

def scroll_to(control, n):
	set_lineno(control, n)

def load_source(app):
	app.my.controls['codeview'].text = prepare_text(open(app.my.gdb.sourcefile, 'r').read())

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
	app.my.controls['gdbout'].text = prepare_text(gdb_output)
	scroll_down(app.my.controls['gdbout'])
	load_source(app)

	app.run()

	import sys
	sys.exit(gdb.get_exitcode())

