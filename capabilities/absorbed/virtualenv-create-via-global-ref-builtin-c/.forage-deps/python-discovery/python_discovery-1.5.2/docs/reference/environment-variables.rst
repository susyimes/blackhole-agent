Environment Variables
======================

``PY_DISCOVERY_TIMEOUT``
------------------------

Controls the timeout for querying individual Python interpreters.

**Type:** Float (seconds)

**Default:** ``15``

**Description:**

When python-discovery verifies an interpreter candidate, it runs a subprocess to collect metadata
(version, architecture, platform, etc.). On slower systems—particularly Windows with antivirus
software or other tools—Python startup can exceed the default timeout.

Setting this variable extends the allowed time for each interpreter query.

**Examples:**

.. code-block:: bash

   # Allow interpreters 30 seconds to respond
   export PY_DISCOVERY_TIMEOUT=30

   # Or pass in Python
   import os
   os.environ["PY_DISCOVERY_TIMEOUT"] = "30"

**Notes:**

- The timeout applies per candidate, not to the entire discovery process
- If a candidate times out, it is skipped and discovery continues with the next one
- Setting the value too low may skip legitimate interpreters
- Setting it too high increases discovery time when encountering problematic interpreters
- The value is read from the environment dict passed to :func:`~python_discovery.get_interpreter`
