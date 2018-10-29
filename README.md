gdbpimp - a console gui for gdb
===============================

unlike the other gdb guis, like gdbgui, pwndbg, peda, etc this
one works with a plain gdb binary, regardless of whether
built with or without shared libs and python scripting support.
and regardless of version. the ones mentioned here tend to only
work properly with the latest and greatest gdb, while this here
was tested with gdb 7.6 and should work with older and newer
versions as well, because it works on stdin/stdout of gdb.

additionally it doesn't have a shitload of library dependencies.
you only need `prompt-toolkit` and `pygments`.

you also dont need to install a .gdbinit file which overrides
normal functioning of gdb.

whereas pwndbg, peda, gef and gdb-dashboard focus on assembly
level debugging, this one is focused on source-level C debugging.

usage:
------

    python2 gdb.py /bin/program arg1 arg2

keyboard shortcuts:
-------------------

- F7     - step into (s)
- F8     - step over (n)
- CTRL-B - set breakpoint at current line in codeview
- TAB    - circle focus

- CTRL-Q - quit
- F1     - switch input applet mode to python or gdb repl
these last ones are likely to change in future versions.

TODO
----
- source file selection dialog
- dialog showing backtrace with possibility to select a frame
- keyboard shortcuts for: runtocursor, stepout
  ( see https://www.shortcuts-keyboard.com/visual-basic-6-0-default-shortcut-keys/ )
  stepout functionality might require an additional dependency on `pycparser`.
- nicer way to highlight the actual line in the codeview
  (optimally red bar over the entire line)
- menu
- ability to customize size of controls
