import subprocess, time, select, sys
class Proc():
	def __init__(self, command, shell=False, *args, **kwargs):
		self.proc = subprocess.Popen(command, stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE, shell=shell)
		self.exitcode = None
	def get_exitcode(self):
		return self.exitcode
	def _cleanup(self):
		self.exitcode = self.proc.wait()
		self.proc.stdout.close()
		self.proc.stderr.close()
		self.proc.stdin.close()
		self.proc.stdout = -1
		self.proc.stderr = -1
		self.proc.stdin = -1
	def canread(self, handle, timeout=0.0001):
		# self.proc.poll()
		if handle == -1 or self.exitcode != None: return False
		a,b,c = select.select([handle], [], [], timeout)
		if handle in c:
			self._cleanup()
			return False
		return handle in a
	def read_until(self, handle, marker):
		s = ''
		while not s.endswith(marker):
			if not self.canread(handle, timeout=1): break
			t = handle.read(1)
			if t == '':
				self._cleanup()
				return s
			s += t
		return s
	def stdout(self):
		return self.proc.stdout
	def stderr(self):
		return self.proc.stderr
	def stdin(self):
		return self.proc.stdin
	def close(self):
		return self.proc.terminate()

