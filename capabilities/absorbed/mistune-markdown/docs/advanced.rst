Advanced Guide
==============


Create plugins
--------------

Mistune has many built-in plugins, you can take a look at the source code
in ``mistune/plugins`` to find out how to write a plugin. In this documentation,
I'll guide you with an example, let's take a look at the math plugin
(located at ``mistune/plugins/math.py``):

.. code-block:: python

    def math(md):
        md.block.register('block_math', BLOCK_MATH_PATTERN, parse_block_math, before='list')
        md.inline.register('inline_math', INLINE_MATH_PATTERN, parse_inline_math, before='link')
        if md.renderer and md.renderer.NAME == 'html':
            md.renderer.register('block_math', render_block_math)
            md.renderer.register('inline_math', render_inline_math)

The parameter ``md`` is the instance of :class:`Markdown`. In our example, we have registered
a block level math plugin and an inline level math plugin.

Block level plugin
~~~~~~~~~~~~~~~~~~

Function ``md.block.register`` will register a block level plugin. In the math example:

.. code-block:: text

    $$
    \operatorname{ker} f=\{g\in G:f(g)=e_{H}\}{\mbox{.}}
    $$

This is how a block level math syntax looks like. Our ``BLOCK_MATH_PATTERN`` is:

.. code-block:: python

    # block level pattern MUST startswith ^
    BLOCK_MATH_PATTERN = r'^ {0,3}\$\$[ \t]*\n(?P<math_text>.+?)\n\$\$[ \t]*$'

    # regex represents:
    BLOCK_MATH_PATTERN = (
      r'^ {0,3}'  # line can startswith 0~3 spaces just like other block elements defined in commonmark
      r'\$\$'  # followed by $$
      r'[ \t]*\n'  # this line can contain extra spaces and tabs
      r'(?P<math_text>.+?)'  # this is the math content, MUST use named group
      r'\n\$\$[ \t]*$'  # endswith $$ + extra spaces and tabs
    )

    # if you want to make the math pattern more strictly, it could be like:
    BLOCK_MATH_PATTERN = r'^\$\$\n(?P<math_text>.+?)\n\$\$$'

Then the block parsing function:

.. code-block:: python

    def parse_block_math(block, m, state):
        text = m.group('math_text')
        # use ``state.append_token`` to save parsed block math token
        state.append_token({'type': 'block_math', 'raw': text})
        # return the end position of parsed text
        # since python doesn't count ``$``, we have to +1
        # if the pattern is not ended with `$`, we can't +1
        return m.end() + 1

The ``token`` MUST contain ``type``, others are optional. Here are some examples:

.. code-block:: python

    {'type': 'thematic_break'}  # <hr>
    {'type': 'paragraph', 'text': text}
    {'type': 'block_code', 'raw': code}
    {'type': 'heading', 'text': text, 'attrs': {'level': level}}

- **text**: inline parser will parse text
- **raw**: inline parser WILL NOT parse the content
- **attrs**: extra information saved here, renderer will use attrs

Inline level plugin
~~~~~~~~~~~~~~~~~~~

Function ``md.inline.register`` will register an inline level plugin. In the math example:

.. code-block:: text

    function $f$

This is how an inline level math syntax looks like. Our ``INLINE_MATH_PATTERN`` is:

.. code-block:: python

    INLINE_MATH_PATTERN = r'\$(?!\s)(?P<math_text>.+?)(?!\s)\$'

    # regex represents:
    INLINE_MATH_PATTERN = (
      r'\$'  # startswith $
      r'(?!\s)'  # not whitespace
      r'(?P<math_text>.+?)'  # content between `$`, MUST use named group
      r'(?!\s)'  # not whitespace
      r'\$'  # endswith $
    )

Then the inline parsing function:

.. code-block:: python

    def parse_inline_math(inline, m, state):
        text = m.group('math_text')
        # use ``state.append_token`` to save parsed inline math token
        state.append_token({'type': 'inline_math', 'raw': text})
        # return the end position of parsed text
        return m.end()

The inline token value looks the same with block token. Available keys:
``type``, ``raw``, ``text``, ``attrs``.

Plugin renderers
~~~~~~~~~~~~~~~~

It is suggested to add default HTML renderers for your plugin. A renderer function
looks like:

.. code-block:: python

    def render_hr(renderer):
        # token with only type, like:
        # {'type': 'hr'}
        return '<hr>'

    def render_math(renderer, text):
        # token with type and (text or raw), e.g.:
        # {'type': 'block_math', 'raw': 'a^b'}
        return '<div class="math">$$' + text + '$$</div>'

    def render_link(renderer, text, **attrs):
        # token with type, text or raw, and attrs
        href = attrs['href']
        return f'<a href="{href}">{text}</a>'

If current markdown instance is using HTML renderer, developers can register
the plugin renderer for converting markdown to HTML.


Write directives
----------------

Mistune has some built-in directives that have been presented in
the directives part of the documentation. These are defined in the
``mistune/directives``, you can learn how to write a new directive
by reading the source code in ``mistune/directives/``.


.. _parsing-ast-tokens:

Parsing AST tokens
------------------

Mistune provides direct access to AST tokens by creating a markdown object
via ``mistune.create_markdown(renderer='ast')`` (see :ref:`abstract-syntax-tree`).
By walking down the AST returned from the markdown object, you can integrate
Mistune's parser into other systems.

.. code-block:: python

    import mistune

    markdown = mistune.create_markdown(renderer='ast')

    tokens = markdown(
    '''# Title

    Subtitle
    --------

    Hello World!'''
    )

    stk = list(reversed(tokens))
    while stk:
        token = stk.pop()
        print({k:v for k, v in token.items() if k != 'children'})
        if 'children' in token:
            for child in reversed(token['children']):
                stk.append(child)

Below is the documentation for the list of tokens that can occur in
``renderer='ast'`` mode.

Token structure
~~~~~~~~~~~~~~~

An AST token is a ``dict`` containing an item whose key is ``'type'`` and value
is a string representing the token type (such as ``'text'``, ``'emphasis'``,
``'strong'``). If the token has children, they are represented as a
``list`` under the ``'children'`` key.

Inline elements
~~~~~~~~~~~~~~~

.. code-block:: python

    { 'type': 'linebreak' }
    { 'type': 'softbreak' }
    { 'type': 'text', 'raw': str }
    { 'type': 'emphasis', 'children': list[dict] }
    { 'type': 'strong', 'children': list[dict] }
    { 'type': 'codespan', 'raw': str }
    { 'type': 'inline_html', 'raw': str }

    # links and images
    #
    # 'children' contains elements in the link text section. If you
    # write something like [**text**](url), **text** goes to 'children'.
    # This behavior is identical for both images and links, but the HTML
    # renderer extracts only the text part of children when actually
    # putting it into 'alt' attribute (e.g., ![**text**](url) returns
    # <img src="url" alt="text">, not <img src="url" alt="**text**">)
    #
    # for reference links and images (like [text][label], [label], etc.),
    # 'ref' and 'label' are also given. Both contain the same content,
    # but 'ref' is an uppercase version, while 'label' is case-sensitive.
    #
    {
        'type': 'image',
        'children': list[dict],    # link text
        'attrs': {
            'url': str,
            'title': str | None    # is None if not given
        },
        'ref': str,     # omitted if not reference links and images
        'label': str    # omitted if not reference links and images
    }
    {
        'type': 'link',
        'children': list[dict],    # link text
        'attrs': {
            'url': str,
            'title': str | None    # is None if not given
        },
        'ref': str,     # omitted if not reference links and images
        'label': str    # omitted if not reference links and images
    }

Block elements
~~~~~~~~~~~~~~

.. code-block:: python

    { 'type': 'blank_line' }
    { 'type': 'thematic_break' }
    { 'type': 'paragraph', 'children': list[dict] }

    # 'block_text' is a special text block that occurs in 'tight' lists.
    #
    # when a list is tight (i.e., there is no blank line between any list
    # items or their children), and if a leaf list item contains only a
    # paragraph, that paragraph's 'type' is changed to 'block_text'
    # ('children' remains the same).
    #
    # block_texts are immediately put between <li>...</li>, where paragraphs
    # (occurring in 'loose' lists) are rendered like <li><p>...</p></li>.
    #
    { 'type': 'block_text', 'children': list[dict] }

    # 'style' can be 'atx' or 'setext'
    {
        'type': 'heading',
        'children': list[dict],
        'attrs': {'level': int},
        'style': str
    }

    { 'type': 'block_quote', 'children': list[dict] }
    { 'type': 'block_html', 'raw': str }
    { 'type': 'block_code', 'raw': str, 'style': 'indent' }

    # fenced block code
    {
        'type': 'block_code',
        'raw': str,
        'style': 'fenced',
        'marker': str,
        'attrs': {'info': str}    # appears if info string is given
    }

List elements
~~~~~~~~~~~~~

.. code-block:: python

    {
        'type': 'list',
        'children': [{'type': 'list_item', 'children': list[dict]}, ...],
        'tight': bool,    # whether the list is 'tight' or 'loose'
        'bullet': str,    # list marker character
        'attrs': {
            'depth': int,
            'ordered': bool,    # whether the list is ordered or unordered
            'start': int    # appears if the list is ordered and start != 1
        }
    }

Plugin elements
~~~~~~~~~~~~~~~

.. code-block:: python

    # strikethrough, mark, insert, superscript, and subscript plugin
    { 'type': 'strikethrough', 'children': list[dict] }
    { 'type': 'mark', 'children': list[dict] }
    { 'type': 'insert', 'children': list[dict] }
    { 'type': 'superscript', 'children': list[dict] }
    { 'type': 'subscript', 'children': list[dict] }

    # footnotes plugin
    { 'type': 'footnote_ref', 'raw': str, 'attrs': {'index': int} }
    {
        'type': 'footnotes',
        'children': [
            {
                'type': 'footnote_item',
                'children': [{'type': 'paragraph', 'children': list[dict]}],
                'attrs': {'key': str, 'index': int}
            },
            ...
        ]
    }

    # table plugin
    {
        'type': 'table',
        'children': [
            {
                'type': 'table_head',
                'children': [
                    {
                        'type': 'table_cell',
                        'children': list[dict],
                        'attrs': {
                            # 'align' is 'center', 'left', 'right', or None
                            'align': str | None,
                            'head': True
                        }
                    },
                    ...
                ]
            },
            {
                'type': 'table_body',
                'children': {
                    'type': 'table_row',
                    'children': [
                        {
                            'type': 'table_cell',
                            'children': list[dict],
                            'attrs': {
                                # 'align' is 'center', 'left', 'right', or None
                                'align': str | None,
                                'head': False
                            }
                        },
                        ...
                    ]
                }
            }
        ]
    }

    # url plugin does not add new elements
    # (it uses 'link' element just like normal links)

    # task_lists plugin
    #
    # task_list_item appears in the same contexts as list_item.
    #
    {
        'type': 'task_list_item',
        'children': list[dict],
        'attrs': {'checked': bool}
    }

    # def_list plugin
    #
    # similar to regular lists, sole paragraphs in def_list_items are
    # converted to 'block_texts' if the definition list is tight.
    #
    {
        'type': 'def_list',
        'children': [
            { 'type': 'def_list_head', 'children': list[dict] },
            { 'type': 'def_list_item', 'children': list[dict] },
            ...
        ]
    }

    # abbr plugin
    {
        'type': 'abbr',
        'children': [{'type': 'text', 'raw': str}],
        'attrs': {'title': str}
    }

    # math plugin
    { 'type': 'block_math', 'raw': str }
    { 'type': 'inline_math', 'raw': str }

    # ruby plugin
    { 'type': 'ruby', 'raw': str, 'attrs': {'rt': str} }

    # spoiler plugin
    { 'type': 'block_spoiler', 'children': list[dict] }
    { 'type': 'inline_spoiler', 'children': list[dict] }
