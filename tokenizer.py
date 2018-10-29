def split_tokens(x):
	b = []
	i = 0
	start = 0
	in_str = False
	while i < len(x):
		if not in_str:
			if x[i] in " \t\n":
				if i > start:
					b.append(x[start:i])
				start = i+1
			if x[i] in "(),={}*":
				token = x[i]
				if i > start:
					b.append(x[start:i])
				start = i+1
				b.append(token)

		if x[i] in '"':
			if i > 0 and x[i-1] == '\\':
				pass
			else:
				in_str = not in_str

		i += 1
	if i > start:
		b.append(x[start:i])
	return b

