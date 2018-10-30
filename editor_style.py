from pygments.style import Style as PygmentsStyle
from pygments.token import Keyword, Name, Comment, String, Error, \
	Number, Operator, Generic, Whitespace

# based on pygment's built-in borland style, with italics removed

class CodeviewStyle(PygmentsStyle):
	default_style = ''
	styles = {
		Whitespace:		'#bbbbbb',
		Comment:		'noitalic #008800',
		Comment.Preproc:	'noitalic #008080',
		Comment.Special:	'noitalic bold',

		String:			'#0000FF',
		String.Char:		'#800080',
		Number:			'#0000FF',
		Keyword:		'bold #000080',
		Operator.Word:		'bold',
		Name.Tag:		'bold #000080',
		Name.Attribute:		'#FF0000',

		Generic.Heading:	'#999999',
		Generic.Subheading:	'#aaaaaa',
		Generic.Deleted:	'bg:#ffdddd #000000',
		Generic.Inserted:	'bg:#ddffdd #000000',
		Generic.Error:		'#aa0000',
		Generic.Emph:		'underline',
		Generic.Strong:		'bold',
		Generic.Prompt:		'#555555',
		Generic.Output:		'#888888',
		Generic.Traceback:	'#aa0000',

		Error:			'bg:#e3d2d2 #a61717'
	}

