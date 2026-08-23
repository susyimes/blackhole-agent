Common Use Cases
================

Find Encoding
-------------

.. code-block:: python

   import webencodings

   encoding = webencodings.lookup("greek")
   assert encoding.name == "iso-8859-7"


Decode Bytestring
-----------------

.. code-block:: python

   import webencodings

   decoded, encoding = webencodings.decode(b"\xb7", "mac")
   assert decoded == "∑"
   assert encoding.name == "macintosh"


Encode Unicode String
---------------------

.. code-block:: python

   import webencodings

   encoded = webencodings.encode("Œ", "csisolatin9")
   assert encoded == b"\xbc"


ASCII-Only Lowercase
--------------------

This is for example used for ASCII case-insensitive matching of encoding labels.

.. code-block:: python

   import webencodings

   keyword = 'Bac\N{KELVIN SIGN}ground'
   assert keyword.lower() == 'background'
   assert webencodings.ascii_lower(keyword) != keyword.lower()
   assert webencodings.ascii_lower(keyword) == 'bac\N{KELVIN SIGN}ground'
