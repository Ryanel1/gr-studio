"""Packager entry point, including isolated read-only camera workers."""

import os
import sys

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
if len(sys.argv) > 1 and sys.argv[1] == "--camera-helper":
    from gr_studio.camera import helper_main

    sys.argv.pop(1)
    helper_main()
else:
    from gr_studio.__main__ import main

    main()
